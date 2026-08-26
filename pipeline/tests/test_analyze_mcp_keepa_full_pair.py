from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "analyze_mcp_keepa_full_pair.py"
SPEC = importlib.util.spec_from_file_location("analyze_mcp_keepa_full_pair_test", SCRIPT)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("cannot load full pair analyzer")
MOD = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MOD
SPEC.loader.exec_module(MOD)


class FullKeepaPairTests(unittest.TestCase):
    def test_runner_price_classifier_contract(self) -> None:
        stable = [{"date": f"2026-07-{day:02d}", "price": 19.99} for day in range(1, 6)]
        declining = [
            {"date": "2026-07-01", "price": 24.99},
            {"date": "2026-07-02", "price": 24.99},
            {"date": "2026-07-03", "price": 16.99},
            {"date": "2026-07-04", "price": 16.99},
        ]
        volatile = [
            {"date": "2026-07-01", "price": 10},
            {"date": "2026-07-02", "price": 20},
            {"date": "2026-07-03", "price": 10},
            {"date": "2026-07-04", "price": 20},
        ]
        self.assertEqual(MOD.classify_price_samples(stable), "stable")
        self.assertEqual(MOD.classify_price_samples(declining), "declining")
        self.assertEqual(MOD.classify_price_samples(volatile), "volatile")

    def test_ranking_is_reorder_only(self) -> None:
        rows = [
            {"asin": "A", "rankingScore": 1, "index": 0},
            {"asin": "B", "rankingScore": 3, "index": 1},
            {"asin": "C", "rankingScore": 3, "index": 2},
        ]
        ranked = sorted(rows, key=lambda row: (-row["rankingScore"], row["index"]))
        self.assertEqual([row["asin"] for row in ranked], ["B", "C", "A"])
        self.assertEqual(sorted(row["asin"] for row in rows), sorted(row["asin"] for row in ranked))


if __name__ == "__main__":
    unittest.main()
