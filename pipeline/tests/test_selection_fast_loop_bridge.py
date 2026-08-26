from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
BRIDGE_PATH = ROOT / "scripts" / "selection_fast_loop_bridge.py"
SPEC = importlib.util.spec_from_file_location("selection_fast_loop_bridge_under_test", BRIDGE_PATH)
if SPEC is None or SPEC.loader is None:  # pragma: no cover
    raise RuntimeError(f"Cannot load {BRIDGE_PATH}")
BRIDGE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = BRIDGE
SPEC.loader.exec_module(BRIDGE)


ASIN_1 = "B0AAAA0001"
ASIN_2 = "B0AAAA0002"
ASIN_3 = "B0AAAA0003"


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def option(command: list[str], name: str) -> str:
    return command[command.index(name) + 1]


class FakeReplay:
    def __init__(self) -> None:
        self.qualified_count = 0
        self.commands: list[list[str]] = []

    def __call__(self, raw_command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        command = [str(value) for value in raw_command]
        self.commands.append(command)
        executable = Path(command[1]).name
        if executable == "replay_existing_batch.py":
            if "--runner-current-price-v1" not in command:
                raise AssertionError("checkpoint replay must use Runner current price authority")
            run_dir = Path(option(command, "--run-dir"))
            attempted = 0
            for index, value in enumerate(command):
                if value == "--batch-json":
                    attempted += len(json.loads(Path(command[index + 1]).read_text(encoding="utf-8"))["results"])
            write_json(
                run_dir / "run_summary.json",
                {
                    "completedTarget": self.qualified_count == int(option(command, "--target")),
                    "qualifiedCount": self.qualified_count,
                    "attempts": attempted,
                },
            )
            return subprocess.CompletedProcess(command, 0, "ok", "")
        if executable == "build_replay_workbooks.mjs":
            run_dir = Path(command[-1])
            final_path = run_dir / "final_candidates_fast_loop.xlsx"
            audit_path = run_dir / "rejected_audit_fast_loop.xlsx"
            final_path.write_bytes(b"final")
            audit_path.write_bytes(b"audit")
            write_json(run_dir / "workbook_build_report.json", {"finalXlsx": str(final_path), "auditXlsx": str(audit_path)})
            return subprocess.CompletedProcess(command, 0, "ok", "")
        if executable == "acceptance_checker.py":
            (Path(command[-1]) / "acceptance_report.md").write_text("PASS\n", encoding="utf-8")
            return subprocess.CompletedProcess(command, 0, "ok", "")
        raise AssertionError(f"Unexpected command: {command}")


class FastLoopBridgeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.project = self.root / "project"
        self.images = self.root / "images"
        self.project.mkdir()
        self.images.mkdir()
        write_json(self.project / "history" / "strict_qualified_asins.json", {"schemaVersion": "strictQualifiedHistory/v1", "asins": {}})
        self.candidates = self.root / "candidates.json"
        write_json(self.candidates, [{"asin": asin, "title": asin} for asin in (ASIN_1, ASIN_2, ASIN_3)])
        self.fake = FakeReplay()
        config = BRIDGE.BridgeConfig(
            project_root=self.project,
            output_root=self.root / "output",
            candidates_json=[self.candidates],
            image_dir=self.images,
            run_id="fast-loop-test",
            run_date="2026-07-31",
            target=2,
            token="test-token",
            runner_version="0.3.10",
            collector_version="0.4.6.2",
            command_timeout_seconds=30,
        )
        self.bridge = BRIDGE.FastLoopBridge(config, command_runner=self.fake)

    def tearDown(self) -> None:
        self.temp.cleanup()

    @staticmethod
    def result(asin: str, *, rule: str = "traffic_error") -> dict[str, object]:
        return {
            "targetAsin": asin,
            "collectorVersion": "0.4.6.2",
            "strictDecision": "reject",
            "rejectionStage": "traffic",
            "rejectionRule": rule,
            "telemetry": {"gate": {"runnerVersion": "0.3.10", "collectorVersion": "0.4.6.2"}},
        }

    @staticmethod
    def batch(queue: list[str], results: list[dict[str, object]], *, name: str = "batch-a", generated: str = "2026-07-31T00:00:00Z") -> dict[str, object]:
        return {
            "schemaVersion": "sellerSpriteIntegratedBatch/v0.3.0",
            "runnerVersion": "0.3.10",
            "fastLoopControlVersion": "fast-loop-control-v1",
            "status": "running",
            "targetQualified": 2,
            "batchName": name,
            "queueHash": name,
            "generatedAt": generated,
            "queue": queue,
            "results": results,
        }

    @staticmethod
    def envelope(batch: dict[str, object]) -> dict[str, object]:
        return {"schemaVersion": BRIDGE.CHECKPOINT_REQUEST_SCHEMA, "batch": batch}

    def test_zero_row_preflight_and_incremental_count(self) -> None:
        batch = self.batch([ASIN_1, ASIN_2], [])
        response = self.bridge.checkpoint(self.envelope(batch), "test-token")
        self.assertEqual(response["qualifiedCount"], 0)
        self.assertEqual(response["remainingTarget"], 2)
        self.assertFalse(response["targetReached"])
        self.assertEqual(self.fake.commands, [])

        batch["results"] = [self.result(ASIN_1)]
        self.fake.qualified_count = 1
        response = self.bridge.checkpoint(self.envelope(batch), "test-token")
        self.assertEqual(response["qualifiedCount"], 1)
        self.assertEqual(response["remainingTarget"], 1)
        self.assertEqual(response["attemptedCount"], 1)
        self.assertIn("--runner-current-price-v1", self.fake.commands[-1])

        batch["status"] = "paused"
        resumed = self.bridge.checkpoint(self.envelope(batch), "test-token")
        self.assertEqual(resumed["qualifiedCount"], 1)
        manifest = BRIDGE.read_json(self.bridge.manifest_path)
        self.assertEqual(len(manifest["checkpointBatches"][0]["checkpoints"]), 3)

    def test_saved_result_mutation_and_result_order_fail_closed(self) -> None:
        batch = self.batch([ASIN_1, ASIN_2], [self.result(ASIN_1)])
        self.bridge.checkpoint(self.envelope(batch), "test-token")
        batch["results"][0]["rejectionRule"] = "changed"  # type: ignore[index]
        with self.assertRaisesRegex(BRIDGE.BridgeError, "已保存结果发生变化"):
            self.bridge.checkpoint(self.envelope(batch), "test-token")

        out_of_order = self.batch([ASIN_1, ASIN_2], [self.result(ASIN_2)], name="batch-order")
        with self.assertRaisesRegex(BRIDGE.BridgeError, "queue 前缀顺序"):
            self.bridge.validate_checkpoint(out_of_order)

    def test_new_batch_rejects_previously_attempted_asin(self) -> None:
        first = self.batch([ASIN_1, ASIN_2], [self.result(ASIN_1)])
        self.bridge.checkpoint(self.envelope(first), "test-token")
        second = self.batch([ASIN_1, ASIN_3], [], name="batch-b", generated="2026-07-31T01:00:00Z")
        with self.assertRaisesRegex(BRIDGE.BridgeError, "已经完成浏览器采集"):
            self.bridge.checkpoint(self.envelope(second), "test-token")

    def test_auth_schema_version_and_target_are_strict(self) -> None:
        batch = self.batch([ASIN_1], [])
        with self.assertRaisesRegex(BRIDGE.BridgeError, "令牌无效"):
            self.bridge.checkpoint(self.envelope(batch), "wrong")
        with self.assertRaisesRegex(BRIDGE.BridgeError, "schema"):
            self.bridge.checkpoint({"schemaVersion": "wrong", "batch": batch}, "test-token")
        batch["runnerVersion"] = "0.3.8.2"
        with self.assertRaisesRegex(BRIDGE.BridgeError, "Runner 顶层版本"):
            self.bridge.validate_checkpoint(batch)
        batch["runnerVersion"] = "0.3.10"
        batch["targetQualified"] = 3
        with self.assertRaisesRegex(BRIDGE.BridgeError, "targetQualified"):
            self.bridge.validate_checkpoint(batch)

    def test_target_checkpoint_and_final_export_use_incremental_evidence(self) -> None:
        batch = self.batch([ASIN_1, ASIN_2], [self.result(ASIN_1), self.result(ASIN_2)])
        self.fake.qualified_count = 2
        checkpoint = self.bridge.checkpoint(self.envelope(batch), "test-token")
        self.assertTrue(checkpoint["targetReached"])
        self.assertEqual(checkpoint["remainingTarget"], 0)

        batch["status"] = "done"
        result = self.bridge.export(
            {"schemaVersion": "sellerSpriteExcelBridgeRequest/v1", "batch": batch},
            "test-token",
        )
        self.assertTrue(result["accepted"])
        self.assertTrue(result["machineAcceptancePassed"])
        self.assertTrue(Path(result["finalWorkbook"]).is_file())
        final_replay = [command for command in self.fake.commands if Path(command[1]).name == "replay_existing_batch.py"][-1]
        self.assertIn("--runner-current-price-v1", final_replay)


if __name__ == "__main__":
    unittest.main()
