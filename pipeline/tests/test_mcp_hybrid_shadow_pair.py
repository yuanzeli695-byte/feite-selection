from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "mcp_hybrid_shadow_pair.py"
SPEC = importlib.util.spec_from_file_location("mcp_hybrid_shadow_pair_test", SCRIPT)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("cannot load shadow pair script")
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)


class ShadowPairTests(unittest.TestCase):
    def test_plan_has_thirty_unique_asins_and_eight_calls(self) -> None:
        plan = json.loads((ROOT / "docs" / "mcp_hybrid_shadow_plan_20260729.json").read_text(encoding="utf-8"))
        self.assertEqual(len(plan["sample"]), 30)
        self.assertEqual(len({row["asin"] for row in plan["sample"]}), 30)
        self.assertEqual(sum(item["calls"] for item in plan["requests"]), 8)

    def test_compare_value_is_fail_closed_for_missing(self) -> None:
        self.assertEqual(MOD.compare_value("", 1), "missing")
        self.assertEqual(MOD.compare_value(1, 1.005), "match")
        self.assertEqual(MOD.compare_value(1, 2), "mismatch")

    def test_analyze_preserves_non_authority_and_agreement(self) -> None:
        baseline = {"rows": [{"asin": "B0AAAA0001", "expectedOutcome": "pass", "browser": {"gate": {"outcome": "pass"}}, "productSnapshot": {"rating": 5, "reviews": 2, "variationsCount": 1}}]}
        evidence = [{"asin": "B0AAAA0001", "price": 9.99, "rating": 5, "reviews": 2, "variations": 1}]
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            baseline_path = root / "baseline.json"
            evidence_path = root / "evidence.json"
            output_path = root / "analysis.json"
            baseline_path.write_text(json.dumps(baseline), encoding="utf-8")
            evidence_path.write_text(json.dumps(evidence), encoding="utf-8")
            result = MOD.analyze(baseline_path, evidence_path, output_path)
            self.assertEqual(result["finalGateAgreementPct"], 100.0)
            self.assertFalse(result["mcpFinalAuthority"])


if __name__ == "__main__":
    unittest.main()
