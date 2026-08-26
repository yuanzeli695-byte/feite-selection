"""Validate and compare canonical strict-qualified-history JSON snapshots."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "strictQualifiedHistory/v1"
ASIN_RE = re.compile(r"^[A-Z0-9]{10}$")


class HistoryAuditError(ValueError):
    """Raised when a history snapshot is malformed or unreadable."""


def audit_history(path: Path) -> tuple[dict[str, Any], bytes]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as error:
        raise HistoryAuditError(f"cannot read {path}: {error}") from error
    if not isinstance(value, dict) or value.get("schemaVersion") != SCHEMA_VERSION:
        raise HistoryAuditError(f"{path}: expected schemaVersion {SCHEMA_VERSION!r}")
    asins = value.get("asins")
    if not isinstance(asins, dict):
        raise HistoryAuditError(f"{path}: asins must be an object")
    for asin, metadata in asins.items():
        if not isinstance(asin, str) or not ASIN_RE.fullmatch(asin.upper()):
            raise HistoryAuditError(f"{path}: invalid ASIN key {asin!r}")
        if not isinstance(metadata, dict):
            raise HistoryAuditError(f"{path}: metadata for {asin} must be an object")
    canonical = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    summary = {
        "path": str(path.resolve()),
        "schemaVersion": SCHEMA_VERSION,
        "asinCount": len(asins),
        "canonicalBytes": len(canonical),
        "canonicalSha256": hashlib.sha256(canonical).hexdigest(),
    }
    return summary, canonical


def compare_histories(paths: list[Path]) -> dict[str, Any]:
    if not paths:
        raise HistoryAuditError("at least one history snapshot is required")
    audited = [audit_history(path) for path in paths]
    canonical_values = [canonical for _, canonical in audited]
    all_equal = all(value == canonical_values[0] for value in canonical_values[1:])
    return {
        "schemaVersion": "strictQualifiedHistoryAudit/v1",
        "allEqual": all_equal,
        "snapshots": [summary for summary, _ in audited],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compare strict-history snapshots by canonical JSON value.")
    parser.add_argument("snapshots", nargs="+", type=Path)
    args = parser.parse_args(argv)
    try:
        result = compare_histories(args.snapshots)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["allEqual"] else 1
    except HistoryAuditError as error:
        print(f"[ERROR] {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
