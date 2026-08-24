#!/usr/bin/env python3
"""Build a strict candidate queue from user-exported SellerSprite tables."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse


CONSOLE_ROOT = Path(__file__).resolve().parent
DEFAULT_PROJECT_ROOT = Path(r"C:\Users\13045\Desktop\amazon_products")
sys.path.insert(0, str(CONSOLE_ROOT))
sys.path.insert(0, str(DEFAULT_PROJECT_ROOT / "scripts"))

from prepare_strict_candidate_pool import SourceContractError, validate_query_url  # noqa: E402
from sellersprite_export_to_runner_queue import (  # noqa: E402
    InputError,
    normalize_row,
    read_export,
    resolve_headers,
)
from sellersprite_api_pipeline import (  # noqa: E402
    PipelineError,
    default_filters,
    make_analysis_workbook,
)


PIPELINE_VERSION = "sellerSpriteBrowserExportPipeline/v1.0.0"


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def query_number(query: dict[str, list[str]], name: str, *aliases: str) -> float:
    raw = ""
    for key in (name, *aliases):
        values = query.get(key, [])
        if values:
            raw = values[0]
            break
    try:
        return float(raw)
    except ValueError as exc:
        raise PipelineError(f"SellerSprite query URL is missing numeric {name}") from exc


def validate_query_contract(raw_url: str, filters: dict[str, Any]) -> dict[str, Any]:
    try:
        contract = validate_query_url(raw_url)
    except SourceContractError as exc:
        raise PipelineError(f"invalid SellerSprite query URL: {exc}") from exc
    query = parse_qs(urlparse(raw_url).query)
    checks = {
        "minPrice": query_number(query, "minPrice") >= float(filters["minPrice"]),
        "maxPrice": query_number(query, "maxPrice") <= float(filters["maxPrice"]),
        "minReviewRating": query_number(query, "minReviewRating") >= float(filters["minRating"]),
        "minReviews": query_number(query, "minReviews") >= float(filters["minReviews"]),
        "maxReviews": query_number(query, "maxReviews") <= float(filters["maxReviews"]),
        "minSales": query_number(query, "minSales", "minAmzUnit") >= float(filters["minChildSales"]),
        "maxSales": query_number(query, "maxSales", "maxAmzUnit") <= float(filters["maxChildSales"]),
        "minVariations": query_number(query, "minVariations") >= float(filters["minVariations"]),
        "maxVariations": query_number(query, "maxVariations") <= float(filters["maxVariations"]),
        "putawayMonth": query_number(query, "putawayMonth") <= float(filters["availableMonth"]),
    }
    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        raise PipelineError(
            "SellerSprite query URL is wider than the batch limits: " + ", ".join(failed)
        )
    return {**contract, "checks": checks}


def run_logged(argv: list[str], log_path: Path, cwd: Path) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        argv,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=1800,
    )
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text((result.stdout or "") + "\n" + (result.stderr or ""), encoding="utf-8")
    return result


def require_success(result: subprocess.CompletedProcess[str], label: str, log_path: Path) -> None:
    if result.returncode:
        detail = (result.stderr or result.stdout or "").strip()[-1200:]
        raise PipelineError(f"{label} failed ({result.returncode}): {detail}; log: {log_path}")


def execute(args: argparse.Namespace) -> dict[str, Any]:
    run_dir = args.run_dir.resolve()
    project_root = args.project_root.resolve()
    config = read_json(args.config)
    filters = default_filters(config.get("filters") or {})
    exports = config.get("exports") or []
    if not isinstance(exports, list) or not exports:
        raise PipelineError("no browser exports were uploaded")

    attempt_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ_%f")
    work_dir = run_dir / "browser_export_attempts" / attempt_id
    source_dir = work_dir / "source_queries"
    source_dir.mkdir(parents=True, exist_ok=True)
    all_rows: list[dict[str, Any]] = []
    normalization_rejected: list[dict[str, Any]] = []
    manifest_inputs: list[dict[str, Any]] = []
    resolved_categories: list[dict[str, Any]] = []
    captured_times: list[datetime] = []
    node_ids: list[str] = []

    for index, item in enumerate(exports, 1):
        export_path = Path(str(item.get("path") or "")).resolve()
        if not export_path.is_file() or export_path.suffix.lower() not in {".xlsx", ".csv", ".tsv"}:
            raise PipelineError(f"invalid browser export file: {export_path}")
        try:
            export_path.relative_to(run_dir)
        except ValueError as exc:
            raise PipelineError(f"browser export is outside the run directory: {export_path}") from exc
        query_url = str(item.get("queryUrl") or "").strip()
        query_contract = validate_query_contract(query_url, filters)
        captured_at = datetime.fromisoformat(str(item.get("capturedAt") or "").replace("Z", "+00:00"))
        if captured_at.tzinfo is None:
            raise PipelineError("browser export capturedAt must include a timezone")
        captured_at = captured_at.astimezone(timezone.utc)
        captured_times.append(captured_at)
        node_ids.extend(str(value) for value in query_contract["nodeIdPaths"])

        headers, raw_rows = read_export(export_path, None)
        mapping = resolve_headers(headers)
        source_page = str(item.get("sourcePage") or item.get("categoryInput") or export_path.stem)
        normalized: list[dict[str, Any]] = []
        rejected: list[dict[str, Any]] = []
        for row_number, raw_row in raw_rows:
            candidate, errors = normalize_row(
                row_number,
                raw_row,
                mapping,
                source_page,
                query_url,
                False,
            )
            if candidate is None:
                rejected.append({
                    "sourceFile": export_path.name,
                    "sourceRow": row_number,
                    "sourcePage": source_page,
                    "reasons": errors,
                })
            else:
                candidate["sourceCategoryInput"] = str(item.get("categoryInput") or "")
                normalized.append(candidate)
        if not normalized:
            raise PipelineError(f"no rows survived normalization: {export_path.name}")

        query_name = f"query_{index:03d}_{hashlib.sha256(source_page.encode('utf-8')).hexdigest()[:10]}.json"
        query_path = source_dir / query_name
        write_json(query_path, normalized)
        manifest_inputs.append({
            "path": query_name,
            "sha256": sha256_file(query_path),
            "queryUrl": query_contract["url"],
        })
        resolved_categories.append({
            "input": str(item.get("categoryInput") or source_page),
            "status": "resolved",
            "nodeIdPath": ":".join(query_contract["nodeIdPaths"]),
            "nodeLabelPath": source_page,
            "nodeLabelPathLocale": source_page,
            "candidateCount": len(normalized),
        })
        all_rows.extend(normalized)
        normalization_rejected.extend(rejected)

    oldest_capture = min(captured_times)
    age_seconds = (datetime.now(timezone.utc) - oldest_capture).total_seconds()
    if age_seconds < -300 or age_seconds > 24 * 60 * 60:
        raise PipelineError("browser exports must be captured within the last 24 hours")

    manifest_path = work_dir / "source_manifest.json"
    write_json(manifest_path, {
        "schemaVersion": "sellerSpriteCandidateSourceManifest/v1",
        "capturedAt": oldest_capture.isoformat(),
        "market": "US",
        "preset": {"name": "sellerSprite-query-hard-filter-v1", "source": "browser_export"},
        "categoryScope": {"name": "Console browser export pool", "nodeIdPaths": list(dict.fromkeys(node_ids))},
        "inputs": manifest_inputs,
    })
    write_json(work_dir / "browser_export_normalization_rejected.json", normalization_rejected)

    history_log = work_dir / "logs" / "strict_history.log"
    history_result = run_logged([
        sys.executable,
        str(project_root / "scripts" / "strict_history.py"),
        "--project-root", str(project_root),
        "--write",
    ], history_log, project_root)
    require_success(history_result, "strict history sync", history_log)

    queue_name = re.sub(r"[^A-Za-z0-9_-]+", "_", args.queue_name).strip("_")[:80] or "console_queue"
    pool_dir = work_dir / "candidate_pool"
    prefilter_log = work_dir / "logs" / "strict_prefilter.log"
    prefilter_args = [
        sys.executable,
        str(project_root / "scripts" / "prepare_strict_candidate_pool.py"),
        "--input-dir", str(source_dir),
        "--source-manifest", str(manifest_path),
        "--project-root", str(project_root),
        "--output-dir", str(pool_dir),
        "--queue-name", queue_name,
        "--queue-size", str(args.queue_size),
        "--max-per-source", str(args.queue_size),
        "--run-date", args.run_date,
    ]
    prefilter_result = run_logged(prefilter_args, prefilter_log, project_root)
    failure_text = (prefilter_result.stderr or "") + "\n" + (prefilter_result.stdout or "")
    short_match = re.search(r"only (\d+) candidates available for requested queue size \d+", failure_text)
    if prefilter_result.returncode and short_match and int(short_match.group(1)) > 0:
        actual_queue_size = int(short_match.group(1))
        prefilter_args[prefilter_args.index("--queue-size") + 1] = str(actual_queue_size)
        prefilter_result = run_logged(prefilter_args, prefilter_log, project_root)
    else:
        actual_queue_size = args.queue_size
    require_success(prefilter_result, "strict candidate preparation", prefilter_log)

    queue_json = pool_dir / f"{queue_name}.json"
    queue_txt = pool_dir / f"asin_queue_{queue_name}.txt"
    summary_path = pool_dir / f"summary_{queue_name}.json"
    rejected_path = pool_dir / "screened_rejected.json"
    queue = read_json(queue_json)
    rejected = read_json(rejected_path) + normalization_rejected
    if not queue:
        raise PipelineError("strict prefilter produced no Runner candidates")

    images_dir = work_dir / "source_images"
    image_report = work_dir / "image_download_report.json"
    image_log = work_dir / "logs" / "image_download.log"
    image_result = run_logged([
        sys.executable,
        str(project_root / "scripts" / "download_candidate_images.py"),
        str(queue_json), str(images_dir), "--report", str(image_report), "--workers", "4",
    ], image_log, project_root)
    require_success(image_result, "candidate image download", image_log)

    analysis_path = work_dir / f"candidate_analysis_{queue_name}.xlsx"
    make_analysis_workbook(queue, rejected, images_dir, analysis_path)
    title_path = work_dir / "zh_title_overrides_auto.json"
    write_json(title_path, {
        row["asin"]: f"{str(row.get('brand') or '').strip()} {str(row.get('categoryPath') or '商品').split(':')[-1]} {row['asin']}".strip()
        for row in queue
    })
    result = {
        "schemaVersion": "sellerSpriteConsoleCandidatePipeline/v1",
        "pipelineVersion": PIPELINE_VERSION,
        "sourceMode": "browser_export",
        "qualificationScope": "runner_queue_only_no_final_AF_pass",
        "runDir": str(run_dir),
        "workDir": str(work_dir),
        "sourceRowCount": len(all_rows),
        "normalizationRejectedCount": len(normalization_rejected),
        "resolvedCategories": resolved_categories,
        "queueCount": len(queue),
        "requestedQueueCount": args.queue_size,
        "preparedQueueCount": actual_queue_size,
        "queuePath": str(queue_txt),
        "queueJsonPath": str(queue_json),
        "analysisWorkbookPath": str(analysis_path),
        "imagesDir": str(images_dir),
        "imageReportPath": str(image_report),
        "titleOverridesPath": str(title_path),
        "summaryPath": str(summary_path),
        "rejectedPath": str(rejected_path),
        "sourceManifestPath": str(manifest_path),
    }
    write_json(run_dir / "candidate_pipeline_result.json", result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare a strict Runner queue from browser-exported SellerSprite tables")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--project-root", type=Path, default=DEFAULT_PROJECT_ROOT)
    parser.add_argument("--queue-name", required=True)
    parser.add_argument("--queue-size", type=int, required=True)
    parser.add_argument("--run-date", required=True)
    args = parser.parse_args()
    try:
        result = execute(args)
    except (InputError, PipelineError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1
    print(json.dumps({"ok": True, "queueCount": result["queueCount"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
