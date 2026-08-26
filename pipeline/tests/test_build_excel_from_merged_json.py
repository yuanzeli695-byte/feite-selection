from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "build_excel_from_merged_json.py"
SPEC = importlib.util.spec_from_file_location("build_excel_from_merged_json_under_test", SCRIPT_PATH)
if SPEC is None or SPEC.loader is None:  # pragma: no cover
    raise RuntimeError(f"Cannot load module from {SCRIPT_PATH}")
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


ASIN_1 = "B0AAAA0001"
ASIN_2 = "B0AAAA0002"
ASIN_3 = "B0AAAA0003"


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def candidate_row(asin: str) -> dict[str, object]:
    return {
        "asin": asin,
        "title": f"Candidate {asin}",
        "categoryPath": "Office Products:Office Supplies",
        "image": f"https://example.com/{asin}.jpg",
        "launchDate": "2026-07-01",
        "sourcePage": "Office Products test source",
        "price": 19.99,
        "rating": 4.8,
        "variations": 2,
    }


def batch_payload(*, status: str = "done", asins: tuple[str, ...] = (ASIN_1,)) -> dict[str, object]:
    return {
        "schemaVersion": MODULE.BATCH_SCHEMA,
        "batchName": "test-batch",
        "queueHash": "abc12345",
        "generatedAt": "2026-07-31T00:00:00Z",
        "status": status,
        "queue": list(asins),
        "results": [
            {
                "targetAsin": asin,
                "actualAsin": asin,
                "status": "ok",
                "decision": "pass",
                "qualified": True,
                "strictDecision": "pass",
                "collectorVersion": "0.4.6.2",
                "telemetry": {"gate": {"runnerVersion": "0.3.8.5"}},
            }
            for asin in asins
        ],
    }


class BuildExcelFromMergedJsonTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _batch_file(self, payload: dict[str, object], name: str = "batch.json") -> Path:
        path = self.root / name
        write_json(path, payload)
        return path

    def _validate(self, path: Path, *, allow_running: bool = False) -> MODULE.BatchEvidence:
        return MODULE.validate_batch(
            path,
            allowed_runner_versions={"0.3.8.5"},
            allowed_collector_versions={"0.4.6.2"},
            allow_running_snapshot=allow_running,
        )

    def test_running_snapshot_and_versions_are_explicitly_gated(self) -> None:
        path = self._batch_file(batch_payload(status="running"))
        with self.assertRaisesRegex(MODULE.AutomationError, "allow-running-snapshot"):
            self._validate(path)

        evidence = self._validate(path, allow_running=True)
        self.assertEqual(evidence.strict_pass_asins, (ASIN_1,))
        self.assertEqual(evidence.runner_versions, frozenset({"0.3.8.5"}))

        payload = batch_payload()
        payload["results"][0]["telemetry"]["gate"]["runnerVersion"] = "0.3.9"  # type: ignore[index]
        path = self._batch_file(payload, "wrong-runner.json")
        with self.assertRaisesRegex(MODULE.AutomationError, "not explicitly allowed"):
            self._validate(path)

    def test_strict_pass_requires_consistent_decision_asin_and_collector(self) -> None:
        payload = batch_payload()
        payload["results"][0]["collectorVersion"] = ""  # type: ignore[index]
        path = self._batch_file(payload, "missing-collector.json")
        with self.assertRaisesRegex(MODULE.AutomationError, "missing Collector version"):
            self._validate(path)

        payload = batch_payload()
        payload["results"][0]["actualAsin"] = ASIN_2  # type: ignore[index]
        path = self._batch_file(payload, "asin-mismatch.json")
        with self.assertRaisesRegex(MODULE.AutomationError, "ASIN mismatch"):
            self._validate(path)

        payload = batch_payload()
        payload["results"][0]["qualified"] = False  # type: ignore[index]
        path = self._batch_file(payload, "inconsistent.json")
        with self.assertRaisesRegex(MODULE.AutomationError, "inconsistent"):
            self._validate(path)

    def test_candidate_discovery_ignores_lookalikes_and_selects_smallest_superset(self) -> None:
        search_root = self.root / "runs"
        write_json(search_root / "enrichment.json", [{"asin": ASIN_1, "dimensions": "1 x 1 x 1"}])
        write_json(search_root / "image_report.json", [{"asin": ASIN_1, "status": "ok", "path": "x.png"}])
        exact = search_root / "exact.json"
        larger = search_root / "larger.json"
        write_json(exact, [candidate_row(ASIN_1), candidate_row(ASIN_2)])
        write_json(larger, [candidate_row(ASIN_1), candidate_row(ASIN_2), candidate_row(ASIN_3)])

        batch = self._validate(self._batch_file(batch_payload(asins=(ASIN_1, ASIN_2))))
        sources = MODULE.discover_candidate_sources([search_root])
        self.assertEqual({source.path.name for source in sources}, {"exact.json", "larger.json"})
        self.assertEqual(MODULE.match_candidate_source(batch, sources).path, exact.resolve())

    def test_candidate_mapping_fails_on_equal_smallest_supersets(self) -> None:
        search_root = self.root / "runs"
        write_json(search_root / "one.json", [candidate_row(ASIN_1), candidate_row(ASIN_2)])
        write_json(search_root / "two.json", [candidate_row(ASIN_1), candidate_row(ASIN_3)])
        batch = self._validate(self._batch_file(batch_payload()))
        sources = MODULE.discover_candidate_sources([search_root])
        with self.assertRaisesRegex(MODULE.AutomationError, "Ambiguous"):
            MODULE.match_candidate_source(batch, sources)

    def test_strict_pass_target_is_unique_across_batches(self) -> None:
        first = self._validate(self._batch_file(batch_payload(asins=(ASIN_1, ASIN_2)), "one.json"))
        second = self._validate(self._batch_file(batch_payload(asins=(ASIN_2, ASIN_3)), "two.json"))
        self.assertEqual(MODULE.collect_strict_pass_asins([first, second]), [ASIN_1, ASIN_2, ASIN_3])

    def test_chinese_titles_are_required_for_every_strict_pass(self) -> None:
        path = self.root / "titles.json"
        write_json(path, {ASIN_1: "中文标题", ASIN_2: "English only"})
        with self.assertRaises(MODULE.AutomationError) as caught:
            MODULE.validate_title_overrides(path, [ASIN_1, ASIN_2])
        self.assertEqual(caught.exception.details, [ASIN_2])

    def test_command_runner_applies_versioned_environment_flag(self) -> None:
        completed = subprocess.CompletedProcess(["tool"], 0, "ok", "")
        with mock.patch.object(MODULE.subprocess, "run", return_value=completed) as runner:
            MODULE._run_command(
                ["tool"],
                project_root=self.root,
                stage="test",
                timeout_seconds=5,
                env_overrides={"SELLERSPRITE_WORKBOOK_FORCE_EXIT_V1": "1"},
            )
        self.assertEqual(
            runner.call_args.kwargs["env"]["SELLERSPRITE_WORKBOOK_FORCE_EXIT_V1"],
            "1",
        )


if __name__ == "__main__":
    unittest.main()
