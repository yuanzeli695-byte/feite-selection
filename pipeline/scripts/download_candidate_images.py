#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import threading
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image


ASIN_RE = re.compile(r"^B0[A-Z0-9]{8}$")
USER_AGENT = "Mozilla/5.0"


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def valid_png(path: Path) -> bool:
    if not path.is_file() or path.stat().st_size < 1:
        return False
    try:
        with Image.open(path) as image:
            image.load()
            return image.format == "PNG" and image.width > 0 and image.height > 0
    except (OSError, ValueError):
        return False


def cache_path_for(cache_dir: Path, asin: str, url: str) -> Path:
    url_hash = hashlib.sha256(url.encode("utf-8")).hexdigest()[:24]
    return cache_dir / f"{asin}_{url_hash}.png"


def cache_age_seconds(path: Path) -> float:
    return max(datetime.now(timezone.utc).timestamp() - path.stat().st_mtime, 0.0)


def atomic_copy(source: Path, target: Path) -> None:
    temporary = target.with_name(f".{target.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    shutil.copy2(source, temporary)
    os.replace(temporary, target)


def save_png(data: bytes, target: Path) -> None:
    temporary = target.with_name(f".{target.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    try:
        with Image.open(BytesIO(data)) as image:
            image.load()
            if image.width < 1 or image.height < 1:
                raise ValueError("image dimensions are empty")
            image.convert("RGB").save(temporary, format="PNG", optimize=True)
        os.replace(temporary, target)
    finally:
        if temporary.exists():
            temporary.unlink()


def download_one(
    row: dict[str, Any],
    *,
    output_dir: Path,
    cache_dir: Path | None,
    cache_ttl_seconds: int,
    timeout: int,
    retries: int,
) -> dict[str, object]:
    asin = str(row.get("asin") or "").strip().upper()
    url = str(row.get("image") or row.get("imageUrl") or "").strip()
    target = output_dir / f"{asin}.png"
    if valid_png(target):
        return {
            "asin": asin,
            "status": "ok",
            "path": str(target),
            "bytes": target.stat().st_size,
            "sha256": file_sha256(target),
            "cacheHit": True,
            "cacheSource": "output",
        }

    cached_path = cache_path_for(cache_dir, asin, url) if cache_dir is not None and url else None
    if cached_path is not None and valid_png(cached_path):
        age = cache_age_seconds(cached_path)
        if age <= cache_ttl_seconds:
            atomic_copy(cached_path, target)
            return {
                "asin": asin,
                "status": "ok",
                "path": str(target),
                "bytes": target.stat().st_size,
                "sha256": file_sha256(target),
                "cacheHit": True,
                "cacheSource": "persistent_url_cache_v1",
                "cachePath": str(cached_path),
                "cacheAgeSeconds": round(age, 3),
            }

    error = "missing image URL"
    for attempt in range(1, retries + 2):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(request, timeout=timeout) as response:
                data = response.read()
            save_png(data, target)
            if cached_path is not None:
                atomic_copy(target, cached_path)
            return {
                "asin": asin,
                "status": "ok",
                "path": str(target),
                "bytes": target.stat().st_size,
                "sha256": file_sha256(target),
                "attempt": attempt,
                "cacheHit": False,
                "cachePath": str(cached_path) if cached_path is not None else None,
            }
        except Exception as exc:  # noqa: BLE001
            error = str(exc)
    return {"asin": asin, "status": "error", "url": url, "error": error, "cacheHit": False}


def download_rows(
    rows: list[dict[str, Any]],
    *,
    output_dir: Path,
    cache_dir: Path | None,
    cache_ttl_seconds: int,
    timeout: int,
    retries: int,
    workers: int,
) -> list[dict[str, object]]:
    output_dir.mkdir(parents=True, exist_ok=True)
    if cache_dir is not None:
        cache_dir.mkdir(parents=True, exist_ok=True)
    worker_args = {
        "output_dir": output_dir,
        "cache_dir": cache_dir,
        "cache_ttl_seconds": cache_ttl_seconds,
        "timeout": timeout,
        "retries": retries,
    }
    if workers == 1:
        return [download_one(row, **worker_args) for row in rows]
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="candidate-image") as executor:
        return list(executor.map(lambda row: download_one(row, **worker_args), rows))


def main() -> int:
    parser = argparse.ArgumentParser(description="Download candidate main images and convert them to PNG.")
    parser.add_argument("candidates_json", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--cache-dir", type=Path)
    parser.add_argument("--cache-ttl-minutes", type=int, default=60)
    args = parser.parse_args()

    rows = json.loads(args.candidates_json.read_text(encoding="utf-8-sig"))
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise ValueError("candidates_json must be an array of objects")
    asins = [str(row.get("asin") or "").strip().upper() for row in rows]
    if any(not ASIN_RE.fullmatch(asin) for asin in asins) or len(set(asins)) != len(asins):
        raise ValueError("candidate rows contain invalid or duplicate ASINs")
    if args.workers < 1 or args.workers > 8:
        raise ValueError("workers must be between 1 and 8")
    if args.cache_ttl_minutes < 1:
        raise ValueError("cache-ttl-minutes must be positive")
    report = download_rows(
        rows,
        output_dir=args.output_dir,
        cache_dir=args.cache_dir,
        cache_ttl_seconds=args.cache_ttl_minutes * 60,
        timeout=args.timeout,
        retries=args.retries,
        workers=args.workers,
    )

    report_path = args.report or args.output_dir / "image_download_report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    ok = sum(item["status"] == "ok" for item in report)
    cache_hits = sum(item.get("cacheHit") is True for item in report)
    print(
        json.dumps(
            {
                "expected": len(rows),
                "ok": ok,
                "failed": len(rows) - ok,
                "cacheHits": cache_hits,
                "workers": args.workers,
                "report": str(report_path),
            },
            ensure_ascii=False,
        )
    )
    return 0 if ok == len(rows) else 2


if __name__ == "__main__":
    raise SystemExit(main())
