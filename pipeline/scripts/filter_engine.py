from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any


@dataclass
class FilterResult:
    decision: str
    stage: str
    rule: str
    reason: str
    warnings: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)

    @property
    def pass_(self) -> bool:
        return self.decision == "pass"


def one_line(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def text_blob(product: dict[str, Any]) -> str:
    fields = [
        product.get("title"),
        product.get("brand"),
        product.get("categoryPath"),
        product.get("rawProduct"),
    ]
    return one_line(" ".join(str(v or "") for v in fields)).lower()


def keyword_hit(blob: str, keyword: str) -> bool:
    key = keyword.strip().lower()
    if not key:
        return False
    escaped = re.escape(key)
    return re.search(rf"(?<![a-z0-9]){escaped}(?![a-z0-9])", blob) is not None


def parse_date(value: Any) -> date | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    try:
        return datetime.fromisoformat(text[:10]).date()
    except ValueError:
        return None


def launch_age_days(product: dict[str, Any], run_date: date) -> int | None:
    if isinstance(product.get("launchAgeDays"), int):
        return int(product["launchAgeDays"])
    launch = parse_date(product.get("launchDate"))
    if not launch:
        return None
    return (run_date - launch).days


def get_number(product: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        value = product.get(key)
        if value is None or value == "":
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return None


def basic_prefilter(product: dict[str, Any], rules: dict[str, Any], run_date: date) -> FilterResult:
    asin = product.get("asin", "")
    price = get_number(product, "price")
    rating = get_number(product, "rating")
    reviews = get_number(product, "reviews")
    variations = get_number(product, "variationsCount", "variations")
    monthly_sales = get_number(product, "monthlySales", "childSales")
    age = launch_age_days(product, run_date)

    missing = []
    if price is None:
        missing.append("price")
    if rating is None:
        missing.append("rating")
    if age is None:
        missing.append("launchDate")
    if variations is None:
        missing.append("variations")
    if missing:
        return FilterResult("fail", "prefilter", "missing_fields", f"{asin} missing fields: {', '.join(missing)}")

    if price < float(rules["priceMinUsd"]) or price > float(rules["priceMaxUsd"]):
        return FilterResult("fail", "prefilter", "price_out_of_range", f"price {price:g} not in {rules['priceMinUsd']}-{rules['priceMaxUsd']}")
    if rating < float(rules["minRating"]):
        return FilterResult("fail", "prefilter", "rating_below_min", f"rating {rating:g} < {rules['minRating']}")
    if reviews is not None and reviews > float(rules["maxReviews"]) + float(rules.get("reviewsTolerance", 0)):
        return FilterResult("fail", "prefilter", "reviews_above_max", f"reviews {reviews:g} > max+tolerance")
    if age > int(rules["launchAgeMaxDays"]):
        return FilterResult("fail", "prefilter", "launch_age_above_max", f"launch age {age} days > {rules['launchAgeMaxDays']}")
    if variations > int(rules["variationsMax"]):
        return FilterResult("fail", "prefilter", "variations_above_max", f"variations {variations:g} > {rules['variationsMax']}")
    if monthly_sales is not None and monthly_sales > int(rules["monthlySalesHardMax"]):
        return FilterResult("fail", "prefilter", "monthly_sales_hard_max", f"monthly sales {monthly_sales:g} > {rules['monthlySalesHardMax']}")
    return FilterResult("pass", "prefilter", "prefilter_pass", "basic commercial fields pass")


def exclusion_check(product: dict[str, Any], exclusions: dict[str, Any]) -> FilterResult:
    blob = text_blob(product)
    for rule, keywords in exclusions.get("hardExclusions", {}).items():
        hits = [kw for kw in keywords if keyword_hit(blob, kw)]
        if hits:
            return FilterResult("fail", "exclusion", rule, f"hard exclusion keyword(s): {', '.join(hits[:5])}")

    warnings: list[str] = []
    tags: list[str] = []
    for rule, keywords in exclusions.get("reviewFlags", {}).items():
        hits = [kw for kw in keywords if keyword_hit(blob, kw)]
        if hits:
            warnings.append(f"{rule}: {', '.join(hits[:3])}")
            tags.append(rule)

    brand = str(product.get("brand") or "").strip().lower()
    if brand and brand in {str(x).lower() for x in exclusions.get("brandScrutiny", [])}:
        return FilterResult("review", "exclusion", "brand_scrutiny", f"brand requires manual scrutiny: {brand}")

    return FilterResult("pass", "exclusion", "exclusion_pass", "no hard exclusion hit", warnings=warnings, tags=tags)


def traffic_check(traffic: dict[str, Any], rules: dict[str, Any]) -> FilterResult:
    status = traffic.get("status")
    if status != "ok":
        rule = "traffic_timeout" if status == "timeout" else "traffic_error"
        detail = traffic.get("note") or status or "missing traffic result"
        return FilterResult("fail", "traffic", rule, str(detail))

    if traffic.get("asinMismatch") is True and rules.get("asinMismatchPolicy") == "review":
        actual = traffic.get("actualAsin") or ""
        return FilterResult("review", "hard_filter", "asin_mismatch_review", f"target ASIN redirected to {actual}")

    if rules.get("trafficGateMode") == "aggregate_weighted_share":
        details = traffic.get("trafficDetails") or traffic.get("details") or []
        aggregate_natural = 0.0
        aggregate_total = 0.0
        aggregate_weeks = 0
        for detail in list(details)[:4]:
            if not isinstance(detail, dict):
                continue
            natural = detail.get("naturalTraffic")
            total = detail.get("totalTraffic")
            if not isinstance(natural, (int, float)) or not isinstance(total, (int, float)):
                continue
            natural_value = float(natural)
            total_value = float(total)
            if total_value <= 0 or natural_value < 0 or natural_value > total_value:
                continue
            aggregate_natural += natural_value
            aggregate_total += total_value
            aggregate_weeks += 1

        required_weeks = int(rules["trafficWeeksReadMin"])
        if aggregate_weeks < required_weeks:
            return FilterResult(
                "review",
                "hard_filter",
                "traffic_weeks_insufficient",
                f"aggregateWeeksRead {aggregate_weeks} < {required_weeks}",
            )
        aggregate_pct = aggregate_natural / aggregate_total * 100
        reported_pct = traffic.get("aggregateNaturalSharePct")
        reported_weeks = traffic.get("aggregateWeeksRead")
        if not isinstance(reported_pct, (int, float)) or abs(float(reported_pct) - aggregate_pct) > 1e-6:
            return FilterResult(
                "fail",
                "hard_filter",
                "traffic_aggregate_evidence_mismatch",
                f"reported aggregateNaturalSharePct {reported_pct} != recomputed {aggregate_pct:.8f}",
            )
        if not isinstance(reported_weeks, (int, float)) or int(reported_weeks) != aggregate_weeks:
            return FilterResult(
                "fail",
                "hard_filter",
                "traffic_aggregate_evidence_mismatch",
                f"reported aggregateWeeksRead {reported_weeks} != recomputed {aggregate_weeks}",
            )
        threshold = float(rules["trafficAggregateNaturalMinPct"])
        if aggregate_pct < threshold:
            return FilterResult(
                "fail",
                "hard_filter",
                "traffic_aggregate_below_min",
                f"{aggregate_pct:.2f}% < {threshold:.2f}%",
            )
        return FilterResult(
            "pass",
            "hard_filter",
            "traffic_aggregate_pass",
            f"aggregate natural traffic {aggregate_natural:.2f}/{aggregate_total:.2f} = {aggregate_pct:.2f}%",
        )

    latest = traffic.get("latestNaturalSharePct")
    avg = traffic.get("recent4AvgNaturalSharePct")
    minv = traffic.get("recent4MinNaturalSharePct")
    checks = [
        ("traffic_latest_below_min", latest, float(rules["trafficNaturalMinPct"])),
        ("traffic_recent4_avg_below_min", avg, float(rules["trafficRecent4AvgMinPct"])),
        ("traffic_recent4_min_below_min", minv, float(rules["trafficRecent4MinMinPct"])),
    ]
    for rule, value, threshold in checks:
        if isinstance(value, (int, float)) and float(value) < threshold:
            return FilterResult("fail", "hard_filter", rule, f"{value:.2f}% < {threshold:.2f}%")

    weeks = int(traffic.get("weeksRead") or 0)
    if weeks < int(rules["trafficWeeksReadMin"]):
        return FilterResult("review", "hard_filter", "traffic_weeks_insufficient", f"weeksRead {weeks} < {rules['trafficWeeksReadMin']}")

    for rule, value, threshold in checks:
        if not isinstance(value, (int, float)):
            return FilterResult("fail", "hard_filter", "traffic_missing_metric", f"{rule} metric missing")
    return FilterResult("pass", "hard_filter", "traffic_pass", "traffic thresholds pass")


def commercial_recheck(product: dict[str, Any], rules: dict[str, Any], run_date: date) -> FilterResult:
    result = basic_prefilter(product, rules, run_date)
    if not result.pass_:
        result.stage = "hard_filter"
    return result


def enrichment_check(product: dict[str, Any], rules: dict[str, Any]) -> FilterResult:
    asin = product.get("asin", "")
    dimensions = one_line(product.get("dimensions"))
    price_trend = one_line(product.get("priceTrend"))
    price_trend_class = one_line(product.get("priceTrendClass")).lower()

    if rules.get("dimensionsRequired", False) and not dimensions:
        return FilterResult("fail", "enrichment", "dimensions_missing", f"{asin} dimensions missing")
    if rules.get("priceTrendRequired", False) and not price_trend:
        return FilterResult("fail", "enrichment", "price_trend_missing", f"{asin} price trend missing")
    if rules.get("priceTrendRequired", False) and not price_trend_class:
        return FilterResult("fail", "enrichment", "price_trend_class_missing", f"{asin} price trend class missing")

    allowed = {str(value).strip().lower() for value in rules.get("allowedPriceTrendClasses", ["stable", "rising"])}
    if price_trend_class and allowed and price_trend_class not in allowed:
        return FilterResult(
            "fail",
            "enrichment",
            "price_trend_not_allowed",
            f"price trend class {price_trend_class} not in {', '.join(sorted(allowed))}",
        )
    return FilterResult("pass", "enrichment", "enrichment_pass", "dimensions and price trend pass")


def evaluate_candidate(
    product: dict[str, Any],
    traffic: dict[str, Any],
    rules: dict[str, Any],
    exclusions: dict[str, Any],
    run_date: date,
) -> dict[str, Any]:
    warnings: list[str] = []
    tags: list[str] = []

    excl = exclusion_check(product, exclusions)
    warnings.extend(excl.warnings)
    tags.extend(excl.tags)
    if not excl.pass_:
        return as_decision(excl, warnings, tags)

    pre = basic_prefilter(product, rules, run_date)
    if not pre.pass_:
        return as_decision(pre, warnings, tags)

    traffic_result = traffic_check(traffic, rules)
    if not traffic_result.pass_:
        return as_decision(traffic_result, warnings, tags)

    commercial = commercial_recheck(product, rules, run_date)
    if not commercial.pass_:
        return as_decision(commercial, warnings, tags)

    enrichment = enrichment_check(product, rules)
    if not enrichment.pass_:
        return as_decision(enrichment, warnings, tags)

    return as_decision(FilterResult("pass", "hard_filter", "all_rules_pass", "all hard rules pass"), warnings, tags)


def as_decision(result: FilterResult, warnings: list[str], tags: list[str]) -> dict[str, Any]:
    return {
        "decision": result.decision,
        "stage": result.stage,
        "rule": result.rule,
        "reason": result.reason,
        "warnings": warnings + result.warnings,
        "tags": sorted(set(tags + result.tags)),
    }
