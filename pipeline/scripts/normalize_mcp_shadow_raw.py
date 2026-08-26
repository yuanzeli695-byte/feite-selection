#!/usr/bin/env python3
"""Normalize archived SellerSprite MCP responses into immutable shadow evidence."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from datetime import timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
BRIDGE_PATH = ROOT / "scripts" / "mcp_hybrid_bridge.py"
SPEC = importlib.util.spec_from_file_location("mcp_hybrid_bridge_normalize", BRIDGE_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("unable to load bridge")
BRIDGE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = BRIDGE
SPEC.loader.exec_module(BRIDGE)


def inner_response(raw: dict[str, Any]) -> dict[str, Any]:
    result = raw.get("result") or {}
    content = result.get("content") or []
    if result.get("isError") or not content or content[0].get("type") != "text":
        return {"code": "TRANSPORT_ERROR", "message": str(raw.get("transportError") or "missing text response"), "data": None}
    try:
        return json.loads(content[0].get("text") or "{}")
    except json.JSONDecodeError:
        return {"code": "INVALID_JSON", "message": "MCP response text was not JSON", "data": None}


def latest(series: Any) -> Any:
    valid = [row for row in (series or []) if isinstance(row, dict) and isinstance(row.get("timePoint"), (int, float)) and isinstance(row.get("value"), (int, float)) and row["value"] >= 0]
    return max(valid, key=lambda row: row["timePoint"])["value"] if valid else None


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-dir", type=Path, required=True)
    parser.add_argument("--reservation", type=Path, required=True)
    parser.add_argument("--normalized", type=Path, required=True)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--bridge-output", type=Path, required=True)
    args = parser.parse_args()

    reservation = json.loads(args.reservation.read_text(encoding="utf-8-sig"))
    requests = {row["id"]: row for row in reservation["requests"]}
    normalized: list[dict[str, Any]] = []
    evidence: list[dict[str, Any]] = []
    calls: list[dict[str, Any]] = []
    for path in sorted(args.raw_dir.glob("*.json")):
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
        call_id = path.stem
        declared = requests[call_id]
        response = inner_response(raw)
        data = response.get("data")
        requested_asins = declared["request"].get("request", declared["request"]).get("asins") or declared["request"].get("request", declared["request"]).get("asinList") or [declared["request"].get("asin")]
        requested_asins = [str(value).upper() for value in requested_asins if value]
        observed_asins: list[str] = []
        exact_records: list[dict[str, Any]] = []
        if raw["tool"] in {"competitor_lookup", "traffic_extend"}:
            items = (data or {}).get("items") or []
            for item in items:
                asin = str(item.get("asin") or "").upper()
                if asin:
                    observed_asins.append(asin)
                if asin in requested_asins:
                    exact_records.append(dict(item))
        elif raw["tool"] == "keepa_info" and isinstance(data, dict):
            asin = str(data.get("asin") or "").upper()
            observed_asins.append(asin)
            if asin in requested_asins:
                record = {
                    "asin": asin,
                    "title": data.get("title"),
                    "brand": data.get("brand"),
                    "price": latest(data.get("price")),
                    "rating": latest(data.get("rating")),
                    "reviews": latest(data.get("reviews")),
                    "variations": data.get("variations"),
                    "imageUrl": data.get("imageUrl"),
                    "categoryPath": data.get("categoryPath"),
                    "dimensions": data.get("dimensions"),
                    "packageDimensions": data.get("packageDimensions"),
                    "pricePointCount": len(data.get("price") or []),
                    "ratingPointCount": len(data.get("rating") or []),
                    "reviewPointCount": len(data.get("reviews") or []),
                    "sourceTool": raw["tool"],
                    "sourceCallId": call_id,
                }
                exact_records.append(record)
        normalized.extend(exact_records)
        calls.append({
            "callId": call_id,
            "tool": raw["tool"],
            "code": response.get("code"),
            "requestedAsins": requested_asins,
            "observedAsins": observed_asins,
            "exactMatchCount": len(exact_records),
            "scopeMismatch": bool(observed_asins) and not any(asin in requested_asins for asin in observed_asins),
            "emptyResult": not observed_asins,
            "rawPath": str(path),
            "rawSha256": file_hash(path),
        })
        if raw["tool"] != "keepa_info":
            continue
        captured = BRIDGE.parse_timestamp(raw["capturedAt"], "capturedAt")
        expires = captured + timedelta(hours=6)
        for record in exact_records:
            missing = [field for field in ("price", "rating", "reviews", "variations", "dimensions", "packageDimensions") if record.get(field) is None]
            fields = {key: value for key, value in record.items() if key not in {"sourceTool", "sourceCallId"}}
            provenance = {key: {"sourceTool": "keepa_info", "sourcePath": f"data.{key}", "semantics": "shadow_observation"} for key in fields if key != "asin"}
            response_sha = hashlib.sha256((raw["result"]["content"][0]["text"] + "\n").encode("utf-8")).hexdigest()
            evidence_id = f"{reservation['runId']}-{call_id}-v1"
            evidence.append({
                "schemaVersion": "sellerSpriteMcpEvidence/v1",
                "evidenceId": evidence_id,
                "runId": reservation["runId"],
                "marketplace": "US",
                "mode": "shadow",
                "finalAuthority": False,
                "targetAsin": requested_asins[0],
                "actualAsin": record["asin"],
                "tool": {"name": "keepa_info", "version": "unknown"},
                "request": {"sha256": declared["requestHash"], "asinCount": 1},
                "response": {"sha256": response_sha, "capturedAt": raw["capturedAt"], "expiresAt": expires.isoformat(timespec="milliseconds").replace("+00:00", "Z")},
                "fields": fields,
                "fieldProvenance": provenance,
                "missingFields": missing,
                "fallbackRequired": False,
            })
    normalized_payload = {"schemaVersion":"sellerSpriteMcpShadowNormalized/v1","runId":reservation["runId"],"finalAuthority":False,"calls":calls,"records":normalized}
    bundle = {"schemaVersion":"sellerSpriteMcpEvidenceBundle/v1","runId":reservation["runId"],"marketplace":"US","generatedAt":BRIDGE.now_iso(),"source":"archived-mcp-shadow-responses","evidence":evidence}
    args.normalized.parent.mkdir(parents=True, exist_ok=True)
    args.normalized.write_text(json.dumps(normalized_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.bundle.write_text(json.dumps(bundle, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    config = BRIDGE.BridgeConfig(project_root=ROOT, output_root=args.bridge_output, run_id=reservation["runId"], token="offline-import", policy_path=ROOT / "config" / "mcp_hybrid_policy.json", run_budget=8)
    bridge = BRIDGE.McpHybridBridge(config)
    imported = bridge.store.import_bundle(bundle)
    print(json.dumps({"calls":len(calls),"records":len(normalized),"evidence":len(evidence),"import":imported}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
