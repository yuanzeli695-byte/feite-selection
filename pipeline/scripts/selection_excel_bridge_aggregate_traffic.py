#!/usr/bin/env python3
"""Dedicated bridge for legacy Runner ASIN-mismatch short circuits."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import threading
from dataclasses import dataclass
from datetime import date, datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qs, urlparse


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_PROJECT_ROOT = SCRIPT_DIR.parent
ASIN_RE = re.compile(r"^B0[A-Z0-9]{8}$")
REQUEST_SCHEMA = "sellerSpriteExcelBridgeRequest/v1"
RESPONSE_SCHEMA = "sellerSpriteExcelBridgeResponse/v1"
MANIFEST_SCHEMA = "sellerSpriteExcelBridgeManifest/v1"
RESULT_SCHEMA = "sellerSpriteExcelBridgeResult/v1"
MAX_REQUEST_BYTES = 12 * 1024 * 1024
ALLOWED_ORIGINS = {"https://www.amazon.com", "https://amazon.com"}


class BridgeError(RuntimeError):
    def __init__(self, message: str, *, status: int = 400, stage: str = "validation", details: Any = None):
        super().__init__(message)
        self.status = status
        self.stage = stage
        self.details = details


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def json_bytes(payload: Any) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(json_bytes(payload))


def json_sha256(payload: Any) -> str:
    return hashlib.sha256(json_bytes(payload)).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalize_asin(value: Any) -> str:
    text = str(value or "").strip().upper()
    return text if ASIN_RE.fullmatch(text) else ""


def is_within(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


@dataclass(frozen=True)
class CandidateSet:
    path: Path
    asins: frozenset[str]


@dataclass
class BridgeConfig:
    project_root: Path
    output_root: Path
    candidates_json: list[Path]
    image_dir: Path
    run_id: str
    run_date: str
    target: int
    token: str
    rules_path: Path
    runner_version: str = "0.3.8.6"
    collector_version: str = "0.4.6.3"
    command_timeout_seconds: int = 900


class SelectionExcelBridge:
    def __init__(
        self,
        config: BridgeConfig,
        *,
        command_runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    ) -> None:
        self.config = config
        self.command_runner = command_runner
        self.lock = threading.Lock()
        self.output_root = config.output_root.resolve()
        self.bridge_root = self.output_root / "excel_bridge"
        self.evidence_dir = self.bridge_root / "evidence"
        self.attempts_dir = self.bridge_root / "attempts"
        self.manifest_path = self.bridge_root / "bridge_manifest.json"
        self.output_root.mkdir(parents=True, exist_ok=True)
        self.evidence_dir.mkdir(parents=True, exist_ok=True)
        self.attempts_dir.mkdir(parents=True, exist_ok=True)
        self.candidate_sets = self._load_candidate_sets(config.candidates_json)
        if not config.image_dir.is_dir():
            raise BridgeError(f"主图目录不存在: {config.image_dir}", stage="startup")
        if config.target < 1:
            raise BridgeError("target 必须大于 0", stage="startup")

    def _load_candidate_sets(self, paths: list[Path]) -> list[CandidateSet]:
        sets: list[CandidateSet] = []
        seen: set[Path] = set()
        for raw_path in paths:
            path = raw_path.resolve()
            if path in seen:
                continue
            seen.add(path)
            if not path.is_file():
                raise BridgeError(f"候选 JSON 不存在: {path}", stage="startup")
            payload = read_json(path)
            if not isinstance(payload, list) or any(not isinstance(item, dict) for item in payload):
                raise BridgeError(f"候选 JSON 必须是对象数组: {path}", stage="startup")
            asins = frozenset(filter(None, (normalize_asin(item.get("asin")) for item in payload)))
            if not asins:
                raise BridgeError(f"候选 JSON 没有有效 ASIN: {path}", stage="startup")
            sets.append(CandidateSet(path=path, asins=asins))
        if not sets:
            raise BridgeError("至少需要一个 --candidates-json", stage="startup")
        return sets

    def _load_manifest(self) -> dict[str, Any]:
        if self.manifest_path.exists():
            payload = read_json(self.manifest_path)
            if payload.get("schemaVersion") != MANIFEST_SCHEMA:
                raise BridgeError("已有 bridge manifest 版本不兼容", stage="manifest")
            if payload.get("runId") != self.config.run_id or int(payload.get("target") or 0) != self.config.target:
                raise BridgeError("已有 bridge manifest 与本次 runId/target 不一致", stage="manifest")
            return payload
        return {
            "schemaVersion": MANIFEST_SCHEMA,
            "runId": self.config.run_id,
            "runDate": self.config.run_date,
            "target": self.config.target,
            "expectedRunnerVersion": self.config.runner_version,
            "expectedCollectorVersion": self.config.collector_version,
            "productionHistoryWriteProtected": True,
            "createdAt": now_iso(),
            "updatedAt": now_iso(),
            "batches": [],
            "attempts": [],
        }

    def validate_batch(self, batch: Any) -> dict[str, Any]:
        if not isinstance(batch, dict):
            raise BridgeError("batch 必须是 JSON 对象")
        if batch.get("schemaVersion") != "sellerSpriteIntegratedBatch/v0.3.0":
            raise BridgeError(f"不支持的 batch schema: {batch.get('schemaVersion')}")
        if batch.get("status") != "done":
            raise BridgeError("只有状态为 done 的批次才能生成 Excel")
        if int(batch.get("targetQualified") or 0) != self.config.target:
            raise BridgeError(
                f"批次 targetQualified={batch.get('targetQualified')} 与服务 target={self.config.target} 不一致"
            )
        batch_name = str(batch.get("batchName") or "").strip()
        queue_hash = str(batch.get("queueHash") or "").strip()
        generated_at = str(batch.get("generatedAt") or batch.get("createdAt") or "").strip()
        queue = batch.get("queue")
        results = batch.get("results")
        if not batch_name or not queue_hash or not generated_at:
            raise BridgeError("batchName、queueHash、generatedAt/createdAt 不能为空")
        if not isinstance(queue, list) or not queue:
            raise BridgeError("批次 queue 不能为空")
        queue_asins = [normalize_asin(value) for value in queue]
        if any(not asin for asin in queue_asins) or len(set(queue_asins)) != len(queue_asins):
            raise BridgeError("批次 queue 含无效或重复 ASIN")
        if not isinstance(results, list) or not results:
            raise BridgeError("批次没有可回放的 results")
        result_asins: list[str] = []
        for index, row in enumerate(results, start=1):
            if not isinstance(row, dict):
                raise BridgeError(f"results[{index}] 不是对象")
            asin = normalize_asin(row.get("targetAsin"))
            if not asin or asin not in queue_asins:
                raise BridgeError(f"results[{index}] targetAsin 无效或不在 queue")
            result_asins.append(asin)
            gate = ((row.get("telemetry") or {}).get("gate") or {})
            runner_version = str(gate.get("runnerVersion") or "").strip()
            collector_version = str(row.get("collectorVersion") or gate.get("collectorVersion") or "").strip()
            skipped_steps = row.get("skippedSteps")
            collector_skipped_for_asin_mismatch = (
                row.get("asinMismatch") is True
                and str(row.get("status") or "").strip() == "error"
                and str(row.get("strictDecision") or "").strip() == "reject"
                and str(row.get("rejectionStage") or "").strip() == "asin"
                and str(row.get("rejectionRule") or "").strip() == "asin_mismatch"
                and isinstance(skipped_steps, list)
                and "traffic" in skipped_steps
            )
            if runner_version != self.config.runner_version:
                raise BridgeError(
                    f"results[{index}] Runner 版本不一致: {runner_version or 'missing'}"
                )
            if collector_skipped_for_asin_mismatch:
                if collector_version and collector_version != self.config.collector_version:
                    raise BridgeError(
                        f"results[{index}] Collector 版本不一致: {collector_version}"
                    )
            elif collector_version != self.config.collector_version:
                raise BridgeError(
                    f"results[{index}] Collector 版本不一致: {collector_version or 'missing'}"
                )
        if len(set(result_asins)) != len(result_asins):
            raise BridgeError("results 含重复 targetAsin")
        return {
            "batchName": batch_name,
            "queueHash": queue_hash,
            "generatedAt": generated_at,
            "queueAsins": queue_asins,
            "resultAsins": result_asins,
        }

    def _candidate_path_for(self, queue_asins: list[str]) -> Path:
        required = set(queue_asins)
        matches = [item.path for item in self.candidate_sets if required.issubset(item.asins)]
        if not matches:
            raise BridgeError("没有候选 JSON 能覆盖该批次完整 queue", stage="candidate_mapping")
        if len(matches) > 1:
            raise BridgeError(
                "多个候选 JSON 同时覆盖该批次，无法确定唯一配对",
                stage="candidate_mapping",
                details=[str(path) for path in matches],
            )
        return matches[0]

    def _persist_batch(self, batch: dict[str, Any], identity: dict[str, Any]) -> dict[str, Any]:
        manifest = self._load_manifest()
        key = f"{identity['queueHash']}::{identity['generatedAt']}"
        for entry in manifest["batches"]:
            if entry.get("identity") == key:
                if entry.get("batchSha256") != json_sha256(batch):
                    raise BridgeError(
                        "相同 queueHash/generatedAt 的批次内容发生变化，拒绝覆盖既有证据",
                        status=409,
                        stage="evidence_conflict",
                        details={
                            "persistedSha256": entry.get("batchSha256"),
                            "receivedSha256": json_sha256(batch),
                        },
                    )
                return entry
        candidate_path = self._candidate_path_for(identity["queueAsins"])
        sequence = len(manifest["batches"]) + 1
        safe_hash = re.sub(r"[^A-Za-z0-9_-]", "", identity["queueHash"])[:24] or f"batch{sequence}"
        batch_path = self.evidence_dir / f"batch_{sequence:03d}_{safe_hash}.json"
        candidate_evidence_path = self.evidence_dir / f"candidate_{sequence:03d}_{safe_hash}.json"
        write_json(batch_path, batch)
        shutil.copy2(candidate_path, candidate_evidence_path)
        entry = {
            "sequence": sequence,
            "identity": key,
            "batchName": identity["batchName"],
            "queueHash": identity["queueHash"],
            "generatedAt": identity["generatedAt"],
            "batchPath": str(batch_path),
            "batchBytes": batch_path.stat().st_size,
            "batchSha256": file_sha256(batch_path),
            "candidateSourcePath": str(candidate_path),
            "candidatePath": str(candidate_evidence_path),
            "candidateBytes": candidate_evidence_path.stat().st_size,
            "candidateSha256": file_sha256(candidate_evidence_path),
            "queueCount": len(identity["queueAsins"]),
            "resultCount": len(identity["resultAsins"]),
            "uploadedAt": now_iso(),
        }
        manifest["batches"].append(entry)
        manifest["updatedAt"] = now_iso()
        write_json(self.manifest_path, manifest)
        return entry

    def _seed_history_sandbox(self, attempt_dir: Path) -> Path:
        sandbox_root = attempt_dir / "sandbox_project"
        history_dir = sandbox_root / "history"
        history_dir.mkdir(parents=True, exist_ok=True)
        source = self.config.project_root / "history" / "strict_qualified_asins.json"
        target = history_dir / "strict_qualified_asins.json"
        if not source.is_file():
            raise BridgeError(f"正式 strict history 不存在: {source}", stage="history_snapshot")
        shutil.copy2(source, target)
        return sandbox_root

    def _run(self, command: list[str], *, stage: str) -> subprocess.CompletedProcess[str]:
        env = dict(os.environ)
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        try:
            completed = self.command_runner(
                command,
                cwd=self.config.project_root,
                env=env,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self.config.command_timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as error:
            raise BridgeError(f"{stage} 超时", status=504, stage=stage) from error
        if completed.returncode != 0:
            raise BridgeError(
                f"{stage} 失败，退出码 {completed.returncode}",
                status=422,
                stage=stage,
                details={"stdout": completed.stdout[-4000:], "stderr": completed.stderr[-4000:]},
            )
        return completed

    def _record_attempt(self, result: dict[str, Any]) -> None:
        manifest = self._load_manifest()
        manifest["attempts"].append(result)
        manifest["updatedAt"] = now_iso()
        write_json(self.manifest_path, manifest)

    def run_pipeline(self) -> dict[str, Any]:
        manifest = self._load_manifest()
        if not manifest["batches"]:
            raise BridgeError("还没有上传批次证据", stage="replay")
        existing_attempts = []
        for path in self.attempts_dir.glob("attempt_*"):
            match = re.fullmatch(r"attempt_(\d+)", path.name)
            if match:
                existing_attempts.append(int(match.group(1)))
        attempt_number = max(existing_attempts, default=0) + 1
        attempt_dir = self.attempts_dir / f"attempt_{attempt_number:03d}"
        if attempt_dir.exists():
            raise BridgeError(f"attempt 目录已存在: {attempt_dir}", stage="attempt")
        attempt_dir.mkdir(parents=True)
        sandbox_root = self._seed_history_sandbox(attempt_dir)

        replay = [
            sys.executable,
            str(self.config.project_root / "scripts" / "replay_existing_batch.py"),
        ]
        for entry in manifest["batches"]:
            replay.extend(["--batch-json", entry["batchPath"], "--candidates-json", entry["candidatePath"]])
        replay.extend(
            [
                "--image-dir",
                str(self.config.image_dir),
                "--run-id",
                self.config.run_id,
                "--run-dir",
                str(attempt_dir),
                "--run-date",
                self.config.run_date,
                "--target",
                str(self.config.target),
                "--max-attempts",
                str(max(1000, sum(int(entry["resultCount"]) for entry in manifest["batches"]) + 10)),
                "--project-root",
                str(sandbox_root),
                "--rules",
                str(self.config.rules_path),
                "--overwrite",
            ]
        )
        self._run(replay, stage="replay")
        summary_path = attempt_dir / "run_summary.json"
        summary = read_json(summary_path)
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
            raise BridgeError(
                f"离线回放仅合格 {result['qualifiedCount']}/{self.config.target}，请补充候选后继续采集",
                status=409,
                stage="target_incomplete",
                details=result,
            )

        node = shutil.which("node")
        if not node:
            raise BridgeError("找不到 Node.js，无法生成工作簿", status=500, stage="workbook")
        self._run(
            [node, str(self.config.project_root / "scripts" / "build_replay_workbooks.mjs"), str(attempt_dir)],
            stage="workbook",
        )
        self._run(
            [
                sys.executable,
                str(self.config.project_root / "scripts" / "acceptance_checker.py"),
                str(attempt_dir),
                "--rules",
                str(self.config.rules_path),
            ],
            stage="acceptance",
        )
        build_report = read_json(attempt_dir / "workbook_build_report.json")
        final_path = Path(build_report["finalXlsx"]).resolve()
        audit_path = Path(build_report["auditXlsx"]).resolve()
        if not is_within(final_path, attempt_dir) or not final_path.is_file():
            raise BridgeError("最终工作簿路径不可信或文件不存在", status=500, stage="publish")
        if not is_within(audit_path, attempt_dir) or not audit_path.is_file():
            raise BridgeError("审计工作簿路径不可信或文件不存在", status=500, stage="publish")
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

    def export(self, envelope: Any, token: str) -> dict[str, Any]:
        if not secrets.compare_digest(token or "", self.config.token):
            raise BridgeError("Excel 服务令牌无效", status=401, stage="auth")
        if not isinstance(envelope, dict) or envelope.get("schemaVersion") != REQUEST_SCHEMA:
            raise BridgeError("Excel bridge 请求 schema 不正确")
        identity = self.validate_batch(envelope.get("batch"))
        with self.lock:
            entry = self._persist_batch(envelope["batch"], identity)
            result = self.run_pipeline()
        result["uploadedBatch"] = entry
        return result

    def download_path(self, kind: str, attempt: int) -> Path:
        attempt_dir = self.attempts_dir / f"attempt_{attempt:03d}"
        result_path = attempt_dir / "bridge_result.json"
        if not result_path.is_file():
            raise BridgeError("找不到对应的 bridge result", status=404, stage="download")
        result = read_json(result_path)
        if result.get("accepted") is not True:
            raise BridgeError("该 attempt 未通过机器验收", status=403, stage="download")
        key = "finalWorkbook" if kind == "final" else "auditWorkbook"
        path = Path(result.get(key) or "").resolve()
        if not is_within(path, attempt_dir) or not path.is_file():
            raise BridgeError("下载文件路径不可信或不存在", status=404, stage="download")
        return path


class BridgeHttpServer(ThreadingHTTPServer):
    bridge: SelectionExcelBridge


class BridgeHandler(BaseHTTPRequestHandler):
    server: BridgeHttpServer

    def log_message(self, fmt: str, *args: Any) -> None:
        print(f"[bridge] {self.address_string()} {fmt % args}")

    def _origin(self) -> str:
        origin = str(self.headers.get("Origin") or "")
        return origin if origin in ALLOWED_ORIGINS else ""

    def _cors_headers(self) -> None:
        origin = self._origin()
        if origin:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Selection-Bridge-Token")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")

    def _send_json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self._cors_headers()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _error(self, error: BridgeError) -> None:
        self._send_json(
            error.status,
            {
                "schemaVersion": RESPONSE_SCHEMA,
                "accepted": False,
                "stage": error.stage,
                "message": str(error),
                "details": error.details,
            },
        )

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(HTTPStatus.NO_CONTENT)
        self._cors_headers()
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/api/v1/health":
            self._send_json(
                200,
                {
                    "schemaVersion": RESPONSE_SCHEMA,
                    "ok": True,
                    "runId": self.server.bridge.config.run_id,
                    "target": self.server.bridge.config.target,
                    "productionHistoryWriteProtected": True,
                },
            )
            return
        if parsed.path == "/api/v1/download":
            query = parse_qs(parsed.query)
            token = (query.get("token") or [""])[0]
            if not secrets.compare_digest(token, self.server.bridge.config.token):
                self._error(BridgeError("下载令牌无效", status=401, stage="auth"))
                return
            try:
                kind = (query.get("kind") or ["final"])[0]
                if kind not in {"final", "audit"}:
                    raise BridgeError("下载 kind 必须是 final 或 audit", status=400, stage="download")
                attempt = int((query.get("attempt") or ["0"])[0])
                path = self.server.bridge.download_path(kind, attempt)
            except (BridgeError, ValueError) as error:
                self._error(error if isinstance(error, BridgeError) else BridgeError("attempt 无效", stage="download"))
                return
            data = path.read_bytes()
            self.send_response(200)
            self._cors_headers()
            self.send_header("Content-Type", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            self.send_header("Content-Disposition", f'attachment; filename="{path.name}"')
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        self._error(BridgeError("接口不存在", status=404, stage="routing"))

    def do_POST(self) -> None:  # noqa: N802
        if urlparse(self.path).path != "/api/v1/export":
            self._error(BridgeError("接口不存在", status=404, stage="routing"))
            return
        try:
            size = int(self.headers.get("Content-Length") or "0")
            if size < 1 or size > MAX_REQUEST_BYTES:
                raise BridgeError("请求大小无效", status=413, stage="request")
            envelope = json.loads(self.rfile.read(size).decode("utf-8"))
            token = str(self.headers.get("X-Selection-Bridge-Token") or "")
            result = self.server.bridge.export(envelope, token)
            base = f"http://127.0.0.1:{self.server.server_port}/api/v1/download"
            result.update(
                {
                    "schemaVersion": RESPONSE_SCHEMA,
                    "finalWorkbookUrl": f"{base}?kind=final&attempt={result['attempt']}&token={self.server.bridge.config.token}",
                    "auditWorkbookUrl": f"{base}?kind=audit&attempt={result['attempt']}&token={self.server.bridge.config.token}",
                    "message": "机器验收通过。已生成待人工预览的 Excel，正式历史尚未更新。",
                }
            )
            self._send_json(200, result)
        except json.JSONDecodeError:
            self._error(BridgeError("请求 JSON 无法解析", stage="request"))
        except BridgeError as error:
            self._error(error)
        except Exception as error:  # fail closed and avoid a traceback in the browser response
            self._error(BridgeError(f"服务内部错误: {error}", status=500, stage="internal"))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the loopback-only strict selection Excel bridge.")
    parser.add_argument("--project-root", type=Path, default=DEFAULT_PROJECT_ROOT)
    parser.add_argument("--output-root", type=Path, required=True, help="Root directory for immutable evidence/attempts.")
    parser.add_argument("--candidates-json", type=Path, action="append", required=True)
    parser.add_argument("--image-dir", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--run-date", default=date.today().isoformat())
    parser.add_argument("--target", type=int, required=True)
    parser.add_argument("--token", default="", help="Optional fixed token; a random token is generated by default.")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--rules", type=Path, default=DEFAULT_PROJECT_ROOT / "config" / "rules_aggregate_natural_traffic.json")
    parser.add_argument("--runner-version", default="0.3.8.6")
    parser.add_argument("--collector-version", default="0.4.6.3")
    parser.add_argument("--command-timeout-seconds", type=int, default=900)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    project_root = args.project_root.resolve()
    token = args.token or secrets.token_urlsafe(24)
    config = BridgeConfig(
        project_root=project_root,
        output_root=args.output_root.resolve(),
        candidates_json=[path.resolve() for path in args.candidates_json],
        image_dir=args.image_dir.resolve(),
        run_id=args.run_id,
        run_date=args.run_date,
        target=args.target,
        token=token,
        rules_path=args.rules.resolve(),
        runner_version=args.runner_version,
        collector_version=args.collector_version,
        command_timeout_seconds=args.command_timeout_seconds,
    )
    bridge = SelectionExcelBridge(config)
    server = BridgeHttpServer(("127.0.0.1", args.port), BridgeHandler)
    server.bridge = bridge
    print("SellerSprite 严格选品 Excel 服务已启动")
    print(f"服务地址: http://127.0.0.1:{args.port}")
    print(f"服务令牌: {token}")
    print(f"runId: {config.run_id}; target: {config.target}")
    print("仅机器验收通过后提供 XLSX；仍需人工预览，正式 history 不会自动更新。")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nExcel 服务已停止")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
