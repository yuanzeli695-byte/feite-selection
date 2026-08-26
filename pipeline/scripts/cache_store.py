from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


def parse_iso(value: str) -> datetime:
    text = value.replace("Z", "+00:00")
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


ASIN_RE = re.compile(r"^[A-Z0-9]{10}$")


class Cache:
    def __init__(self, root: str | Path, kind: str, ttl_hours: float):
        self.base_root = Path(root)
        self.kind = kind
        self.root = self.base_root / kind
        self.ttl = timedelta(hours=ttl_hours)
        self.ttl_hours = ttl_hours
        self.root.mkdir(parents=True, exist_ok=True)

    def path_for(self, key: str) -> Path:
        clean = str(key).strip().upper()
        if not ASIN_RE.match(clean):
            raise ValueError(f"invalid ASIN cache key: {key}")
        return self.root / f"{clean}.json"

    def read(self, key: str) -> dict[str, Any] | None:
        try:
            path = self.path_for(key)
        except ValueError:
            raise
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
        except json.JSONDecodeError:
            return None
        collected_at = data.get("collectedAt") or data.get("cachedAt")
        if not collected_at:
            return None
        if self._age(collected_at) > self.ttl:
            return None
        return data

    def write(self, key: str, data: dict[str, Any]) -> Path:
        path = self.path_for(key)
        payload = dict(data)
        payload.setdefault("cachedAt", datetime.now(timezone.utc).isoformat(timespec="seconds"))
        payload.setdefault("cacheKind", self.kind)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    def hit(self, key: str) -> bool:
        return self.read(key) is not None

    def invalidate(self, key: str) -> None:
        path = self.path_for(key)
        if path.exists():
            path.unlink()

    def _age(self, value: str) -> timedelta:
        return datetime.now(timezone.utc) - parse_iso(value).astimezone(timezone.utc)

    def age_hours(self, key: str) -> float | None:
        path = self.path_for(key)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
        except json.JSONDecodeError:
            return None
        collected_at = data.get("collectedAt") or data.get("cachedAt")
        if not collected_at:
            return None
        return self._age(collected_at).total_seconds() / 3600

    def stats(self) -> dict[str, Any]:
        total = fresh = stale = 0
        for path in self.root.glob("*.json"):
            total += 1
            try:
                data = json.loads(path.read_text(encoding="utf-8-sig"))
                collected_at = data.get("collectedAt") or data.get("cachedAt")
                if collected_at and self._age(collected_at) <= self.ttl:
                    fresh += 1
                else:
                    stale += 1
            except json.JSONDecodeError:
                stale += 1
        return {
            "kind": self.kind,
            "total": total,
            "fresh": fresh,
            "stale": stale,
            "ttlHours": self.ttl_hours,
            "root": str(self.root),
        }


JsonCache = Cache


def sellersprite_cache(root: str | Path, ttl_hours: float = 168) -> Cache:
    return Cache(root, "sellersprite", ttl_hours=ttl_hours)


def product_meta_cache(root: str | Path, ttl_hours: float = 24) -> Cache:
    return Cache(root, "product_meta", ttl_hours=ttl_hours)
