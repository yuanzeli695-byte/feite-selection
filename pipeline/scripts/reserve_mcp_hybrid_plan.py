#!/usr/bin/env python3
"""Atomically reserve a predeclared MCP shadow call plan."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BRIDGE_PATH = ROOT / "scripts" / "mcp_hybrid_bridge.py"
SPEC = importlib.util.spec_from_file_location("mcp_hybrid_bridge_reserve", BRIDGE_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("unable to load bridge")
BRIDGE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = BRIDGE
SPEC.loader.exec_module(BRIDGE)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--ledger", type=Path, default=ROOT / "cache" / "mcp_hybrid_call_ledger.jsonl")
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--run-budget", type=int, default=None)
    parser.add_argument("--allow-emergency", action="store_true")
    parser.add_argument("--test-mode", action="store_true")
    args = parser.parse_args()
    plan = json.loads(args.plan.read_text(encoding="utf-8-sig"))
    policy = BRIDGE.load_policy(ROOT / "config" / "mcp_hybrid_policy.json")
    sample = plan.get("sample") or []
    asins = [row["asin"] for row in sample]
    resolved = []
    for item in plan.get("requests") or []:
        request = json.loads(json.dumps(item["request"]))
        marker = request.get("asins") or request.get("asinList")
        if marker == "__SAMPLE__":
            request["asins"] = asins
        elif marker == "__FIRST20__":
            request["asinList"] = asins[:20]
        elif marker == "__LAST10__":
            request["asinList"] = asins[20:]
        tool_args = {"request": request} if item["tool"] in {"competitor_lookup", "traffic_extend"} else request
        request_hash = BRIDGE.payload_sha256(tool_args)
        tool_policy = policy["tools"].get(item["tool"])
        if not tool_policy:
            raise ValueError(f"unsupported tool: {item['tool']}")
        request_asins = request.get("asins") or request.get("asinList") or ([request.get("asin")] if request.get("asin") else [])
        resolved.append(
            {
                "id": item["id"],
                "tool": item["tool"],
                "calls": int(item.get("calls") or 1),
                "asinCount": len(request_asins),
                "pool": str(item.get("pool") or "primary"),
                "request": tool_args,
                "requestHash": request_hash,
            }
        )
    total = sum(item["calls"] for item in resolved)
    ledger = BRIDGE.CallLedger(
        args.ledger,
        run_id=args.run_id,
        policy=policy,
        run_budget=args.run_budget,
        test_mode=args.test_mode,
    )
    reservation = ledger.reserve_plan(
        plan_id=plan["planId"],
        requests=resolved,
        allow_emergency=args.allow_emergency,
    )
    report = {
        "schemaVersion": "sellerSpriteMcpShadowReservation/v1",
        "bridgeVersion": BRIDGE.BRIDGE_VERSION,
        "planId": plan["planId"],
        "runId": args.run_id,
        "totalCalls": total,
        "requests": resolved,
        "reservation": reservation,
        "reservations": [reservation],
        "ledger": reservation["summary"],
        "automaticRetry": False,
        "finalAuthority": False,
    }
    BRIDGE.atomic_write_json(args.report, report)
    print(json.dumps({"planId":plan["planId"],"runId":args.run_id,"totalCalls":total,"ledger":report["ledger"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
