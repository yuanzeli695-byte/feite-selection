#!/usr/bin/env python3
"""Analyze full 30-ASIN Keepa shadow coverage without changing A-F authority."""

from __future__ import annotations

import argparse
import json
import math
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def inner_data(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    raw = json.loads(path.read_text(encoding="utf-8-sig"))
    result = raw.get("result") or {}
    content = result.get("content") or []
    if result.get("isError") or not content or content[0].get("type") != "text":
        return raw, {}
    try:
        response = json.loads(content[0].get("text") or "{}")
    except json.JSONDecodeError:
        return raw, {}
    return raw, response.get("data") if response.get("code") == "OK" and isinstance(response.get("data"), dict) else {}


def positive_series(value: Any) -> list[dict[str, float]]:
    rows = []
    for item in value or []:
        if not isinstance(item, dict):
            continue
        try:
            point = float(item["timePoint"])
            number = float(item["value"])
        except (KeyError, TypeError, ValueError):
            continue
        if math.isfinite(point) and math.isfinite(number) and number >= 0:
            rows.append({"timePoint": point, "value": number})
    return sorted(rows, key=lambda item: item["timePoint"])


def daily_price_samples(value: Any) -> list[dict[str, Any]]:
    by_date: dict[str, dict[str, Any]] = {}
    for row in positive_series(value):
        if row["value"] <= 0:
            continue
        date = datetime.fromtimestamp(row["timePoint"] / 1000, timezone.utc).date().isoformat()
        by_date[date] = {"date": date, "price": row["value"]}
    return [by_date[key] for key in sorted(by_date)]


def average(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def classify_price_samples(samples: list[dict[str, Any]]) -> str:
    clean = [row for row in samples if row.get("date") and isinstance(row.get("price"), (int, float)) and row["price"] > 0]
    if len(clean) < 3:
        return "no_data"
    prices = [float(row["price"]) for row in clean]
    group_size = max(1, math.ceil(len(prices) / 3))
    first_average = average(prices[:group_size]) or 0
    last_average = average(prices[-group_size:]) or 0
    current = prices[-1]
    minimum = min(prices)
    maximum = max(prices)
    change_pct = (last_average - first_average) / first_average if first_average else 0
    range_pct = (maximum - minimum) / minimum if minimum else 0
    peak_to_current = (maximum - current) / maximum if maximum else 0
    reversals = 0
    previous_direction = 0
    for index in range(1, len(prices)):
        base = prices[index - 1] or 1
        delta_pct = (prices[index] - prices[index - 1]) / base
        direction = 0 if abs(delta_pct) < 0.01 else (1 if delta_pct > 0 else -1)
        if direction and previous_direction and direction != previous_direction:
            reversals += 1
        if direction:
            previous_direction = direction
    if change_pct <= -0.08 or (peak_to_current >= 0.12 and current <= minimum * 1.03):
        return "declining"
    if range_pct >= 0.35 and reversals >= 2:
        return "volatile"
    if change_pct >= 0.05 or (current >= maximum * 0.97 and current > first_average * 1.03):
        return "rising"
    if range_pct <= 0.20 or abs(change_pct) < 0.05:
        return "stable"
    return "volatile"


def latest(value: Any) -> float | None:
    rows = positive_series(value)
    return rows[-1]["value"] if rows else None


def number(value: Any) -> float | None:
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def same_number(left: Any, right: Any, tolerance: float = 0.01) -> bool | None:
    a, b = number(left), number(right)
    if a is None or b is None:
        return None
    return abs(a - b) <= tolerance


def text_contains(browser: Any, mcp: Any) -> bool | None:
    left = " ".join(str(browser or "").lower().split())
    right = " ".join(str(mcp or "").lower().split())
    if not left or not right:
        return None
    return right in left or left in right


def score_record(record: dict[str, Any]) -> int:
    score = 0
    price = number(record.get("currentPrice"))
    rating = number(record.get("rating"))
    reviews = number(record.get("reviews"))
    if price is not None and 9.9 <= price <= 50:
        score += 2
    if rating is not None and rating >= 4:
        score += 1
    if reviews is not None and reviews <= 115:
        score += 1
    if record.get("dimensions") or record.get("packageDimensions"):
        score += 2
    if record.get("priceTrendClass") in {"stable", "rising"}:
        score += 3
    return score


def milestone_cost(rows: list[dict[str, Any]], target_passes: int) -> int | None:
    cost = 0
    passes = 0
    for row in rows:
        cost += int(number(row.get("browserTotalMs")) or 0)
        if row["expectedOutcome"] == "pass":
            passes += 1
        if passes >= target_passes:
            return cost
    return None


def build_report(baseline: dict[str, Any], raw_dirs: list[Path]) -> dict[str, Any]:
    raw_by_asin: dict[str, tuple[dict[str, Any], dict[str, Any], Path]] = {}
    for root in raw_dirs:
        for path in root.glob("keepa-*.json"):
            raw, data = inner_data(path)
            requested = str((raw.get("args") or {}).get("asin") or "").upper()
            if requested:
                raw_by_asin[requested] = (raw, data, path)
    details = []
    for index, baseline_row in enumerate(baseline["rows"]):
        asin = baseline_row["asin"]
        raw, data, path = raw_by_asin.get(asin, ({}, {}, Path("")))
        price_samples = daily_price_samples(data.get("price"))
        trend = classify_price_samples(price_samples)
        browser_gate = baseline_row["browser"]["gate"]
        browser_product = baseline_row.get("productSnapshot") or {}
        current_price = latest(data.get("price"))
        rating = latest(data.get("rating"))
        reviews = latest(data.get("reviews"))
        dimensions = data.get("dimensions")
        package_dimensions = data.get("packageDimensions")
        actual = str(data.get("asin") or "").upper()
        exact = actual == asin
        browser_price = browser_gate.get("currentPrice")
        browser_trend = str(browser_gate.get("priceTrendClass") or "")
        price_gate_ran = browser_gate.get("gateE") in {"pass", "reject"}
        record = {
            "index": index,
            "asin": asin,
            "expectedOutcome": baseline_row["expectedOutcome"],
            "sourceClass": baseline_row["sourceClass"],
            "actualAsin": actual,
            "exactAsin": exact,
            "rawPath": str(path) if path else "",
            "capturedAt": raw.get("capturedAt"),
            "currentPrice": current_price,
            "browserCurrentPrice": number(browser_price),
            "priceMatch": same_number(browser_price, current_price),
            "rating": rating,
            "browserRating": number(browser_product.get("rating")),
            "ratingMatch": same_number(browser_product.get("rating"), rating),
            "reviews": reviews,
            "browserReviews": number(browser_product.get("reviews")),
            "reviewsMatch": same_number(browser_product.get("reviews"), reviews, tolerance=0),
            "variations": data.get("variations"),
            "browserVariations": number(browser_product.get("variationsCount")),
            "variationsMatch": same_number(browser_product.get("variationsCount"), data.get("variations"), tolerance=0),
            "dimensions": dimensions,
            "packageDimensions": package_dimensions,
            "browserDimensions": browser_gate.get("dimensions"),
            "dimensionsMatch": text_contains(browser_gate.get("dimensions"), dimensions or package_dimensions),
            "priceTrendClass": trend,
            "browserPriceTrendClass": browser_trend,
            "priceTrendComparable": price_gate_ran,
            "priceTrendMatch": trend == browser_trend if price_gate_ran else None,
            "pricePointCount": len(price_samples),
            "browserTotalMs": int(number(baseline_row["browser"]["timing"].get("totalMs")) or 0),
            "browserDimensionsMs": int(number(baseline_row["browser"]["timing"].get("dimensionsMs")) or 0),
            "browserPriceChartMs": int(number(baseline_row["browser"]["timing"].get("priceChartMs")) or 0),
        }
        record["rankingScore"] = score_record(record)
        record["browserStepBypassAuthorized"] = False
        record["finalAuthority"] = False
        details.append(record)
    original = list(details)
    ranked = sorted(details, key=lambda row: (-row["rankingScore"], row["index"]))
    comparable_trends = [row for row in details if row["priceTrendComparable"]]
    matching_trends = [row for row in comparable_trends if row["priceTrendMatch"]]
    price_comparable = [row for row in details if row["priceMatch"] is not None]
    dimension_comparable = [row for row in details if row["dimensionsMatch"] is not None]
    theoretical_ms = sum(
        row["browserDimensionsMs"] + row["browserPriceChartMs"]
        for row in details
        if row["priceMatch"] is True and row["priceTrendMatch"] is True and row["dimensionsMatch"] is True
    )
    milestones = {}
    for target in (1, 5, 10, 12):
        old_cost = milestone_cost(original, target)
        new_cost = milestone_cost(ranked, target)
        milestones[str(target)] = {
            "originalMs": old_cost,
            "rankedMs": new_cost,
            "savedMs": (old_cost - new_cost) if old_cost is not None and new_cost is not None else None,
            "savedPct": round(100 * (old_cost - new_cost) / old_cost, 2) if old_cost and new_cost is not None else None,
        }
    return {
        "schemaVersion": "sellerSpriteMcpKeepaFullPairAnalysis/v1",
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "sampleSize": len(details),
        "exactAsinCount": sum(row["exactAsin"] for row in details),
        "mcpFinalAuthority": False,
        "gateCProvided": False,
        "fieldAgreement": {
            "price": {"comparable": len(price_comparable), "match": sum(row["priceMatch"] is True for row in price_comparable)},
            "rating": {"comparable": sum(row["ratingMatch"] is not None for row in details), "match": sum(row["ratingMatch"] is True for row in details)},
            "reviews": {"comparable": sum(row["reviewsMatch"] is not None for row in details), "match": sum(row["reviewsMatch"] is True for row in details)},
            "variations": {"comparable": sum(row["variationsMatch"] is not None for row in details), "match": sum(row["variationsMatch"] is True for row in details)},
            "dimensions": {"comparable": len(dimension_comparable), "match": sum(row["dimensionsMatch"] is True for row in dimension_comparable)},
            "priceTrend": {"comparable": len(comparable_trends), "match": len(matching_trends)},
        },
        "ranking": {
            "originalAsins": [row["asin"] for row in original],
            "rankedAsins": [row["asin"] for row in ranked],
            "passesInFirst10Original": sum(row["expectedOutcome"] == "pass" for row in original[:10]),
            "passesInFirst10Ranked": sum(row["expectedOutcome"] == "pass" for row in ranked[:10]),
            "milestoneCosts": milestones,
            "multisetUnchanged": sorted(row["asin"] for row in original) == sorted(row["asin"] for row in ranked),
        },
        "theoreticalOnly": {
            "matchingDimensionsPriceTrendRows": sum(row["priceMatch"] is True and row["priceTrendMatch"] is True and row["dimensionsMatch"] is True for row in details),
            "browserDimensionsAndPriceMs": theoretical_ms,
            "browserDimensionsAndPriceMinutes": round(theoretical_ms / 60000, 3),
            "authorizedToBypass": False,
        },
        "timing": {
            "browserTotalMs": sum(row["browserTotalMs"] for row in details),
            "browserMedianMs": statistics.median(row["browserTotalMs"] for row in details),
        },
        "details": details,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--raw-dir", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = build_report(json.loads(args.baseline.read_text(encoding="utf-8-sig")), args.raw_dir)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: result[key] for key in ("sampleSize", "exactAsinCount", "fieldAgreement", "ranking", "theoreticalOnly", "timing")}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
