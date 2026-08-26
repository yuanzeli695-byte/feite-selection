#!/usr/bin/env python3
"""Create an immutable corrected copy of a formal Runner batch.

This helper never edits the raw browser export.  It records independently
verified ASIN/URL mismatches so the ordinary fail-closed replay can reject the
affected row.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse


def asin_from_url(url: str) -> str:
    parts = [part for part in urlparse(url).path.split("/") if part]
    for marker in ("dp", "gp", "product"):
        if marker in parts:
            index = parts.index(marker) + 1
            if index < len(parts):
                return parts[index].upper()
    return ""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--target-asin", required=True)
    parser.add_argument("--actual-asin", required=True)
    parser.add_argument("--evidence", required=True)
    args = parser.parse_args()

    if args.input.resolve() == args.output.resolve():
        raise SystemExit("output must differ from immutable raw input")

    batch = json.loads(args.input.read_text(encoding="utf-8-sig"))
    target = args.target_asin.strip().upper()
    actual = args.actual_asin.strip().upper()
    matches = [row for row in batch.get("results", []) if str(row.get("targetAsin") or "").upper() == target]
    if len(matches) != 1:
        raise SystemExit(f"expected exactly one {target} row, found {len(matches)}")
    row = matches[0]
    url_asin = asin_from_url(str(row.get("url") or ""))
    if url_asin != actual or actual == target:
        raise SystemExit(f"correction evidence conflict: target={target} actual={actual} urlAsin={url_asin}")

    reason = f"verified URL ASIN {actual} does not match target ASIN {target}; {args.evidence.strip()}"
    row["actualAsin"] = actual
    row["asinMismatch"] = True
    row["mismatchReason"] = reason
    row["strictDecision"] = "review"
    row["qualified"] = False
    row["decision"] = "review"
    row["rejectionStage"] = "hard_filter"
    row["rejectionRule"] = "asin_mismatch_review"
    row["rejectionReason"] = reason
    row["note"] = reason
    batch.setdefault("evidenceCorrections", []).append({
        "targetAsin": target,
        "actualAsin": actual,
        "url": row.get("url"),
        "reason": reason,
        "correctedAt": datetime.now().astimezone().isoformat(timespec="seconds"),
        "sourceBatch": str(args.input),
    })
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(batch, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(args.output), "targetAsin": target, "actualAsin": actual}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
