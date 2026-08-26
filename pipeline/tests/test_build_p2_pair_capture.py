from __future__ import annotations

import copy
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from analyze_p2_paired_evidence import compare_capture  # noqa: E402
from build_p2_pair_capture import CaptureBuildError, build_capture  # noqa: E402


HISTORY = {
    "schemaVersion": "strictQualifiedHistorySnapshot/v1",
    "sourceSchemaVersion": "strictQualifiedHistory/v1",
    "asins": [],
}


def detail(week_sort: int, *, kind: str = "normal") -> dict[str, object]:
    if kind == "zero":
        return {
            "week": f"2026 W{week_sort - 202600:02d}",
            "weekSort": week_sort,
            "totalTraffic": 100,
            "naturalTraffic": 0,
            "naturalSharePct": 0,
            "naturalShareDerived": True,
            "naturalShareSource": "derived_explicit_zero_over_positive_total",
            "tier2ReaderVersion": "tier2.1-zero-share-v1",
            "rawText": "Total 100 Natural 0 0%",
        }
    if kind == "missing":
        return {
            "week": f"2026 W{week_sort - 202600:02d}",
            "weekSort": week_sort,
            "totalTraffic": 100,
            "naturalTraffic": None,
            "naturalSharePct": None,
            "naturalShareDerived": False,
            "naturalShareSource": "missing",
            "tier2ReaderVersion": "tier2.1-zero-share-v1",
            "rawText": "Natural --",
        }
    return {
        "week": f"2026 W{week_sort - 202600:02d}",
        "weekSort": week_sort,
        "totalTraffic": 100,
        "naturalTraffic": 80,
        "naturalSharePct": 80,
        "naturalShareDerived": False,
        "naturalShareSource": "sellersprite_explicit",
        "tier2ReaderVersion": "tier2.1-zero-share-v1",
        "rawText": "Total 100 Natural 80 80%",
    }


def attempt(payload: dict[str, object] | None, run_id: str, *, error: str = "") -> dict[str, object]:
    if payload is None:
        return {
            "schemaVersion": "collectorAttemptEvidence/v1",
            "outcome": "error",
            "payload": None,
            "error": error or "Timed out after 45000ms",
            "errorCode": "collector_timeout",
            "attemptSnapshot": {
                "collectorRunId": run_id,
                "outcome": "error",
                "payloadAccepted": False,
            },
        }
    return {
        "schemaVersion": "collectorAttemptEvidence/v1",
        "outcome": "payload",
        "payload": copy.deepcopy(payload),
        "error": "",
        "errorCode": "",
        "attemptSnapshot": {
            "collectorRunId": run_id,
            "outcome": "payload",
            "payloadAccepted": True,
        },
    }


def result(index: int, p2: bool, *, old_timeout: bool = False, gate: str = "reject") -> dict[str, object]:
    asin = f"B0{index:08d}"
    run_id = f"run-{index:03d}"
    accepted = 1_000_000 + index * 10_000
    if index == 0:
        details = [detail(202627, kind="zero"), detail(202626, kind="zero"), detail(202625, kind="zero")]
    elif index == 1:
        details = [detail(202627, kind="missing")]
    elif index == 2:
        details = [detail(202627), {**detail(202626), "rawText": "traffic --", "markers": ["--"]}]
    elif index == 3:
        details = [detail(202627), detail(202626)]
    else:
        details = [detail(202627), detail(202626), detail(202625)]
    if old_timeout:
        evidence = {"status": "error", "collectorVersion": "0.4.7", "weeksRead": 0, "details": [], "deadlineProtocol": None, "telemetry": {"timing": {}, "deadline": None}}
        first = attempt(None, run_id)
        status = "error"
        rejection_rule = "collection_error"
        error = "Timed out after 45000ms"
    else:
        payload = {"status": "ok", "collectorVersion": "0.4.7", "weeksRead": sum(item["naturalSharePct"] is not None for item in details), "details": details}
        first = attempt(payload, run_id)
        status = "ok"
        rejection_rule = "" if gate == "pass" else "traffic_weeks_insufficient"
        error = ""
        evidence = payload
    protocol = None
    deadline_snapshot = None
    if p2:
        protocol = {
            "protocolName": "p2-collector-owned-deadline-v1",
            "protocolVersion": "2",
            "deadlineOwner": "collector",
            "runId": run_id,
            "acceptedAtMs": accepted,
            "chartReadyDeadlineAtMs": accepted + 60_000,
            "phase": "result_ready",
            "phaseStartedAtMs": accepted + 1_000,
            "phaseDeadlineAtMs": None,
            "heartbeatAtMs": accepted + 1_000,
            "lastObservedAtMs": accepted + 1_000,
            "clockAnomalyKind": "",
            "clockAnomalyObservedAtMs": None,
            "chartReadyAtMs": accepted + 500,
            "resultReadyAtMs": accepted + 1_000,
            "terminalReason": status,
            "deadlineExceededByMs": 0,
            "visibilityState": "visible",
            "hiddenObservedAtMs": None,
        }
        deadline_snapshot = {
            "protocolName": protocol["protocolName"],
            "protocolVersion": "p2-collector-owned-deadline-v1",
            "domProtocolVersion": "2",
            "owner": "collector",
            "runId": run_id,
            "acceptedAtMs": accepted,
            "chartReadyDeadlineAtMs": accepted + 60_000,
            "phase": "result_ready",
            "phaseStartedAtMs": accepted + 1_000,
            "phaseDeadlineAtMs": None,
            "heartbeatAtMs": accepted + 1_000,
            "lastObservedAtMs": accepted + 1_000,
            "clockAnomalyKind": "",
            "clockAnomalyObservedAtMs": None,
            "chartReadyAtMs": accepted + 500,
            "resultReadyAtMs": accepted + 1_000,
            "terminalReason": status,
            "deadlineExceededByMs": 0,
            "visibilityState": "visible",
            "hiddenObservedAtMs": None,
        }
        evidence["deadlineProtocol"] = protocol
        evidence["telemetry"] = {"timing": {"totalMs": 40_000 if 4 <= index <= 7 else 900}, "deadline": deadline_snapshot}
    retry = {
        "retryCount": 0,
        "retryDecision": "no_retry",
        "retryReason": "",
        "firstAttemptStatus": status,
        "firstAttemptWeeksRead": evidence["weeksRead"],
        "secondAttemptStatus": "",
        "secondAttemptWeeksRead": None,
        "retryReplacedFirst": False,
        "retryRecoveryYield": None,
        "firstAttemptEvidence": first,
        "secondAttemptEvidence": None,
    }
    if not old_timeout:
        retry["firstAttemptEvidence"] = attempt(evidence, run_id)
    protocol_recovery = {
        "schemaVersion": "collectorProtocolRecoveryEvidence/v1",
        "pauseCount": 0,
        "pauseReasons": [],
        "staleRunIds": [],
        "freshRunId": run_id if p2 else "",
        "payloadRunId": run_id if p2 else "",
        "protocolRunId": run_id if p2 else "",
        "attemptRunId": run_id if p2 else "",
        "runIdentityConsistent": True,
        "freshRunIdVerified": True,
        "pendingRecoveryState": "not_applicable",
        "recovered": False,
        "quarantinedAttempts": [],
    }
    return {
        "targetAsin": asin,
        "strictDecision": gate,
        "status": status,
        "collectorVersion": "0.4.7",
        "collectorProtocolMode": "p2-collector-owned-deadline-v1" if p2 else "legacy_status_text_v1",
        "collectorValidationIdentity": {
            "runnerP2Enabled": p2,
            "collectorVersion": "0.4.7",
            "collectorP2Enabled": p2,
            "protocolName": "p2-collector-owned-deadline-v1" if p2 else "legacy_status_text_v1",
            "protocolVersion": "2" if p2 else "1",
            "deadlineOwner": "collector" if p2 else "runner",
            "attemptCount": 1,
            "complete": True,
        },
        "collectorEvidence": evidence,
        "retryEvidence": retry,
        "protocolRecoveryEvidence": protocol_recovery,
        "telemetry": {"timing": {"runnerVersion": "0.3.9", "totalMs": 40_000 if 4 <= index <= 7 else 1000, "trafficChartMs": 40_000 if 4 <= index <= 7 else 500}},
        "rejectionReason": error or ("weeksRead < 3" if gate == "reject" else ""),
        "rejectionRule": rejection_rule,
        "error": error,
    }


def history_isolation(side: str) -> dict[str, object]:
    return {
        "schemaVersion": "p2PairHistoryIsolation/v1",
        "version": "p2-paired-sandbox-history-v1",
        "mode": "sandbox",
        "p2Side": side,
        "productionWriteProtected": True,
        "productionKey": "ssIntegratedRunner:v0.3:strict-qualified-history",
        "activeSandboxKey": f"ssIntegratedRunner:v0.3:p2-paired-sandbox-history:{side}",
        "productionSnapshot": copy.deepcopy(HISTORY),
        "sandboxSeedSnapshot": copy.deepcopy(HISTORY),
    }


def batch(rows: list[dict[str, object]], label: str) -> dict[str, object]:
    side = "off" if label == "old" else "on"
    return {
        "schemaVersion": "sellerSpriteIntegratedBatch/v0.3.0",
        "batchName": f"p2-{label}-fixture",
        "status": "done",
        "queue": [str(row["targetAsin"]) for row in rows],
        "historySkippedCount": 0,
        "historySkippedAsins": [],
        "pendingRecovery": {"schemaVersion": "collectorProtocolPendingRecovery/v1", "state": "none", "count": 0, "asins": [], "pauseAttempts": 0, "reasons": []},
        "historySnapshotAtGeneration": copy.deepcopy(HISTORY),
        "historyIsolation": history_isolation(side),
        "results": rows,
    }


def review(
    capture: dict[str, object], rows: list[int], root: Path
) -> dict[str, object]:
    root.mkdir(parents=True, exist_ok=True)
    analyzed = compare_capture(capture)
    review_rows: list[dict[str, object]] = []
    for index in rows:
        binding = analyzed["pairs"][index]["reviewBinding"]
        evidence_path = root / f"evidence_{index}.json"
        evidence_raw = json.dumps(
            {"reviewBinding": binding}, sort_keys=True
        ).encode("utf-8")
        evidence_path.write_bytes(evidence_raw)
        review_rows.append(
            {
                "asin": f"B0{index:08d}",
                "pairId": binding["pairId"],
                "reviewBinding": binding,
                "manualTooltipVerified": True,
                "offlineReplayOutcome": "pass",
                "acceptanceOutcome": "pass",
                "evidenceArtifacts": [
                    {
                        "path": str(evidence_path),
                        "bytes": len(evidence_raw),
                        "sha256": hashlib.sha256(evidence_raw).hexdigest(),
                    }
                ],
                "verifiedBy": "fixture",
                "verifiedAt": "2026-07-15T00:00:00Z",
            }
        )
    return {
        "schemaVersion": "sellerSpriteP2RecoveryReview/v2",
        "rows": review_rows,
    }


class BuildP2PairCaptureTests(unittest.TestCase):
    def write_batches(self, root: Path, *, mismatch_history: bool = False) -> tuple[Path, Path]:
        old_rows = [result(i, False, old_timeout=20 <= i <= 24) for i in range(30)]
        new_rows = [result(i, True, gate="pass" if 20 <= i <= 22 else "reject") for i in range(30)]
        old = batch(old_rows, "old")
        new = batch(new_rows, "new")
        if mismatch_history:
            new["historyIsolation"]["productionSnapshot"]["asins"] = ["B0ZZZZZZZZ"]
        old_path, new_path = root / "old.json", root / "new.json"
        old_path.write_text(json.dumps(old), encoding="utf-8")
        new_path.write_text(json.dumps(new), encoding="utf-8")
        return old_path, new_path

    def test_builds_sandbox_capture_with_provenance_and_attempts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            old_path, new_path = self.write_batches(Path(directory))
            capture = build_capture([old_path], [new_path])
            self.assertEqual(capture["historyIsolation"]["mode"], "sandbox")
            self.assertEqual(capture["pairs"][0]["new"]["weeks"][0]["naturalShareSource"], "derived_explicit_zero_over_positive_total")
            self.assertEqual(capture["pairs"][0]["old"]["firstAttempt"]["outcome"], "payload")
            self.assertEqual(capture["pairs"][20]["old"]["readClass"], "timeout_error")
            comparison = compare_capture(capture)
            self.assertFalse(comparison["passed"])
            self.assertEqual(comparison["validation"]["releasePendingCount"], 5)

            reviewed = build_capture(
                [old_path],
                [new_path],
                recovery_review=review(capture, [20, 21, 22, 23, 24], Path(directory)),
            )
            self.assertTrue(compare_capture(reviewed)["passed"])

    def test_protocol_resume_attempts_are_counted_separately_from_retries(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            old_row = result(0, False)
            new_row = result(0, True)
            stale = attempt(
                None,
                "stale-run",
                error="Collector deadline protocol paused: watchdog_tooltip_scan_watchdog_exceeded_active",
            )
            stale["errorCode"] = "collector_protocol_pause"
            new_row["collectorValidationIdentity"]["attemptCount"] = 2
            new_row["protocolRecoveryEvidence"] = {
                "schemaVersion": "collectorProtocolRecoveryEvidence/v1",
                "pauseCount": 1,
                "pauseReasons": ["watchdog_tooltip_scan_watchdog_exceeded_active"],
                "staleRunIds": ["stale-run"],
                "freshRunId": "run-000",
                "payloadRunId": "run-000",
                "protocolRunId": "run-000",
                "attemptRunId": "run-000",
                "runIdentityConsistent": True,
                "freshRunIdVerified": True,
                "pendingRecoveryState": "recovered",
                "recovered": True,
                "quarantinedAttempts": [stale],
            }
            old_path = root / "old.json"
            new_path = root / "new.json"
            old_path.write_text(json.dumps(batch([old_row], "old")), encoding="utf-8")
            new_path.write_text(json.dumps(batch([new_row], "new")), encoding="utf-8")

            capture = build_capture([old_path], [new_path])
            self.assertEqual(capture["pairs"][0]["new"]["protocolPauseCount"], 1)
            quarantined = capture["pairs"][0]["new"]["protocolRecovery"]["quarantinedAttempts"]
            self.assertEqual(quarantined[0]["weeks"], [])
            parsed = compare_capture(capture)
            self.assertFalse(
                any(
                    "quarantinedAttempts" in error or "protocolPauseCount" in error
                    for error in parsed["errors"]
                )
            )

            new_row["collectorValidationIdentity"]["attemptCount"] = 1
            new_path.write_text(json.dumps(batch([new_row], "new")), encoding="utf-8")
            with self.assertRaisesRegex(
                CaptureBuildError,
                "attemptCount must equal retryCount \+ protocolPauseCount \+ 1",
            ):
                build_capture([old_path], [new_path])

    def test_protocol_quarantine_must_be_exact_pause_errors(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            old_row = result(0, False)
            new_row = result(0, True)
            stale = attempt(None, "stale-run")
            stale["errorCode"] = "collector_timeout"
            new_row["collectorValidationIdentity"]["attemptCount"] = 2
            new_row["protocolRecoveryEvidence"].update(
                {
                    "pauseCount": 1,
                    "pauseReasons": ["watchdog_tooltip_scan_watchdog_exceeded_active"],
                    "staleRunIds": ["stale-run"],
                    "freshRunId": "run-000",
                    "payloadRunId": "run-000",
                    "protocolRunId": "run-000",
                    "attemptRunId": "run-000",
                    "pendingRecoveryState": "recovered",
                    "recovered": True,
                    "quarantinedAttempts": [stale],
                }
            )
            old_path = root / "old.json"
            new_path = root / "new.json"
            old_path.write_text(json.dumps(batch([old_row], "old")), encoding="utf-8")
            new_path.write_text(json.dumps(batch([new_row], "new")), encoding="utf-8")
            with self.assertRaisesRegex(
                CaptureBuildError,
                "must be a collector_protocol_pause error",
            ):
                build_capture([old_path], [new_path])

    def test_review_binding_and_artifact_hash_are_enforced(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            old_path, new_path = self.write_batches(root)
            capture = build_capture([old_path], [new_path])
            review_data = review(capture, [20], root)
            review_data["rows"][0]["pairId"] = "stale-pair"
            with self.assertRaisesRegex(CaptureBuildError, "reviewBinding is invalid"):
                build_capture([old_path], [new_path], recovery_review=review_data)

            review_data = review(capture, [20], root)
            Path(review_data["rows"][0]["evidenceArtifacts"][0]["path"]).write_text(
                "changed", encoding="utf-8"
            )
            with self.assertRaisesRegex(CaptureBuildError, "bytes/hash mismatch"):
                build_capture([old_path], [new_path], recovery_review=review_data)

    def test_builder_rejects_provenance_type_coercion(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            old_path, new_path = self.write_batches(root)
            data = json.loads(new_path.read_text(encoding="utf-8"))
            data["results"][3]["collectorEvidence"]["details"][0][
                "naturalShareDerived"
            ] = 0
            new_path.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaisesRegex(
                CaptureBuildError, "naturalShareDerived must be boolean"
            ):
                build_capture([old_path], [new_path])

    def test_missing_attempt_evidence_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            old_path, new_path = self.write_batches(Path(directory))
            data = json.loads(old_path.read_text(encoding="utf-8"))
            data["results"][0]["retryEvidence"].pop("firstAttemptEvidence")
            old_path.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaisesRegex(CaptureBuildError, "firstAttemptEvidence"):
                build_capture([old_path], [new_path])

    def test_retry_yield_is_recomputed_from_full_attempts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rows: dict[str, dict[str, object]] = {}
            for label, p2 in (("old", False), ("new", True)):
                row = result(0, p2)
                incomplete = {
                    "status": "no_chart_loaded",
                    "collectorVersion": "0.4.7",
                    "weeksRead": 0,
                    "details": [],
                }
                retry = row["retryEvidence"]
                retry.update(
                    {
                        "retryCount": 1,
                        "firstAttemptStatus": "no_chart_loaded",
                        "firstAttemptWeeksRead": 0,
                        "secondAttemptStatus": "ok",
                        "secondAttemptWeeksRead": row["collectorEvidence"]["weeksRead"],
                        "retryReplacedFirst": True,
                        "retryRecoveryYield": True,
                        "firstAttemptEvidence": attempt(incomplete, "first-run"),
                        "secondAttemptEvidence": attempt(row["collectorEvidence"], f"run-{0:03d}"),
                    }
                )
                row["collectorValidationIdentity"]["attemptCount"] = 2
                rows[label] = row
            old_path, new_path = root / "old.json", root / "new.json"
            old_path.write_text(json.dumps(batch([rows["old"]], "old")), encoding="utf-8")
            new_path.write_text(json.dumps(batch([rows["new"]], "new")), encoding="utf-8")
            capture = build_capture([old_path], [new_path])
            self.assertTrue(capture["pairs"][0]["old"]["recoveryYield"])
            self.assertEqual(capture["pairs"][0]["new"]["firstAttempt"]["weeksRead"], 0)

            rows["new"]["retryEvidence"]["retryRecoveryYield"] = False
            new_path.write_text(json.dumps(batch([rows["new"]], "new")), encoding="utf-8")
            with self.assertRaisesRegex(CaptureBuildError, "retryRecoveryYield"):
                build_capture([old_path], [new_path])

    def test_history_seed_mismatch_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            old_path, new_path = self.write_batches(Path(directory), mismatch_history=True)
            with self.assertRaisesRegex(CaptureBuildError, "production, sandbox seed"):
                build_capture([old_path], [new_path])

    def test_pending_batch_cannot_enter_capture(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            old_path, new_path = self.write_batches(Path(directory))
            data = json.loads(old_path.read_text(encoding="utf-8"))
            data["pendingRecovery"]["state"] = "pending-recovery"
            data["pendingRecovery"]["count"] = 1
            data["pendingRecovery"]["asins"] = [data["queue"][20]]
            old_path.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaisesRegex(CaptureBuildError, "pending-recovery"):
                build_capture([old_path], [new_path])

    def test_backward_wall_clock_evidence_cannot_enter_capture(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            old_path, new_path = self.write_batches(Path(directory))
            data = json.loads(new_path.read_text(encoding="utf-8"))
            row = data["results"][0]["collectorEvidence"]
            row["deadlineProtocol"]["clockAnomalyKind"] = "wall_clock_backward"
            row["deadlineProtocol"]["clockAnomalyObservedAtMs"] = row["deadlineProtocol"]["acceptedAtMs"] - 1
            row["telemetry"]["deadline"]["clockAnomalyKind"] = "wall_clock_backward"
            row["telemetry"]["deadline"]["clockAnomalyObservedAtMs"] = row["deadlineProtocol"]["acceptedAtMs"] - 1
            new_path.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaisesRegex(CaptureBuildError, "backward wall-clock"):
                build_capture([old_path], [new_path])


if __name__ == "__main__":
    unittest.main()
