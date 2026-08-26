from __future__ import annotations

import json
import sys
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from filter_engine import basic_prefilter, enrichment_check, evaluate_candidate, exclusion_check, traffic_check  # noqa: E402


RULES = json.loads((ROOT / "config" / "rules.json").read_text(encoding="utf-8"))
AGGREGATE_RULES = json.loads((ROOT / "config" / "rules_aggregate_natural_traffic.json").read_text(encoding="utf-8"))
EXCLUSIONS = json.loads((ROOT / "config" / "exclusions.json").read_text(encoding="utf-8"))
RUN_DATE = date.fromisoformat(RULES["runDate"])


def product(title: str, **overrides):
    base = {
        "asin": "B0TEST0000",
        "title": title,
        "brand": "",
        "price": 19.99,
        "rating": 5,
        "reviews": 5,
        "launchDate": "2026-06-01",
        "variationsCount": 1,
        "monthlySales": 300,
    }
    base.update(overrides)
    return base


def traffic(**overrides):
    base = {
        "status": "ok",
        "latestNaturalSharePct": 99.0,
        "recent4AvgNaturalSharePct": 90.0,
        "recent4MinNaturalSharePct": 80.0,
        "weeksRead": 4,
        "pass70": True,
        "asinMismatch": False,
    }
    base.update(overrides)
    return base


class FilterEngineTests(unittest.TestCase):
    def test_basic_prefilter_passes_good_candidate(self):
        result = basic_prefilter(product("Simple picture frame"), RULES, RUN_DATE)
        self.assertEqual(result.decision, "pass")

    def test_ip_keyword_hard_fails(self):
        result = exclusion_check(product("Super Mario Birthday Decorations Set"), EXCLUSIONS)
        self.assertEqual(result.decision, "fail")
        self.assertEqual(result.rule, "ip_character_risk")

    def test_health_chemical_keyword_hard_fails(self):
        result = exclusion_check(product("Oxyteeth Tooth Armor Drops with Nano Hydroxyapatite"), EXCLUSIONS)
        self.assertEqual(result.decision, "fail")
        self.assertEqual(result.rule, "health_medical_chemical")

    def test_hard_exclusion_runs_before_business_metrics(self):
        result = evaluate_candidate(
            product("Super Mario Birthday Decorations Set", price=1.0),
            traffic(),
            RULES,
            EXCLUSIONS,
            RUN_DATE,
        )
        self.assertEqual(result["decision"], "fail")
        self.assertEqual(result["stage"], "exclusion")
        self.assertEqual(result["rule"], "ip_character_risk")

    def test_floor_cleaning_tablets_hard_fail_before_traffic(self):
        result = exclusion_check(product("Floor Cleaning Tablets 100 Pcs Multiple Effect"), EXCLUSIONS)
        self.assertEqual(result.decision, "fail")
        self.assertEqual(result.rule, "chemical_consumable")

    def test_traffic_minimum_uses_strict_70_floor(self):
        result = traffic_check(traffic(recent4MinNaturalSharePct=68.55), RULES)
        self.assertEqual(result.decision, "fail")
        self.assertEqual(result.rule, "traffic_recent4_min_below_min")

    def test_known_traffic_failure_precedes_week_count_review(self):
        result = traffic_check(traffic(weeksRead=1, latestNaturalSharePct=65.0), RULES)
        self.assertEqual(result.decision, "fail")
        self.assertEqual(result.rule, "traffic_latest_below_min")

    def test_aggregate_traffic_passes_when_weighted_total_is_70_or_more(self):
        details = [
            {"week": "w3", "totalTraffic": 1000, "naturalTraffic": 800, "naturalSharePct": 80},
            {"week": "w2", "totalTraffic": 100, "naturalTraffic": 40, "naturalSharePct": 40},
            {"week": "w1", "totalTraffic": 100, "naturalTraffic": 100, "naturalSharePct": 100},
        ]
        result = traffic_check(
            traffic(
                weeksRead=3,
                aggregateNaturalTraffic=940,
                aggregateTotalTraffic=1200,
                aggregateNaturalSharePct=940 / 1200 * 100,
                aggregateWeeksRead=3,
                trafficDetails=details,
            ),
            AGGREGATE_RULES,
        )
        self.assertEqual(result.decision, "pass")
        self.assertEqual(result.rule, "traffic_aggregate_pass")

    def test_aggregate_traffic_rejects_when_weighted_total_is_below_70(self):
        details = [
            {"week": "w3", "totalTraffic": 100, "naturalTraffic": 80},
            {"week": "w2", "totalTraffic": 100, "naturalTraffic": 50},
            {"week": "w1", "totalTraffic": 100, "naturalTraffic": 60},
        ]
        result = traffic_check(
            traffic(
                weeksRead=3,
                aggregateNaturalTraffic=190,
                aggregateTotalTraffic=300,
                aggregateNaturalSharePct=190 / 300 * 100,
                aggregateWeeksRead=3,
                trafficDetails=details,
            ),
            AGGREGATE_RULES,
        )
        self.assertEqual(result.decision, "fail")
        self.assertEqual(result.rule, "traffic_aggregate_below_min")

    def test_aggregate_traffic_fails_closed_on_reported_value_mismatch(self):
        details = [
            {"week": "w3", "totalTraffic": 100, "naturalTraffic": 80},
            {"week": "w2", "totalTraffic": 100, "naturalTraffic": 80},
            {"week": "w1", "totalTraffic": 100, "naturalTraffic": 80},
        ]
        result = traffic_check(
            traffic(
                weeksRead=3,
                aggregateNaturalSharePct=90,
                aggregateWeeksRead=3,
                trafficDetails=details,
            ),
            AGGREGATE_RULES,
        )
        self.assertEqual(result.decision, "fail")
        self.assertEqual(result.rule, "traffic_aggregate_evidence_mismatch")

    def test_compatibility_brand_is_warning_not_hard_fail(self):
        result = exclusion_check(product("Replacement Filter Compatible with Craftsman Wet Dry Vac"), EXCLUSIONS)
        self.assertEqual(result.decision, "pass")
        self.assertIn("compatibility_brand_review", result.tags)

    def test_brand_scrutiny_requires_review(self):
        result = exclusion_check(product("Simple phone stand", brand="Apple"), EXCLUSIONS)
        self.assertEqual(result.decision, "review")
        self.assertEqual(result.rule, "brand_scrutiny")

    def test_enrichment_rejects_missing_dimensions(self):
        result = enrichment_check(product("Simple frame", priceTrend="近30天稳定", priceTrendClass="stable"), RULES)
        self.assertEqual(result.decision, "fail")
        self.assertEqual(result.rule, "dimensions_missing")

    def test_enrichment_rejects_declining_price(self):
        result = enrichment_check(
            product("Simple frame", dimensions="商品尺寸 10 x 8 inches", priceTrend="近30天下降", priceTrendClass="declining"),
            RULES,
        )
        self.assertEqual(result.decision, "fail")
        self.assertEqual(result.rule, "price_trend_not_allowed")

    def test_enrichment_accepts_stable_price(self):
        result = enrichment_check(
            product("Simple frame", dimensions="商品尺寸 10 x 8 inches", priceTrend="近30天稳定", priceTrendClass="stable"),
            RULES,
        )
        self.assertEqual(result.decision, "pass")


if __name__ == "__main__":
    unittest.main()
