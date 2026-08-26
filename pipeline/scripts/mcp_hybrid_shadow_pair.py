#!/usr/bin/env python3
"""Prepare and analyze a non-authoritative MCP shadow paired validation."""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import math
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
BRIDGE_PATH = ROOT / "scripts" / "mcp_hybrid_bridge.py"
SPEC = importlib.util.spec_from_file_location("mcp_hybrid_bridge_shadow", BRIDGE_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("unable to load bridge")
BRIDGE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = BRIDGE
SPEC.loader.exec_module(BRIDGE)

ASIN_RE = re.compile(r"^B0[A-Z0-9]{8}$")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def iso(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    except ValueError:
        return text


def load_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def candidate_dicts(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from candidate_dicts(child)
    elif isinstance(value, list):
        for child in value:
            yield from candidate_dicts(child)


def product_snapshot(root: Path, asin: str) -> dict[str, Any]:
    best: dict[str, Any] = {}
    for path in root.glob("*.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            continue
        for item in candidate_dicts(payload):
            if str(item.get("asin") or "").upper() == asin:
                if isinstance(item.get("product"), dict):
                    best.update(item["product"])
                else:
                    best.update({k: v for k, v in item.items() if k not in {"traffic", "warnings", "tags", "source"}})
                if isinstance(item.get("traffic"), dict):
                    best["traffic"] = dict(item["traffic"])
    return best


def find_log(root: Path, prefix: str, preferred: str = "") -> Path:
    if preferred:
        exact = root / preferred
        if exact.is_file():
            return exact
    matches = sorted(root.glob(f"{prefix}*.tsv"))
    if not matches:
        raise FileNotFoundError(f"no {prefix} log in {root}")
    return matches[0]


def pick_row(paths: list[Path], asin: str) -> tuple[dict[str, str], Path]:
    found: list[tuple[dict[str, str], Path]] = []
    for path in paths:
        for row in load_rows(path):
            if str(row.get("asin") or "").strip().upper() == asin:
                found.append((row, path))
    if not found:
        raise KeyError(f"ASIN not found in logs: {asin}")
    return found[-1]


def prepare(plan_path: Path, output_path: Path) -> dict[str, Any]:
    plan = json.loads(plan_path.read_text(encoding="utf-8-sig"))
    sample = plan.get("sample")
    if not isinstance(sample, list) or len(sample) != 30:
        raise ValueError("plan sample must contain exactly 30 rows")
    asins = [str(row.get("asin") or "").upper() for row in sample]
    if len(set(asins)) != 30 or any(not ASIN_RE.fullmatch(asin) for asin in asins):
        raise ValueError("sample must contain 30 unique valid ASINs")
    rows: list[dict[str, Any]] = []
    source_manifest: dict[str, Any] = {}
    for spec in sample:
        asin = str(spec["asin"]).upper()
        root = ROOT / Path(spec["sourceRoot"])
        if not root.is_dir():
            raise FileNotFoundError(root)
        gate_pref = "gate_log_batch02_clean.tsv" if spec["sourceClass"] == "recent_browser" else ""
        timing_pref = "timing_log_batch02_clean.tsv" if spec["sourceClass"] == "recent_browser" else ""
        gate_path = find_log(root, "gate_log_" if spec["sourceClass"] == "historical_browser" else "gate_log", gate_pref)
        timing_path = find_log(root, "timing_log_" if spec["sourceClass"] == "historical_browser" else "timing_log", timing_pref)
        gate_row, gate_source = pick_row([gate_path] if gate_pref else sorted(root.glob("gate_log_*.tsv")), asin)
        timing_row, timing_source = pick_row([timing_path] if timing_pref else sorted(root.glob("timing_log_*.tsv")), asin)
        if gate_row.get("outcome") != spec["expectedOutcome"]:
            raise ValueError(f"expected outcome mismatch for {asin}: {gate_row.get('outcome')} != {spec['expectedOutcome']}")
        source_key = str(root)
        source_manifest.setdefault(source_key, {"files": {}})
        for path in {gate_source, timing_source}:
            source_manifest[source_key]["files"][str(path.relative_to(ROOT)).replace("\\", "/")] = {"sha256": sha256(path), "bytes": path.stat().st_size}
        rows.append({
            "asin": asin,
            "expectedOutcome": spec["expectedOutcome"],
            "sourceClass": spec["sourceClass"],
            "sourceRoot": spec["sourceRoot"],
            "browser": {
                "gate": gate_row,
                "timing": timing_row,
                "gateSource": str(gate_source.relative_to(ROOT)).replace("\\", "/"),
                "timingSource": str(timing_source.relative_to(ROOT)).replace("\\", "/"),
            },
            "productSnapshot": product_snapshot(ROOT / Path((plan.get("metadataRoots") or {}).get(spec["sourceClass"], spec["sourceRoot"])), asin),
        })
    result = {
        "schemaVersion": "sellerSpriteMcpShadowBaseline/v1",
        "planId": plan["planId"],
        "createdAt": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "sampleSize": 30,
        "passCount": sum(row["expectedOutcome"] == "pass" for row in rows),
        "rejectCount": sum(row["expectedOutcome"] == "reject" for row in rows),
        "strictHistoryUnchangedRequired": True,
        "sourceManifest": source_manifest,
        "rows": rows,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def flatten(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from flatten(child)
    elif isinstance(value, list):
        for child in value:
            yield from flatten(child)


def records_by_asin(value: Any) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for item in flatten(value):
        asin = str(item.get("asin") or item.get("ASIN") or item.get("targetAsin") or item.get("actualAsin") or "").upper()
        if ASIN_RE.fullmatch(asin):
            result.setdefault(asin, {}).update(item)
    return result


def num(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def compare_value(browser: Any, mcp: Any, tolerance: float = 0.01) -> str:
    left, right = num(browser), num(mcp)
    if left is None or right is None:
        return "missing"
    return "match" if abs(left - right) <= tolerance else "mismatch"


def analyze(baseline_path: Path, evidence_path: Path, output_path: Path) -> dict[str, Any]:
    baseline = json.loads(baseline_path.read_text(encoding="utf-8-sig"))
    evidence = json.loads(evidence_path.read_text(encoding="utf-8-sig"))
    raw_records = records_by_asin(evidence)
    details: list[dict[str, Any]] = []
    for row in baseline["rows"]:
        asin = row["asin"]
        mcp = raw_records.get(asin, {})
        product = row.get("productSnapshot") or {}
        browser = row["browser"]["gate"]
        # MCP fields are shadow-only; comparison is informational and never gate-authoritative.
        field_status = {
            "price": compare_value(browser.get("currentPrice"), mcp.get("price")),
            "rating": compare_value(product.get("rating"), mcp.get("rating")),
            "reviews": compare_value(product.get("reviews"), mcp.get("reviews")),
            "variations": compare_value(product.get("variationsCount"), mcp.get("variations")),
        }
        final_agreement = row["expectedOutcome"] == ("pass" if browser.get("outcome") == "pass" else "reject")
        details.append({"asin": asin, "expectedOutcome": row["expectedOutcome"], "mcpPresent": bool(mcp), "fieldStatus": field_status, "finalGateAgreement": final_agreement, "mcpRecord": mcp})
    agreement = sum(item["finalGateAgreement"] for item in details)
    result = {
        "schemaVersion": "sellerSpriteMcpShadowAnalysis/v1",
        "analyzedAt": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "baseline": str(baseline_path),
        "evidence": str(evidence_path),
        "sampleSize": len(details),
        "mcpRecordCoverage": sum(item["mcpPresent"] for item in details),
        "finalGateAgreementCount": agreement,
        "finalGateAgreementPct": round(100 * agreement / len(details), 2) if details else 0,
        "zeroFalsePositive": all(not (item["expectedOutcome"] == "reject" and item["finalGateAgreement"] is False) for item in details),
        "mcpFinalAuthority": False,
        "details": details,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    p_prepare = sub.add_parser("prepare")
    p_prepare.add_argument("--plan", type=Path, required=True)
    p_prepare.add_argument("--output", type=Path, required=True)
    p_analyze = sub.add_parser("analyze")
    p_analyze.add_argument("--baseline", type=Path, required=True)
    p_analyze.add_argument("--evidence", type=Path, required=True)
    p_analyze.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "prepare":
        result = prepare(args.plan, args.output)
    else:
        result = analyze(args.baseline, args.evidence, args.output)
    print(json.dumps({k: result[k] for k in result if k not in {"rows", "details", "sourceManifest"}}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
