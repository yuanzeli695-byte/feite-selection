#!/usr/bin/env python3
"""Read-only integrity preflight for the Amazon US strict-selection project."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any


APPROVED_RULES: dict[str, Any] = {
    "priceMinUsd": 9.9,
    "priceMaxUsd": 50.0,
    "minRating": 4.0,
    "maxReviews": 100,
    "reviewsTolerance": 15,
    "launchAgeMaxDays": 90,
    "variationsMax": 25,
    "monthlySalesIdealMin": 50,
    "monthlySalesIdealMax": 300,
    "monthlySalesHardMax": 1500,
    "trafficNaturalMinPct": 70,
    "trafficRecent4AvgMinPct": 70,
    "trafficRecent4MinMinPct": 70,
    "trafficWeeksReadMin": 3,
    "asinMismatchPolicy": "review",
    "imageEmbedRequired": True,
    "dimensionsRequired": True,
    "priceTrendRequired": True,
    "allowedPriceTrendClasses": ["stable", "rising"],
}

APPROVED_SCRIPTS = {
    "collector": ("scripts/sellersprite_traffic_collector_v0.4.6.user.js", "0.4.6"),
    "runner": ("scripts/sellersprite_integrated_runner_v0.3.7.user.js", "0.3.7"),
    "collectorRollback": ("scripts/sellersprite_traffic_collector_v0.4.5.user.js", "0.4.5"),
    "runnerRollback": ("scripts/sellersprite_integrated_runner_v0.3.6.user.js", "0.3.6"),
}

APPROVED_FLAGS = {
    "collector": "ENABLE_TIER2_1_ZERO_SHARE_DERIVATION",
    "runner": "ENABLE_TIER2_2_CONDITIONAL_RETRY",
}

REQUIRED_FILES = [
    "README.md",
    "PIPELINE_RUNBOOK.md",
    "config/rules.json",
    "config/exclusions.json",
    "config/pipeline.json",
    "history/strict_qualified_asins.json",
    "scripts/candidate_tsv_to_json.py",
    "scripts/prepare_strict_candidate_pool.py",
    "scripts/download_candidate_images.py",
    "scripts/replay_existing_batch.py",
    "scripts/build_replay_workbooks.mjs",
    "scripts/acceptance_checker.py",
    "scripts/strict_history.py",
]

RUN_FILES = [
    "run_summary.json",
    "final_candidates_data.json",
    "rejected_audit_data.json",
    "workbook_build_report.json",
    "acceptance_report.md",
]


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def is_project_root(path: Path) -> bool:
    return (path / "config" / "rules.json").is_file() and (
        path / "scripts" / "replay_existing_batch.py"
    ).is_file()


def discover_root(explicit: str | None) -> Path:
    if explicit:
        resolved = Path(explicit).expanduser().resolve()
        if not is_project_root(resolved):
            raise FileNotFoundError(f"explicit --project-root is not the Amazon selection project: {resolved}")
        return resolved

    candidates: list[Path] = []
    env_root = os.environ.get("AMAZON_PRODUCTS_ROOT")
    if env_root:
        resolved = Path(env_root).expanduser().resolve()
        if not is_project_root(resolved):
            raise FileNotFoundError(f"AMAZON_PRODUCTS_ROOT is not the Amazon selection project: {resolved}")
        return resolved
    cwd = Path.cwd()
    candidates.extend([cwd, *cwd.parents])
    candidates.append(Path.home() / "Desktop" / "amazon_products")

    seen: set[Path] = set()
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        if is_project_root(resolved):
            return resolved
    raise FileNotFoundError(
        "Amazon selection project not found; pass --project-root or set AMAZON_PRODUCTS_ROOT"
    )


def userscript_version(path: Path) -> str | None:
    match = re.search(
        r"^\s*//\s*@version\s+([^\s]+)",
        path.read_text(encoding="utf-8-sig"),
        re.MULTILINE,
    )
    return match.group(1) if match else None


def userscript_flag_enabled(path: Path, flag: str) -> bool:
    text = path.read_text(encoding="utf-8-sig")
    pattern = rf"\b(?:var|let|const)\s+{re.escape(flag)}\s*=\s*true\s*;"
    return re.search(pattern, text) is not None


def history_count(payload: Any) -> int | None:
    if not isinstance(payload, dict):
        return None
    if isinstance(payload.get("count"), int):
        return payload["count"]
    if isinstance(payload.get("asins"), list):
        return len(payload["asins"])
    return None


def compare_rules(actual: dict[str, Any]) -> list[dict[str, Any]]:
    drift = []
    for key, expected in APPROVED_RULES.items():
        value = actual.get(key, "<missing>")
        if value != expected:
            drift.append({"key": key, "expected": expected, "actual": value})
    return drift


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root")
    parser.add_argument("--run-dir", help="Optionally verify that a completed run bundle has its core files")
    parser.add_argument("--json-out", type=Path, help="Optionally save the JSON report")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    errors: list[str] = []
    warnings: list[str] = []

    try:
        root = discover_root(args.project_root)
    except Exception as exc:
        report = {
            "schemaVersion": "amazonStrictSelectionPreflight/v1",
            "ok": False,
            "errors": [str(exc)],
        }
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 2

    missing = [rel for rel in REQUIRED_FILES if not (root / rel).is_file()]
    errors.extend(f"missing required file: {rel}" for rel in missing)

    parsed_json: dict[str, Any] = {}
    json_files = (
        "config/rules.json",
        "config/exclusions.json",
        "config/pipeline.json",
        "history/strict_qualified_asins.json",
    )
    for rel in json_files:
        path = root / rel
        if not path.is_file():
            continue
        try:
            parsed_json[rel] = load_json(path)
        except Exception as exc:
            errors.append(f"invalid JSON {rel}: {exc}")

    rules = parsed_json.get("config/rules.json")
    rule_drift = compare_rules(rules) if isinstance(rules, dict) else []
    if not isinstance(rules, dict) and (root / "config/rules.json").is_file():
        errors.append("config/rules.json must be a JSON object")
    if rule_drift:
        errors.append("approved hard-rule snapshot drift detected; obtain explicit authorization before changing it")

    script_report: dict[str, Any] = {}
    for role, (relative, expected_version) in APPROVED_SCRIPTS.items():
        path = root / relative
        actual_version = userscript_version(path) if path.is_file() else None
        script_report[role] = {
            "path": str(path),
            "expectedVersion": expected_version,
            "actualVersion": actual_version,
            "ok": actual_version == expected_version,
        }
        if actual_version != expected_version:
            errors.append(f"{role} version mismatch: expected {expected_version}, got {actual_version}")

    for role, flag in APPROVED_FLAGS.items():
        relative = APPROVED_SCRIPTS[role][0]
        path = root / relative
        enabled = path.is_file() and userscript_flag_enabled(path, flag)
        script_report[role]["requiredFlag"] = flag
        script_report[role]["requiredFlagEnabled"] = enabled
        script_report[role]["ok"] = script_report[role]["ok"] and enabled
        if not enabled:
            errors.append(f"{role} approved feature flag is not enabled: {flag}")

    history_payload = parsed_json.get("history/strict_qualified_asins.json")
    strict_history_count = history_count(history_payload)
    if strict_history_count is None and (root / "history/strict_qualified_asins.json").is_file():
        errors.append("strict history count could not be determined")

    run_report = None
    if args.run_dir:
        run_dir = Path(args.run_dir).expanduser()
        if not run_dir.is_absolute():
            run_dir = root / run_dir
        run_dir = run_dir.resolve()
        missing_run_files = [name for name in RUN_FILES if not (run_dir / name).is_file()]
        run_report = {
            "path": str(run_dir),
            "missingFiles": missing_run_files,
            "ok": not missing_run_files,
        }
        errors.extend(f"run bundle missing: {name}" for name in missing_run_files)

    if not (root / "tests" / "test_sellersprite_traffic_collector_v046.mjs").is_file():
        warnings.append("Collector 0.4.6 regression test was not found")
    if not (root / "tests" / "test_sellersprite_integrated_runner_v037.mjs").is_file():
        warnings.append("Runner 0.3.7 regression test was not found")

    report = {
        "schemaVersion": "amazonStrictSelectionPreflight/v1",
        "ok": not errors,
        "projectRoot": str(root),
        "requiredFilesMissing": missing,
        "approvedRuleDrift": rule_drift,
        "userscripts": script_report,
        "strictQualifiedHistoryCount": strict_history_count,
        "runBundle": run_report,
        "warnings": warnings,
        "errors": errors,
    }

    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    print(rendered)
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(rendered + "\n", encoding="utf-8")
    return 0 if report["ok"] else 2


if __name__ == "__main__":
    sys.exit(main())
