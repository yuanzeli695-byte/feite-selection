from __future__ import annotations

import copy
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "build_mcp_validation_pair_view.py"
PLAN_PATH = ROOT / "docs" / "mcp_hybrid_shadow_plan_20260729.json"
BASELINE_PATH = ROOT / "runs" / "mcp_shadow_20260729" / "browser_baseline.json"
CONTROLLED_PATH = (
    ROOT
    / "runs"
    / "mcp_hybrid_phase15_candidate"
    / "controlled_tests"
    / "CONTROLLED_MCP_RAW_RESPONSES.json"
)
SMOKE_PATH = ROOT / "runs" / "mcp_hybrid_phase15_candidate" / "BROWSER_SMOKE_20260729.json"
HASHES_PATH = ROOT / "runs" / "mcp_hybrid_phase15_candidate" / "ARTIFACT_HASHES.json"
OPTIONAL_EVIDENCE_FILES = (
    BASELINE_PATH,
    CONTROLLED_PATH,
    SMOKE_PATH,
    HASHES_PATH,
)


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


MOD = load_module("build_mcp_validation_pair_view_test", SCRIPT)


@unittest.skipUnless(
    all(path.is_file() for path in OPTIONAL_EVIDENCE_FILES),
    "optional historical MCP evidence is not included in the source package",
)
class PairViewBuilderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.plan = json.loads(PLAN_PATH.read_text(encoding="utf-8"))
        cls.baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
        controlled = json.loads(CONTROLLED_PATH.read_text(encoding="utf-8"))
        cls.payloads = {row["tool"]: row["payload"] for row in controlled["responses"]}

    def test_controlled_tool_payloads_normalize_with_strict_roles(self) -> None:
        asin = "B0GTQFW672"
        detail, detail_provenance, actual = MOD.normalize_detail(
            self.payloads["asin_detail"]["data"], asin
        )
        self.assertEqual(actual, asin)
        self.assertEqual(detail["price"], 12.99)
        self.assertEqual(detail_provenance["price"]["sourceTool"], "asin_detail")

        trend, trend_provenance, actual = MOD.normalize_sales_trend(
            self.payloads["asin_sales_trend"]["data"], asin
        )
        self.assertEqual(actual, asin)
        self.assertEqual(trend["priceTrendClass"], "rising")
        self.assertEqual(trend["pricePointCount"], 3)
        self.assertIn("existing_runner", trend_provenance["priceTrendClass"]["semantics"])

        traffic, traffic_provenance, actual = MOD.normalize_traffic(
            self.payloads["traffic_listing_stat"]["data"], asin
        )
        self.assertEqual(actual, asin)
        self.assertAlmostEqual(traffic["freeTrafficShare"], 659 / 676)
        self.assertTrue(
            all("not_gate_c" in row["semantics"] for row in traffic_provenance.values())
        )
        self.assertNotIn("weeksRead", traffic)

    def test_asin_and_raw_hash_mismatches_fail_closed(self) -> None:
        changed = copy.deepcopy(self.payloads["asin_detail"]["data"])
        changed["asin"] = "B0ZZZZ9999"
        with self.assertRaises(MOD.BuildError):
            MOD.normalize_detail(changed, "B0GTQFW672")

        with tempfile.TemporaryDirectory(dir=ROOT) as temp:
            path = Path(temp) / "artifact.json"
            path.write_text("{}", encoding="utf-8")
            with self.assertRaises(MOD.BuildError):
                MOD.verify_declared_artifact(
                    path,
                    {"sha256": "0" * 64, "bytes": path.stat().st_size},
                    "fixture",
                )

    def test_paired_outcomes_are_derived_from_exact_replay_union(self) -> None:
        ordered, baseline = MOD.validate_plan_and_baseline(
            self.plan,
            self.baseline,
            plan_hash=MOD.file_sha256(PLAN_PATH),
        )
        final_rows = []
        rejected_rows = []
        for asin in ordered:
            outcome = next(row["expectedOutcome"] for row in self.plan["sample"] if row["asin"] == asin)
            target = final_rows if outcome == "pass" else rejected_rows
            target.append({"asin": asin, "source": "browser replay fixture"})
        source_files = {"fixture": MOD.file_record(PLAN_PATH)}
        paired = MOD.derive_paired_outcomes(
            plan=self.plan,
            ordered_asins=ordered,
            baseline_by_asin=baseline,
            final_value=final_rows,
            rejected_value=rejected_rows,
            run_summary={
                "attempts": 30,
                "qualifiedCount": len(final_rows),
                "rejectedCount": len(rejected_rows),
            },
            source_files=source_files,
        )
        self.assertTrue(paired["derivedFromReplayArtifacts"])
        self.assertEqual(len(paired["rows"]), 30)
        self.assertEqual(
            {row["hybridOutcome"] for row in paired["rows"]}, {"pass", "reject"}
        )
        with self.assertRaises(MOD.BuildError):
            MOD.derive_paired_outcomes(
                plan=self.plan,
                ordered_asins=ordered,
                baseline_by_asin=baseline,
                final_value=final_rows[:-1],
                rejected_value=rejected_rows,
                run_summary={"attempts": 29, "qualifiedCount": len(final_rows) - 1, "rejectedCount": len(rejected_rows)},
                source_files=source_files,
            )

    def test_existing_smoke_is_verified_but_not_current_or_task_bound(self) -> None:
        smoke = json.loads(SMOKE_PATH.read_text(encoding="utf-8"))
        hashes = json.loads(HASHES_PATH.read_text(encoding="utf-8"))
        derived = MOD.derive_live_smoke(
            smoke=smoke,
            hashes=hashes,
            smoke_path=SMOKE_PATH,
            hashes_path=HASHES_PATH,
            sample_asins={row["asin"] for row in self.plan["sample"]},
            task={"taskId": "validation-current", "runId": "mcp-validate-task-current"},
            expected_bridge="0.3.2",
            expected_assist="0.3.0",
            expected_adapter="0.2.0",
            expected_collector="0.4.6",
            expected_runners={"0.3.7", "0.3.8.2"},
        )
        self.assertTrue(derived["evidenceHashVerified"])
        self.assertTrue(derived["screenshotHashVerified"])
        self.assertFalse(derived["taskBound"])
        self.assertFalse(derived["currentCombination"])
        self.assertFalse(derived["collectorEnabled"])


if __name__ == "__main__":
    unittest.main()
