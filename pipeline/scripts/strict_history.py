"""Persistent registry of ASINs that have already passed strict selection.

The registry is intentionally built from both the durable history file and prior
run artifacts. This keeps future queues deduplicated even when a run was
delivered outside the standard replay command.
"""
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any


ASIN_RE = re.compile(r"^B0[A-Z0-9]{8}$")
REGISTRY_RELATIVE_PATH = Path("history") / "strict_qualified_asins.json"
QUALIFIED_FILE_NAMES = ("qualified_pool.json", "final_candidates_data.json")
ACCEPTANCE_REPORT_NAME = "acceptance_report.md"
ACCEPTANCE_COMPLETE_MARKER = "- Delivery complete: yes"


def _is_accepted_delivery_dir(run_dir: Path) -> bool:
    """Only machine-accepted run directories may seed durable history."""
    report = run_dir / ACCEPTANCE_REPORT_NAME
    try:
        return ACCEPTANCE_COMPLETE_MARKER in report.read_text(encoding="utf-8-sig")
    except OSError:
        return False


def normalize_asin(value: Any) -> str:
    text = str(value or "").strip().upper()
    return text if ASIN_RE.fullmatch(text) else ""


def registry_path(project_root: str | Path) -> Path:
    return Path(project_root).resolve() / REGISTRY_RELATIVE_PATH


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _extract_asins(payload: Any) -> set[str]:
    if isinstance(payload, dict):
        for key in ("candidates", "asins", "strictQualifiedAsins"):
            if key in payload:
                return _extract_asins(payload[key])
        return {asin for asin in (normalize_asin(payload.get("asin")),) if asin}
    if not isinstance(payload, list):
        return set()
    out: set[str] = set()
    for item in payload:
        value = item.get("asin") if isinstance(item, dict) else item
        asin = normalize_asin(value)
        if asin:
            out.add(asin)
    return out


def _is_under(path: Path, parent: Path | None) -> bool:
    if parent is None:
        return False
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def collect_strict_history(
    project_root: str | Path,
    *,
    exclude_run_dir: str | Path | None = None,
) -> dict[str, set[str]]:
    """Return ASIN -> provenance paths for all known strict-qualified products."""
    root = Path(project_root).resolve()
    excluded = Path(exclude_run_dir).resolve() if exclude_run_dir else None
    records: dict[str, set[str]] = {}

    def add_from(path: Path) -> None:
        try:
            asins = _extract_asins(_read_json(path))
        except (OSError, ValueError, json.JSONDecodeError):
            return
        try:
            source = str(path.resolve().relative_to(root))
        except ValueError:
            source = str(path.resolve())
        for asin in asins:
            records.setdefault(asin, set()).add(source)

    registry = registry_path(root)
    if registry.exists():
        add_from(registry)

    runs_dir = root / "runs"
    if runs_dir.exists():
        for file_name in QUALIFIED_FILE_NAMES:
            for path in runs_dir.glob(f"*/{file_name}"):
                if _is_under(path, excluded):
                    continue
                if not _is_accepted_delivery_dir(path.parent):
                    continue
                add_from(path)
    return records


def load_strict_qualified_asins(
    project_root: str | Path,
    *,
    exclude_run_dir: str | Path | None = None,
) -> set[str]:
    return set(collect_strict_history(project_root, exclude_run_dir=exclude_run_dir))


def sync_strict_history_registry(project_root: str | Path) -> dict[str, Any]:
    """Merge prior strict-delivery artifacts into the durable registry."""
    root = Path(project_root).resolve()
    records = collect_strict_history(root)
    payload = {
        "schemaVersion": "strictQualifiedHistory/v1",
        "updatedAt": datetime.now().astimezone().isoformat(timespec="seconds"),
        "count": len(records),
        "asins": [
            {"asin": asin, "sources": sorted(records[asin])}
            for asin in sorted(records)
        ],
    }
    output = registry_path(root)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the strict-qualified ASIN history registry.")
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parent.parent)
    parser.add_argument("--write", action="store_true", help="Write history/strict_qualified_asins.json.")
    parser.add_argument("--print-asins", action="store_true")
    args = parser.parse_args()

    if args.write:
        payload = sync_strict_history_registry(args.project_root)
        print(f"[OK] strict history registry: {payload['count']} ASINs")
        print(registry_path(args.project_root))
        return 0

    records = collect_strict_history(args.project_root)
    if args.print_asins:
        print("\n".join(sorted(records)))
    else:
        print(json.dumps({"count": len(records)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
