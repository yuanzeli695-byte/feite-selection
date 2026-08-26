#!/usr/bin/env python3
"""Loopback bridge for incremental strict replay and accepted workbook delivery."""

from __future__ import annotations

import argparse
import json
import re
import secrets
import shutil
import sys
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from selection_excel_bridge_legacy_runner_compat import (
    MAX_REQUEST_BYTES,
    RESPONSE_SCHEMA,
    RESULT_SCHEMA,
    BridgeConfig,
    BridgeError,
    BridgeHandler,
    BridgeHttpServer,
    SelectionExcelBridge,
    file_sha256,
    is_within,
    json_sha256,
    normalize_asin,
    now_iso,
    read_json,
    write_json,
)


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_PROJECT_ROOT = SCRIPT_DIR.parent
CHECKPOINT_REQUEST_SCHEMA = "sellerSpriteFastLoopCheckpointRequest/v1"
CHECKPOINT_RESPONSE_SCHEMA = "sellerSpriteFastLoopCheckpointResponse/v1"
FAST_MANIFEST_SCHEMA = "sellerSpriteFastLoopBridgeManifest/v1"
FAST_CONTROL_VERSION = "fast-loop-control-v1"


class FastLoopBridge(SelectionExcelBridge):
    def __init__(self, config: BridgeConfig, **kwargs: Any) -> None:
        super().__init__(config, **kwargs)
        self.checkpoint_dir = self.bridge_root / "checkpoints"
        self.checkpoint_replay_dir = self.bridge_root / "checkpoint_replay"
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)

    def _load_manifest(self) -> dict[str, Any]:
        if self.manifest_path.exists():
            payload = read_json(self.manifest_path)
            if payload.get("schemaVersion") != FAST_MANIFEST_SCHEMA:
                raise BridgeError("已有 fast-loop manifest 版本不兼容", stage="manifest")
            if payload.get("runId") != self.config.run_id or int(payload.get("target") or 0) != self.config.target:
                raise BridgeError("已有 fast-loop manifest 与本次 runId/target 不一致", stage="manifest")
            return payload
        return {
            "schemaVersion": FAST_MANIFEST_SCHEMA,
            "runId": self.config.run_id,
            "runDate": self.config.run_date,
            "target": self.config.target,
            "expectedRunnerVersion": self.config.runner_version,
            "expectedCollectorVersion": self.config.collector_version,
            "fastLoopControlVersion": FAST_CONTROL_VERSION,
            "productionHistoryWriteProtected": True,
            "createdAt": now_iso(),
            "updatedAt": now_iso(),
            "checkpointBatches": [],
            "batches": [],
            "attempts": [],
        }

    def validate_checkpoint(self, batch: Any) -> dict[str, Any]:
        if not isinstance(batch, dict):
            raise BridgeError("checkpoint batch 必须是 JSON 对象")
        if batch.get("schemaVersion") != "sellerSpriteIntegratedBatch/v0.3.0":
            raise BridgeError(f"不支持的 batch schema: {batch.get('schemaVersion')}")
        if batch.get("status") not in {"idle", "running", "paused", "done"}:
            raise BridgeError("checkpoint batch 状态无效")
        if str(batch.get("runnerVersion") or "") != self.config.runner_version:
            raise BridgeError("checkpoint Runner 顶层版本不一致")
        if str(batch.get("fastLoopControlVersion") or "") != FAST_CONTROL_VERSION:
            raise BridgeError("checkpoint 快速闭环控制版本不一致")
        if int(batch.get("targetQualified") or 0) != self.config.target:
            raise BridgeError("checkpoint targetQualified 与服务 target 不一致")

        batch_name = str(batch.get("batchName") or "").strip()
        queue_hash = str(batch.get("queueHash") or "").strip()
        generated_at = str(batch.get("generatedAt") or batch.get("createdAt") or "").strip()
        queue = batch.get("queue")
        results = batch.get("results")
        if not batch_name or not queue_hash or not generated_at:
            raise BridgeError("checkpoint batchName、queueHash、generatedAt 不能为空")
        if not isinstance(queue, list) or not queue:
            raise BridgeError("checkpoint queue 不能为空")
        queue_asins = [normalize_asin(value) for value in queue]
        if any(not asin for asin in queue_asins) or len(set(queue_asins)) != len(queue_asins):
            raise BridgeError("checkpoint queue 含无效或重复 ASIN")
        if not isinstance(results, list):
            raise BridgeError("checkpoint results 必须是数组")

        if results:
            finished = dict(batch)
            finished["status"] = "done"
            identity = super().validate_batch(finished)
            if identity["resultAsins"] != queue_asins[: len(identity["resultAsins"])]:
                raise BridgeError("checkpoint results 必须按 queue 前缀顺序递增", stage="checkpoint_order")
            return identity
        return {
            "batchName": batch_name,
            "queueHash": queue_hash,
            "generatedAt": generated_at,
            "queueAsins": queue_asins,
            "resultAsins": [],
        }

    @staticmethod
    def _checkpoint_key(identity: dict[str, Any]) -> str:
        return f"{identity['queueHash']}::{identity['generatedAt']}"

    def _persist_checkpoint(self, batch: dict[str, Any], identity: dict[str, Any]) -> dict[str, Any]:
        manifest = self._load_manifest()
        key = self._checkpoint_key(identity)
        entries = manifest["checkpointBatches"]
        entry = next((item for item in entries if item.get("identity") == key), None)

        if entry is None:
            attempted_elsewhere = {
                asin
                for item in entries
                for asin in item.get("resultAsins", [])
            }
            duplicates = sorted(set(identity["queueAsins"]) & attempted_elsewhere)
            if duplicates:
                raise BridgeError(
                    "新批次包含已经完成浏览器采集的 ASIN",
                    status=409,
                    stage="duplicate_attempted_asin",
                    details={"duplicateAsins": duplicates},
                )
            candidate_path = self._candidate_path_for(identity["queueAsins"])
            sequence = len(entries) + 1
            safe_hash = re.sub(r"[^A-Za-z0-9_-]", "", identity["queueHash"])[:24] or f"batch{sequence}"
            candidate_evidence_path = self.checkpoint_dir / f"candidate_{sequence:03d}_{safe_hash}.json"
            shutil.copy2(candidate_path, candidate_evidence_path)
            entry = {
                "sequence": sequence,
                "identity": key,
                "batchName": identity["batchName"],
                "queueHash": identity["queueHash"],
                "generatedAt": identity["generatedAt"],
                "queueAsins": identity["queueAsins"],
                "resultAsins": [],
                "candidateSourcePath": str(candidate_path),
                "candidatePath": str(candidate_evidence_path),
                "candidateSha256": file_sha256(candidate_evidence_path),
                "checkpoints": [],
            }
            entries.append(entry)
        elif entry.get("queueAsins") != identity["queueAsins"]:
            raise BridgeError("同一 checkpoint identity 的 queue 发生变化", status=409, stage="evidence_conflict")

        previous_results: list[dict[str, Any]] = []
        latest_path = Path(entry.get("latestCheckpointPath") or "")
        if latest_path.is_file():
            previous_results = list(read_json(latest_path).get("results") or [])
        current_results = list(batch.get("results") or [])
        if len(current_results) < len(previous_results):
            raise BridgeError("checkpoint 结果数量发生回退", status=409, stage="evidence_conflict")
        if previous_results and json_sha256(current_results[: len(previous_results)]) != json_sha256(previous_results):
            raise BridgeError("checkpoint 已保存结果发生变化", status=409, stage="evidence_conflict")

        batch_sha = json_sha256(batch)
        if len(current_results) == len(previous_results) and entry.get("latestCheckpointSha256") == batch_sha:
            return entry

        checkpoint_id = f"b{entry['sequence']:03d}-r{len(current_results):04d}-{batch_sha[:12]}"
        checkpoint_path = self.checkpoint_dir / f"checkpoint_{checkpoint_id}.json"
        write_json(checkpoint_path, batch)
        checkpoint_record = {
            "checkpointId": checkpoint_id,
            "path": str(checkpoint_path),
            "sha256": file_sha256(checkpoint_path),
            "resultCount": len(current_results),
            "createdAt": now_iso(),
        }
        entry["checkpoints"].append(checkpoint_record)
        entry["latestCheckpointPath"] = str(checkpoint_path)
        entry["latestCheckpointSha256"] = batch_sha
        entry["latestCheckpointId"] = checkpoint_id
        entry["resultCount"] = len(current_results)
        entry["resultAsins"] = identity["resultAsins"]
        entry["updatedAt"] = now_iso()
        manifest["updatedAt"] = now_iso()
        write_json(self.manifest_path, manifest)
        return entry

    def _checkpoint_replay_entries(self) -> list[dict[str, Any]]:
        manifest = self._load_manifest()
        return [
            {
                "batchPath": entry["latestCheckpointPath"],
                "candidatePath": entry["candidatePath"],
                "resultCount": int(entry.get("resultCount") or 0),
            }
            for entry in manifest["checkpointBatches"]
            if int(entry.get("resultCount") or 0) > 0
        ]

    def _replay_command(self, entries: list[dict[str, Any]], run_dir: Path, sandbox_root: Path) -> list[str]:
        command = [sys.executable, str(self.config.project_root / "scripts" / "replay_existing_batch.py")]
        for entry in entries:
            command.extend(["--batch-json", entry["batchPath"], "--candidates-json", entry["candidatePath"]])
        command.extend(
            [
                "--image-dir", str(self.config.image_dir),
                "--run-id", self.config.run_id,
                "--run-dir", str(run_dir),
                "--run-date", self.config.run_date,
                "--target", str(self.config.target),
                "--max-attempts", str(max(1000, sum(entry["resultCount"] for entry in entries) + 10)),
                "--project-root", str(sandbox_root),
                "--runner-current-price-v1",
                "--overwrite",
            ]
        )
        return command

    def run_checkpoint_replay(self) -> dict[str, Any]:
        entries = self._checkpoint_replay_entries()
        if not entries:
            return {"qualifiedCount": 0, "remainingTarget": self.config.target, "attemptedCount": 0}
        self.checkpoint_replay_dir.mkdir(parents=True, exist_ok=True)
        sandbox_root = self._seed_history_sandbox(self.checkpoint_replay_dir)
        self._run(self._replay_command(entries, self.checkpoint_replay_dir, sandbox_root), stage="checkpoint_replay")
        summary = read_json(self.checkpoint_replay_dir / "run_summary.json")
        qualified = int(summary.get("qualifiedCount") or 0)
        return {
            "qualifiedCount": qualified,
            "remainingTarget": max(self.config.target - qualified, 0),
            "attemptedCount": int(summary.get("attempts") or 0),
        }

    def checkpoint(self, envelope: Any, token: str) -> dict[str, Any]:
        if not secrets.compare_digest(token or "", self.config.token):
            raise BridgeError("快速闭环服务令牌无效", status=401, stage="auth")
        if not isinstance(envelope, dict) or envelope.get("schemaVersion") != CHECKPOINT_REQUEST_SCHEMA:
            raise BridgeError("快速闭环 checkpoint 请求 schema 不正确")
        batch = envelope.get("batch")
        identity = self.validate_checkpoint(batch)
        with self.lock:
            entry = self._persist_checkpoint(batch, identity)
            replay = self.run_checkpoint_replay()
        return {
            "schemaVersion": CHECKPOINT_RESPONSE_SCHEMA,
            "accepted": True,
            "finalAuthority": False,
            "productionHistoryUpdated": False,
            "target": self.config.target,
            "qualifiedCount": replay["qualifiedCount"],
            "remainingTarget": replay["remainingTarget"],
            "targetReached": replay["qualifiedCount"] == self.config.target,
            "attemptedCount": replay["attemptedCount"],
            "checkpointId": entry["latestCheckpointId"],
        }

    def run_pipeline(self) -> dict[str, Any]:
        entries = self._checkpoint_replay_entries()
        if not entries:
            raise BridgeError("还没有可回放的 checkpoint 证据", stage="replay")
        existing_attempts = []
        for path in self.attempts_dir.glob("attempt_*"):
            match = re.fullmatch(r"attempt_(\d+)", path.name)
            if match:
                existing_attempts.append(int(match.group(1)))
        attempt_number = max(existing_attempts, default=0) + 1
        attempt_dir = self.attempts_dir / f"attempt_{attempt_number:03d}"
        attempt_dir.mkdir(parents=True)
        sandbox_root = self._seed_history_sandbox(attempt_dir)
        self._run(self._replay_command(entries, attempt_dir, sandbox_root), stage="replay")
        summary = read_json(attempt_dir / "run_summary.json")
        if not summary.get("completedTarget") or int(summary.get("qualifiedCount") or 0) != self.config.target:
            result = {
                "schemaVersion": RESULT_SCHEMA,
                "accepted": False,
                "stage": "target_incomplete",
                "attempt": attempt_number,
                "attemptDir": str(attempt_dir),
                "qualifiedCount": int(summary.get("qualifiedCount") or 0),
                "target": self.config.target,
                "remainingTarget": max(self.config.target - int(summary.get("qualifiedCount") or 0), 0),
                "productionHistoryUpdated": False,
                "createdAt": now_iso(),
            }
            write_json(attempt_dir / "bridge_result.json", result)
            self._record_attempt(result)
            raise BridgeError("离线严格目标尚未达到", status=409, stage="target_incomplete", details=result)

        node = shutil.which("node")
        if not node:
            raise BridgeError("找不到 Node.js，无法生成工作簿", status=500, stage="workbook")
        self._run([node, str(self.config.project_root / "scripts" / "build_replay_workbooks.mjs"), str(attempt_dir)], stage="workbook")
        self._run([sys.executable, str(self.config.project_root / "scripts" / "acceptance_checker.py"), str(attempt_dir)], stage="acceptance")
        build_report = read_json(attempt_dir / "workbook_build_report.json")
        final_path = Path(build_report["finalXlsx"]).resolve()
        audit_path = Path(build_report["auditXlsx"]).resolve()
        if not is_within(final_path, attempt_dir) or not final_path.is_file():
            raise BridgeError("最终工作簿路径不可信或不存在", status=500, stage="publish")
        if not is_within(audit_path, attempt_dir) or not audit_path.is_file():
            raise BridgeError("审计工作簿路径不可信或不存在", status=500, stage="publish")
        result = {
            "schemaVersion": RESULT_SCHEMA,
            "accepted": True,
            "machineAcceptancePassed": True,
            "visualAcceptanceRequired": True,
            "productionHistoryUpdated": False,
            "attempt": attempt_number,
            "attemptDir": str(attempt_dir),
            "qualifiedCount": self.config.target,
            "target": self.config.target,
            "finalWorkbook": str(final_path),
            "finalWorkbookName": final_path.name,
            "finalWorkbookBytes": final_path.stat().st_size,
            "finalWorkbookSha256": file_sha256(final_path),
            "auditWorkbook": str(audit_path),
            "auditWorkbookName": audit_path.name,
            "auditWorkbookBytes": audit_path.stat().st_size,
            "auditWorkbookSha256": file_sha256(audit_path),
            "acceptanceReport": str(attempt_dir / "acceptance_report.md"),
            "createdAt": now_iso(),
        }
        write_json(attempt_dir / "bridge_result.json", result)
        self._record_attempt(result)
        return result


class FastLoopHandler(BridgeHandler):
    def do_POST(self) -> None:  # noqa: N802
        if urlparse(self.path).path != "/api/v1/checkpoint":
            super().do_POST()
            return
        try:
            size = int(self.headers.get("Content-Length") or "0")
            if size < 1 or size > MAX_REQUEST_BYTES:
                raise BridgeError("请求大小无效", status=413, stage="request")
            envelope = json.loads(self.rfile.read(size).decode("utf-8"))
            token = str(self.headers.get("X-Selection-Bridge-Token") or "")
            self._send_json(200, self.server.bridge.checkpoint(envelope, token))
        except json.JSONDecodeError:
            self._error(BridgeError("请求 JSON 无法解析", stage="request"))
        except BridgeError as error:
            self._error(error)
        except Exception as error:
            self._error(BridgeError(f"服务内部错误: {error}", status=500, stage="internal"))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the loopback-only strict selection fast-loop bridge.")
    parser.add_argument("--project-root", type=Path, default=DEFAULT_PROJECT_ROOT)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--candidates-json", type=Path, action="append", required=True)
    parser.add_argument("--image-dir", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--run-date", default=date.today().isoformat())
    parser.add_argument("--target", type=int, required=True)
    parser.add_argument("--token", default="")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--runner-version", default="0.3.10")
    parser.add_argument("--collector-version", default="0.4.6.2")
    parser.add_argument("--command-timeout-seconds", type=int, default=120)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = BridgeConfig(
        project_root=args.project_root.resolve(),
        output_root=args.output_root.resolve(),
        candidates_json=[path.resolve() for path in args.candidates_json],
        image_dir=args.image_dir.resolve(),
        run_id=args.run_id,
        run_date=args.run_date,
        target=args.target,
        token=args.token or secrets.token_urlsafe(24),
        runner_version=args.runner_version,
        collector_version=args.collector_version,
        command_timeout_seconds=args.command_timeout_seconds,
    )
    bridge = FastLoopBridge(config)
    server = BridgeHttpServer(("127.0.0.1", args.port), FastLoopHandler)
    server.bridge = bridge
    print("SellerSprite 严格选品快速闭环服务已启动")
    print(f"服务地址: http://127.0.0.1:{args.port}")
    print(f"服务令牌: {config.token}")
    print(f"runId: {config.run_id}; target: {config.target}")
    print("逐行计数仅来自离线 A-F 回放；正式历史不会自动更新。")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n快速闭环服务已停止")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
