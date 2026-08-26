#!/usr/bin/env python3
"""Build the exact remaining-ASIN Keepa plan for a frozen shadow baseline."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


RETURN_FIELDS = (
    "asin,title,brand,price,rating,reviews,variations,imageUrl,categoryPath,"
    "dimensions,packageDimensions,itemWeight,packageWeight,parentAsin,"
    "priceHistory,ratingHistory,reviewsHistory"
)


def build(baseline: dict, normalized: dict, *, prior_calls: int, hard_ceiling: int) -> dict:
    all_asins = [row["asin"] for row in baseline["rows"]]
    existing = {row["asin"] for row in normalized.get("records") or []}
    remaining = [asin for asin in all_asins if asin not in existing]
    if len(all_asins) != 30 or len(set(all_asins)) != 30:
        raise ValueError("baseline must contain exactly 30 unique ASINs")
    if len(remaining) != 25:
        raise ValueError(f"expected 25 remaining ASINs, found {len(remaining)}")
    if prior_calls + len(remaining) > hard_ceiling:
        raise ValueError("completion plan would exceed task hard ceiling")
    requests = []
    for asin in remaining:
        requests.append({
            "id": f"keepa-{asin}",
            "tool": "keepa_info",
            "calls": 1,
            "asins": [asin],
            "request": {
                "marketplace": "US",
                "asin": asin,
                "dailyLatest": True,
                "returnFields": RETURN_FIELDS,
            },
        })
    return {
        "schemaVersion": "sellerSpriteMcpShadowPlan/v1",
        "planId": "mcp-shadow-20260729-keepa-complete-25",
        "marketplace": "US",
        "purpose": "Complete the frozen 30-ASIN Keepa shadow comparison without changing A-F decisions.",
        "taskCallBudget": {
            "hardCeiling": hard_ceiling,
            "priorCalls": prior_calls,
            "plannedCalls": len(requests),
            "maximumAfterPlan": prior_calls + len(requests),
        },
        "sample": [{"asin": asin} for asin in remaining],
        "requests": requests,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--normalized", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--prior-calls", type=int, default=8)
    parser.add_argument("--hard-ceiling", type=int, default=50)
    args = parser.parse_args()
    result = build(
        json.loads(args.baseline.read_text(encoding="utf-8-sig")),
        json.loads(args.normalized.read_text(encoding="utf-8-sig")),
        prior_calls=args.prior_calls,
        hard_ceiling=args.hard_ceiling,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result["taskCallBudget"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
