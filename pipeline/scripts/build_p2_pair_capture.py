"""Build a strict P2 old/new pair capture from Runner 0.3.9 combined JSON.

This script only reshapes evidence already persisted by Runner. It does not
derive missing traffic values, outcomes, retry recovery, or protocol state.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Iterable


CAPTURE_SCHEMA = "sellerSpriteP2PairCapture/v1"
RUNNER_SCHEMA = "sellerSpriteIntegratedBatch/v0.3.0"
P2_PROTOCOL_NAME = "p2-collector-owned-deadline-v1"
LEGACY_PROTOCOL_NAME = "legacy_status_text_v1"
EXPECTED_RUNNER_VERSION = "0.3.9"
EXPECTED_COLLECTOR_VERSION = "0.4.7"
HISTORY_SNAPSHOT_SCHEMA = "strictQualifiedHistorySnapshot/v1"
HISTORY_ISOLATION_SCHEMA = "p2PairHistoryIsolation/v1"
ATTEMPT_EVIDENCE_SCHEMA = "collectorAttemptEvidence/v1"
PROTOCOL_RECOVERY_SCHEMA = "collectorProtocolRecoveryEvidence/v1"
PENDING_RECOVERY_SCHEMA = "collectorProtocolPendingRecovery/v1"
RECOVERY_REVIEW_SCHEMA = "sellerSpriteP2RecoveryReview/v2"
REVIEW_BINDING_SCHEMA = "sellerSpriteP2ReviewBinding/v1"
PRODUCTION_HISTORY_KEY = "ssIntegratedRunner:v0.3:strict-qualified-history"
SANDBOX_HISTORY_KEY_PREFIX = "ssIntegratedRunner:v0.3:p2-paired-sandbox-history:"
ASIN_RE = re.compile(r"^[A-Z0-9]{10}$")


class CaptureBuildError(ValueError):
    """Raised when source Runner evidence cannot be reshaped safely."""


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as error:
        raise CaptureBuildError(f"cannot read {path}: {error}") from error
    if not isinstance(value, dict):
        raise CaptureBuildError(f"{path}: root must be an object")
    return value


def _number_or_none(value: Any) -> int | float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value
    return None


def _asin(result: dict[str, Any], context: str) -> str:
    value = str(result.get("targetAsin") or result.get("asin") or "").upper()
    if not ASIN_RE.fullmatch(value):
        raise CaptureBuildError(f"{context}: result has no valid ASIN")
    return value


def _markers(detail: dict[str, Any]) -> list[str]:
    markers: list[str] = []
    raw = str(detail.get("rawText") or "")
    if "--" in raw:
        markers.append("--")
    total = detail.get("totalTraffic")
    natural = detail.get("naturalTraffic")
    share = detail.get("naturalSharePct")
    if isinstance(total, (int, float)) and total > 0 and natural == 0 and share == 0:
        markers.append("explicit_zero")
    if share is None:
        markers.append("missing_ratio")
    return markers


def _weeks(evidence: dict[str, Any], context: str) -> list[dict[str, Any]]:
    details = evidence.get("details", [])
    if details is None:
        details = []
    if not isinstance(details, list):
        raise CaptureBuildError(f"{context}: collectorEvidence.details must be a list")
    weeks: list[dict[str, Any]] = []
    for index, detail in enumerate(details):
        if not isinstance(detail, dict):
            raise CaptureBuildError(f"{context}: detail {index} must be an object")
        week_sort = detail.get("weekSort")
        week_label = detail.get("week")
        if not isinstance(week_sort, int) or not isinstance(week_label, str) or not week_label.strip():
            raise CaptureBuildError(f"{context}: detail {index} lacks weekSort/week")
        derived = detail.get("naturalShareDerived")
        share_source = detail.get("naturalShareSource")
        reader_version = detail.get("tier2ReaderVersion")
        raw_text = detail.get("rawText")
        if not isinstance(derived, bool):
            raise CaptureBuildError(
                f"{context}: detail {index} naturalShareDerived must be boolean"
            )
        if not isinstance(share_source, str):
            raise CaptureBuildError(
                f"{context}: detail {index} naturalShareSource must be a string"
            )
        if not isinstance(reader_version, str):
            raise CaptureBuildError(
                f"{context}: detail {index} tier2ReaderVersion must be a string"
            )
        if not isinstance(raw_text, str):
            raise CaptureBuildError(f"{context}: detail {index} rawText must be a string")
        weeks.append(
            {
                "weekSort": week_sort,
                "weekLabel": week_label,
                "totalTraffic": detail.get("totalTraffic"),
                "naturalTraffic": detail.get("naturalTraffic"),
                "naturalSharePct": detail.get("naturalSharePct"),
                "naturalShareDerived": derived,
                "naturalShareSource": share_source,
                "tier2ReaderVersion": reader_version,
                "rawText": raw_text,
                "markers": _markers(detail),
            }
        )
    return weeks


def _history_snapshot_value(snapshot: Any, context: str) -> dict[str, Any]:
    if not isinstance(snapshot, dict) or snapshot.get("schemaVersion") != HISTORY_SNAPSHOT_SCHEMA:
        raise CaptureBuildError(f"{context}: strict-history snapshot is required from Runner 0.3.9")
    if snapshot.get("sourceSchemaVersion") != "strictQualifiedHistory/v1":
        raise CaptureBuildError(f"{context}: unexpected strict-history source schema")
    raw_asins = snapshot.get("asins")
    if not isinstance(raw_asins, list):
        raise CaptureBuildError(f"{context}: history snapshot asins must be a list")
    asins = [str(value).upper() for value in raw_asins]
    if any(not ASIN_RE.fullmatch(asin) for asin in asins):
        raise CaptureBuildError(f"{context}: history snapshot contains an invalid ASIN")
    if asins != sorted(set(asins)):
        raise CaptureBuildError(f"{context}: history snapshot ASINs must be sorted and unique")
    return {
        "schemaVersion": HISTORY_SNAPSHOT_SCHEMA,
        "sourceSchemaVersion": "strictQualifiedHistory/v1",
        "asins": asins,
    }


def _history_snapshot(batch: dict[str, Any], context: str) -> dict[str, Any]:
    return _history_snapshot_value(batch.get("historySnapshotAtGeneration"), f"{context}.historySnapshotAtGeneration")


def _history_isolation(batch: dict[str, Any], context: str, label: str) -> dict[str, Any]:
    isolation = batch.get("historyIsolation")
    if not isinstance(isolation, dict) or isolation.get("schemaVersion") != HISTORY_ISOLATION_SCHEMA:
        raise CaptureBuildError(f"{context}: historyIsolation must be {HISTORY_ISOLATION_SCHEMA}")
    expected_side = "off" if label == "old" else "on"
    expected_sandbox_key = SANDBOX_HISTORY_KEY_PREFIX + expected_side
    expected = {
        "mode": "sandbox",
        "p2Side": expected_side,
        "productionWriteProtected": True,
        "productionKey": PRODUCTION_HISTORY_KEY,
        "activeSandboxKey": expected_sandbox_key,
    }
    for field, value in expected.items():
        if isolation.get(field) != value:
            raise CaptureBuildError(f"{context}: historyIsolation.{field} must be {value!r}")
    production = _history_snapshot_value(
        isolation.get("productionSnapshot"), f"{context}.historyIsolation.productionSnapshot"
    )
    sandbox_seed = _history_snapshot_value(
        isolation.get("sandboxSeedSnapshot"), f"{context}.historyIsolation.sandboxSeedSnapshot"
    )
    active = _history_snapshot(batch, context)
    if production != sandbox_seed or sandbox_seed != active:
        raise CaptureBuildError(f"{context}: production, sandbox seed, and Generate snapshots must match exactly")
    return {
        "schemaVersion": HISTORY_ISOLATION_SCHEMA,
        "version": str(isolation.get("version") or ""),
        **expected,
        "productionSnapshot": production,
        "sandboxSeedSnapshot": sandbox_seed,
    }


def _collector_identity(result: dict[str, Any], context: str, label: str) -> dict[str, Any]:
    identity = result.get("collectorValidationIdentity")
    if not isinstance(identity, dict):
        raise CaptureBuildError(f"{context}: collectorValidationIdentity is required")
    expected_enabled = label == "new"
    expected_protocol = P2_PROTOCOL_NAME if expected_enabled else LEGACY_PROTOCOL_NAME
    expected_protocol_version = "2" if expected_enabled else "1"
    expected_owner = "collector" if expected_enabled else "runner"
    expected = {
        "runnerP2Enabled": expected_enabled,
        "collectorP2Enabled": expected_enabled,
        "collectorVersion": EXPECTED_COLLECTOR_VERSION,
        "protocolName": expected_protocol,
        "protocolVersion": expected_protocol_version,
        "deadlineOwner": expected_owner,
    }
    if identity.get("complete") is not True:
        raise CaptureBuildError(f"{context}: collector validation identity is incomplete")
    for field, value in expected.items():
        if identity.get(field) != value:
            raise CaptureBuildError(
                f"{context}: collector identity {field}={identity.get(field)!r}, expected {value!r}"
            )
    attempt_count = identity.get("attemptCount")
    if not isinstance(attempt_count, int) or isinstance(attempt_count, bool) or attempt_count < 1:
        raise CaptureBuildError(f"{context}: collector identity attemptCount must be a positive integer")
    return {**expected, "attemptCount": attempt_count, "complete": True}


def _attempt_evidence(value: Any, context: str, required: bool) -> dict[str, Any] | None:
    if value is None and not required:
        return None
    if not isinstance(value, dict) or value.get("schemaVersion") != ATTEMPT_EVIDENCE_SCHEMA:
        raise CaptureBuildError(f"{context}: attempt evidence must be {ATTEMPT_EVIDENCE_SCHEMA}")
    outcome = str(value.get("outcome") or "")
    if outcome not in {"payload", "error"}:
        raise CaptureBuildError(f"{context}: outcome must be payload or error")
    payload = value.get("payload")
    if outcome == "payload" and not isinstance(payload, dict):
        raise CaptureBuildError(f"{context}: payload outcome requires a payload object")
    if outcome == "error" and payload is not None:
        raise CaptureBuildError(f"{context}: error outcome payload must be null")
    attempt = value.get("attemptSnapshot")
    if not isinstance(attempt, dict):
        raise CaptureBuildError(f"{context}: attemptSnapshot must be an object")
    payload_copy = json.loads(json.dumps(payload)) if isinstance(payload, dict) else None
    weeks = _weeks(payload_copy, context) if payload_copy is not None else []
    weeks_read = payload_copy.get("weeksRead", 0) if payload_copy is not None else 0
    if not isinstance(weeks_read, int) or isinstance(weeks_read, bool) or weeks_read < 0:
        raise CaptureBuildError(f"{context}: payload weeksRead must be a non-negative integer")
    return {
        "schemaVersion": ATTEMPT_EVIDENCE_SCHEMA,
        "outcome": outcome,
        "status": str((payload_copy or {}).get("status") or ""),
        "weeksRead": weeks_read,
        "weeks": weeks,
        "payload": payload_copy,
        "error": str(value.get("error") or ""),
        "errorCode": str(value.get("errorCode") or ""),
        "attemptSnapshot": json.loads(json.dumps(attempt)),
    }


def _protocol_recovery(value: Any, context: str, label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or value.get("schemaVersion") != PROTOCOL_RECOVERY_SCHEMA:
        raise CaptureBuildError(f"{context}: protocolRecoveryEvidence must be {PROTOCOL_RECOVERY_SCHEMA}")
    pause_count = value.get("pauseCount")
    if not isinstance(pause_count, int) or isinstance(pause_count, bool) or pause_count < 0:
        raise CaptureBuildError(f"{context}: pauseCount must be a non-negative integer")
    reasons = value.get("pauseReasons")
    stale_ids = value.get("staleRunIds")
    quarantined = value.get("quarantinedAttempts")
    if not isinstance(reasons, list) or any(not isinstance(item, str) or not item for item in reasons):
        raise CaptureBuildError(f"{context}: pauseReasons must be a non-empty string list")
    if not isinstance(stale_ids, list) or any(not isinstance(item, str) or not item for item in stale_ids):
        raise CaptureBuildError(f"{context}: staleRunIds must be a non-empty string list")
    if not isinstance(quarantined, list):
        raise CaptureBuildError(f"{context}: quarantinedAttempts must be a list")
    if len(quarantined) != pause_count:
        raise CaptureBuildError(
            f"{context}: quarantinedAttempts count must equal pauseCount"
        )
    normalized_quarantined: list[dict[str, Any]] = []
    for index, item in enumerate(quarantined):
        checked = _attempt_evidence(
            item, f"{context}.quarantinedAttempts[{index}]", True
        )
        if checked["outcome"] != "error" or checked["errorCode"] != "collector_protocol_pause":
            raise CaptureBuildError(
                f"{context}.quarantinedAttempts[{index}]: must be a collector_protocol_pause error"
            )
        normalized_quarantined.append(checked)
    recovered = value.get("recovered")
    fresh_verified = value.get("freshRunIdVerified")
    identity_consistent = value.get("runIdentityConsistent")
    pending_state = str(value.get("pendingRecoveryState") or "")
    fresh_run_id = str(value.get("freshRunId") or "")
    payload_run_id = str(value.get("payloadRunId") or "")
    protocol_run_id = str(value.get("protocolRunId") or "")
    attempt_run_id = str(value.get("attemptRunId") or "")
    if label == "old" and pause_count != 0:
        raise CaptureBuildError(f"{context}: flag-off side cannot have protocol pauses")
    if pause_count == 0:
        if recovered is not False or fresh_verified is not True or pending_state != "not_applicable":
            raise CaptureBuildError(f"{context}: zero-pause recovery state is invalid")
    else:
        if (
            recovered is not True
            or fresh_verified is not True
            or identity_consistent is not True
            or pending_state != "recovered"
            or not reasons
            or not fresh_run_id
            or not stale_ids
            or len(quarantined) != pause_count
            or not payload_run_id
            or payload_run_id != protocol_run_id
            or protocol_run_id != attempt_run_id
            or attempt_run_id != fresh_run_id
            or fresh_run_id in stale_ids
        ):
            raise CaptureBuildError(f"{context}: completed pause recovery lacks a verified fresh run ID")
    return {
        "schemaVersion": PROTOCOL_RECOVERY_SCHEMA,
        "pauseCount": pause_count,
        "pauseReasons": list(reasons),
        "staleRunIds": list(stale_ids),
        "freshRunId": fresh_run_id,
        "payloadRunId": payload_run_id,
        "protocolRunId": protocol_run_id,
        "attemptRunId": attempt_run_id,
        "runIdentityConsistent": identity_consistent is True,
        "freshRunIdVerified": fresh_verified is True,
        "pendingRecoveryState": pending_state,
        "recovered": recovered is True,
        "quarantinedAttempts": normalized_quarantined,
    }


def _side(result: dict[str, Any], pair_id: str, source: Path, label: str) -> dict[str, Any]:
    context = f"{source} {label} {pair_id}"
    asin = _asin(result, context)
    evidence = result.get("collectorEvidence")
    if not isinstance(evidence, dict):
        raise CaptureBuildError(f"{context}: collectorEvidence is required; use Runner 0.3.9")
    timing = ((result.get("telemetry") or {}).get("timing") or {})
    if not isinstance(timing, dict):
        raise CaptureBuildError(f"{context}: telemetry.timing must be an object")
    retry = result.get("retryEvidence")
    if not isinstance(retry, dict):
        raise CaptureBuildError(f"{context}: retryEvidence is required; use Runner 0.3.9")
    protocol_recovery_raw = result.get("protocolRecoveryEvidence")
    identity = _collector_identity(result, context, label)
    p2_enabled = identity["runnerP2Enabled"]
    mode = str(result.get("collectorProtocolMode") or "")
    expected_mode = P2_PROTOCOL_NAME if p2_enabled else LEGACY_PROTOCOL_NAME
    if mode != expected_mode:
        raise CaptureBuildError(f"{context}: collectorProtocolMode {mode!r}, expected {expected_mode!r}")
    raw_protocol = evidence.get("deadlineProtocol")
    telemetry = evidence.get("telemetry") if isinstance(evidence.get("telemetry"), dict) else {}
    raw_telemetry_protocol = telemetry.get("deadline")
    if not p2_enabled and (raw_protocol is not None or raw_telemetry_protocol is not None):
        raise CaptureBuildError(f"{context}: flag-off row contains P2 Collector protocol evidence")
    protocol = raw_protocol if p2_enabled else None
    if p2_enabled and not isinstance(protocol, dict):
        raise CaptureBuildError(f"{context}: enabled P2 row lacks deadlineProtocol")
    if p2_enabled and not isinstance(raw_telemetry_protocol, dict):
        raise CaptureBuildError(f"{context}: enabled P2 row lacks telemetry.deadline")
    if p2_enabled:
        protocol_identity_fields = {
            "protocolName": ("protocolName", "protocolName"),
            "protocolVersion": ("protocolVersion", "domProtocolVersion"),
            "deadlineOwner": ("deadlineOwner", "owner"),
            "runId": ("runId", "runId"),
            "acceptedAtMs": ("acceptedAtMs", "acceptedAtMs"),
            "chartReadyDeadlineAtMs": ("chartReadyDeadlineAtMs", "chartReadyDeadlineAtMs"),
            "chartReadyAtMs": ("chartReadyAtMs", "chartReadyAtMs"),
            "phase": ("phase", "phase"),
            "phaseStartedAtMs": ("phaseStartedAtMs", "phaseStartedAtMs"),
            "phaseDeadlineAtMs": ("phaseDeadlineAtMs", "phaseDeadlineAtMs"),
            "heartbeatAtMs": ("heartbeatAtMs", "heartbeatAtMs"),
            "lastObservedAtMs": ("lastObservedAtMs", "lastObservedAtMs"),
            "clockAnomalyKind": ("clockAnomalyKind", "clockAnomalyKind"),
            "clockAnomalyObservedAtMs": ("clockAnomalyObservedAtMs", "clockAnomalyObservedAtMs"),
            "resultReadyAtMs": ("resultReadyAtMs", "resultReadyAtMs"),
            "terminalReason": ("terminalReason", "terminalReason"),
            "deadlineExceededByMs": ("deadlineExceededByMs", "deadlineExceededByMs"),
            "visibilityState": ("visibilityState", "visibilityState"),
            "hiddenObservedAtMs": ("hiddenObservedAtMs", "hiddenObservedAtMs"),
        }
        for label_name, (payload_field, telemetry_field) in protocol_identity_fields.items():
            if payload_field not in protocol or telemetry_field not in raw_telemetry_protocol:
                raise CaptureBuildError(f"{context}: payload/telemetry deadline {label_name} is missing")
            if protocol.get(payload_field) != raw_telemetry_protocol.get(telemetry_field):
                raise CaptureBuildError(f"{context}: payload/telemetry deadline {label_name} mismatch")
        if protocol.get("clockAnomalyKind") or protocol.get("clockAnomalyObservedAtMs") is not None:
            raise CaptureBuildError(f"{context}: backward wall-clock evidence is quarantined, not capturable")
        accepted_at = protocol.get("acceptedAtMs")
        last_observed_at = protocol.get("lastObservedAtMs")
        if (
            not isinstance(accepted_at, (int, float))
            or isinstance(accepted_at, bool)
            or not isinstance(last_observed_at, (int, float))
            or isinstance(last_observed_at, bool)
            or last_observed_at < accepted_at
        ):
            raise CaptureBuildError(f"{context}: deadline wall-clock timestamps are non-monotonic")
    if isinstance(protocol, dict):
        protocol = json.loads(json.dumps(protocol))
        protocol.setdefault("watchdogClassification", "")
    protocol_recovery = _protocol_recovery(
        protocol_recovery_raw, f"{context}.protocolRecoveryEvidence", label
    )
    strict_decision = str(result.get("strictDecision") or "").lower()
    if strict_decision not in {"pass", "reject"}:
        raise CaptureBuildError(f"{context}: strictDecision must be pass or reject")
    rejection_reason = str(result.get("rejectionReason") or "")
    retry_count = retry.get("retryCount")
    if not isinstance(retry_count, int) or isinstance(retry_count, bool) or retry_count not in {0, 1}:
        raise CaptureBuildError(f"{context}: retryEvidence.retryCount must be 0 or 1")
    expected_attempt_count = retry_count + protocol_recovery["pauseCount"] + 1
    if identity["attemptCount"] != expected_attempt_count:
        raise CaptureBuildError(
            f"{context}: collector attemptCount must equal retryCount + protocolPauseCount + 1"
        )
    first_attempt = _attempt_evidence(retry.get("firstAttemptEvidence"), f"{context}.firstAttemptEvidence", True)
    second_attempt = _attempt_evidence(
        retry.get("secondAttemptEvidence"), f"{context}.secondAttemptEvidence", retry_count == 1
    )
    if retry_count == 0 and second_attempt is not None:
        raise CaptureBuildError(f"{context}: secondAttemptEvidence must be null without retry")
    assert first_attempt is not None
    first_status = str(retry.get("firstAttemptStatus") or "")
    first_weeks = retry.get("firstAttemptWeeksRead")
    if first_attempt["outcome"] == "payload" and (
        first_status != first_attempt["status"] or first_weeks != first_attempt["weeksRead"]
    ):
        raise CaptureBuildError(f"{context}: first-attempt scalar fields do not match full evidence")
    if second_attempt is not None and second_attempt["outcome"] == "payload":
        if (
            str(retry.get("secondAttemptStatus") or "") != second_attempt["status"]
            or retry.get("secondAttemptWeeksRead") != second_attempt["weeksRead"]
        ):
            raise CaptureBuildError(f"{context}: second-attempt scalar fields do not match full evidence")
    recovery = retry.get("retryRecoveryYield")
    if retry_count == 0:
        recovery = None
    elif not isinstance(recovery, bool):
        raise CaptureBuildError(f"{context}: retried row lacks boolean retryRecoveryYield")
    if retry_count == 1:
        assert second_attempt is not None
        computed_recovery = bool(
            first_attempt["outcome"] == "payload"
            and (first_attempt["status"] != "ok" or first_attempt["weeksRead"] < 3)
            and second_attempt["outcome"] == "payload"
            and second_attempt["status"] == "ok"
            and second_attempt["weeksRead"] >= 3
        )
        if recovery is not computed_recovery:
            raise CaptureBuildError(f"{context}: retryRecoveryYield does not match full attempt evidence")
    retry_replaced_first = retry.get("retryReplacedFirst")
    if not isinstance(retry_replaced_first, bool) or (retry_count == 0 and retry_replaced_first):
        raise CaptureBuildError(f"{context}: retryReplacedFirst is invalid")
    selected_attempt = second_attempt if retry_replaced_first else first_attempt
    if (
        selected_attempt is not None
        and selected_attempt["outcome"] == "payload"
        and str(result.get("rejectionRule") or "") != "collection_error"
        and selected_attempt["payload"] != evidence
    ):
        raise CaptureBuildError(f"{context}: final collectorEvidence does not match the selected attempt payload")
    protocol_pause_count = protocol_recovery["pauseCount"]
    protocol_recovered = protocol_recovery["recovered"]
    if protocol_recovered and isinstance(protocol, dict) and protocol_recovery["freshRunId"] != protocol.get("runId"):
        raise CaptureBuildError(f"{context}: recovery freshRunId does not match final Collector protocol")
    collector_timing = (telemetry.get("timing") or {})
    if not isinstance(collector_timing, dict):
        collector_timing = {}
    terminal_reason = (
        str(protocol.get("terminalReason") or "")
        if isinstance(protocol, dict)
        else str(evidence.get("status") or result.get("rejectionRule") or "legacy_result")
    )
    weeks = _weeks(evidence, context)
    weeks_read = evidence.get("weeksRead", 0)
    if not isinstance(weeks_read, int) or weeks_read < 0:
        raise CaptureBuildError(f"{context}: collectorEvidence.weeksRead must be a non-negative integer")
    error_text = str(result.get("error") or "")
    rejection_rule = str(result.get("rejectionRule") or "")
    status = str(result.get("status") or evidence.get("status") or "")
    timeout_text = " ".join(
        str(value or "")
        for value in (error_text, result.get("rejectionReason"), rejection_rule)
    )
    if re.search(r"Timed out after \d+ms", timeout_text):
        timeout_kind = "legacy_runner_wait"
    elif str(evidence.get("status") or "") == "no_chart_loaded" or terminal_reason == "no_chart_loaded":
        timeout_kind = "collector_no_chart_loaded"
    else:
        timeout_kind = ""
    read_class = "timeout_error" if (
        timeout_kind
        or error_text
        or rejection_rule == "collection_error"
        or status not in {"ok", "pass", "reject"}
        or str(evidence.get("status") or "") != "ok"
    ) else "non_timeout"
    return {
        "pairId": pair_id,
        "asin": asin,
        "runnerVersion": str(timing.get("runnerVersion") or ""),
        "collectorVersion": identity["collectorVersion"],
        "p2Enabled": p2_enabled,
        "collectorIdentity": identity,
        "protocol": protocol,
        "status": status,
        "gateOutcome": strict_decision,
        "error": error_text,
        "rejectionRule": rejection_rule,
        "rejectionReason": rejection_reason,
        "readClass": read_class,
        "timing": {
            "totalMs": _number_or_none(timing.get("totalMs")),
            "chartMs": _number_or_none(timing.get("trafficChartMs")),
            "collectorMs": _number_or_none(collector_timing.get("totalMs")),
        },
        "timeout": bool(timeout_kind),
        "timeoutKind": timeout_kind,
        "retryCount": retry_count,
        "recoveryYield": recovery,
        "retryReplacedFirst": retry_replaced_first,
        "firstAttempt": first_attempt,
        "secondAttempt": second_attempt,
        "protocolPauseCount": protocol_pause_count,
        "protocolRecovered": protocol_recovered,
        "protocolRecovery": protocol_recovery,
        "weeksRead": weeks_read,
        "terminalReason": terminal_reason,
        "weeks": weeks,
        "source": str(source.resolve()),
    }


def _index(
    paths: Iterable[Path], label: str
) -> tuple[dict[str, tuple[dict[str, Any], Path]], list[str], dict[str, Any], dict[str, Any]]:
    index: dict[str, tuple[dict[str, Any], Path]] = {}
    order: list[str] = []
    history_baseline: dict[str, Any] | None = None
    isolation_baseline: dict[str, Any] | None = None
    for path in paths:
        batch = _load_json(path)
        if batch.get("schemaVersion") != RUNNER_SCHEMA:
            raise CaptureBuildError(f"{path}: expected {RUNNER_SCHEMA}")
        batch_name = str(batch.get("batchName") or "")
        if not batch_name.startswith(f"p2-{label}-"):
            raise CaptureBuildError(f"{path}: batchName must start with 'p2-{label}-'")
        if batch.get("status") != "done":
            raise CaptureBuildError(f"{path}: paired evidence batch must have status='done'")
        pending = batch.get("pendingRecovery")
        if (
            not isinstance(pending, dict)
            or pending.get("schemaVersion") != PENDING_RECOVERY_SCHEMA
            or pending.get("state") != "none"
            or pending.get("count") != 0
            or pending.get("asins") != []
        ):
            raise CaptureBuildError(f"{path}: done batch must have zero pending-recovery rows")
        snapshot = _history_snapshot(batch, str(path))
        isolation = _history_isolation(batch, str(path), label)
        if history_baseline is None:
            history_baseline = snapshot
        elif snapshot != history_baseline:
            raise CaptureBuildError(f"{path}: {label} batches do not share one history baseline")
        if isolation_baseline is None:
            isolation_baseline = isolation
        elif isolation != isolation_baseline:
            raise CaptureBuildError(f"{path}: {label} batches do not share one sandbox-history baseline")
        if batch.get("historySkippedCount") != 0 or batch.get("historySkippedAsins") != []:
            raise CaptureBuildError(f"{path}: paired evidence batch must have zero history auto-skips")
        results = batch.get("results")
        if not isinstance(results, list):
            raise CaptureBuildError(f"{path}: results must be a list")
        if any(not isinstance(result, dict) for result in results):
            raise CaptureBuildError(f"{path}: every result must be an object")
        queue = batch.get("queue")
        if not isinstance(queue, list):
            raise CaptureBuildError(f"{path}: queue must be a list")
        normalized_queue = [str(value).upper() for value in queue]
        if any(not isinstance(value, str) or not ASIN_RE.fullmatch(value.upper()) for value in queue):
            raise CaptureBuildError(f"{path}: queue must contain only valid ASIN strings")
        result_order = [_asin(result, f"{path} result {row}") for row, result in enumerate(results, start=1)]
        if normalized_queue != result_order:
            raise CaptureBuildError(f"{path}: queue and completed result order must match exactly")
        for row, result in enumerate(results, start=1):
            if not isinstance(result, dict):
                raise CaptureBuildError(f"{path}: result {row} must be an object")
            asin = _asin(result, f"{path} result {row}")
            if asin in index:
                raise CaptureBuildError(f"duplicate {label} ASIN {asin} in {path} and {index[asin][1]}")
            index[asin] = (result, path)
            order.append(asin)
    if history_baseline is None or isolation_baseline is None:
        raise CaptureBuildError(f"no {label} evidence batches supplied")
    return index, order, history_baseline, isolation_baseline


def _recovery_review_index(
    value: dict[str, Any] | None, base_dir: Path
) -> dict[str, dict[str, Any]]:
    if value is None:
        return {}
    if value.get("schemaVersion") != RECOVERY_REVIEW_SCHEMA:
        raise CaptureBuildError(f"recovery review must use {RECOVERY_REVIEW_SCHEMA}")
    rows = value.get("rows")
    if not isinstance(rows, list):
        raise CaptureBuildError("recovery review rows must be a list")
    index: dict[str, dict[str, Any]] = {}
    for position, row in enumerate(rows, start=1):
        context = f"recovery review row {position}"
        if not isinstance(row, dict):
            raise CaptureBuildError(f"{context}: row must be an object")
        asin = str(row.get("asin") or "").upper()
        if not ASIN_RE.fullmatch(asin) or asin in index:
            raise CaptureBuildError(f"{context}: ASIN must be valid and unique")
        pair_id = str(row.get("pairId") or "")
        binding = row.get("reviewBinding")
        if not pair_id:
            raise CaptureBuildError(f"{context}: pairId is required")
        if (
            not isinstance(binding, dict)
            or binding.get("schemaVersion") != REVIEW_BINDING_SCHEMA
            or binding.get("pairId") != pair_id
            or binding.get("asin") != asin
            or not re.fullmatch(r"[0-9a-fA-F]{64}", str(binding.get("evidenceSha256") or ""))
        ):
            raise CaptureBuildError(f"{context}: reviewBinding is invalid")
        manual = row.get("manualTooltipVerified")
        replay = str(row.get("offlineReplayOutcome") or "")
        acceptance = str(row.get("acceptanceOutcome") or "")
        evidence_artifacts = row.get("evidenceArtifacts")
        if not isinstance(manual, bool):
            raise CaptureBuildError(f"{context}: manualTooltipVerified must be boolean")
        if replay not in {"pass", "reject", "not_required"}:
            raise CaptureBuildError(f"{context}: offlineReplayOutcome is invalid")
        if acceptance not in {"pass", "reject", "not_required"}:
            raise CaptureBuildError(f"{context}: acceptanceOutcome is invalid")
        if not isinstance(evidence_artifacts, list) or not evidence_artifacts:
            raise CaptureBuildError(f"{context}: evidenceArtifacts must be a non-empty list")
        verified_artifacts: list[dict[str, Any]] = []
        for artifact_index, artifact in enumerate(evidence_artifacts):
            artifact_context = f"{context}.evidenceArtifacts[{artifact_index}]"
            if not isinstance(artifact, dict):
                raise CaptureBuildError(f"{artifact_context}: artifact must be an object")
            path_text = str(artifact.get("path") or "")
            expected_hash = str(artifact.get("sha256") or "").lower()
            expected_bytes = artifact.get("bytes")
            if not path_text or not re.fullmatch(r"[0-9a-f]{64}", expected_hash):
                raise CaptureBuildError(f"{artifact_context}: path/sha256 is invalid")
            if not isinstance(expected_bytes, int) or isinstance(expected_bytes, bool) or expected_bytes < 0:
                raise CaptureBuildError(f"{artifact_context}: bytes must be a non-negative integer")
            artifact_path = Path(path_text)
            if not artifact_path.is_absolute():
                artifact_path = base_dir / artifact_path
            artifact_path = artifact_path.resolve()
            if not artifact_path.is_file():
                raise CaptureBuildError(f"{artifact_context}: evidence file does not exist: {artifact_path}")
            raw = artifact_path.read_bytes()
            actual_hash = hashlib.sha256(raw).hexdigest()
            if len(raw) != expected_bytes or actual_hash != expected_hash:
                raise CaptureBuildError(f"{artifact_context}: evidence file bytes/hash mismatch")
            verified_artifacts.append(
                {
                    "path": str(artifact_path),
                    "bytes": len(raw),
                    "sha256": actual_hash,
                }
            )
        normalized_review = {
            "schemaVersion": RECOVERY_REVIEW_SCHEMA,
            "asin": asin,
            "pairId": pair_id,
            "reviewBinding": {
                **binding,
                "evidenceSha256": str(binding["evidenceSha256"]).lower(),
            },
            "artifactsVerifiedByBuilder": True,
            "manualTooltipVerified": manual,
            "offlineReplayOutcome": replay,
            "acceptanceOutcome": acceptance,
            "evidenceArtifacts": verified_artifacts,
            "verifiedBy": str(row.get("verifiedBy") or ""),
            "verifiedAt": str(row.get("verifiedAt") or ""),
        }
        attestation_payload = {
            field: normalized_review[field]
            for field in (
                "schemaVersion",
                "asin",
                "pairId",
                "reviewBinding",
                "manualTooltipVerified",
                "offlineReplayOutcome",
                "acceptanceOutcome",
                "evidenceArtifacts",
                "verifiedBy",
                "verifiedAt",
            )
        }
        normalized_review["reviewAttestationSha256"] = hashlib.sha256(
            json.dumps(
                attestation_payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        index[asin] = normalized_review
    return index


def build_capture(
    old_paths: Iterable[Path],
    new_paths: Iterable[Path],
    slow_threshold_ms: float = 40_000,
    recovery_review: dict[str, Any] | None = None,
    recovery_review_base_dir: Path | None = None,
) -> dict[str, Any]:
    old_index, old_order, old_history, old_isolation = _index(old_paths, "old")
    new_index, new_order, new_history, new_isolation = _index(new_paths, "new")
    if old_order != new_order:
        raise CaptureBuildError("old/new completed ASIN sequence must match exactly")
    if old_history != new_history:
        raise CaptureBuildError("old/new sandbox history baselines must match exactly")
    if any(asin in set(old_history["asins"]) for asin in old_order):
        raise CaptureBuildError("paired ASIN sequence contains an ASIN already present in strict history baseline")
    if old_isolation["productionSnapshot"] != new_isolation["productionSnapshot"]:
        raise CaptureBuildError("old/new production history snapshots must match exactly")
    if old_isolation["sandboxSeedSnapshot"] != new_isolation["sandboxSeedSnapshot"]:
        raise CaptureBuildError("old/new sandbox seed snapshots must match exactly")
    reviews = _recovery_review_index(
        recovery_review, (recovery_review_base_dir or Path.cwd()).resolve()
    )
    unknown_reviews = sorted(set(reviews) - set(old_order))
    if unknown_reviews:
        raise CaptureBuildError(f"recovery review contains ASINs outside the paired sequence: {unknown_reviews}")
    pairs: list[dict[str, Any]] = []
    for position, asin in enumerate(old_order, start=1):
        pair_id = f"p2-{position:03d}-{asin}"
        old_entry = old_index.get(asin)
        new_entry = new_index.get(asin)
        row_review = reviews.get(asin)
        if row_review is not None and row_review["pairId"] != pair_id:
            raise CaptureBuildError(
                f"recovery review for {asin} has pairId {row_review['pairId']!r}; expected {pair_id!r}"
            )
        pairs.append(
            {
                "pairId": pair_id,
                "asin": asin,
                "old": _side(old_entry[0], pair_id, old_entry[1], "old") if old_entry else None,
                "new": _side(new_entry[0], pair_id, new_entry[1], "new") if new_entry else None,
                "recoveryReview": row_review,
            }
        )
    return {
        "schemaVersion": CAPTURE_SCHEMA,
        "slowPageThresholdMs": slow_threshold_ms,
        "sequence": old_order,
        "historyBaseline": {"old": old_history, "new": new_history, "exactMatch": True},
        "historyIsolation": {
            "schemaVersion": HISTORY_ISOLATION_SCHEMA,
            "mode": "sandbox",
            "productionWriteProtected": True,
            "old": old_isolation,
            "new": new_isolation,
            "exactProductionSnapshotMatch": True,
            "exactSandboxSeedMatch": True,
        },
        "recoveryReviewProvided": recovery_review is not None,
        "pairs": pairs,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build strict P2 paired evidence from Runner 0.3.9 batches.")
    parser.add_argument("--old", action="append", required=True, type=Path, help="P2-flag-off combined JSON; repeatable")
    parser.add_argument("--new", action="append", required=True, type=Path, help="P2-flag-on combined JSON; repeatable")
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--recovery-review", type=Path, help="Optional manual/replay/acceptance review JSON")
    parser.add_argument("--slow-page-threshold-ms", type=float, default=40_000)
    args = parser.parse_args()
    try:
        review = _load_json(args.recovery_review) if args.recovery_review else None
        capture = build_capture(
            args.old,
            args.new,
            args.slow_page_threshold_ms,
            review,
            args.recovery_review.resolve().parent if args.recovery_review else None,
        )
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(capture, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(args.out.resolve())
        return 0
    except CaptureBuildError as error:
        print(f"[ERROR] {error}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
