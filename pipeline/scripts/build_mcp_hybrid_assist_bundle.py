#!/usr/bin/env python3
"""Build one 30-ASIN immutable evidence bundle for Hybrid Assist 0.2.0."""

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


def load_module(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


BRIDGE = load_module("mcp_hybrid_bridge_assist_bundle", ROOT / "scripts" / "mcp_hybrid_bridge.py")
ANALYZER = load_module("mcp_keepa_pair_assist_bundle", ROOT / "scripts" / "analyze_mcp_keepa_full_pair.py")


def reservation_index(paths: list[Path]) -> dict[str, dict[str, Any]]:
    result = {}
    for path in paths:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
        for request in payload.get("requests") or []:
            result[request["id"]] = request
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-dir", type=Path, action="append", required=True)
    parser.add_argument("--reservation", type=Path, action="append", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--bridge-output", type=Path, required=True)
    args = parser.parse_args()
    reservations = reservation_index(args.reservation)
    evidence = []
    raw_manifest = []
    seen = set()
    for root in args.raw_dir:
        for path in sorted(root.glob("keepa-*.json")):
            raw, data = ANALYZER.inner_data(path)
            target = str((raw.get("args") or {}).get("asin") or "").upper()
            actual = str(data.get("asin") or "").upper()
            if not target or target in seen or actual != target:
                continue
            call_id = f"keepa-{target}"
            declared = reservations.get(call_id)
            if not declared:
                raise ValueError(f"missing reservation for {call_id}")
            captured = BRIDGE.parse_timestamp(raw.get("capturedAt"), "capturedAt")
            samples = ANALYZER.daily_price_samples(data.get("price"))
            fields = {
                "asin": actual,
                "title": data.get("title"),
                "brand": data.get("brand"),
                "price": ANALYZER.latest(data.get("price")),
                "rating": ANALYZER.latest(data.get("rating")),
                "reviews": ANALYZER.latest(data.get("reviews")),
                "variations": data.get("variations"),
                "imageUrl": data.get("imageUrl"),
                "categoryPath": data.get("categoryPath"),
                "dimensions": data.get("dimensions"),
                "packageDimensions": data.get("packageDimensions"),
                "itemWeight": data.get("itemWeight"),
                "packageWeight": data.get("packageWeight"),
                "parentAsin": data.get("parentAsin"),
                "priceTrendClass": ANALYZER.classify_price_samples(samples),
                "pricePointCount": len(samples),
            }
            missing = [key for key, value in fields.items() if key != "asin" and value is None]
            text = raw["result"]["content"][0]["text"]
            evidence.append({
                "schemaVersion": "sellerSpriteMcpEvidence/v1",
                "evidenceId": f"{args.run_id}-{call_id}-v1",
                "runId": args.run_id,
                "marketplace": "US",
                "mode": "shadow",
                "finalAuthority": False,
                "targetAsin": target,
                "actualAsin": actual,
                "tool": {"name": "keepa_info", "version": "unknown"},
                "request": {"sha256": declared["requestHash"], "asinCount": 1},
                "response": {
                    "sha256": hashlib.sha256((text + "\n").encode("utf-8")).hexdigest(),
                    "capturedAt": raw["capturedAt"],
                    "expiresAt": (captured + timedelta(hours=6)).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
                },
                "fields": fields,
                "fieldProvenance": {
                    key: {"sourceTool": "keepa_info", "sourcePath": f"data.{key}", "semantics": "shadow_advisory"}
                    for key in fields if key != "asin"
                },
                "missingFields": missing,
                "fallbackRequired": False,
            })
            raw_manifest.append({"asin": target, "path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
            seen.add(target)
    if len(evidence) != 30:
        raise ValueError(f"expected 30 exact evidence rows, found {len(evidence)}")
    bundle = {
        "schemaVersion": "sellerSpriteMcpEvidenceBundle/v1",
        "runId": args.run_id,
        "marketplace": "US",
        "generatedAt": BRIDGE.now_iso(),
        "source": "mcp-hybrid-assist-v0.2-paired-30",
        "rawManifest": raw_manifest,
        "evidence": evidence,
    }
    args.bundle.parent.mkdir(parents=True, exist_ok=True)
    args.bundle.write_text(json.dumps(bundle, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    config = BRIDGE.BridgeConfig(
        project_root=ROOT,
        output_root=args.bridge_output,
        run_id=args.run_id,
        token="offline-import",
        policy_path=ROOT / "config" / "mcp_hybrid_policy.json",
        run_budget=1,
    )
    imported = BRIDGE.McpHybridBridge(config).store.import_bundle(bundle)
    print(json.dumps({"evidence": len(evidence), "import": imported}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
