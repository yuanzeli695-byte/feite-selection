from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import subprocess
import sys
import threading
import time
from urllib.parse import urlencode
import unittest
from http.client import HTTPConnection
from pathlib import Path
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[1]
BRIDGE_PATH = ROOT / "scripts" / "mcp_hybrid_bridge.py"
SPEC = importlib.util.spec_from_file_location("mcp_hybrid_bridge_under_test", BRIDGE_PATH)
if SPEC is None or SPEC.loader is None:  # pragma: no cover
    raise RuntimeError(f"Cannot load bridge module from {BRIDGE_PATH}")
BRIDGE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = BRIDGE
SPEC.loader.exec_module(BRIDGE)


FIXTURE_PATH = ROOT / "tests" / "fixtures_mcp_hybrid_valid_bundle.json"
POLICY_PATH = ROOT / "config" / "mcp_hybrid_policy.json"
BASELINE_PATH = ROOT / "docs" / "mcp_hybrid_original_baseline_20260728.json"


def load_fixture() -> dict:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def make_bridge(temp_root: Path, *, run_budget: int | None = None, test_mode: bool = False) -> object:
    project_root = temp_root / "project"
    project_root.mkdir(parents=True, exist_ok=True)
    config = BRIDGE.BridgeConfig(
        project_root=project_root,
        output_root=temp_root / "run",
        run_id="fixture-run",
        token="fixture-token",
        policy_path=POLICY_PATH,
        run_budget=run_budget,
        test_mode=test_mode,
    )
    return BRIDGE.McpHybridBridge(config)


def reservation_request(
    request_id: str,
    hash_character: str,
    *,
    calls: int = 1,
    pool: str = "primary",
    tool: str = "keepa_info",
    asin_count: int = 1,
) -> dict:
    return {
        "id": request_id,
        "tool": tool,
        "requestHash": hash_character * 64,
        "asinCount": asin_count,
        "calls": calls,
        "pool": pool,
    }


def run_parallel_python(code: str, arguments: list[list[str]], start_path: Path) -> list[dict]:
    processes = [
        subprocess.Popen(
            [sys.executable, "-c", code, *args],
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        for args in arguments
    ]
    time.sleep(0.2)
    start_path.write_text("go\n", encoding="ascii")
    outputs = []
    for process in processes:
        stdout, stderr = process.communicate(timeout=15)
        if process.returncode != 0:
            raise AssertionError(f"child failed ({process.returncode}): {stderr}\n{stdout}")
        outputs.append(json.loads(stdout.strip()))
    return outputs


class McpHybridBridgeTests(unittest.TestCase):
    def test_policy_is_shadow_only_and_health_is_non_authoritative(self) -> None:
        with TemporaryDirectory() as temp:
            bridge = make_bridge(Path(temp))
            health = bridge.health()
            self.assertEqual(health["mode"], "shadow")
            self.assertEqual(health["version"], "0.3.2")
            self.assertEqual(health["policyVersion"], "0.3.1")
            self.assertFalse(health["outboundMcpEnabled"])
            self.assertFalse(health["finalAuthority"])
            self.assertFalse(health["testMode"])
            self.assertEqual(health["budget"]["monthlyUsed"], 0)
            self.assertEqual(health["budget"]["dailyHardLimit"], 500)
            self.assertEqual(health["budget"]["dailyPools"]["primary"]["limit"], 300)
            self.assertEqual(health["budget"]["dailyPools"]["conditional"]["limit"], 100)
            self.assertEqual(health["budget"]["dailyPools"]["emergency"]["limit"], 100)
            self.assertEqual(bridge.policy["tools"]["keepa_info"]["validationStatus"], "validated_shadow")
            self.assertTrue(bridge.policy["tools"]["keepa_info"]["reservationEnabled"])
            for tool in ("competitor_lookup", "traffic_extend"):
                self.assertFalse(bridge.policy["tools"][tool]["enabled"])
                self.assertEqual(bridge.policy["tools"][tool]["validationStatus"], "blocked")
            for tool in ("product_research", "asin_detail", "asin_sales_trend", "traffic_listing_stat"):
                self.assertEqual(bridge.policy["tools"][tool]["validationStatus"], "pending")
                self.assertFalse(bridge.policy["tools"][tool]["reservationEnabled"])
            self.assertTrue(bridge.policy["tools"]["product_research"]["testReservationEnabled"])

    def test_import_lookup_is_fresh_and_idempotent(self) -> None:
        with TemporaryDirectory() as temp:
            bridge = make_bridge(Path(temp))
            bundle = load_fixture()
            first = bridge.store.import_bundle(bundle)
            second = bridge.store.import_bundle(bundle)
            self.assertEqual(first["imported"], 1)
            self.assertEqual(second["imported"], 0)
            self.assertEqual(second["duplicates"], 1)
            result = bridge.store.lookup("B0AAAA0001", at=BRIDGE.parse_timestamp("2026-07-28T03:00:00Z", "test"))
            self.assertEqual(result["evidenceCount"], 1)
            self.assertTrue(result["results"][0]["usableForRanking"])
            self.assertTrue(result["results"][0]["usableForShadow"])
            self.assertFalse(result["results"][0]["browserFallbackRequired"])
            self.assertFalse(result["results"][0]["usableForFinal"])
            self.assertTrue(result["mergedRanking"]["usableForRanking"])
            self.assertEqual(result["mergedRanking"]["fields"]["price"], 19.99)
            self.assertFalse(result["mergedRanking"]["usableForFinal"])
            self.assertFalse(result["mergedRanking"]["finalAuthority"])

    def test_evidence_expiry_cannot_exceed_tool_ttl(self) -> None:
        with TemporaryDirectory() as temp:
            bridge = make_bridge(Path(temp))
            bundle = load_fixture()
            bundle["evidence"][0]["response"]["expiresAt"] = "2099-07-28T07:00:00Z"
            with self.assertRaises(BRIDGE.BridgeError) as raised:
                bridge.store.import_bundle(bundle)
            self.assertIn("TTL", str(raised.exception))

    def test_same_evidence_id_cannot_be_overwritten(self) -> None:
        with TemporaryDirectory() as temp:
            bridge = make_bridge(Path(temp))
            bundle = load_fixture()
            bridge.store.import_bundle(bundle)
            changed = copy.deepcopy(bundle)
            changed["evidence"][0]["fields"]["price"] = 20.0
            with self.assertRaises(BRIDGE.BridgeError) as raised:
                bridge.store.import_bundle(changed)
            self.assertEqual(raised.exception.status, 409)
            self.assertEqual(raised.exception.stage, "evidence_conflict")

    def test_stale_and_mismatched_evidence_fail_closed(self) -> None:
        with TemporaryDirectory() as temp:
            bridge = make_bridge(Path(temp))
            stale = load_fixture()
            stale["evidence"][0]["evidenceId"] = "fixture-stale-v1"
            stale["evidence"][0]["response"]["expiresAt"] = "2026-07-28T02:00:00Z"
            bridge.store.import_bundle(stale)
            mismatch = load_fixture()
            mismatch["evidence"][0]["evidenceId"] = "fixture-mismatch-v1"
            mismatch["evidence"][0]["actualAsin"] = "B0AAAA0002"
            bridge.store.import_bundle(mismatch)
            result = bridge.store.lookup("B0AAAA0001", at=BRIDGE.parse_timestamp("2026-07-28T03:00:00Z", "test"))
            self.assertEqual(result["evidenceCount"], 2)
            self.assertTrue(all(row["usableForRanking"] is False for row in result["results"]))
            self.assertTrue(all(row["usableForShadow"] is False for row in result["results"]))
            reasons = {reason for row in result["results"] for reason in row["fallbackReasons"]}
            self.assertIn("stale", reasons)
            self.assertIn("asin_mismatch", reasons)
            self.assertFalse(result["mergedRanking"]["usableForRanking"])
            self.assertEqual(result["mergedRanking"]["fields"], {})

    def test_field_level_merge_uses_fresh_exact_provenance_and_requires_browser_fallback(self) -> None:
        with TemporaryDirectory() as temp:
            bridge = make_bridge(Path(temp))
            older = load_fixture()
            newer = copy.deepcopy(older)
            row = newer["evidence"][0]
            row["evidenceId"] = "fixture-keepa-b0aaaa0001-newer-v1"
            row["response"]["capturedAt"] = "2026-07-28T02:00:00Z"
            row["response"]["expiresAt"] = "2026-07-28T08:00:00Z"
            row["fields"]["price"] = 18.5
            row["fields"]["childMonthlySales"] = None
            row["missingFields"] = ["childMonthlySales"]
            bridge.store.import_bundle(older)
            bridge.store.import_bundle(newer)

            result = bridge.store.lookup(
                "B0AAAA0001", at=BRIDGE.parse_timestamp("2026-07-28T03:00:00Z", "test")
            )
            merged = result["mergedRanking"]
            self.assertTrue(merged["usableForRanking"])
            self.assertTrue(merged["browserFallbackRequired"])
            self.assertFalse(merged["usableForFinal"])
            self.assertEqual(merged["fields"]["price"], 18.5)
            self.assertEqual(merged["fields"]["childMonthlySales"], 100)
            self.assertEqual(
                merged["fieldSources"]["price"]["evidenceId"],
                "fixture-keepa-b0aaaa0001-newer-v1",
            )
            self.assertEqual(
                merged["fieldSources"]["childMonthlySales"]["evidenceId"],
                "fixture-keepa-b0aaaa0001-v1",
            )

    def test_provenance_mismatch_is_rejected_and_blocked_tool_never_ranks(self) -> None:
        with TemporaryDirectory() as temp:
            bridge = make_bridge(Path(temp))
            invalid = load_fixture()
            invalid["evidence"][0]["fieldProvenance"]["price"]["sourceTool"] = "competitor_lookup"
            with self.assertRaises(BRIDGE.BridgeError):
                bridge.store.import_bundle(invalid)

            blocked = load_fixture()
            blocked_row = blocked["evidence"][0]
            blocked_row["evidenceId"] = "fixture-blocked-competitor-v1"
            blocked_row["tool"]["name"] = "competitor_lookup"
            for source in blocked_row["fieldProvenance"].values():
                source["sourceTool"] = "competitor_lookup"
            bridge.store.import_bundle(blocked)
            result = bridge.store.lookup(
                "B0AAAA0001", at=BRIDGE.parse_timestamp("2026-07-28T03:00:00Z", "test")
            )
            self.assertFalse(result["results"][0]["usableForRanking"])
            self.assertIn("tool_not_rankable:blocked", result["results"][0]["fallbackReasons"])
            self.assertFalse(result["mergedRanking"]["usableForRanking"])

    def test_pending_tool_ranks_only_in_explicit_test_mode(self) -> None:
        pending = load_fixture()
        row = pending["evidence"][0]
        row["evidenceId"] = "fixture-pending-asin-detail-v1"
        row["tool"]["name"] = "asin_detail"
        for source in row["fieldProvenance"].values():
            source["sourceTool"] = "asin_detail"
        with TemporaryDirectory() as temp:
            normal = make_bridge(Path(temp) / "normal")
            normal.store.import_bundle(pending)
            normal_result = normal.store.lookup(
                "B0AAAA0001", at=BRIDGE.parse_timestamp("2026-07-28T03:00:00Z", "test")
            )
            self.assertFalse(normal_result["mergedRanking"]["usableForRanking"])
            with self.assertRaises(BRIDGE.BridgeError):
                normal.ledger.reserve_plan(
                    plan_id="pending-formal",
                    requests=[reservation_request("pending", "9", tool="asin_detail")],
                )
        with TemporaryDirectory() as temp:
            test_bridge = make_bridge(Path(temp) / "test", test_mode=True)
            test_bridge.store.import_bundle(pending)
            test_result = test_bridge.store.lookup(
                "B0AAAA0001", at=BRIDGE.parse_timestamp("2026-07-28T03:00:00Z", "test")
            )
            self.assertTrue(test_result["mergedRanking"]["usableForRanking"])
            self.assertFalse(test_result["mergedRanking"]["usableForFinal"])
            reserved = test_bridge.ledger.reserve_plan(
                plan_id="pending-test",
                requests=[reservation_request("pending", "9", tool="asin_detail")],
            )
            self.assertEqual(reserved["summary"]["runUsed"], 1)

    def test_ledger_enforces_run_budget_and_operational_cap(self) -> None:
        with TemporaryDirectory() as temp:
            bridge = make_bridge(Path(temp), run_budget=2)
            request_hash = "c" * 64
            bridge.ledger.reserve(tool="keepa_info", request_hash=request_hash, asin_count=2, calls=2)
            with self.assertRaises(BRIDGE.BridgeError) as raised:
                bridge.ledger.reserve(tool="keepa_info", request_hash="d" * 64, asin_count=1)
            self.assertEqual(raised.exception.status, 429)
            self.assertEqual(raised.exception.stage, "budget")

            policy = {
                "officialMonthlyLimit": 10,
                "operationalMonthlyCap": 3,
                "defaultRunBudget": 10,
            }
            ledger = BRIDGE.CallLedger(Path(temp) / "small-ledger.jsonl", run_id="r", policy=policy)
            ledger.reserve(tool="x", request_hash="e" * 64, asin_count=1, calls=3)
            with self.assertRaises(BRIDGE.BridgeError):
                ledger.reserve(tool="x", request_hash="f" * 64, asin_count=1)

    def test_monthly_ledger_is_shared_across_runs(self) -> None:
        with TemporaryDirectory() as temp:
            ledger_path = Path(temp) / "shared-ledger.jsonl"
            policy = {
                "officialMonthlyLimit": 10,
                "operationalMonthlyCap": 3,
                "defaultRunBudget": 10,
            }
            first = BRIDGE.CallLedger(ledger_path, run_id="run-a", policy=policy)
            second = BRIDGE.CallLedger(ledger_path, run_id="run-b", policy=policy)
            first.reserve(tool="x", request_hash="1" * 64, asin_count=2, calls=2)
            self.assertEqual(second.summary()["monthlyUsed"], 2)
            with self.assertRaises(BRIDGE.BridgeError):
                second.reserve(tool="x", request_hash="2" * 64, asin_count=2, calls=2)

    def test_reserve_plan_is_atomic_idempotent_and_terminal_status_does_not_retry(self) -> None:
        with TemporaryDirectory() as temp:
            ledger_path = Path(temp) / "ledger.jsonl"
            policy = BRIDGE.load_policy(POLICY_PATH)
            ledger = BRIDGE.CallLedger(ledger_path, run_id="plan-run", policy=policy, run_budget=3)
            requests = [reservation_request("keepa-a", "a", calls=2)]
            first = ledger.reserve_plan(plan_id="plan-1", requests=requests)
            duplicate = ledger.reserve_plan(plan_id="plan-1", requests=requests)
            self.assertFalse(first["idempotent"])
            self.assertTrue(duplicate["idempotent"])
            self.assertEqual(
                first["event"]["requestHash"],
                BRIDGE.payload_sha256(
                    {
                        "runId": "plan-run",
                        "planId": "plan-1",
                        "requests": requests,
                        "allowEmergency": False,
                    }
                ),
            )
            self.assertEqual(duplicate["currentStatus"], "reserved")
            self.assertEqual(ledger.summary()["runUsed"], 2)
            self.assertEqual(len(ledger_path.read_text(encoding="utf-8").splitlines()), 1)

            changed = [reservation_request("keepa-a", "b", calls=2)]
            with self.assertRaises(BRIDGE.BridgeError) as conflict:
                ledger.reserve_plan(plan_id="plan-1", requests=changed)
            self.assertEqual(conflict.exception.status, 409)

            failed = ledger.mark_plan_status(plan_id="plan-1", status="failed", details={"code": "timeout"})
            duplicate_failed = ledger.mark_plan_status(
                plan_id="plan-1", status="failed", details={"code": "timeout"}
            )
            self.assertFalse(failed["idempotent"])
            self.assertTrue(duplicate_failed["idempotent"])
            after_failure = ledger.reserve_plan(plan_id="plan-1", requests=requests)
            self.assertTrue(after_failure["idempotent"])
            self.assertEqual(after_failure["currentStatus"], "failed")
            self.assertEqual(after_failure["summary"]["statusCalls"]["failed"], 2)
            self.assertEqual(after_failure["summary"]["monthlyUsed"], 2)
            with self.assertRaises(BRIDGE.BridgeError):
                ledger.mark_plan_status(plan_id="plan-1", status="succeeded", details={})

    def test_sealed_validation_run_allows_exactly_91_requests_and_blocks_every_append_path(self) -> None:
        with TemporaryDirectory() as temp:
            ledger_path = Path(temp) / "shared-ledger.jsonl"
            policy = BRIDGE.load_policy(POLICY_PATH)
            legacy = BRIDGE.CallLedger(
                ledger_path,
                run_id="legacy-run-budget-50",
                policy=policy,
                run_budget=50,
            )
            legacy.reserve(tool="keepa_info", request_hash="0" * 64, asin_count=1)

            ledger = BRIDGE.CallLedger(
                ledger_path,
                run_id="mcp-validate-task-fixture",
                policy=policy,
                run_budget=100,
                test_mode=True,
            )
            requests = [
                reservation_request(
                    "task-product-research-001",
                    "1",
                    tool="product_research",
                    asin_count=0,
                )
            ]
            for tool, hash_character in (
                ("asin_detail", "2"),
                ("asin_sales_trend", "3"),
                ("traffic_listing_stat", "4"),
            ):
                requests.extend(
                    reservation_request(
                        f"task-{tool.replace('_', '-')}-{index:02d}",
                        hash_character,
                        tool=tool,
                    )
                    for index in range(30)
                )

            reserved = ledger.reserve_plan(
                plan_id="validation-plan-91",
                requests=requests,
                seal_run=True,
            )
            self.assertEqual(len(requests), 91)
            self.assertEqual(reserved["event"]["calls"], 91)
            self.assertTrue(reserved["event"]["sealedRun"])
            self.assertEqual(reserved["event"]["authorizedCalls"], 91)
            self.assertEqual(reserved["event"]["taskBudget"], 100)
            self.assertEqual(reserved["event"]["sealedReserveCalls"], 9)
            self.assertEqual(reserved["summary"]["runUsed"], 91)
            self.assertEqual(reserved["summary"]["monthlyUsed"], 92)
            self.assertEqual(legacy.summary()["runUsed"], 1)
            self.assertEqual(legacy.summary()["monthlyUsed"], 92)

            duplicate = ledger.reserve_plan(
                plan_id="validation-plan-91",
                requests=requests,
                seal_run=True,
            )
            self.assertTrue(duplicate["idempotent"])
            self.assertEqual(duplicate["summary"]["runUsed"], 91)

            with self.assertRaises(BRIDGE.BridgeError) as second_plan:
                ledger.reserve_plan(
                    plan_id="validation-plan-92",
                    requests=[reservation_request("extra-request", "5", tool="asin_detail")],
                )
            self.assertEqual(second_plan.exception.status, 409)
            self.assertEqual(second_plan.exception.stage, "budget_sealed")

            with self.assertRaises(BRIDGE.BridgeError) as legacy_append:
                ledger.reserve(tool="asin_detail", request_hash="6" * 64, asin_count=1)
            self.assertEqual(legacy_append.exception.status, 409)
            self.assertEqual(legacy_append.exception.stage, "budget_sealed")

            changed = copy.deepcopy(requests)
            changed[-1]["requestHash"] = "7" * 64
            with self.assertRaises(BRIDGE.BridgeError) as changed_plan:
                ledger.reserve_plan(
                    plan_id="validation-plan-91",
                    requests=changed,
                    seal_run=True,
                )
            self.assertEqual(changed_plan.exception.status, 409)
            self.assertEqual(changed_plan.exception.stage, "budget_conflict")

            with self.assertRaises(BRIDGE.BridgeError) as no_claims:
                ledger.mark_plan_status(plan_id="validation-plan-91", status="succeeded", details={})
            self.assertEqual(no_claims.exception.stage, "ledger_incomplete")

            for index, request in enumerate(requests[:90]):
                ledger.claim_plan_request(
                    plan_id="validation-plan-91",
                    request_id=request["id"],
                    claim_id=f"validation-claim-{index:02d}",
                )
            with self.assertRaises(BRIDGE.BridgeError) as ninety_claims:
                ledger.mark_plan_status(plan_id="validation-plan-91", status="succeeded", details={})
            self.assertEqual(ninety_claims.exception.stage, "ledger_incomplete")
            ledger.claim_plan_request(
                plan_id="validation-plan-91",
                request_id=requests[90]["id"],
                claim_id="validation-claim-90",
            )
            self.assertEqual(ledger.summary()["claimedCount"], 91)
            with self.assertRaises(BRIDGE.BridgeError) as extra_claim:
                ledger.claim_plan_request(
                    plan_id="validation-plan-91",
                    request_id="extra-request",
                    claim_id="validation-claim-92",
                )
            self.assertEqual(extra_claim.exception.status, 404)
            self.assertFalse(extra_claim.exception.details["executionAllowed"])

            with self.assertRaises(BRIDGE.BridgeError) as incomplete_details:
                ledger.mark_plan_status(
                    plan_id="validation-plan-91",
                    status="succeeded",
                    details={
                        "requestCount": 91,
                        "authorizedCalls": 91,
                        "rawResponseArchiveCount": 90,
                        "outcomeCounts": {"succeeded": 91, "partial": 0, "failed": 0},
                        "claimManifestSha256": "a" * 64,
                        "resultManifestSha256": "b" * 64,
                        "rawManifestSha256": "c" * 64,
                    },
                )
            self.assertEqual(incomplete_details.exception.stage, "ledger")

            with self.assertRaises(BRIDGE.BridgeError) as status_conflict:
                ledger.mark_plan_status(
                    plan_id="validation-plan-91",
                    status="succeeded",
                    details={
                        "requestCount": 91,
                        "authorizedCalls": 91,
                        "rawResponseArchiveCount": 91,
                        "outcomeCounts": {"succeeded": 90, "partial": 1, "failed": 0},
                        "claimManifestSha256": "a" * 64,
                        "resultManifestSha256": "b" * 64,
                        "rawManifestSha256": "c" * 64,
                    },
                )
            self.assertEqual(status_conflict.exception.stage, "ledger_conflict")

            closed = ledger.mark_plan_status(
                plan_id="validation-plan-91",
                status="succeeded",
                details={
                    "requestCount": 91,
                    "authorizedCalls": 91,
                    "rawResponseArchiveCount": 91,
                    "outcomeCounts": {"succeeded": 91, "partial": 0, "failed": 0},
                    "claimManifestSha256": "a" * 64,
                    "resultManifestSha256": "b" * 64,
                    "rawManifestSha256": "c" * 64,
                },
            )
            self.assertFalse(closed["idempotent"])
            self.assertEqual(ledger.plan_state("validation-plan-91")["status"], "succeeded")

    def test_product_research_reservation_remains_test_mode_only(self) -> None:
        with TemporaryDirectory() as temp:
            ledger_path = Path(temp) / "formal-ledger.jsonl"
            policy = BRIDGE.load_policy(POLICY_PATH)
            formal = BRIDGE.CallLedger(
                ledger_path,
                run_id="formal-product-research",
                policy=policy,
                run_budget=100,
            )
            request = reservation_request(
                "product-research",
                "8",
                tool="product_research",
                asin_count=0,
            )
            with self.assertRaises(BRIDGE.BridgeError) as rejected:
                formal.reserve_plan(plan_id="formal-product-plan", requests=[request], seal_run=True)
            self.assertEqual(rejected.exception.status, 409)
            self.assertEqual(rejected.exception.stage, "tool_policy")
            self.assertFalse(ledger_path.exists())

    def test_plan_request_claim_is_single_use_and_never_idempotently_regranted(self) -> None:
        with TemporaryDirectory() as temp:
            ledger = BRIDGE.CallLedger(
                Path(temp) / "claims.jsonl",
                run_id="claim-run",
                policy=BRIDGE.load_policy(POLICY_PATH),
                run_budget=3,
            )
            requests = [
                reservation_request("packet-a", "a"),
                reservation_request("packet-b", "b"),
            ]
            ledger.reserve_plan(plan_id="claim-plan", requests=requests)
            first = ledger.claim_plan_request(
                plan_id="claim-plan", request_id="packet-a", claim_id="worker-claim-a"
            )
            self.assertTrue(first["executionAllowed"])
            self.assertFalse(first["idempotent"])
            self.assertFalse(first["finalAuthority"])
            self.assertEqual(first["summary"]["claimedCount"], 1)

            with self.assertRaises(BRIDGE.BridgeError) as exact_replay:
                ledger.claim_plan_request(
                    plan_id="claim-plan", request_id="packet-a", claim_id="worker-claim-a"
                )
            self.assertEqual(exact_replay.exception.status, 409)
            self.assertTrue(exact_replay.exception.details["sameClaimId"])
            self.assertFalse(exact_replay.exception.details["executionAllowed"])

            with self.assertRaises(BRIDGE.BridgeError) as second_worker:
                ledger.claim_plan_request(
                    plan_id="claim-plan", request_id="packet-a", claim_id="worker-claim-b"
                )
            self.assertEqual(second_worker.exception.status, 409)
            self.assertFalse(second_worker.exception.details["sameClaimId"])
            self.assertFalse(second_worker.exception.details["executionAllowed"])

            with self.assertRaises(BRIDGE.BridgeError) as reused_claim_id:
                ledger.claim_plan_request(
                    plan_id="claim-plan", request_id="packet-b", claim_id="worker-claim-a"
                )
            self.assertEqual(reused_claim_id.exception.status, 409)
            self.assertFalse(reused_claim_id.exception.details["executionAllowed"])

            second = ledger.claim_plan_request(
                plan_id="claim-plan", request_id="packet-b", claim_id="worker-claim-c"
            )
            self.assertTrue(second["executionAllowed"])
            self.assertEqual(second["summary"]["claimedCount"], 2)

    def test_claim_requires_reserved_non_terminal_plan_and_declared_request(self) -> None:
        with TemporaryDirectory() as temp:
            ledger = BRIDGE.CallLedger(
                Path(temp) / "terminal-claims.jsonl",
                run_id="terminal-run",
                policy=BRIDGE.load_policy(POLICY_PATH),
                run_budget=2,
            )
            with self.assertRaises(BRIDGE.BridgeError) as missing_plan:
                ledger.claim_plan_request(plan_id="absent", request_id="packet", claim_id="claim-absent")
            self.assertEqual(missing_plan.exception.status, 404)
            self.assertFalse(missing_plan.exception.details["executionAllowed"])

            ledger.reserve_plan(
                plan_id="terminal-plan",
                requests=[reservation_request("packet", "c")],
            )
            with self.assertRaises(BRIDGE.BridgeError) as missing_request:
                ledger.claim_plan_request(
                    plan_id="terminal-plan", request_id="not-declared", claim_id="claim-missing"
                )
            self.assertEqual(missing_request.exception.status, 404)
            self.assertFalse(missing_request.exception.details["executionAllowed"])

            ledger.mark_plan_status(plan_id="terminal-plan", status="succeeded", details={})
            with self.assertRaises(BRIDGE.BridgeError) as terminal:
                ledger.claim_plan_request(
                    plan_id="terminal-plan", request_id="packet", claim_id="claim-terminal"
                )
            self.assertEqual(terminal.exception.status, 409)
            self.assertEqual(terminal.exception.stage, "claim_terminal")
            self.assertFalse(terminal.exception.details["executionAllowed"])

    def test_plan_state_reconstructs_reserved_claimed_and_terminal_phases(self) -> None:
        with TemporaryDirectory() as temp:
            ledger = BRIDGE.CallLedger(
                Path(temp) / "plan-state.jsonl",
                run_id="recovery-run",
                policy=BRIDGE.load_policy(POLICY_PATH),
                run_budget=2,
            )
            requests = [
                reservation_request("recover-a", "a"),
                reservation_request("recover-b", "b", pool="conditional"),
            ]
            ledger.reserve_plan(plan_id="recovery-plan", requests=requests)

            reserved = ledger.plan_state("recovery-plan")
            self.assertEqual(reserved["schemaVersion"], "sellerSpriteMcpPlanState/v1")
            self.assertEqual(reserved["phase"], "reserved")
            self.assertEqual(reserved["status"], "reserved")
            self.assertEqual(reserved["requests"], requests)
            self.assertEqual(reserved["claimEvents"], [])
            self.assertEqual(reserved["claimedRequestIds"], [])
            self.assertIsNone(reserved["terminalEvent"])
            self.assertFalse(reserved["reservation"]["finalAuthority"])
            self.assertFalse(reserved["finalAuthority"])

            ledger.claim_plan_request(
                plan_id="recovery-plan", request_id="recover-a", claim_id="recovery-claim-a"
            )
            claimed = ledger.plan_state("recovery-plan")
            self.assertEqual(claimed["phase"], "claimed")
            self.assertEqual(claimed["status"], "reserved")
            self.assertEqual(claimed["claimedRequestIds"], ["recover-a"])
            self.assertEqual(len(claimed["claimEvents"]), 1)
            self.assertFalse(claimed["claimEvents"][0]["finalAuthority"])
            self.assertIsNone(claimed["terminalEvent"])

            ledger.mark_plan_status(
                plan_id="recovery-plan", status="failed", details={"code": "worker_crash"}
            )
            terminal = ledger.plan_state("recovery-plan")
            self.assertEqual(terminal["phase"], "terminal")
            self.assertEqual(terminal["status"], "failed")
            self.assertEqual(terminal["claimedRequestIds"], ["recover-a"])
            self.assertEqual(terminal["terminalEvent"]["eventType"], "failed")
            self.assertFalse(terminal["terminalEvent"]["finalAuthority"])

            with self.assertRaises(BRIDGE.BridgeError) as missing:
                ledger.plan_state("missing-plan")
            self.assertEqual(missing.exception.status, 404)
            self.assertFalse(missing.exception.details["finalAuthority"])

    def test_invalid_or_over_budget_plan_never_partially_writes(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)
            policy = BRIDGE.load_policy(POLICY_PATH)
            invalid_path = root / "invalid.jsonl"
            invalid_ledger = BRIDGE.CallLedger(invalid_path, run_id="invalid-run", policy=policy, run_budget=10)
            requests = [
                reservation_request("valid-first", "a"),
                reservation_request("blocked-second", "b", tool="competitor_lookup"),
            ]
            with self.assertRaises(BRIDGE.BridgeError):
                invalid_ledger.reserve_plan(plan_id="invalid-plan", requests=requests)
            self.assertFalse(invalid_path.exists())

            budget_path = root / "budget.jsonl"
            budget_ledger = BRIDGE.CallLedger(budget_path, run_id="budget-run", policy=policy, run_budget=3)
            over_budget = [
                reservation_request("first", "c", calls=2),
                reservation_request("second", "d", calls=2),
            ]
            with self.assertRaises(BRIDGE.BridgeError) as raised:
                budget_ledger.reserve_plan(plan_id="over-budget", requests=over_budget)
            self.assertEqual(raised.exception.status, 429)
            self.assertFalse(budget_path.exists())

    def test_reserve_plan_cli_uses_one_idempotent_plan_event(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)
            plan_path = root / "plan.json"
            ledger_path = root / "ledger.jsonl"
            report_path = root / "report.json"
            plan_path.write_text(
                json.dumps(
                    {
                        "planId": "cli-plan-1",
                        "sample": [],
                        "requests": [
                            {
                                "id": "keepa-cli",
                                "tool": "keepa_info",
                                "calls": 1,
                                "pool": "primary",
                                "request": {"asin": "B0AAAA0001"},
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            command = [
                sys.executable,
                str(ROOT / "scripts" / "reserve_mcp_hybrid_plan.py"),
                "--plan",
                str(plan_path),
                "--run-id",
                "cli-run",
                "--ledger",
                str(ledger_path),
                "--report",
                str(report_path),
            ]
            subprocess.run(command, cwd=ROOT, check=True, capture_output=True, text=True)
            first = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertFalse(first["reservation"]["idempotent"])
            subprocess.run(command, cwd=ROOT, check=True, capture_output=True, text=True)
            second = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertTrue(second["reservation"]["idempotent"])
            self.assertEqual(second["totalCalls"], 1)
            self.assertFalse(second["automaticRetry"])
            self.assertFalse(second["finalAuthority"])
            self.assertEqual(len(ledger_path.read_text(encoding="utf-8").splitlines()), 1)

    def test_daily_pools_use_asia_shanghai_and_emergency_requires_explicit_authority(self) -> None:
        with TemporaryDirectory() as temp:
            ledger_path = Path(temp) / "daily.jsonl"
            policy = BRIDGE.load_policy(POLICY_PATH)
            first_day = BRIDGE.CallLedger(ledger_path, run_id="day-one", policy=policy, run_budget=500)
            before_midnight = BRIDGE.parse_timestamp("2026-07-29T15:59:00Z", "test")
            first_day.reserve(
                tool="keepa_info", request_hash="1" * 64, asin_count=1, calls=300, pool="primary", at=before_midnight
            )
            with self.assertRaises(BRIDGE.BridgeError):
                first_day.reserve(
                    tool="keepa_info", request_hash="2" * 64, asin_count=1, pool="primary", at=before_midnight
                )
            first_day.reserve(
                tool="keepa_info",
                request_hash="3" * 64,
                asin_count=1,
                calls=100,
                pool="conditional",
                at=before_midnight,
            )
            with self.assertRaises(BRIDGE.BridgeError) as emergency_denied:
                first_day.reserve(
                    tool="keepa_info",
                    request_hash="4" * 64,
                    asin_count=1,
                    pool="emergency",
                    at=before_midnight,
                )
            self.assertEqual(emergency_denied.exception.status, 409)
            first_day.reserve(
                tool="keepa_info",
                request_hash="5" * 64,
                asin_count=1,
                calls=100,
                pool="emergency",
                allow_emergency=True,
                at=before_midnight,
            )
            summary = first_day.summary(before_midnight)
            self.assertEqual(summary["day"], "2026-07-29")
            self.assertEqual(summary["dailyUsed"], 500)
            self.assertEqual(summary["dailyPools"]["primary"]["used"], 300)
            self.assertEqual(summary["dailyPools"]["conditional"]["used"], 100)
            self.assertEqual(summary["dailyPools"]["emergency"]["used"], 100)

            second_day = BRIDGE.CallLedger(ledger_path, run_id="day-two", policy=policy, run_budget=500)
            after_midnight = BRIDGE.parse_timestamp("2026-07-29T16:00:00Z", "test")
            second_day.reserve(
                tool="keepa_info", request_hash="6" * 64, asin_count=1, calls=300, pool="primary", at=after_midnight
            )
            next_summary = second_day.summary(after_midnight)
            self.assertEqual(next_summary["day"], "2026-07-30")
            self.assertEqual(next_summary["dailyUsed"], 300)
            self.assertEqual(next_summary["monthlyUsed"], 800)

    def test_cross_process_file_lock_prevents_quota_penetration(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)
            ledger_path = root / "shared.jsonl"
            start_path = root / "start.flag"
            policy = BRIDGE.load_policy(POLICY_PATH)
            fixed_at = BRIDGE.parse_timestamp("2026-07-29T03:00:00Z", "test")
            prefill = BRIDGE.CallLedger(ledger_path, run_id="prefill", policy=policy, run_budget=299)
            prefill.reserve(
                tool="keepa_info",
                request_hash="f" * 64,
                asin_count=1,
                calls=299,
                pool="primary",
                at=fixed_at,
            )
            code = r'''
import importlib.util, json, pathlib, sys, time
bridge_path, policy_path, ledger_path, start_path, request_hash, run_id = map(pathlib.Path, sys.argv[1:])
spec = importlib.util.spec_from_file_location("bridge_child", bridge_path)
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
policy = module.load_policy(policy_path)
ledger = module.CallLedger(ledger_path, run_id=run_id.name, policy=policy, run_budget=1)
while not start_path.exists():
    time.sleep(0.01)
try:
    ledger.reserve(
        tool="keepa_info",
        request_hash=request_hash.name,
        asin_count=1,
        at=module.parse_timestamp("2026-07-29T03:00:00Z", "test"),
    )
    print(json.dumps({"ok": True}))
except module.BridgeError as error:
    print(json.dumps({"ok": False, "status": error.status, "stage": error.stage}))
'''
            common = [str(BRIDGE_PATH), str(POLICY_PATH), str(ledger_path), str(start_path)]
            outputs = run_parallel_python(
                code,
                [common + ["a" * 64, "run-a"], common + ["b" * 64, "run-b"]],
                start_path,
            )
            self.assertEqual(sum(1 for item in outputs if item["ok"]), 1)
            self.assertEqual(sum(1 for item in outputs if item.get("status") == 429), 1)
            self.assertEqual(len(ledger_path.read_text(encoding="utf-8").splitlines()), 2)
            ledger = BRIDGE.CallLedger(
                ledger_path,
                run_id="observer",
                policy=policy,
                run_budget=1,
            )
            summary = ledger.summary(fixed_at)
            self.assertEqual(summary["dailyPools"]["primary"]["used"], 300)
            self.assertEqual(summary["monthlyUsed"], 300)

    def test_cross_process_sealed_run_accepts_only_one_91_request_plan(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)
            ledger_path = root / "sealed-race.jsonl"
            start_path = root / "start.flag"
            code = r'''
import importlib.util, json, pathlib, sys, time
bridge_path, policy_path, ledger_path, start_path, plan_id = map(pathlib.Path, sys.argv[1:])
spec = importlib.util.spec_from_file_location("bridge_sealed_child", bridge_path)
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
ledger = module.CallLedger(
    ledger_path,
    run_id="mcp-validate-task-race",
    policy=module.load_policy(policy_path),
    run_budget=100,
    test_mode=True,
)
requests = [{
    "id": "task-product-research-001",
    "tool": "product_research",
    "requestHash": "1" * 64,
    "asinCount": 0,
    "calls": 1,
    "pool": "primary",
}]
for tool, marker in (("asin_detail", "2"), ("asin_sales_trend", "3"), ("traffic_listing_stat", "4")):
    for index in range(30):
        requests.append({
            "id": f"task-{tool.replace('_', '-')}-{index:02d}",
            "tool": tool,
            "requestHash": marker * 64,
            "asinCount": 1,
            "calls": 1,
            "pool": "primary",
        })
while not start_path.exists():
    time.sleep(0.01)
try:
    result = ledger.reserve_plan(plan_id=plan_id.name, requests=requests, seal_run=True)
    print(json.dumps({"ok": True, "calls": result["event"]["calls"]}))
except module.BridgeError as error:
    print(json.dumps({"ok": False, "status": error.status, "stage": error.stage}))
'''
            common = [str(BRIDGE_PATH), str(POLICY_PATH), str(ledger_path), str(start_path)]
            outputs = run_parallel_python(
                code,
                [common + ["sealed-plan-a"], common + ["sealed-plan-b"]],
                start_path,
            )
            self.assertEqual(sum(1 for item in outputs if item["ok"]), 1)
            self.assertEqual(sum(1 for item in outputs if item.get("stage") == "budget_sealed"), 1)
            self.assertEqual(len(ledger_path.read_text(encoding="utf-8").splitlines()), 1)
            observer = BRIDGE.CallLedger(
                ledger_path,
                run_id="mcp-validate-task-race",
                policy=BRIDGE.load_policy(POLICY_PATH),
                run_budget=100,
                test_mode=True,
            )
            self.assertEqual(observer.summary()["runUsed"], 91)
            self.assertTrue(observer.summary()["sealedRun"])

    def test_cross_process_claim_allows_only_one_worker_for_the_same_packet(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)
            ledger_path = root / "claim-ledger.jsonl"
            start_path = root / "start.flag"
            policy = BRIDGE.load_policy(POLICY_PATH)
            ledger = BRIDGE.CallLedger(ledger_path, run_id="claim-race", policy=policy, run_budget=1)
            ledger.reserve_plan(
                plan_id="race-plan",
                requests=[reservation_request("race-packet", "e")],
            )
            code = r'''
import importlib.util, json, pathlib, sys, time
bridge_path, policy_path, ledger_path, start_path, claim_id = map(pathlib.Path, sys.argv[1:])
spec = importlib.util.spec_from_file_location("bridge_claim_child", bridge_path)
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
ledger = module.CallLedger(
    ledger_path,
    run_id="claim-race",
    policy=module.load_policy(policy_path),
    run_budget=1,
)
while not start_path.exists():
    time.sleep(0.01)
try:
    result = ledger.claim_plan_request(
        plan_id="race-plan",
        request_id="race-packet",
        claim_id=claim_id.name,
    )
    print(json.dumps({"ok": True, "executionAllowed": result["executionAllowed"]}))
except module.BridgeError as error:
    print(json.dumps({
        "ok": False,
        "status": error.status,
        "stage": error.stage,
        "executionAllowed": bool((error.details or {}).get("executionAllowed")),
    }))
'''
            common = [str(BRIDGE_PATH), str(POLICY_PATH), str(ledger_path), str(start_path)]
            outputs = run_parallel_python(
                code,
                [common + ["claim-worker-a"], common + ["claim-worker-b"]],
                start_path,
            )
            self.assertEqual(sum(1 for item in outputs if item["ok"]), 1)
            self.assertEqual(sum(1 for item in outputs if item.get("status") == 409), 1)
            self.assertEqual(sum(1 for item in outputs if item["executionAllowed"]), 1)
            self.assertEqual(len(ledger_path.read_text(encoding="utf-8").splitlines()), 2)
            summary = ledger.summary()
            self.assertEqual(summary["claimedCount"], 1)

    def test_cross_process_audit_append_is_idempotent(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)
            audit_path = root / "audit.jsonl"
            start_path = root / "start.flag"
            payload_path = root / "payload.json"
            payload_path.write_text(
                json.dumps(
                    {
                        "schemaVersion": "sellerSpriteMcpAuditEvent/v1",
                        "requestId": "runner-adapter:cross-process:1",
                        "auditId": "rank:cross-process:1",
                        "eventType": "queue-ranked",
                        "payload": {"queueHash": "a" * 64},
                    }
                ),
                encoding="utf-8",
            )
            code = r'''
import importlib.util, json, pathlib, sys, time
bridge_path, audit_path, start_path, payload_path = map(pathlib.Path, sys.argv[1:])
spec = importlib.util.spec_from_file_location("bridge_audit_child", bridge_path)
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
audit = module.AuditLog(audit_path, run_id="audit-run")
payload = json.loads(payload_path.read_text(encoding="utf-8"))
while not start_path.exists():
    time.sleep(0.01)
print(json.dumps(audit.append(payload)))
'''
            common = [str(BRIDGE_PATH), str(audit_path), str(start_path), str(payload_path)]
            outputs = run_parallel_python(code, [common, common], start_path)
            self.assertTrue(all(item["persisted"] for item in outputs))
            self.assertEqual(sum(1 for item in outputs if item["idempotent"]), 1)
            self.assertEqual(sum(1 for item in outputs if not item["idempotent"]), 1)
            self.assertEqual(len(audit_path.read_text(encoding="utf-8").splitlines()), 1)
            stored = json.loads(audit_path.read_text(encoding="utf-8"))
            self.assertFalse(stored["finalAuthority"])
            self.assertEqual(stored["runId"], "audit-run")
            conflict = json.loads(payload_path.read_text(encoding="utf-8"))
            conflict["payload"]["queueHash"] = "b" * 64
            with self.assertRaises(BRIDGE.BridgeError) as raised:
                BRIDGE.AuditLog(audit_path, run_id="audit-run").append(conflict)
            self.assertEqual(raised.exception.status, 409)
            authoritative = json.loads(payload_path.read_text(encoding="utf-8"))
            authoritative["auditId"] = "audit-authority-claim"
            authoritative["finalAuthority"] = True
            with self.assertRaises(BRIDGE.BridgeError):
                BRIDGE.AuditLog(audit_path, run_id="audit-run").append(authoritative)
            nested_authoritative = json.loads(payload_path.read_text(encoding="utf-8"))
            nested_authoritative["auditId"] = "audit-nested-authority-claim"
            nested_authoritative["payload"]["decision"] = {"usableForFinal": True}
            with self.assertRaises(BRIDGE.BridgeError):
                BRIDGE.AuditLog(audit_path, run_id="audit-run").append(nested_authoritative)
            self.assertIsNone(BRIDGE.SAFE_ID_RE.fullmatch("field:name"))
            for invalid_id in ("bad id", "bad/id", "bad\\id", "bad\nid", "x" * 129):
                invalid_payload = json.loads(payload_path.read_text(encoding="utf-8"))
                invalid_payload["requestId"] = invalid_id
                invalid_payload["auditId"] = "rank:invalid:id"
                with self.assertRaises(BRIDGE.BridgeError) as invalid_error:
                    BRIDGE.AuditLog(audit_path, run_id="audit-run").append(invalid_payload)
                self.assertEqual(invalid_error.exception.status, 400)

    def test_http_layer_is_loopback_token_protected(self) -> None:
        with TemporaryDirectory() as temp:
            bridge = make_bridge(Path(temp))
            server = BRIDGE.BridgeHttpServer(("127.0.0.1", 0), BRIDGE.BridgeHandler)
            server.bridge = bridge
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                port = server.server_port
                connection = HTTPConnection("127.0.0.1", port, timeout=3)
                connection.request("GET", "/api/v1/health")
                response = connection.getresponse()
                self.assertEqual(response.status, 200)
                self.assertFalse(json.loads(response.read())["finalAuthority"])
                connection.close()

                connection = HTTPConnection("127.0.0.1", port, timeout=3)
                connection.request("GET", "/api/v1/ledger")
                self.assertEqual(connection.getresponse().status, 401)
                connection.close()

                connection = HTTPConnection("127.0.0.1", port, timeout=3)
                connection.request(
                    "POST",
                    "/api/v1/evidence/import",
                    body=json.dumps(load_fixture()),
                    headers={
                        "Content-Type": "application/json",
                        "Content-Length": str(len(json.dumps(load_fixture()).encode("utf-8"))),
                        "X-MCP-Hybrid-Token": "fixture-token",
                    },
                )
                import_response = connection.getresponse()
                self.assertEqual(import_response.status, 200)
                self.assertEqual(json.loads(import_response.read())["result"]["imported"], 1)
                connection.close()

                connection = HTTPConnection("127.0.0.1", port, timeout=3)
                query = urlencode({"asin": "B0AAAA0001"})
                connection.request(
                    "GET",
                    f"/api/v1/evidence?{query}",
                    headers={"X-MCP-Hybrid-Token": "fixture-token"},
                )
                evidence_response = connection.getresponse()
                self.assertEqual(evidence_response.status, 200)
                self.assertEqual(json.loads(evidence_response.read())["evidenceCount"], 1)
                connection.close()

                batch_body = json.dumps({"asins": ["B0AAAA0001"]})
                connection = HTTPConnection("127.0.0.1", port, timeout=3)
                connection.request(
                    "POST",
                    "/api/v1/evidence/batch",
                    body=batch_body,
                    headers={
                        "Content-Type": "application/json",
                        "Content-Length": str(len(batch_body.encode("utf-8"))),
                        "X-MCP-Hybrid-Token": "fixture-token",
                    },
                )
                batch_response = connection.getresponse()
                self.assertEqual(batch_response.status, 200)
                batch_payload = json.loads(batch_response.read())
                self.assertEqual(batch_payload["result"]["schemaVersion"], "sellerSpriteMcpBatchLookup/v1")
                self.assertEqual(batch_payload["result"]["rowCount"], 1)
                self.assertFalse(batch_payload["result"]["finalAuthority"])
                self.assertEqual(batch_payload["result"]["rows"][0]["asin"], "B0AAAA0001")
                connection.close()

                plan_body = json.dumps(
                    {
                        "planId": "http-plan-1",
                        "requests": [reservation_request("keepa-http", "7")],
                        "sealRun": True,
                    }
                )
                connection = HTTPConnection("127.0.0.1", port, timeout=3)
                connection.request(
                    "POST",
                    "/api/v1/calls/reserve-plan",
                    body=plan_body,
                    headers={
                        "Content-Type": "application/json",
                        "Content-Length": str(len(plan_body.encode("utf-8"))),
                        "X-MCP-Hybrid-Token": "fixture-token",
                    },
                )
                plan_response = connection.getresponse()
                self.assertEqual(plan_response.status, 200)
                plan_result = json.loads(plan_response.read())["result"]
                self.assertEqual(plan_result["currentStatus"], "reserved")
                self.assertTrue(plan_result["event"]["sealedRun"])
                self.assertFalse(plan_result["event"]["automaticRetry"])
                connection.close()

                claim_body = json.dumps(
                    {
                        "planId": "http-plan-1",
                        "requestId": "keepa-http",
                        "claimId": "http-claim-1",
                    }
                )
                connection = HTTPConnection("127.0.0.1", port, timeout=3)
                connection.request(
                    "POST",
                    "/api/v1/calls/claim",
                    body=claim_body,
                    headers={
                        "Content-Type": "application/json",
                        "Content-Length": str(len(claim_body.encode("utf-8"))),
                        "X-MCP-Hybrid-Token": "fixture-token",
                    },
                )
                claim_response = connection.getresponse()
                self.assertEqual(claim_response.status, 200)
                claim_result = json.loads(claim_response.read())["result"]
                self.assertTrue(claim_result["executionAllowed"])
                self.assertFalse(claim_result["finalAuthority"])
                connection.close()

                connection = HTTPConnection("127.0.0.1", port, timeout=3)
                connection.request(
                    "POST",
                    "/api/v1/calls/claim",
                    body=claim_body,
                    headers={
                        "Content-Type": "application/json",
                        "Content-Length": str(len(claim_body.encode("utf-8"))),
                        "X-MCP-Hybrid-Token": "fixture-token",
                    },
                )
                repeated_claim = connection.getresponse()
                self.assertEqual(repeated_claim.status, 409)
                repeated_payload = json.loads(repeated_claim.read())
                self.assertFalse(repeated_payload["details"]["executionAllowed"])
                self.assertTrue(repeated_payload["details"]["sameClaimId"])
                connection.close()

                connection = HTTPConnection("127.0.0.1", port, timeout=3)
                state_query = urlencode({"planId": "http-plan-1"})
                connection.request(
                    "GET",
                    f"/api/v1/calls/plan-state?{state_query}",
                    headers={"X-MCP-Hybrid-Token": "fixture-token"},
                )
                state_response = connection.getresponse()
                self.assertEqual(state_response.status, 200)
                plan_state = json.loads(state_response.read())["result"]
                self.assertEqual(plan_state["phase"], "claimed")
                self.assertEqual(plan_state["status"], "reserved")
                self.assertEqual(plan_state["claimedRequestIds"], ["keepa-http"])
                self.assertFalse(plan_state["reservation"]["finalAuthority"])
                self.assertFalse(plan_state["claimEvents"][0]["finalAuthority"])
                self.assertFalse(plan_state["finalAuthority"])
                connection.close()

                audit_body = json.dumps(
                    {
                        "schemaVersion": "sellerSpriteMcpAuditEvent/v1",
                        "requestId": "runner-adapter:http:1",
                        "auditId": "rank:http:1",
                        "eventType": "queue-ranked",
                        "payload": {"evidenceIdsHash": "8" * 64},
                    }
                )
                receipts = []
                for _ in range(2):
                    connection = HTTPConnection("127.0.0.1", port, timeout=3)
                    connection.request(
                        "POST",
                        "/api/v1/audit/events",
                        body=audit_body,
                        headers={
                            "Content-Type": "application/json",
                            "Content-Length": str(len(audit_body.encode("utf-8"))),
                            "X-MCP-Hybrid-Token": "fixture-token",
                        },
                    )
                    audit_response = connection.getresponse()
                    self.assertEqual(audit_response.status, 200)
                    receipts.append(json.loads(audit_response.read())["result"])
                    connection.close()
                self.assertEqual(receipts[0]["schemaVersion"], "sellerSpriteMcpAuditReceipt/v1")
                self.assertEqual(receipts[0]["requestId"], "runner-adapter:http:1")
                self.assertEqual(receipts[0]["auditId"], "rank:http:1")
                self.assertTrue(receipts[0]["persisted"])
                self.assertFalse(receipts[0]["idempotent"])
                self.assertTrue(receipts[1]["idempotent"])
                self.assertFalse(receipts[0]["finalAuthority"])

                application_body = json.dumps(
                    {
                        "schemaVersion": "sellerSpriteMcpAuditEvent/v1",
                        "requestId": "runner-adapter:http:1",
                        "auditId": "apply:http:1",
                        "eventType": "queue_applied",
                        "payload": {"queueHash": "9" * 64},
                    }
                )
                connection = HTTPConnection("127.0.0.1", port, timeout=3)
                connection.request(
                    "POST",
                    "/api/v1/audit/events",
                    body=application_body,
                    headers={
                        "Content-Type": "application/json",
                        "Content-Length": str(len(application_body.encode("utf-8"))),
                        "X-MCP-Hybrid-Token": "fixture-token",
                    },
                )
                application_response = connection.getresponse()
                self.assertEqual(application_response.status, 200)
                application_receipt = json.loads(application_response.read())["result"]
                self.assertEqual(application_receipt["auditId"], "apply:http:1")
                self.assertTrue(application_receipt["persisted"])
                connection.close()

                connection = HTTPConnection("127.0.0.1", port, timeout=3)
                connection.request(
                    "GET",
                    "/api/v1/ledger",
                    headers={"X-MCP-Hybrid-Token": "fixture-token", "Origin": "https://evil.example"},
                )
                self.assertEqual(connection.getresponse().status, 403)
                connection.close()
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=3)

    def test_frozen_original_hashes_match(self) -> None:
        baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
        for entry in baseline["files"]:
            path = ROOT / Path(entry["path"])
            self.assertTrue(path.is_file(), entry["path"])
            # The baseline was captured from LF content. Git may check files out
            # with CRLF (core.autocrlf), which is a checkout artifact, not a
            # content change, so normalise line endings before comparing.
            normalized = path.read_bytes().replace(b"\r\n", b"\n")
            self.assertEqual(
                hashlib.sha256(normalized).hexdigest(), entry["sha256"], entry["path"]
            )
            self.assertEqual(len(normalized), entry["bytes"], entry["path"])


if __name__ == "__main__":
    unittest.main()
