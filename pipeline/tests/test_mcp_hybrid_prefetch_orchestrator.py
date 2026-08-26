from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import subprocess
import sys
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "mcp_hybrid_prefetch_orchestrator.py"
SPEC = importlib.util.spec_from_file_location("mcp_hybrid_prefetch_orchestrator_test", SCRIPT)
if SPEC is None or SPEC.loader is None:  # pragma: no cover
    raise RuntimeError(f"cannot load orchestrator: {SCRIPT}")
MOD = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MOD
SPEC.loader.exec_module(MOD)

CANDIDATE_FIXTURE = ROOT / "tests" / "fixtures_mcp_hybrid_prefiltered_candidates.json"
RESULT_FIXTURE = ROOT / "tests" / "fixtures_mcp_hybrid_packet_results.json"
SHADOW_PLAN_FIXTURE = ROOT / "docs" / "mcp_hybrid_shadow_plan_20260729.json"
FIXED_AT = datetime(2026, 7, 29, 1, 30, tzinfo=timezone.utc)


def run_parallel_commands(commands: list[list[str]], start_path: Path) -> list[dict]:
    code = r'''
import json, pathlib, subprocess, sys, time
start_path = pathlib.Path(sys.argv[1])
while not start_path.exists():
    time.sleep(0.01)
result = subprocess.run(sys.argv[2:], capture_output=True, text=True, check=False)
print(json.dumps({"returncode": result.returncode, "stdout": result.stdout, "stderr": result.stderr}))
'''
    processes = [
        subprocess.Popen(
            [sys.executable, "-c", code, str(start_path), *command],
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        for command in commands
    ]
    time.sleep(0.2)
    start_path.write_text("go\n", encoding="ascii")
    outputs = []
    for process in processes:
        stdout, stderr = process.communicate(timeout=30)
        if process.returncode != 0:
            raise AssertionError(f"parallel command wrapper failed ({process.returncode}): {stderr}\n{stdout}")
        outputs.append(json.loads(stdout))
    return outputs


class FakeLedger:
    def __init__(
        self,
        *,
        test_mode: bool = False,
        run_id: str = "fixture-prefetch-run",
        run_budget: int = 100,
    ) -> None:
        self.test_mode = test_mode
        self.run_id = run_id
        self.run_budget = run_budget
        self.reservations: list[dict] = []
        self.claims: list[dict] = []
        self.statuses: list[dict] = []

    def reserve_plan(self, *, plan_id, requests, allow_emergency=False, seal_run=False, at=None):
        entry = {
            "planId": plan_id,
            "requests": copy.deepcopy(requests),
            "allowEmergency": allow_emergency,
            "sealRun": seal_run,
            "at": at,
        }
        self.reservations.append(entry)
        return {
            "event": {
                "eventType": "reserved",
                "runId": self.run_id,
                "planId": plan_id,
                "calls": sum(item["calls"] for item in requests),
                "requests": copy.deepcopy(requests),
                "sealedRun": seal_run,
                "authorizedCalls": sum(item["calls"] for item in requests) if seal_run else 0,
                "taskBudget": self.run_budget if seal_run else None,
                "sealedReserveCalls": self.run_budget - sum(item["calls"] for item in requests)
                if seal_run
                else 0,
                "automaticRetry": False,
            },
            "idempotent": False,
            "currentStatus": "reserved",
        }

    def claim_plan_request(self, *, plan_id, request_id, claim_id, at=None):
        if any(item["planId"] == plan_id and item["requestId"] == request_id for item in self.claims):
            raise RuntimeError("packet already claimed")
        reservation = next(item for item in self.reservations if item["planId"] == plan_id)
        request = next(item for item in reservation["requests"] if item["id"] == request_id)
        entry = {
            "runId": self.run_id,
            "planId": plan_id,
            "requestId": request_id,
            "claimId": claim_id,
            "requestHash": request["requestHash"],
            "tool": request["tool"],
        }
        self.claims.append(entry)
        return {
            "event": {
                "eventType": "claimed",
                **entry,
                "at": MOD.iso_z(at or FIXED_AT),
                "executionAllowed": True,
                "automaticRetry": False,
                "finalAuthority": False,
            },
            "executionAllowed": True,
            "idempotent": False,
            "finalAuthority": False,
        }

    def mark_plan_status(self, *, plan_id, status, details=None):
        entry = {"planId": plan_id, "status": status, "details": copy.deepcopy(details or {})}
        prior = next((item for item in reversed(self.statuses) if item["planId"] == plan_id), None)
        if prior is not None:
            if prior == entry:
                return {"event": copy.deepcopy(prior), "idempotent": True}
            raise RuntimeError("plan already terminal")
        self.statuses.append(entry)
        return {"event": copy.deepcopy(entry), "idempotent": False}

    def plan_state(self, plan_id):
        reservation = next(item for item in self.reservations if item["planId"] == plan_id)
        requests = copy.deepcopy(reservation["requests"])
        claims = [item for item in self.claims if item["planId"] == plan_id]
        terminal = next((item for item in reversed(self.statuses) if item["planId"] == plan_id), None)
        status = terminal["status"] if terminal is not None else "reserved"
        return {
            "runId": self.run_id,
            "planId": plan_id,
            "phase": "terminal" if terminal is not None else "claimed" if claims else "reserved",
            "status": status,
            "reservation": {
                "eventType": "reserved",
                "runId": self.run_id,
                "planId": plan_id,
                "calls": sum(item["calls"] for item in requests),
                "requests": requests,
                "automaticRetry": False,
            },
            "requests": requests,
            "claimEvents": [
                {
                    "eventType": "claimed",
                    **item,
                    "at": MOD.iso_z(FIXED_AT),
                    "executionAllowed": True,
                    "automaticRetry": False,
                    "finalAuthority": False,
                }
                for item in claims
            ],
            "claimedRequestIds": [item["requestId"] for item in claims],
            "terminalEvent": copy.deepcopy(terminal),
            "finalAuthority": False,
        }


class PrefetchOrchestratorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.candidates = json.loads(CANDIDATE_FIXTURE.read_text(encoding="utf-8"))
        self.results = json.loads(RESULT_FIXTURE.read_text(encoding="utf-8"))["templates"]
        self.shadow_plan = json.loads(SHADOW_PLAN_FIXTURE.read_text(encoding="utf-8"))
        self.discovery_request = {
            "request": {
                "marketplace": "US",
                "keyword": "office organizer",
                "page": 1,
                "size": 100,
            }
        }

    def plan(self, count: int = 2, **kwargs):
        payload = copy.deepcopy(self.candidates)
        payload["candidates"] = payload["candidates"][:count]
        return MOD.plan_workflow(
            payload,
            input_sha256=MOD.file_sha256(CANDIDATE_FIXTURE),
            created_at=FIXED_AT,
            **kwargs,
        )

    def result_for(self, template: str, workflow: dict, packet_index: int) -> dict:
        packet = workflow["packets"][packet_index]
        replacements = {
            "__WORKFLOW_ID__": workflow["workflowId"],
            "__RUN_ID__": workflow["runId"],
            "__PACKET_ID__": packet["packetId"],
            "__REQUEST_HASH__": packet["requestHash"],
            "__TARGET_ASIN__": packet["targetAsin"],
        }
        text = json.dumps(self.results[template])
        for marker, value in replacements.items():
            text = text.replace(marker, value)
        return json.loads(text)

    def validation_task(self) -> dict:
        return MOD.plan_validation_task(
            copy.deepcopy(self.shadow_plan),
            sample_sha256=MOD.file_sha256(SHADOW_PLAN_FIXTURE),
            discovery_request=copy.deepcopy(self.discovery_request),
            run_id="mcp-validate-task-fixture",
            created_at=FIXED_AT,
        )

    def validation_ledger(self, task: dict, ledger: FakeLedger | None = None) -> FakeLedger:
        active = ledger or FakeLedger(test_mode=True, run_id=task["runId"], run_budget=100)
        reservation = MOD.reserve_validation_task_with_bridge_ledger(active, task)
        MOD.attach_validation_task_reservation(task, reservation, at=FIXED_AT)
        return active

    def claim_validation(
        self,
        task: dict,
        ledger,
        request_index: int = 0,
        token: str | None = None,
    ) -> str:
        task, claim_token = MOD.claim_validation_task_request(
            ledger,
            task,
            request_id=task["requests"][request_index]["requestId"],
            executor_id=f"validation-executor-{request_index:03d}",
            claim_token=token or f"token-{request_index:03d}-" + "a" * 52,
            at=FIXED_AT,
        )
        return claim_token

    def validation_result(
        self,
        task: dict,
        request_index: int,
        raw_path: Path,
        *,
        status: str = "succeeded",
    ) -> dict:
        item = task["requests"][request_index]
        raw_payload = json.dumps(
            {"fixture": True, "requestId": item["requestId"], "status": status},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        raw_path.write_bytes(raw_payload)
        target = item.get("targetAsin")
        failed = status == "failed"
        return {
            "schemaVersion": MOD.VALIDATION_TASK_RESULT_SCHEMA,
            "taskId": task["taskId"],
            "runId": task["runId"],
            "requestId": item["requestId"],
            "requestHash": item["requestHash"],
            "claimId": item["claim"]["claimId"],
            "targetAsin": target,
            "actualAsin": None if failed or target is None else target,
            "tool": {"name": item["tool"], "version": "fixture-1"},
            "status": status,
            "startedAt": "2026-07-29T01:30:00Z",
            "completedAt": "2026-07-29T01:30:02Z",
            "rawResponse": {
                "sha256": hashlib.sha256(raw_payload).hexdigest(),
                "byteLength": len(raw_payload),
                "capturedAt": "2026-07-29T01:30:01Z",
            },
            "responseMetadata": {"fixture": True},
            "error": {"code": "fixture_failure", "message": "fixture failure", "retryable": False}
            if failed
            else None,
            "usableForFinal": False,
            "finalAuthority": False,
        }

    def reserve(self, workflow: dict, ledger: FakeLedger | None = None) -> FakeLedger:
        active = ledger or FakeLedger(test_mode=workflow["toolRouting"].get("testOnlyReservation") is True)
        reservation = MOD.reserve_with_bridge_ledger(active, workflow)
        MOD.attach_reservation(workflow, reservation, at=FIXED_AT)
        return active

    def claim(self, workflow: dict, ledger, packet_index: int = 0, token: str | None = None) -> str:
        workflow, claim_token = MOD.claim_packet(
            ledger,
            workflow,
            packet_id=workflow["packets"][packet_index]["packetId"],
            executor_id=f"test-executor-{packet_index}",
            claim_token=token or (str(packet_index + 1) * 64),
            at=FIXED_AT,
        )
        return claim_token

    def assert_no_final_authority(self, value) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                if key in {"finalAuthority", "usableForFinal"}:
                    self.assertIs(child, False, key)
                self.assert_no_final_authority(child)
        elif isinstance(value, list):
            for child in value:
                self.assert_no_final_authority(child)

    def test_plan_requires_prefilter_pass_and_source_proof(self) -> None:
        missing_status = copy.deepcopy(self.candidates)
        missing_status["candidates"][0].pop("prefilterStatus")
        with self.assertRaises(MOD.OrchestratorError) as raised:
            MOD.plan_workflow(missing_status, input_sha256="a" * 64)
        self.assertEqual(raised.exception.code, "prefilter_not_passed")

        missing_provenance = copy.deepcopy(self.candidates)
        missing_provenance["candidates"][0].pop("sourceProvenance")
        with self.assertRaises(MOD.OrchestratorError) as raised:
            MOD.plan_workflow(missing_provenance, input_sha256="a" * 64)
        self.assertEqual(raised.exception.code, "invalid_schema")

        missing_hash = copy.deepcopy(self.candidates)
        missing_hash["sourceProvenance"].pop("sourceSha256")
        with self.assertRaises(MOD.OrchestratorError) as raised:
            MOD.plan_workflow(missing_hash, input_sha256="a" * 64)
        self.assertEqual(raised.exception.code, "invalid_hash")

    def test_duplicate_asin_is_rejected_instead_of_silently_deduped(self) -> None:
        duplicate = copy.deepcopy(self.candidates)
        duplicate["candidates"][1]["asin"] = duplicate["candidates"][0]["asin"]
        with self.assertRaises(MOD.OrchestratorError) as raised:
            MOD.plan_workflow(duplicate, input_sha256="b" * 64)
        self.assertEqual(raised.exception.code, "duplicate_asin")

    def test_planned_workflow_is_written_atomically(self) -> None:
        workflow = self.plan(1)
        with TemporaryDirectory() as temp:
            path = Path(temp) / "workflow.json"
            MOD.atomic_write_json(path, workflow)
            self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["workflowId"], workflow["workflowId"])
            self.assertEqual(list(path.parent.glob(f".{path.name}.*.tmp")), [])

    def test_validation_task_is_exactly_91_calls_with_no_retry_or_final_authority(self) -> None:
        task = self.validation_task()
        self.assertEqual(task["budget"]["taskBudget"], 100)
        self.assertEqual(task["budget"]["authorizedCalls"], 91)
        self.assertEqual(task["budget"]["sealedReserveCalls"], 9)
        self.assertEqual(len(task["requests"]), 91)
        self.assertEqual(
            task["budget"]["plannedByTool"],
            {
                "product_research": 1,
                "asin_detail": 30,
                "asin_sales_trend": 30,
                "traffic_listing_stat": 30,
            },
        )
        self.assertEqual(task["requests"][0]["tool"], "product_research")
        self.assertIsNone(task["requests"][0]["targetAsin"])
        expected_asins = set(task["source"]["sampleAsins"])
        for tool in MOD.VALIDATION_TOOLS:
            self.assertEqual(
                {row["targetAsin"] for row in task["requests"] if row["tool"] == tool},
                expected_asins,
            )
        self.assertTrue(
            all(
                row["attemptPolicy"] == {"maxAttempts": 1, "automaticRetry": False}
                for row in task["requests"]
            )
        )
        self.assert_no_final_authority(task)

        appended = copy.deepcopy(task)
        appended["requests"].append(copy.deepcopy(appended["requests"][-1]))
        with self.assertRaises(MOD.OrchestratorError) as raised:
            MOD.validate_validation_task(appended)
        self.assertEqual(raised.exception.code, "invalid_task_budget")

        changed_budget = copy.deepcopy(task)
        changed_budget["budget"]["authorizedCalls"] = 92
        with self.assertRaises(MOD.OrchestratorError) as raised:
            MOD.validate_validation_task(changed_budget)
        self.assertEqual(raised.exception.code, "invalid_task_budget")

        authority_claim = copy.deepcopy(task)
        authority_claim["requests"][1]["sourceEvidence"]["usableForFinal"] = True
        with self.assertRaises(MOD.OrchestratorError) as raised:
            MOD.validate_validation_task(authority_claim)
        self.assertEqual(raised.exception.code, "authority_violation")

        placeholder_request = copy.deepcopy(self.discovery_request)
        placeholder_request["request"]["keyword"] = "__KEYWORD__"
        with self.assertRaises(MOD.OrchestratorError) as raised:
            MOD.plan_validation_task(
                self.shadow_plan,
                sample_sha256=MOD.file_sha256(SHADOW_PLAN_FIXTURE),
                discovery_request=placeholder_request,
                run_id="mcp-validate-task-placeholder",
            )
        self.assertEqual(raised.exception.code, "invalid_discovery_request")

        with self.assertRaises(MOD.OrchestratorError) as raised:
            MOD.plan_validation_task(
                self.shadow_plan,
                sample_sha256=MOD.file_sha256(SHADOW_PLAN_FIXTURE),
                discovery_request=self.discovery_request,
                run_id="legacy-run-budget-50",
            )
        self.assertEqual(raised.exception.code, "run_isolation_required")

    def test_validation_task_reserves_once_and_claims_each_request_once(self) -> None:
        task = self.validation_task()
        ledger = FakeLedger(
            test_mode=True,
            run_id=task["runId"],
            run_budget=100,
        )
        reservation = MOD.reserve_validation_task_with_bridge_ledger(ledger, task)
        self.assertEqual(len(ledger.reservations), 1)
        self.assertTrue(ledger.reservations[0]["sealRun"])
        self.assertEqual(reservation["event"]["calls"], 91)
        MOD.attach_validation_task_reservation(task, reservation, at=FIXED_AT)
        request_id = task["requests"][0]["requestId"]
        task, token = MOD.claim_validation_task_request(
            ledger,
            task,
            request_id=request_id,
            executor_id="validation-executor",
            claim_token="a" * 64,
            at=FIXED_AT,
        )
        self.assertEqual(token, "a" * 64)
        self.assertEqual(task["status"], "in_progress")
        self.assertEqual(task["requests"][0]["attemptsStarted"], 1)
        self.assertFalse(task["requests"][0]["claim"]["automaticRetry"])

        with self.assertRaises(MOD.OrchestratorError) as duplicate:
            MOD.claim_validation_task_request(
                ledger,
                task,
                request_id=request_id,
                executor_id="validation-executor",
            )
        self.assertEqual(duplicate.exception.code, "attempt_already_started")

        with self.assertRaises(MOD.OrchestratorError) as extra:
            MOD.claim_validation_task_request(
                ledger,
                task,
                request_id="task-asin-detail-extra",
                executor_id="validation-executor",
            )
        self.assertEqual(extra.exception.code, "request_not_found")

    def test_current_bridge_seals_validation_task_at_91_of_100(self) -> None:
        task = self.validation_task()
        with TemporaryDirectory() as temp:
            ledger_path = Path(temp) / "shared-ledger.jsonl"
            ledger = MOD.load_validation_task_ledger(
                ROOT / "scripts" / "mcp_hybrid_bridge.py",
                ROOT / "config" / "mcp_hybrid_policy.json",
                ledger_path,
                task,
                test_mode=True,
            )
            reservation = MOD.reserve_validation_task_with_bridge_ledger(ledger, task)
            MOD.attach_validation_task_reservation(task, reservation, at=FIXED_AT)
            self.assertEqual(reservation["summary"]["runBudget"], 100)
            self.assertEqual(reservation["summary"]["runUsed"], 91)
            self.assertTrue(reservation["summary"]["sealedRun"])
            self.assertEqual(reservation["summary"]["sealedReserveCalls"], 9)
            self.assertEqual(len(ledger_path.read_text(encoding="utf-8").splitlines()), 1)

            with self.assertRaises(Exception) as second_plan:
                ledger.reserve_plan(
                    plan_id="validation-extra-plan",
                    requests=[
                        {
                            "id": "task-asin-detail-extra",
                            "tool": "asin_detail",
                            "requestHash": "f" * 64,
                            "asinCount": 1,
                            "calls": 1,
                            "pool": "primary",
                        }
                    ],
                )
            self.assertEqual(getattr(second_plan.exception, "stage", None), "budget_sealed")

            with self.assertRaises(MOD.OrchestratorError) as formal:
                MOD.load_validation_task_ledger(
                    ROOT / "scripts" / "mcp_hybrid_bridge.py",
                    ROOT / "config" / "mcp_hybrid_policy.json",
                    Path(temp) / "formal-ledger.jsonl",
                    self.validation_task(),
                    test_mode=False,
                )
            self.assertEqual(formal.exception.code, "test_mode_required")

    def test_validation_task_cli_plans_reserves_and_claims_without_provider_access(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)
            discovery_path = root / "product_research_request.json"
            task_path = root / "validation_task.json"
            ledger_path = root / "ledger.jsonl"
            discovery_path.write_text(json.dumps(self.discovery_request), encoding="utf-8")
            common = [
                "--bridge",
                str(ROOT / "scripts" / "mcp_hybrid_bridge.py"),
                "--policy",
                str(ROOT / "config" / "mcp_hybrid_policy.json"),
                "--ledger",
                str(ledger_path),
            ]
            planned = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "plan-validation-task",
                    "--sample-plan",
                    str(SHADOW_PLAN_FIXTURE),
                    "--discovery-request",
                    str(discovery_path),
                    "--task",
                    str(task_path),
                    "--run-id",
                    "mcp-validate-task-cli-fixture",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(planned.returncode, 0, planned.stderr)
            reserved = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "reserve-validation-task",
                    "--task",
                    str(task_path),
                    "--test-mode",
                    *common,
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(reserved.returncode, 0, reserved.stderr)
            task = json.loads(task_path.read_text(encoding="utf-8"))
            self.assertEqual(task["status"], "reserved")
            self.assertEqual(len(ledger_path.read_text(encoding="utf-8").splitlines()), 1)
            request_id = task["requests"][0]["requestId"]
            claimed = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "claim-validation-task",
                    "--task",
                    str(task_path),
                    "--request-id",
                    request_id,
                    "--executor-id",
                    "cli-fixture",
                    "--test-mode",
                    *common,
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(claimed.returncode, 0, claimed.stderr)
            duplicate = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "claim-validation-task",
                    "--task",
                    str(task_path),
                    "--request-id",
                    request_id,
                    "--executor-id",
                    "cli-fixture",
                    "--test-mode",
                    *common,
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(duplicate.returncode, 2)
            self.assertIn("attempt_already_started", duplicate.stderr)

    def test_validation_result_requires_claim_token_and_exact_bridge_receipt(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)
            unclaimed = self.validation_task()
            with self.assertRaises(MOD.OrchestratorError) as raised:
                MOD.record_validation_task_result(
                    FakeLedger(test_mode=True, run_id=unclaimed["runId"]),
                    unclaimed,
                    {"requestId": unclaimed["requests"][0]["requestId"]},
                    raw_response_path=root / "missing.json",
                    archive_root=root / "archive",
                    claim_token="a" * 64,
                )
            self.assertEqual(raised.exception.code, "claim_required")

            task = self.validation_task()
            ledger = self.validation_ledger(task)
            token = self.claim_validation(task, ledger, request_index=1)
            raw_path = root / "raw.json"
            result = self.validation_result(task, 1, raw_path)

            with self.assertRaises(MOD.OrchestratorError) as raised:
                MOD.record_validation_task_result(
                    ledger,
                    task,
                    result,
                    raw_response_path=raw_path,
                    archive_root=root / "archive",
                    claim_token="wrong-" + "b" * 58,
                )
            self.assertEqual(raised.exception.code, "claim_token_mismatch")

            cases = (
                ("requestHash", "0" * 64, "request_hash_mismatch"),
                ("claimId", "claim-forged", "claim_mismatch"),
            )
            for field, value, code in cases:
                changed = copy.deepcopy(result)
                changed[field] = value
                with self.assertRaises(MOD.OrchestratorError) as raised:
                    MOD.record_validation_task_result(
                        ledger,
                        task,
                        changed,
                        raw_response_path=raw_path,
                        archive_root=root / "archive",
                        claim_token=token,
                    )
                self.assertEqual(raised.exception.code, code)

            wrong_tool = copy.deepcopy(result)
            wrong_tool["tool"]["name"] = "traffic_listing_stat"
            with self.assertRaises(MOD.OrchestratorError) as raised:
                MOD.record_validation_task_result(
                    ledger,
                    task,
                    wrong_tool,
                    raw_response_path=raw_path,
                    archive_root=root / "archive",
                    claim_token=token,
                )
            self.assertEqual(raised.exception.code, "tool_mismatch")

            wrong_asin = copy.deepcopy(result)
            wrong_asin["actualAsin"] = "B0ZZZZ9999"
            with self.assertRaises(MOD.OrchestratorError) as raised:
                MOD.record_validation_task_result(
                    ledger,
                    task,
                    wrong_asin,
                    raw_response_path=raw_path,
                    archive_root=root / "archive",
                    claim_token=token,
                )
            self.assertEqual(raised.exception.code, "asin_mismatch")

            original_hash = ledger.claims[0]["requestHash"]
            ledger.claims[0]["requestHash"] = "f" * 64
            with self.assertRaises(MOD.OrchestratorError) as raised:
                MOD.record_validation_task_result(
                    ledger,
                    task,
                    result,
                    raw_response_path=raw_path,
                    archive_root=root / "archive",
                    claim_token=token,
                )
            self.assertEqual(raised.exception.code, "claim_mismatch")
            ledger.claims[0]["requestHash"] = original_hash
            self.assertFalse((root / "archive").exists())

    def test_validation_result_archives_raw_json_once_and_rejects_replacement(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)
            task = self.validation_task()
            ledger = self.validation_ledger(task)
            token = self.claim_validation(task, ledger, request_index=1)
            raw_path = root / "raw.json"
            result = self.validation_result(task, 1, raw_path)

            mismatched = copy.deepcopy(result)
            mismatched["rawResponse"]["sha256"] = "0" * 64
            with self.assertRaises(MOD.OrchestratorError) as raised:
                MOD.record_validation_task_result(
                    ledger,
                    task,
                    mismatched,
                    raw_response_path=raw_path,
                    archive_root=root / "archive",
                    claim_token=token,
                )
            self.assertEqual(raised.exception.code, "raw_response_mismatch")

            invalid_raw = root / "invalid.json"
            invalid_raw.write_bytes(b"not-json")
            invalid_result = copy.deepcopy(result)
            invalid_result["rawResponse"]["sha256"] = hashlib.sha256(b"not-json").hexdigest()
            invalid_result["rawResponse"]["byteLength"] = len(b"not-json")
            with self.assertRaises(MOD.OrchestratorError) as raised:
                MOD.record_validation_task_result(
                    ledger,
                    task,
                    invalid_result,
                    raw_response_path=invalid_raw,
                    archive_root=root / "archive",
                    claim_token=token,
                )
            self.assertEqual(raised.exception.code, "raw_response_invalid")

            task, changed = MOD.record_validation_task_result(
                ledger,
                task,
                result,
                raw_response_path=raw_path,
                archive_root=root / "archive",
                claim_token=token,
                recorded_at=FIXED_AT,
            )
            self.assertTrue(changed)
            archive = Path(task["requests"][1]["rawResponseArchive"]["path"])
            self.assertTrue(archive.is_file())
            self.assertEqual(archive.read_bytes(), raw_path.read_bytes())

            task, changed = MOD.record_validation_task_result(
                ledger,
                task,
                result,
                raw_response_path=raw_path,
                archive_root=root / "archive",
                claim_token=token,
            )
            self.assertFalse(changed)
            replacement = copy.deepcopy(result)
            replacement["responseMetadata"]["replacement"] = True
            with self.assertRaises(MOD.OrchestratorError) as raised:
                MOD.record_validation_task_result(
                    ledger,
                    task,
                    replacement,
                    raw_response_path=raw_path,
                    archive_root=root / "archive",
                    claim_token=token,
                )
            self.assertEqual(raised.exception.code, "retry_forbidden")
            self.assertEqual(
                sum(item["event"] == "result_recorded" for item in task["history"]),
                1,
            )
            self.assert_no_final_authority(task)

    def test_validation_failed_result_must_be_non_retryable(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)
            task = self.validation_task()
            ledger = self.validation_ledger(task)
            token = self.claim_validation(task, ledger, request_index=1)
            raw_path = root / "failed.json"
            result = self.validation_result(task, 1, raw_path, status="failed")
            result["error"]["retryable"] = True
            with self.assertRaises(MOD.OrchestratorError) as raised:
                MOD.record_validation_task_result(
                    ledger,
                    task,
                    result,
                    raw_response_path=raw_path,
                    archive_root=root / "archive",
                    claim_token=token,
                )
            self.assertEqual(raised.exception.code, "invalid_failure")
            result["error"]["retryable"] = False
            task, changed = MOD.record_validation_task_result(
                ledger,
                task,
                result,
                raw_response_path=raw_path,
                archive_root=root / "archive",
                claim_token=token,
            )
            self.assertTrue(changed)
            self.assertEqual(task["requests"][1]["status"], "failed")

    def test_validation_task_records_91_and_cli_finalizes_with_manifests(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)
            task_path = root / "validation_task.json"
            ledger_path = root / "ledger.jsonl"
            summary_path = root / "validation_summary.json"
            archive_root = root / "raw_responses"
            task = self.validation_task()
            ledger = MOD.load_validation_task_ledger(
                ROOT / "scripts" / "mcp_hybrid_bridge.py",
                ROOT / "config" / "mcp_hybrid_policy.json",
                ledger_path,
                task,
                test_mode=True,
            )
            reservation = MOD.reserve_validation_task_with_bridge_ledger(ledger, task)
            MOD.attach_validation_task_reservation(task, reservation, at=FIXED_AT)
            tokens = [self.claim_validation(task, ledger, index) for index in range(91)]
            self.assertEqual(task["status"], "all_claimed")

            for index in range(90):
                status = "partial" if index == 1 else "failed" if index == 2 else "succeeded"
                raw_path = root / "incoming" / f"{index:03d}.json"
                result = self.validation_result(task, index, raw_path, status=status)
                task, changed = MOD.record_validation_task_result(
                    ledger,
                    task,
                    result,
                    raw_response_path=raw_path,
                    archive_root=archive_root,
                    claim_token=tokens[index],
                    recorded_at=FIXED_AT,
                )
                self.assertTrue(changed)

            with self.assertRaises(MOD.OrchestratorError) as raised:
                MOD.finalize_validation_task(
                    ledger,
                    task,
                    summary_path=summary_path,
                    archive_root=archive_root,
                    generated_at=FIXED_AT,
                )
            self.assertEqual(raised.exception.code, "workflow_incomplete")

            last_raw = root / "incoming" / "090.json"
            last_result = self.validation_result(task, 90, last_raw)
            task, _ = MOD.record_validation_task_result(
                ledger,
                task,
                last_result,
                raw_response_path=last_raw,
                archive_root=archive_root,
                claim_token=tokens[90],
                recorded_at=FIXED_AT,
            )
            self.assertEqual(task["status"], "ready_to_finalize")
            self.assertEqual(len(list(archive_root.glob("*.json"))), 91)

            first_archive = Path(task["requests"][0]["rawResponseArchive"]["path"])
            original_payload = first_archive.read_bytes()
            first_archive.write_bytes(b"{}")
            with self.assertRaises(MOD.OrchestratorError) as raised:
                MOD.finalize_validation_task(
                    ledger,
                    task,
                    summary_path=summary_path,
                    archive_root=archive_root,
                    generated_at=FIXED_AT,
                )
            self.assertEqual(raised.exception.code, "raw_response_mismatch")
            first_archive.write_bytes(original_payload)
            MOD.atomic_write_json(task_path, task)

            finalized = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "finalize-validation-task",
                    "--task",
                    str(task_path),
                    "--summary",
                    str(summary_path),
                    "--test-mode",
                    "--bridge",
                    str(ROOT / "scripts" / "mcp_hybrid_bridge.py"),
                    "--policy",
                    str(ROOT / "config" / "mcp_hybrid_policy.json"),
                    "--ledger",
                    str(ledger_path),
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(finalized.returncode, 0, finalized.stderr)
            stored_task = json.loads(task_path.read_text(encoding="utf-8"))
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            self.assertEqual(stored_task["status"], "finalized_with_failures")
            self.assertEqual(summary["schemaVersion"], MOD.VALIDATION_TASK_FINAL_SUMMARY_SCHEMA)
            self.assertEqual(summary["requestCount"], 91)
            self.assertEqual(summary["outcomeCounts"], {"failed": 1, "partial": 1, "succeeded": 89})
            self.assertEqual(set(summary["manifestHashes"]), {
                "claimManifestSha256",
                "resultManifestSha256",
                "rawManifestSha256",
            })
            self.assertEqual(ledger.plan_state(task["taskId"])["status"], "failed")
            self.assert_no_final_authority(stored_task)
            self.assert_no_final_authority(summary)

            inspected = subprocess.run(
                [sys.executable, str(SCRIPT), "inspect-validation-task", "--task", str(task_path)],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(inspected.returncode, 0, inspected.stderr)
            inspection = json.loads(inspected.stdout)
            self.assertEqual(inspection["recorded"], 91)
            self.assertEqual(inspection["rawResponsesArchived"], 91)
            self.assertEqual(inspection["finalization"]["ledgerStatus"], "failed")

    def test_validation_record_cli_is_cross_process_idempotent(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)
            task_path = root / "validation_task.json"
            ledger_path = root / "ledger.jsonl"
            result_path = root / "result.json"
            raw_path = root / "raw.json"
            start_path = root / "start.flag"
            task = self.validation_task()
            ledger = MOD.load_validation_task_ledger(
                ROOT / "scripts" / "mcp_hybrid_bridge.py",
                ROOT / "config" / "mcp_hybrid_policy.json",
                ledger_path,
                task,
                test_mode=True,
            )
            reservation = MOD.reserve_validation_task_with_bridge_ledger(ledger, task)
            MOD.attach_validation_task_reservation(task, reservation, at=FIXED_AT)
            token = self.claim_validation(task, ledger, request_index=1, token="c" * 64)
            result = self.validation_result(task, 1, raw_path)
            MOD.atomic_write_json(task_path, task)
            MOD.atomic_write_json(result_path, result)
            command = [
                sys.executable,
                str(SCRIPT),
                "record-validation-task",
                "--task",
                str(task_path),
                "--result",
                str(result_path),
                "--raw-response",
                str(raw_path),
                "--claim-token",
                token,
                "--test-mode",
                "--bridge",
                str(ROOT / "scripts" / "mcp_hybrid_bridge.py"),
                "--policy",
                str(ROOT / "config" / "mcp_hybrid_policy.json"),
                "--ledger",
                str(ledger_path),
            ]
            outputs = run_parallel_commands([command, command], start_path)
            self.assertTrue(all(item["returncode"] == 0 for item in outputs), outputs)
            changed = [json.loads(item["stdout"])["changed"] for item in outputs]
            self.assertEqual(sorted(changed), [False, True])
            stored = json.loads(task_path.read_text(encoding="utf-8"))
            self.assertEqual(stored["requests"][1]["status"], "succeeded")
            self.assertEqual(
                sum(item["event"] == "result_recorded" for item in stored["history"]),
                1,
            )
            self.assertEqual(len(list((root / "raw_responses").glob("*.json"))), 1)

    def test_budget_pools_need_explicit_flags_and_reserve_atomically(self) -> None:
        with self.assertRaises(MOD.OrchestratorError) as raised:
            self.plan(4, primary_limit=2, conditional_limit=1, emergency_limit=1)
        self.assertEqual(raised.exception.code, "budget_exceeded")

        with self.assertRaises(MOD.OrchestratorError):
            self.plan(4, primary_limit=2, conditional_limit=1, emergency_limit=1, enable_conditional=True)

        workflow = self.plan(
            4,
            primary_limit=2,
            conditional_limit=1,
            emergency_limit=1,
            enable_conditional=True,
            enable_emergency=True,
        )
        self.assertEqual([packet["pool"] for packet in workflow["packets"]], ["primary", "primary", "conditional", "emergency"])
        self.assertEqual(workflow["budget"]["plannedCalls"], 4)
        ledger = FakeLedger()
        result = MOD.reserve_with_bridge_ledger(ledger, workflow)
        self.assertEqual(result["event"]["calls"], 4)
        self.assertEqual(len(ledger.reservations), 1)
        self.assertTrue(ledger.reservations[0]["allowEmergency"])
        self.assertEqual({row["pool"] for row in ledger.reservations[0]["requests"]}, {"primary", "conditional", "emergency"})

        with self.assertRaises(MOD.OrchestratorError) as raised:
            self.plan(1, primary_limit=301)
        self.assertEqual(raised.exception.code, "invalid_budget")

    def test_only_keepa_is_validated_shadow_and_pending_is_test_only(self) -> None:
        workflow = self.plan(1)
        self.assertEqual(workflow["toolRouting"]["contractState"], "validated_shadow")
        self.assertTrue(workflow["toolRouting"]["reservationEligible"])

        with self.assertRaises(MOD.OrchestratorError) as raised:
            self.plan(1, tool="asin_detail")
        self.assertEqual(raised.exception.code, "tool_pending")

        pending = self.plan(1, tool="asin_detail", test_only_allow_pending_tool=True)
        self.assertFalse(pending["toolRouting"]["reservationEligible"])
        self.assertTrue(pending["toolRouting"]["testOnly"])
        with self.assertRaises(MOD.OrchestratorError):
            MOD.reserve_with_bridge_ledger(FakeLedger(test_mode=True), pending)

        test_reserved = self.plan(
            1,
            tool="asin_detail",
            test_only_allow_pending_tool=True,
            test_only_reserve_pending=True,
        )
        self.assertTrue(test_reserved["toolRouting"]["reservationEligible"])
        self.assertTrue(test_reserved["toolRouting"]["testOnlyReservation"])
        self.assertFalse(test_reserved["finalAuthority"])
        with self.assertRaises(MOD.OrchestratorError) as raised:
            MOD.reserve_with_bridge_ledger(FakeLedger(), test_reserved)
        self.assertEqual(raised.exception.code, "test_mode_required")
        test_ledger = FakeLedger(test_mode=True)
        reservation = MOD.reserve_with_bridge_ledger(test_ledger, test_reserved)
        self.assertEqual(reservation["event"]["calls"], 1)
        self.assertEqual(len(test_ledger.reservations), 1)
        self.assertFalse(test_reserved["packets"][0]["finalAuthority"])

        for pending_tool in ("asin_detail", "asin_sales_trend", "traffic_listing_stat"):
            pending_workflow = self.plan(
                1,
                tool=pending_tool,
                test_only_allow_pending_tool=True,
                test_only_reserve_pending=True,
            )
            self.assertNotIn("contractState", pending_workflow["packets"][0]["request"])
            self.assertEqual(pending_workflow["packets"][0]["request"]["marketplace"], "US")
            self.assertEqual(pending_workflow["packets"][0]["request"]["asin"], "B0AAAA0001")

        with self.assertRaises(MOD.OrchestratorError) as raised:
            self.plan(
                1,
                tool="product_research",
                test_only_allow_pending_tool=True,
                test_only_reserve_pending=True,
            )
        self.assertEqual(raised.exception.code, "tool_requires_discovery_planner")

        for disabled in ("competitor_lookup", "traffic_extend"):
            with self.assertRaises(MOD.OrchestratorError) as raised:
                self.plan(1, tool=disabled, test_only_allow_pending_tool=True)
            self.assertEqual(raised.exception.code, "tool_disabled")

    def test_request_hash_and_asin_mismatch_fail_closed(self) -> None:
        workflow = self.plan(1)
        ledger = self.reserve(workflow)
        token = self.claim(workflow, ledger)
        bad_hash = self.result_for("partial", workflow, 0)
        bad_hash["requestHash"] = "0" * 64
        with self.assertRaises(MOD.OrchestratorError) as raised:
            MOD.record_result(workflow, bad_hash, claim_token=token)
        self.assertEqual(raised.exception.code, "request_hash_mismatch")
        self.assertEqual(workflow["packets"][0]["attemptsRecorded"], 0)

        bad_asin = self.result_for("partial", workflow, 0)
        bad_asin["actualAsin"] = "B0ZZZZ9999"
        bad_asin["fields"]["asin"] = "B0ZZZZ9999"
        with self.assertRaises(MOD.OrchestratorError) as raised:
            MOD.record_result(workflow, bad_asin, claim_token=token)
        self.assertEqual(raised.exception.code, "asin_mismatch")
        self.assertEqual(workflow["packets"][0]["attemptsRecorded"], 0)

        authority_claim = self.result_for("partial", workflow, 0)
        authority_claim["fields"]["dimensions"] = {"finalAuthority": True}
        authority_claim["missingFields"].remove("dimensions")
        authority_claim["fieldProvenance"]["dimensions"] = {
            "sourceTool": "keepa_info",
            "sourcePath": "data.dimensions",
            "semantics": "shadow_advisory",
        }
        with self.assertRaises(MOD.OrchestratorError) as raised:
            MOD.record_result(workflow, authority_claim, claim_token=token)
        self.assertEqual(raised.exception.code, "authority_violation")

    def test_partial_and_failed_packets_finalize_without_false_authority(self) -> None:
        workflow = self.plan(2)
        ledger = self.reserve(workflow)
        token0 = self.claim(workflow, ledger, 0)
        workflow, changed = MOD.record_result(
            workflow,
            self.result_for("partial", workflow, 0),
            claim_token=token0,
        )
        self.assertTrue(changed)
        token1 = self.claim(workflow, ledger, 1)
        workflow, changed = MOD.record_result(
            workflow,
            self.result_for("failed", workflow, 1),
            claim_token=token1,
        )
        self.assertTrue(changed)
        self.assertEqual(workflow["status"], "ready_to_finalize")

        workflow, bundle = MOD.finalize_workflow(workflow, ledger=ledger)
        self.assertEqual(workflow["status"], "finalized_with_failures")
        self.assertEqual(len(bundle["evidence"]), 1)
        self.assertEqual(bundle["evidence"][0]["targetAsin"], workflow["packets"][0]["targetAsin"])
        self.assertNotIn(workflow["packets"][1]["targetAsin"], {row["targetAsin"] for row in bundle["evidence"]})
        self.assertTrue(bundle["evidence"][0]["fallbackRequired"])
        self.assertTrue(bundle["evidence"][0]["browserFallbackRequired"])
        self.assertFalse(bundle["evidence"][0]["usableForFinal"])
        self.assertEqual(bundle["outcomeCounts"], {"succeeded": 0, "partial": 1, "failed": 1})
        self.assertEqual(ledger.statuses[-1]["status"], "failed")
        self.assert_no_final_authority(workflow)
        self.assert_no_final_authority(bundle)

    def test_failed_packet_is_a_structured_outcome_not_evidence(self) -> None:
        workflow = self.plan(1)
        ledger = self.reserve(workflow)
        token = self.claim(workflow, ledger)
        workflow, _ = MOD.record_result(
            workflow,
            self.result_for("failed", workflow, 0),
            claim_token=token,
        )
        workflow, bundle = MOD.finalize_workflow(workflow, ledger=ledger)
        self.assertEqual(workflow["status"], "finalized_with_failures")
        self.assertEqual(bundle["evidence"], [])

        claimed_workflow = self.plan(1)
        claimed_ledger = self.reserve(claimed_workflow)
        self.claim(claimed_workflow, claimed_ledger)
        MOD.reconcile_claim_as_failed(
            claimed_ledger,
            claimed_workflow,
            packet_id=claimed_workflow["packets"][0]["packetId"],
            at=FIXED_AT,
        )
        self.assertEqual(claimed_workflow["packets"][0]["status"], "failed")
        self.assertEqual(claimed_workflow["packets"][0]["attemptsRecorded"], 1)
        self.assertFalse(bundle["importEligible"])
        self.assertEqual(bundle["packetOutcomes"][0]["status"], "failed")
        self.assertEqual(bundle["packetOutcomes"][0]["error"]["code"], "provider_timeout")

    def test_pause_resume_and_single_attempt_are_durable(self) -> None:
        workflow = self.plan(1)
        ledger = self.reserve(workflow)
        token = self.claim(workflow, ledger)
        MOD.pause_workflow(workflow, "operator pause", at=FIXED_AT)
        with self.assertRaises(MOD.OrchestratorError) as raised:
            MOD.record_result(workflow, self.result_for("partial", workflow, 0), claim_token=token)
        self.assertEqual(raised.exception.code, "workflow_paused")

        MOD.resume_workflow(workflow, at=FIXED_AT)
        result = self.result_for("partial", workflow, 0)
        workflow, changed = MOD.record_result(workflow, result, claim_token=token, recorded_at=FIXED_AT)
        self.assertTrue(changed)
        workflow, changed = MOD.record_result(workflow, result, claim_token=token, recorded_at=FIXED_AT)
        self.assertFalse(changed)

        replacement = copy.deepcopy(result)
        replacement["rawResponse"]["sha256"] = "d" * 64
        with self.assertRaises(MOD.OrchestratorError) as raised:
            MOD.record_result(workflow, replacement, claim_token=token)
        self.assertEqual(raised.exception.code, "retry_forbidden")
        self.assertEqual(workflow["packets"][0]["attemptsRecorded"], 1)
        self.assertFalse(workflow["packets"][0]["attemptPolicy"]["automaticRetry"])

    def test_reservation_claim_token_and_ttl_are_mandatory(self) -> None:
        unreserved = self.plan(1)
        with self.assertRaises(MOD.OrchestratorError) as raised:
            MOD.record_result(
                unreserved,
                self.result_for("partial", unreserved, 0),
                claim_token="x" * 64,
            )
        self.assertEqual(raised.exception.code, "reservation_required")

        workflow = self.plan(1)
        ledger = self.reserve(workflow)
        token = self.claim(workflow, ledger)
        with self.assertRaises(MOD.OrchestratorError) as raised:
            self.claim(workflow, ledger)
        self.assertEqual(raised.exception.code, "attempt_already_started")

        with self.assertRaises(MOD.OrchestratorError) as raised:
            MOD.record_result(
                workflow,
                self.result_for("partial", workflow, 0),
                claim_token="wrong" * 16,
            )
        self.assertEqual(raised.exception.code, "claim_token_mismatch")

        over_ttl = self.result_for("partial", workflow, 0)
        over_ttl["rawResponse"]["expiresAt"] = "2026-07-29T08:00:02Z"
        with self.assertRaises(MOD.OrchestratorError) as raised:
            MOD.record_result(workflow, over_ttl, claim_token=token)
        self.assertEqual(raised.exception.code, "ttl_exceeded")

        before_claim = self.result_for("partial", workflow, 0)
        before_claim["startedAt"] = "2026-07-29T01:29:59Z"
        with self.assertRaises(MOD.OrchestratorError) as raised:
            MOD.record_result(workflow, before_claim, claim_token=token)
        self.assertEqual(raised.exception.code, "execution_before_claim")

    def test_terminal_result_is_revalidated_before_finalize(self) -> None:
        workflow = self.plan(1)
        ledger = self.reserve(workflow)
        token = self.claim(workflow, ledger)
        workflow, _ = MOD.record_result(
            workflow,
            self.result_for("partial", workflow, 0),
            claim_token=token,
        )
        workflow["packets"][0]["result"]["fields"]["price"] = 0.01
        with self.assertRaises(MOD.OrchestratorError) as raised:
            MOD.finalize_workflow(workflow, ledger=ledger)
        self.assertEqual(raised.exception.code, "result_integrity")

    def test_idempotent_or_terminal_reservation_cannot_reopen_execution(self) -> None:
        workflow = self.plan(1)
        ledger = FakeLedger()
        reservation = MOD.reserve_with_bridge_ledger(ledger, workflow)
        reservation["idempotent"] = True
        with self.assertRaises(MOD.OrchestratorError) as raised:
            MOD.attach_reservation(workflow, reservation, at=FIXED_AT)
        self.assertEqual(raised.exception.code, "reservation_not_new")

        reservation["idempotent"] = False
        reservation["currentStatus"] = "failed"
        with self.assertRaises(MOD.OrchestratorError) as raised:
            MOD.attach_reservation(workflow, reservation, at=FIXED_AT)
        self.assertEqual(raised.exception.code, "reservation_not_new")

    def test_explicit_recovery_closes_write_interruptions_without_retry(self) -> None:
        workflow = self.plan(1)
        ledger = FakeLedger()
        MOD.reserve_with_bridge_ledger(ledger, workflow)
        MOD.reconcile_reservation(ledger, workflow, at=FIXED_AT)
        self.assertEqual(workflow["status"], "reserved")
        self.assertTrue(workflow["reservation"]["reconciled"])

        packet_id = workflow["packets"][0]["packetId"]
        ledger.claim_plan_request(
            plan_id=workflow["workflowId"],
            request_id=packet_id,
            claim_id="claim-interrupted",
            at=FIXED_AT,
        )
        MOD.reconcile_claim_as_failed(ledger, workflow, packet_id=packet_id, at=FIXED_AT)
        self.assertEqual(workflow["status"], "ready_to_finalize")
        self.assertEqual(workflow["packets"][0]["status"], "failed")
        self.assertEqual(workflow["packets"][0]["result"]["error"]["code"], "claim_recovery_discarded")
        self.assertFalse(workflow["packets"][0]["result"]["error"]["retryable"])
        workflow, bundle = MOD.finalize_workflow(workflow, ledger=ledger)
        self.assertEqual(workflow["status"], "finalized_with_failures")
        self.assertEqual(bundle["evidence"], [])

    def test_packet_tool_must_match_workflow_route(self) -> None:
        workflow = self.plan(1)
        workflow["packets"][0]["tool"] = "asin_detail"
        with self.assertRaises(MOD.OrchestratorError) as raised:
            MOD.validate_workflow(workflow)
        self.assertEqual(raised.exception.code, "invalid_workflow")

    def test_bridge_adapter_never_falls_back_to_partial_reservations(self) -> None:
        with self.assertRaises(MOD.OrchestratorError) as raised:
            MOD.reserve_with_bridge_ledger(object(), self.plan(1))
        self.assertEqual(raised.exception.code, "reserve_plan_unavailable")

    def test_current_bridge_atomic_api_accepts_and_closes_the_workflow(self) -> None:
        workflow = self.plan(1)
        with TemporaryDirectory() as temp:
            ledger = MOD.load_bridge_ledger(
                ROOT / "scripts" / "mcp_hybrid_bridge.py",
                ROOT / "config" / "mcp_hybrid_policy.json",
                Path(temp) / "ledger.jsonl",
                workflow,
            )
            reservation = MOD.reserve_with_bridge_ledger(ledger, workflow)
            self.assertFalse(reservation["idempotent"])
            MOD.attach_reservation(workflow, reservation, at=FIXED_AT)
            token = self.claim(workflow, ledger)
            workflow, _ = MOD.record_result(
                workflow,
                self.result_for("partial", workflow, 0),
                claim_token=token,
            )
            workflow, bundle = MOD.finalize_workflow(workflow, ledger=ledger)
            self.assertEqual(workflow["status"], "finalized")
            self.assertEqual(bundle["outcomeCounts"]["partial"], 1)
            self.assertEqual(workflow["finalization"]["ledgerStatus"], "succeeded")

    def test_current_bridge_test_mode_atomically_accounts_for_pending_tool(self) -> None:
        workflow = self.plan(
            1,
            tool="asin_detail",
            test_only_allow_pending_tool=True,
            test_only_reserve_pending=True,
        )
        with TemporaryDirectory() as temp:
            ledger = MOD.load_bridge_ledger(
                ROOT / "scripts" / "mcp_hybrid_bridge.py",
                ROOT / "config" / "mcp_hybrid_policy.json",
                Path(temp) / "ledger.jsonl",
                workflow,
                test_mode=True,
            )
            reservation = MOD.reserve_with_bridge_ledger(ledger, workflow)
            self.assertFalse(reservation["idempotent"])
            self.assertEqual(reservation["event"]["calls"], 1)
            self.assertEqual(reservation["event"]["requests"][0]["tool"], "asin_detail")
            MOD.attach_reservation(workflow, reservation, at=FIXED_AT)
            token = self.claim(workflow, ledger)
            self.assertGreaterEqual(len(token), 32)
            self.assertEqual(workflow["packets"][0]["status"], "claimed")
            self.assertFalse(workflow["finalAuthority"])


if __name__ == "__main__":
    unittest.main()
