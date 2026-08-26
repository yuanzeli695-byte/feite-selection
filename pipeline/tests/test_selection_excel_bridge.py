from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


BRIDGE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "selection_excel_bridge_legacy_runner_compat.py"
SPEC = importlib.util.spec_from_file_location("selection_excel_bridge_under_test", BRIDGE_PATH)
if SPEC is None or SPEC.loader is None:  # pragma: no cover - import setup guard
    raise RuntimeError(f"Cannot load bridge module from {BRIDGE_PATH}")
BRIDGE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = BRIDGE
SPEC.loader.exec_module(BRIDGE)


ASIN_1 = "B0AAAA0001"
ASIN_2 = "B0AAAA0002"
ASIN_3 = "B0AAAA0003"


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def option_value(command: list[str], name: str) -> str:
    return command[command.index(name) + 1]


class FakeCommandRunner:
    """Create only the offline artifacts each pipeline stage is expected to own."""

    def __init__(
        self,
        *,
        qualified_count: int,
        completed_target: bool,
        acceptance_returncode: int = 0,
    ) -> None:
        self.qualified_count = qualified_count
        self.completed_target = completed_target
        self.acceptance_returncode = acceptance_returncode
        self.stages: list[str] = []
        self.commands: list[list[str]] = []
        self.sandbox_roots: list[Path] = []

    def __call__(self, raw_command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        command = [str(value) for value in raw_command]
        self.commands.append(command)
        executable = Path(command[1]).name if len(command) > 1 else ""

        if executable == "replay_existing_batch.py":
            self.stages.append("replay")
            attempt_dir = Path(option_value(command, "--run-dir"))
            sandbox_root = Path(option_value(command, "--project-root"))
            self.sandbox_roots.append(sandbox_root)
            write_json(
                sandbox_root / "history" / "strict_qualified_asins.json",
                {"sandboxOnlyMutation": True},
            )
            write_json(
                attempt_dir / "run_summary.json",
                {
                    "completedTarget": self.completed_target,
                    "qualifiedCount": self.qualified_count,
                },
            )
            return subprocess.CompletedProcess(command, 0, "replay ok", "")

        if executable == "build_replay_workbooks.mjs":
            self.stages.append("workbook")
            attempt_dir = Path(command[-1])
            final_path = attempt_dir / "final_candidates_test.xlsx"
            audit_path = attempt_dir / "rejected_audit_test.xlsx"
            final_path.write_bytes(b"final workbook")
            audit_path.write_bytes(b"audit workbook")
            write_json(
                attempt_dir / "workbook_build_report.json",
                {"finalXlsx": str(final_path), "auditXlsx": str(audit_path)},
            )
            return subprocess.CompletedProcess(command, 0, "workbook ok", "")

        if executable == "acceptance_checker.py":
            self.stages.append("acceptance")
            attempt_dir = Path(command[-1])
            if self.acceptance_returncode == 0:
                (attempt_dir / "acceptance_report.md").write_text("PASS\n", encoding="utf-8")
                return subprocess.CompletedProcess(command, 0, "acceptance ok", "")
            return subprocess.CompletedProcess(
                command,
                self.acceptance_returncode,
                "acceptance rejected",
                "machine acceptance failed",
            )

        raise AssertionError(f"Unexpected command: {command}")


class SelectionExcelBridgeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.project_root = self.root / "project"
        self.image_dir = self.root / "images"
        self.project_root.mkdir()
        self.image_dir.mkdir()
        self.formal_history = self.project_root / "history" / "strict_qualified_asins.json"
        write_json(self.formal_history, {"formalHistory": ["B0ZZZZ0001"]})
        self.formal_history_bytes = self.formal_history.read_bytes()
        self.primary_candidates = self._candidate_file("primary.json", [ASIN_1, ASIN_2])
        self.bridge_sequence = 0

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _candidate_file(self, name: str, asins: list[str]) -> Path:
        path = self.root / "candidates" / name
        write_json(path, [{"asin": asin, "title": f"Candidate {asin}"} for asin in asins])
        return path

    def _make_bridge(
        self,
        *,
        candidates: list[Path] | None = None,
        command_runner: FakeCommandRunner | None = None,
        target: int = 2,
    ) -> BRIDGE.SelectionExcelBridge:
        self.bridge_sequence += 1
        config = BRIDGE.BridgeConfig(
            project_root=self.project_root,
            output_root=self.root / f"output_{self.bridge_sequence}",
            candidates_json=candidates or [self.primary_candidates],
            image_dir=self.image_dir,
            run_id="strict-ui-test",
            run_date="2026-07-17",
            target=target,
            token="test-token",
            runner_version="0.3.8.2",
            collector_version="0.4.6.2",
            command_timeout_seconds=30,
        )
        return BRIDGE.SelectionExcelBridge(
            config,
            command_runner=command_runner or self._unexpected_command_runner,
        )

    @staticmethod
    def _unexpected_command_runner(*_: object, **__: object) -> subprocess.CompletedProcess[str]:
        raise AssertionError("No external command should run in this test")

    def _valid_batch(self) -> dict[str, object]:
        results = []
        for asin in (ASIN_1, ASIN_2):
            results.append(
                {
                    "targetAsin": asin,
                    "collectorVersion": "0.4.6.2",
                    "telemetry": {
                        "gate": {
                            "runnerVersion": "0.3.8.2",
                            "collectorVersion": "0.4.6.2",
                        }
                    },
                }
            )
        return {
            "schemaVersion": "sellerSpriteIntegratedBatch/v0.3.0",
            "status": "done",
            "targetQualified": 2,
            "batchName": "ui-test-batch",
            "queueHash": "abc12345",
            "generatedAt": "2026-07-17T00:00:00Z",
            "queue": [ASIN_1, ASIN_2],
            "results": results,
        }

    def _envelope(self, batch: dict[str, object] | None = None) -> dict[str, object]:
        return {"schemaVersion": BRIDGE.REQUEST_SCHEMA, "batch": batch or self._valid_batch()}

    def test_validate_batch_accepts_well_formed_batch_and_rejects_bad_shape(self) -> None:
        bridge = self._make_bridge()
        identity = bridge.validate_batch(self._valid_batch())
        self.assertEqual(identity["batchName"], "ui-test-batch")
        self.assertEqual(identity["queueAsins"], [ASIN_1, ASIN_2])
        self.assertEqual(identity["resultAsins"], [ASIN_1, ASIN_2])

        bad_schema = self._valid_batch()
        bad_schema["schemaVersion"] = "sellerSpriteIntegratedBatch/v9"
        with self.assertRaisesRegex(BRIDGE.BridgeError, "不支持的 batch schema"):
            bridge.validate_batch(bad_schema)

        duplicate_queue = self._valid_batch()
        duplicate_queue["queue"] = [ASIN_1, ASIN_1]
        with self.assertRaisesRegex(BRIDGE.BridgeError, "queue 含无效或重复 ASIN"):
            bridge.validate_batch(duplicate_queue)

        result_outside_queue = self._valid_batch()
        result_outside_queue["results"][0]["targetAsin"] = ASIN_3  # type: ignore[index]
        with self.assertRaisesRegex(BRIDGE.BridgeError, "targetAsin 无效或不在 queue"):
            bridge.validate_batch(result_outside_queue)

    def test_validate_batch_rejects_runner_and_collector_version_drift(self) -> None:
        bridge = self._make_bridge()

        wrong_runner = self._valid_batch()
        wrong_runner["results"][0]["telemetry"]["gate"]["runnerVersion"] = "0.3.8"  # type: ignore[index]
        with self.assertRaisesRegex(BRIDGE.BridgeError, "Runner 版本不一致"):
            bridge.validate_batch(wrong_runner)

        wrong_collector = self._valid_batch()
        wrong_collector["results"][0]["collectorVersion"] = "0.4.7"  # type: ignore[index]
        with self.assertRaisesRegex(BRIDGE.BridgeError, "Collector 版本不一致"):
            bridge.validate_batch(wrong_collector)

        missing_runner = self._valid_batch()
        missing_runner["results"][0]["telemetry"]["gate"]["runnerVersion"] = ""  # type: ignore[index]
        with self.assertRaisesRegex(BRIDGE.BridgeError, "Runner 版本不一致: missing"):
            bridge.validate_batch(missing_runner)

        missing_collector = self._valid_batch()
        missing_collector["results"][0]["collectorVersion"] = ""  # type: ignore[index]
        missing_collector["results"][0]["telemetry"]["gate"]["collectorVersion"] = ""  # type: ignore[index]
        with self.assertRaisesRegex(BRIDGE.BridgeError, "Collector 版本不一致: missing"):
            bridge.validate_batch(missing_collector)

    def test_validate_batch_allows_missing_collector_only_for_exact_asin_mismatch_short_circuit(self) -> None:
        bridge = self._make_bridge()
        mismatch = self._valid_batch()
        row = mismatch["results"][0]  # type: ignore[index]
        row.update(  # type: ignore[union-attr]
            {
                "asinMismatch": True,
                "status": "error",
                "strictDecision": "reject",
                "rejectionStage": "asin",
                "rejectionRule": "asin_mismatch",
                "skippedSteps": ["traffic", "dimensions", "price"],
                "collectorVersion": "",
            }
        )
        row["telemetry"]["gate"]["collectorVersion"] = ""  # type: ignore[index]
        identity = bridge.validate_batch(mismatch)
        self.assertEqual(identity["resultAsins"], [ASIN_1, ASIN_2])

        wrong_collector = self._valid_batch()
        wrong_row = wrong_collector["results"][0]  # type: ignore[index]
        wrong_row.update(  # type: ignore[union-attr]
            {
                "asinMismatch": True,
                "status": "error",
                "strictDecision": "reject",
                "rejectionStage": "asin",
                "rejectionRule": "asin_mismatch",
                "skippedSteps": ["traffic", "dimensions", "price"],
                "collectorVersion": "0.4.7",
            }
        )
        wrong_row["telemetry"]["gate"]["collectorVersion"] = "0.4.7"  # type: ignore[index]
        with self.assertRaisesRegex(BRIDGE.BridgeError, "Collector 版本不一致"):
            bridge.validate_batch(wrong_collector)

    def test_validate_batch_rejects_non_done_and_target_mismatch(self) -> None:
        bridge = self._make_bridge()

        non_done = self._valid_batch()
        non_done["status"] = "paused"
        with self.assertRaisesRegex(BRIDGE.BridgeError, "状态为 done"):
            bridge.validate_batch(non_done)

        wrong_target = self._valid_batch()
        wrong_target["targetQualified"] = 1
        with self.assertRaisesRegex(BRIDGE.BridgeError, "与服务 target=2 不一致"):
            bridge.validate_batch(wrong_target)

    def test_candidate_json_must_be_the_unique_complete_queue_mapping(self) -> None:
        bridge = self._make_bridge()
        self.assertEqual(
            bridge._candidate_path_for([ASIN_1, ASIN_2]),
            self.primary_candidates.resolve(),
        )

        with self.assertRaises(BRIDGE.BridgeError) as missing:
            bridge._candidate_path_for([ASIN_3])
        self.assertEqual(missing.exception.stage, "candidate_mapping")
        self.assertIn("没有候选 JSON", str(missing.exception))

        overlap = self._candidate_file("overlap.json", [ASIN_1, ASIN_2, ASIN_3])
        ambiguous_bridge = self._make_bridge(candidates=[self.primary_candidates, overlap])
        with self.assertRaises(BRIDGE.BridgeError) as ambiguous:
            ambiguous_bridge._candidate_path_for([ASIN_1, ASIN_2])
        self.assertEqual(ambiguous.exception.stage, "candidate_mapping")
        self.assertEqual(len(ambiguous.exception.details), 2)

    def test_batch_and_candidate_evidence_are_immutable(self) -> None:
        bridge = self._make_bridge()
        batch = self._valid_batch()
        identity = bridge.validate_batch(batch)
        entry = bridge._persist_batch(batch, identity)
        candidate_evidence = Path(entry["candidatePath"])
        original_candidate_bytes = candidate_evidence.read_bytes()

        write_json(self.primary_candidates, [{"asin": ASIN_3, "title": "mutated source"}])
        self.assertEqual(candidate_evidence.read_bytes(), original_candidate_bytes)
        self.assertTrue(BRIDGE.is_within(candidate_evidence, bridge.evidence_dir))
        self.assertEqual(entry["candidateSourcePath"], str(self.primary_candidates.resolve()))

        changed_batch = self._valid_batch()
        changed_batch["results"][0]["note"] = "changed after evidence upload"  # type: ignore[index]
        with self.assertRaises(BRIDGE.BridgeError) as conflict:
            bridge._persist_batch(changed_batch, bridge.validate_batch(changed_batch))
        self.assertEqual(conflict.exception.status, 409)
        self.assertEqual(conflict.exception.stage, "evidence_conflict")

    def test_replay_uses_sandbox_history_without_writing_formal_history(self) -> None:
        fake = FakeCommandRunner(qualified_count=2, completed_target=True)
        bridge = self._make_bridge(command_runner=fake)

        with mock.patch.object(BRIDGE.shutil, "which", return_value="node"):
            result = bridge.export(self._envelope(), "test-token")

        self.assertEqual(self.formal_history.read_bytes(), self.formal_history_bytes)
        self.assertEqual(len(fake.sandbox_roots), 1)
        sandbox_root = fake.sandbox_roots[0].resolve()
        self.assertNotEqual(sandbox_root, self.project_root.resolve())
        self.assertTrue(BRIDGE.is_within(sandbox_root, bridge.attempts_dir))
        self.assertEqual(
            json.loads((sandbox_root / "history" / "strict_qualified_asins.json").read_text("utf-8")),
            {"sandboxOnlyMutation": True},
        )
        self.assertFalse(result["productionHistoryUpdated"])

    def test_target_incomplete_does_not_build_or_publish_workbooks(self) -> None:
        fake = FakeCommandRunner(qualified_count=1, completed_target=False)
        bridge = self._make_bridge(command_runner=fake)

        with self.assertRaises(BRIDGE.BridgeError) as raised:
            bridge.export(self._envelope(), "test-token")

        self.assertEqual(raised.exception.status, 409)
        self.assertEqual(raised.exception.stage, "target_incomplete")
        self.assertEqual(fake.stages, ["replay"])
        attempt_dir = bridge.attempts_dir / "attempt_001"
        result = json.loads((attempt_dir / "bridge_result.json").read_text("utf-8"))
        self.assertFalse(result["accepted"])
        self.assertEqual(result["qualifiedCount"], 1)
        self.assertEqual(list(attempt_dir.glob("*.xlsx")), [])
        with self.assertRaises(BRIDGE.BridgeError) as download:
            bridge.download_path("final", 1)
        self.assertEqual(download.exception.status, 403)

    def test_acceptance_failure_never_exposes_generated_workbook_for_download(self) -> None:
        fake = FakeCommandRunner(
            qualified_count=2,
            completed_target=True,
            acceptance_returncode=7,
        )
        bridge = self._make_bridge(command_runner=fake)

        with mock.patch.object(BRIDGE.shutil, "which", return_value="node"):
            with self.assertRaises(BRIDGE.BridgeError) as raised:
                bridge.export(self._envelope(), "test-token")

        self.assertEqual(raised.exception.status, 422)
        self.assertEqual(raised.exception.stage, "acceptance")
        self.assertEqual(fake.stages, ["replay", "workbook", "acceptance"])
        attempt_dir = bridge.attempts_dir / "attempt_001"
        self.assertTrue((attempt_dir / "final_candidates_test.xlsx").is_file())
        self.assertFalse((attempt_dir / "bridge_result.json").exists())
        with self.assertRaises(BRIDGE.BridgeError) as download:
            bridge.download_path("final", 1)
        self.assertEqual(download.exception.status, 404)

        with mock.patch.object(BRIDGE.shutil, "which", return_value="node"):
            with self.assertRaises(BRIDGE.BridgeError) as retry:
                bridge.export(self._envelope(), "test-token")
        self.assertEqual(retry.exception.stage, "acceptance", retry.exception.details)
        self.assertTrue((bridge.attempts_dir / "attempt_002").is_dir())

    def test_success_returns_and_allows_only_accepted_workbooks(self) -> None:
        fake = FakeCommandRunner(qualified_count=2, completed_target=True)
        bridge = self._make_bridge(command_runner=fake)

        with mock.patch.object(BRIDGE.shutil, "which", return_value="node"):
            result = bridge.export(self._envelope(), "test-token")

        self.assertTrue(result["accepted"])
        self.assertTrue(result["machineAcceptancePassed"])
        self.assertTrue(result["visualAcceptanceRequired"])
        self.assertEqual(result["qualifiedCount"], 2)
        self.assertEqual(fake.stages, ["replay", "workbook", "acceptance"])
        final_path = Path(result["finalWorkbook"])
        audit_path = Path(result["auditWorkbook"])
        self.assertTrue(final_path.is_file())
        self.assertTrue(audit_path.is_file())
        self.assertEqual(bridge.download_path("final", 1), final_path.resolve())
        self.assertEqual(bridge.download_path("audit", 1), audit_path.resolve())
        uploaded = result["uploadedBatch"]
        self.assertEqual(uploaded["candidateSourcePath"], str(self.primary_candidates.resolve()))
        self.assertTrue(BRIDGE.is_within(Path(uploaded["candidatePath"]), bridge.evidence_dir))

    def test_second_batch_replays_all_immutable_batches_together(self) -> None:
        candidates = self._candidate_file("three_candidates.json", [ASIN_1, ASIN_2, ASIN_3])
        fake = FakeCommandRunner(qualified_count=3, completed_target=True)
        bridge = self._make_bridge(
            candidates=[candidates],
            command_runner=fake,
            target=3,
        )

        first = self._valid_batch()
        first["targetQualified"] = 3
        first["batchName"] = "ui-test-batch-1"
        first["queueHash"] = "batch0001"
        bridge._persist_batch(first, bridge.validate_batch(first))

        second = self._valid_batch()
        second["targetQualified"] = 3
        second["batchName"] = "ui-test-batch-2"
        second["queueHash"] = "batch0002"
        second["queue"] = [ASIN_3]
        second["results"] = [
            {
                "targetAsin": ASIN_3,
                "collectorVersion": "0.4.6.2",
                "telemetry": {
                    "gate": {
                        "runnerVersion": "0.3.8.2",
                        "collectorVersion": "0.4.6.2",
                    }
                },
            }
        ]

        with mock.patch.object(BRIDGE.shutil, "which", return_value="node"):
            result = bridge.export(self._envelope(second), "test-token")

        self.assertTrue(result["accepted"])
        replay_command = fake.commands[0]
        self.assertEqual(replay_command.count("--batch-json"), 2)
        self.assertEqual(replay_command.count("--candidates-json"), 2)
        manifest = json.loads(bridge.manifest_path.read_text("utf-8"))
        self.assertEqual([entry["batchName"] for entry in manifest["batches"]], [
            "ui-test-batch-1",
            "ui-test-batch-2",
        ])


if __name__ == "__main__":
    unittest.main()
