from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "build_mcp_keepa_completion_plan.py"
SPEC = importlib.util.spec_from_file_location("build_mcp_keepa_completion_plan_test", SCRIPT)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("cannot load completion plan builder")
MOD = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MOD
SPEC.loader.exec_module(MOD)


class KeepaCompletionPlanTests(unittest.TestCase):
    def test_builds_exact_twenty_five_without_exceeding_fifty(self) -> None:
        asins = [f"B0{i:08d}" for i in range(30)]
        baseline = {"rows": [{"asin": asin} for asin in asins]}
        normalized = {"records": [{"asin": asin} for asin in asins[:5]]}
        result = MOD.build(baseline, normalized, prior_calls=8, hard_ceiling=50)
        self.assertEqual(len(result["requests"]), 25)
        self.assertEqual(result["taskCallBudget"]["maximumAfterPlan"], 33)
        self.assertEqual({row["request"]["asin"] for row in result["requests"]}, set(asins[5:]))

    def test_hard_ceiling_fails_closed(self) -> None:
        asins = [f"B0{i:08d}" for i in range(30)]
        baseline = {"rows": [{"asin": asin} for asin in asins]}
        normalized = {"records": [{"asin": asin} for asin in asins[:5]]}
        with self.assertRaises(ValueError):
            MOD.build(baseline, normalized, prior_calls=30, hard_ceiling=50)


if __name__ == "__main__":
    unittest.main()
