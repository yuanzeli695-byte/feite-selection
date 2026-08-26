"""Compare old/new SellerSprite P2 live evidence without changing hard eligibility.

The input is an auditable JSON capture with one object per paired ASIN.  This
tool only compares values already present in the capture; it never fills in
missing weeks, derives traffic values, or creates synthetic rows.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import sys
from collections import Counter
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "sellerSpriteP2PairedEvidence/v1"
INPUT_SCHEMA_VERSION = "sellerSpriteP2PairCapture/v1"
MIN_PAIRS = 30
MIN_OLD_TIMEOUT_ERROR_PAIRS = 5
MIN_GENUINE_RECOVERIES = 3
DEFAULT_SLOW_PAGE_THRESHOLD_MS = 40_000.0
OUTCOMES = {"pass", "reject"}
NUMERIC_WEEK_FIELDS = ("totalTraffic", "naturalTraffic", "naturalSharePct")
TIMING_FIELDS = ("totalMs", "chartMs", "collectorMs")
OVERLAP_EXACT_FIELDS = (
    *NUMERIC_WEEK_FIELDS,
    "naturalShareDerived",
    "naturalShareSource",
    "tier2ReaderVersion",
    "rawText",
    "markers",
    "exactScalarEncodings",
)
ASIN_RE = re.compile(r"^[A-Z0-9]{10}$")
P2_PROTOCOL_NAME = "p2-collector-owned-deadline-v1"
P2_PROTOCOL_VERSION = "2"
P2_DEADLINE_OWNER = "collector"
LEGACY_PROTOCOL_NAME = "legacy_status_text_v1"
HISTORY_SNAPSHOT_SCHEMA = "strictQualifiedHistorySnapshot/v1"
HISTORY_ISOLATION_SCHEMA = "p2PairHistoryIsolation/v1"
ATTEMPT_EVIDENCE_SCHEMA = "collectorAttemptEvidence/v1"
PROTOCOL_RECOVERY_SCHEMA = "collectorProtocolRecoveryEvidence/v1"
RECOVERY_REVIEW_SCHEMA = "sellerSpriteP2RecoveryReview/v2"
REVIEW_BINDING_SCHEMA = "sellerSpriteP2ReviewBinding/v1"
REPRESENTATIVE_RUN_SCHEMA = "sellerSpriteP2RepresentativeRun/v1"
TIER2_READER_VERSION = "tier2.1-zero-share-v1"
TIMEOUT_KINDS = {"", "legacy_runner_wait", "collector_no_chart_loaded"}
EXPECTED_RUNNER_VERSION = "0.3.9"
EXPECTED_COLLECTOR_VERSION = "0.4.7"


class ContractError(ValueError):
    """Raised when the top-level capture contract cannot be read."""


def _text(value: Any, field: str, context: str, *, required: bool = True) -> str:
    if not isinstance(value, str):
        if value is None and not required:
            return ""
        raise ContractError(f"{context}: {field} must be a string")
    if required and not value.strip():
        raise ContractError(f"{context}: {field} must not be blank")
    return value


def _asin(value: Any, field: str, context: str) -> str:
    text = _text(value, field, context).upper()
    if not ASIN_RE.fullmatch(text):
        raise ContractError(f"{context}: {field} is not a 10-character ASIN: {text!r}")
    return text


def _decimal(value: Any, field: str, context: str, *, allow_none: bool = True) -> Decimal | None:
    if value is None:
        if allow_none:
            return None
        raise ContractError(f"{context}: {field} is required")
    if isinstance(value, bool):
        raise ContractError(f"{context}: {field} must be a decimal or null")
    if isinstance(value, float) and not math.isfinite(value):
        raise ContractError(f"{context}: {field} must be finite")
    try:
        parsed = Decimal(str(value).strip())
    except (InvalidOperation, ValueError, AttributeError) as error:
        raise ContractError(f"{context}: {field} is not a decimal: {value!r}") from error
    if not parsed.is_finite():
        raise ContractError(f"{context}: {field} must be finite")
    return parsed


def _decimal_text(value: Any, field: str, context: str) -> str | None:
    parsed = _decimal(value, field, context)
    if parsed is None:
        return None
    if parsed == 0:
        return "0"
    # Fixed-point formatting removes exponent notation while preserving the
    # exact decimal value.  Trailing zeroes are not significant for pairing.
    text = format(parsed.normalize(), "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def _nonnegative_number(value: Any, field: str, context: str, *, required: bool = True) -> float | None:
    if value is None:
        if required:
            raise ContractError(f"{context}: {field} is required")
        return None
    if isinstance(value, bool):
        raise ContractError(f"{context}: {field} must be a non-negative number")
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise ContractError(f"{context}: {field} is not numeric: {value!r}") from error
    if not math.isfinite(number) or number < 0:
        raise ContractError(f"{context}: {field} must be a finite non-negative number")
    return number


def _integer(value: Any, field: str, context: str) -> int:
    if isinstance(value, bool):
        raise ContractError(f"{context}: {field} must be an integer")
    try:
        number = int(value)
    except (TypeError, ValueError) as error:
        raise ContractError(f"{context}: {field} must be an integer") from error
    if str(value).strip() != str(number) and not isinstance(value, int):
        raise ContractError(f"{context}: {field} must be an integer")
    if number < 0:
        raise ContractError(f"{context}: {field} must be non-negative")
    return number


def _percentile(values: list[float], quantile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * quantile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def _stats(values: list[float], total: int) -> dict[str, Any]:
    return {
        "count": len(values),
        "missing": total - len(values),
        "sumMs": round(sum(values), 3),
        "p50Ms": _round(_percentile(values, 0.5)),
        "p90Ms": _round(_percentile(values, 0.9)),
        "maxMs": _round(max(values) if values else None),
    }


def _round(value: float | None) -> float | None:
    return None if value is None else round(value, 3)


def _exact_scalar_encoding(value: Any) -> str:
    return f"{type(value).__name__}:{json.dumps(value, ensure_ascii=False, separators=(',', ':'))}"


def _week_map(side: dict[str, Any], context: str) -> dict[tuple[int, str], dict[str, Any]]:
    weeks = side.get("weeks")
    if not isinstance(weeks, list):
        raise ContractError(f"{context}: weeks must be a list")
    result: dict[tuple[int, str], dict[str, Any]] = {}
    seen_sort: set[int] = set()
    seen_label: set[str] = set()
    for index, week in enumerate(weeks):
        week_context = f"{context}.weeks[{index}]"
        if not isinstance(week, dict):
            raise ContractError(f"{week_context}: week must be an object")
        if "weekSort" not in week or "weekLabel" not in week:
            raise ContractError(f"{week_context}: weekSort and weekLabel are required")
        week_sort = _integer(week["weekSort"], "weekSort", week_context)
        week_label = _text(week["weekLabel"], "weekLabel", week_context)
        if week_sort in seen_sort or week_label in seen_label:
            raise ContractError(f"{week_context}: duplicate weekSort or weekLabel")
        seen_sort.add(week_sort)
        seen_label.add(week_label)
        numeric = {}
        for field in NUMERIC_WEEK_FIELDS:
            if field not in week:
                raise ContractError(f"{week_context}: missing {field}")
            numeric[field] = _decimal_text(week[field], field, week_context)
        markers = week.get("markers", [])
        if markers is None:
            markers = []
        if not isinstance(markers, list) or any(not isinstance(marker, str) for marker in markers):
            raise ContractError(f"{week_context}: markers must be a string list")
        raw_text = week.get("rawText", "")
        if raw_text is not None and not isinstance(raw_text, str):
            raise ContractError(f"{week_context}: rawText must be a string or null")
        derived = week.get("naturalShareDerived")
        if not isinstance(derived, bool):
            raise ContractError(f"{week_context}: naturalShareDerived must be boolean")
        share_source = _text(
            week.get("naturalShareSource", ""), "naturalShareSource", week_context, required=False
        )
        reader_version = _text(
            week.get("tier2ReaderVersion", ""), "tier2ReaderVersion", week_context, required=False
        )
        result[(week_sort, week_label)] = {
            "weekSort": week_sort,
            "weekLabel": week_label,
            **numeric,
            "markers": list(markers),
            "rawText": raw_text or "",
            "naturalShareDerived": derived,
            "naturalShareSource": share_source,
            "tier2ReaderVersion": reader_version,
            "exactScalarEncodings": {
                field: _exact_scalar_encoding(week.get(field))
                for field in (
                    *NUMERIC_WEEK_FIELDS,
                    "naturalShareDerived",
                    "naturalShareSource",
                    "tier2ReaderVersion",
                    "rawText",
                    "markers",
                )
            },
        }
    return result


def _history_snapshot(value: Any, field: str, context: str) -> dict[str, Any]:
    if not isinstance(value, dict) or value.get("schemaVersion") != HISTORY_SNAPSHOT_SCHEMA:
        raise ContractError(f"{context}: {field} must be a {HISTORY_SNAPSHOT_SCHEMA} object")
    if value.get("sourceSchemaVersion") != "strictQualifiedHistory/v1":
        raise ContractError(f"{context}: {field}.sourceSchemaVersion is invalid")
    raw_asins = value.get("asins")
    if not isinstance(raw_asins, list):
        raise ContractError(f"{context}: {field}.asins must be a list")
    asins = [_asin(asin, f"{field}.asins", context) for asin in raw_asins]
    if asins != sorted(set(asins)):
        raise ContractError(f"{context}: {field}.asins must be sorted and unique")
    return {
        "schemaVersion": HISTORY_SNAPSHOT_SCHEMA,
        "sourceSchemaVersion": "strictQualifiedHistory/v1",
        "asins": asins,
    }


def _history_isolation(value: Any, context: str) -> dict[str, Any]:
    if not isinstance(value, dict) or value.get("schemaVersion") != HISTORY_ISOLATION_SCHEMA:
        raise ContractError(f"{context}: historyIsolation must be {HISTORY_ISOLATION_SCHEMA}")
    if value.get("mode") != "sandbox" or value.get("productionWriteProtected") is not True:
        raise ContractError(f"{context}: production history must be write-protected sandbox mode")
    if value.get("exactProductionSnapshotMatch") is not True or value.get("exactSandboxSeedMatch") is not True:
        raise ContractError(f"{context}: old/new history isolation snapshots must match exactly")
    old = value.get("old")
    new = value.get("new")
    if not isinstance(old, dict) or not isinstance(new, dict):
        raise ContractError(f"{context}: historyIsolation old/new objects are required")
    for label, side, expected_side in (("old", old, "off"), ("new", new, "on")):
        if (
            side.get("schemaVersion") != HISTORY_ISOLATION_SCHEMA
            or side.get("mode") != "sandbox"
            or side.get("productionWriteProtected") is not True
            or side.get("p2Side") != expected_side
            or not str(side.get("activeSandboxKey") or "").endswith(":" + expected_side)
        ):
            raise ContractError(f"{context}: {label} sandbox identity is invalid")
    old_production = _history_snapshot(old.get("productionSnapshot"), "old.productionSnapshot", context)
    new_production = _history_snapshot(new.get("productionSnapshot"), "new.productionSnapshot", context)
    old_seed = _history_snapshot(old.get("sandboxSeedSnapshot"), "old.sandboxSeedSnapshot", context)
    new_seed = _history_snapshot(new.get("sandboxSeedSnapshot"), "new.sandboxSeedSnapshot", context)
    if not (old_production == new_production == old_seed == new_seed):
        raise ContractError(f"{context}: production and sandbox seed snapshots differ")
    return {
        "schemaVersion": HISTORY_ISOLATION_SCHEMA,
        "mode": "sandbox",
        "productionWriteProtected": True,
        "productionSnapshot": old_production,
        "oldSandboxKey": old.get("activeSandboxKey"),
        "newSandboxKey": new.get("activeSandboxKey"),
    }


def _parse_attempt(value: Any, context: str, required: bool) -> dict[str, Any] | None:
    if value is None and not required:
        return None
    if not isinstance(value, dict) or value.get("schemaVersion") != ATTEMPT_EVIDENCE_SCHEMA:
        raise ContractError(f"{context}: attempt evidence must be {ATTEMPT_EVIDENCE_SCHEMA}")
    outcome = _text(value.get("outcome"), "outcome", context)
    if outcome not in {"payload", "error"}:
        raise ContractError(f"{context}: attempt outcome must be payload or error")
    status = _text(value.get("status", ""), "status", context, required=False)
    weeks_read = _integer(value.get("weeksRead", 0), "weeksRead", context)
    weeks = _week_map(value, context)
    if outcome == "error" and (weeks_read != 0 or weeks):
        raise ContractError(f"{context}: error attempt cannot contain accepted week evidence")
    return {
        "outcome": outcome,
        "status": status,
        "weeksRead": weeks_read,
        "weeks": weeks,
        "error": _text(value.get("error", ""), "error", context, required=False),
    }


def _parse_protocol_recovery(value: Any, context: str) -> dict[str, Any]:
    if not isinstance(value, dict) or value.get("schemaVersion") != PROTOCOL_RECOVERY_SCHEMA:
        raise ContractError(f"{context}: protocolRecovery must be {PROTOCOL_RECOVERY_SCHEMA}")
    pause_count = _integer(value.get("pauseCount"), "pauseCount", context)
    recovered = value.get("recovered")
    if not isinstance(recovered, bool):
        raise ContractError(f"{context}: recovered must be boolean")
    state = _text(value.get("pendingRecoveryState"), "pendingRecoveryState", context)
    fresh_verified = value.get("freshRunIdVerified")
    identity_consistent = value.get("runIdentityConsistent")
    stale = value.get("staleRunIds")
    quarantined = value.get("quarantinedAttempts")
    if not isinstance(stale, list) or any(not isinstance(item, str) or not item for item in stale):
        raise ContractError(f"{context}: staleRunIds must be a string list")
    if not isinstance(quarantined, list):
        raise ContractError(f"{context}: quarantinedAttempts must be a list")
    if pause_count == 0:
        if recovered or fresh_verified is not True or state != "not_applicable" or quarantined:
            raise ContractError(f"{context}: zero-pause recovery state is invalid")
    elif (
        not recovered
        or fresh_verified is not True
        or identity_consistent is not True
        or state != "recovered"
        or not stale
        or str(value.get("freshRunId") or "") in stale
        or len(quarantined) != pause_count
    ):
        raise ContractError(f"{context}: resumed row lacks verified fresh-run recovery")
    for index, item in enumerate(quarantined):
        parsed = _parse_attempt(item, f"{context}.quarantinedAttempts[{index}]", True)
        if parsed["outcome"] != "error" or item.get("errorCode") != "collector_protocol_pause":
            raise ContractError(
                f"{context}.quarantinedAttempts[{index}]: must be a collector_protocol_pause error"
            )
    return {
        "pauseCount": pause_count,
        "recovered": recovered,
        "pendingRecoveryState": state,
        "freshRunId": str(value.get("freshRunId") or ""),
        "staleRunIds": list(stale),
        "freshRunIdVerified": fresh_verified is True,
    }


def _parse_side(side: Any, pair_id: str, pair_asin: str, label: str) -> dict[str, Any]:
    context = f"pair {pair_id} {label}"
    if not isinstance(side, dict):
        raise ContractError(f"{context}: side must be an object")
    side_pair_id = _text(side.get("pairId", pair_id), "pairId", context)
    side_asin = _asin(side.get("asin"), "asin", context)
    if side_pair_id != pair_id or side_asin != pair_asin:
        raise ContractError(f"{context}: pair identity does not match top-level pair")
    outcome = _text(side.get("gateOutcome"), "gateOutcome", context).lower()
    if outcome not in OUTCOMES:
        raise ContractError(f"{context}: unsupported gateOutcome {outcome!r}")
    status = _text(side.get("status"), "status", context)
    runner_version = _text(side.get("runnerVersion"), "runnerVersion", context)
    collector_version = _text(side.get("collectorVersion"), "collectorVersion", context)
    if runner_version != EXPECTED_RUNNER_VERSION:
        raise ContractError(f"{context}: runnerVersion must be {EXPECTED_RUNNER_VERSION!r}")
    if collector_version != EXPECTED_COLLECTOR_VERSION:
        raise ContractError(f"{context}: collectorVersion must be {EXPECTED_COLLECTOR_VERSION!r}")
    p2_enabled = side.get("p2Enabled")
    if not isinstance(p2_enabled, bool):
        raise ContractError(f"{context}: p2Enabled must be boolean")
    identity_raw = side.get("collectorIdentity")
    if not isinstance(identity_raw, dict) or identity_raw.get("complete") is not True:
        raise ContractError(f"{context}: complete collectorIdentity is required")
    expected_enabled = label == "new"
    expected_identity = {
        "runnerP2Enabled": expected_enabled,
        "collectorP2Enabled": expected_enabled,
        "collectorVersion": EXPECTED_COLLECTOR_VERSION,
        "protocolName": P2_PROTOCOL_NAME if expected_enabled else LEGACY_PROTOCOL_NAME,
        "protocolVersion": "2" if expected_enabled else "1",
        "deadlineOwner": "collector" if expected_enabled else "runner",
    }
    for field, expected in expected_identity.items():
        if identity_raw.get(field) != expected:
            raise ContractError(f"{context}: collectorIdentity.{field} must be {expected!r}")
    attempt_count = _integer(identity_raw.get("attemptCount"), "collectorIdentity.attemptCount", context)
    if attempt_count < 1:
        raise ContractError(f"{context}: collectorIdentity.attemptCount must be positive")
    if p2_enabled != identity_raw.get("runnerP2Enabled"):
        raise ContractError(f"{context}: p2Enabled does not match collectorIdentity.runnerP2Enabled")
    protocol_raw = side.get("protocol")
    protocol: dict[str, Any] | None = None
    if p2_enabled:
        if not isinstance(protocol_raw, dict):
            raise ContractError(f"{context}: protocol object is required when p2Enabled is true")
        protocol_name = _text(protocol_raw.get("protocolName"), "protocol.protocolName", context)
        protocol_version = _text(protocol_raw.get("protocolVersion"), "protocol.protocolVersion", context)
        deadline_owner = _text(protocol_raw.get("deadlineOwner"), "protocol.deadlineOwner", context)
        run_id = _text(protocol_raw.get("runId"), "protocol.runId", context)
        if protocol_name != P2_PROTOCOL_NAME:
            raise ContractError(f"{context}: unexpected protocol name {protocol_name!r}")
        if protocol_version != P2_PROTOCOL_VERSION:
            raise ContractError(f"{context}: unexpected protocol version {protocol_version!r}")
        if deadline_owner != P2_DEADLINE_OWNER:
            raise ContractError(f"{context}: deadline owner must be {P2_DEADLINE_OWNER!r}")
        protocol = {
            "protocolName": protocol_name,
            "protocolVersion": protocol_version,
            "deadlineOwner": deadline_owner,
            "runId": run_id,
            "acceptedAtMs": _nonnegative_number(protocol_raw.get("acceptedAtMs"), "protocol.acceptedAtMs", context),
            "phase": _text(protocol_raw.get("phase"), "protocol.phase", context),
            "phaseStartedAtMs": _nonnegative_number(protocol_raw.get("phaseStartedAtMs"), "protocol.phaseStartedAtMs", context),
            "phaseDeadlineAtMs": _nonnegative_number(
                protocol_raw.get("phaseDeadlineAtMs"), "protocol.phaseDeadlineAtMs", context, required=False
            ),
            "heartbeatAtMs": _nonnegative_number(protocol_raw.get("heartbeatAtMs"), "protocol.heartbeatAtMs", context),
            "lastObservedAtMs": _nonnegative_number(
                protocol_raw.get("lastObservedAtMs"), "protocol.lastObservedAtMs", context
            ),
            "clockAnomalyKind": _text(
                protocol_raw.get("clockAnomalyKind", ""), "protocol.clockAnomalyKind", context, required=False
            ),
            "clockAnomalyObservedAtMs": _nonnegative_number(
                protocol_raw.get("clockAnomalyObservedAtMs"),
                "protocol.clockAnomalyObservedAtMs",
                context,
                required=False,
            ),
            "chartReadyDeadlineAtMs": _nonnegative_number(
                protocol_raw.get("chartReadyDeadlineAtMs"), "protocol.chartReadyDeadlineAtMs", context
            ),
            "chartReadyAtMs": _nonnegative_number(
                protocol_raw.get("chartReadyAtMs"), "protocol.chartReadyAtMs", context, required=False
            ),
            "resultReadyAtMs": _nonnegative_number(protocol_raw.get("resultReadyAtMs"), "protocol.resultReadyAtMs", context),
            "terminalReason": _text(protocol_raw.get("terminalReason"), "protocol.terminalReason", context),
            "visibilityState": _text(protocol_raw.get("visibilityState"), "protocol.visibilityState", context),
            "hiddenObservedAtMs": _nonnegative_number(
                protocol_raw.get("hiddenObservedAtMs"), "protocol.hiddenObservedAtMs", context, required=False
            ),
            "deadlineExceededByMs": _nonnegative_number(
                protocol_raw.get("deadlineExceededByMs"), "protocol.deadlineExceededByMs", context, required=False
            ),
            "watchdogClassification": _text(
                protocol_raw.get("watchdogClassification", ""),
                "protocol.watchdogClassification",
                context,
                required=False,
            ),
        }
        if protocol["phase"] != "result_ready":
            raise ContractError(f"{context}: completed P2 evidence must have protocol.phase='result_ready'")
        if protocol["visibilityState"] != "visible" or protocol["hiddenObservedAtMs"] is not None:
            raise ContractError(f"{context}: hidden/throttled protocol evidence cannot be accepted")
        if protocol["clockAnomalyKind"] or protocol["clockAnomalyObservedAtMs"] is not None:
            raise ContractError(f"{context}: backward wall-clock evidence cannot be accepted")
        if protocol["lastObservedAtMs"] < protocol["acceptedAtMs"]:
            raise ContractError(f"{context}: protocol wall-clock timestamps are non-monotonic")
        if (
            protocol["chartReadyAtMs"] is not None
            and protocol["chartReadyAtMs"] > protocol["chartReadyDeadlineAtMs"]
        ):
            raise ContractError(f"{context}: chart became ready after the 60s hard deadline")
    elif protocol_raw is not None:
        raise ContractError(f"{context}: protocol must be null when p2Enabled is false")
    protocol_recovery = _parse_protocol_recovery(
        side.get("protocolRecovery"), f"{context}.protocolRecovery"
    )
    protocol_pause_count = _integer(side.get("protocolPauseCount"), "protocolPauseCount", context)
    protocol_recovered = side.get("protocolRecovered")
    if (
        not isinstance(protocol_recovered, bool)
        or protocol_pause_count != protocol_recovery["pauseCount"]
        or protocol_recovered != protocol_recovery["recovered"]
    ):
        raise ContractError(f"{context}: protocol recovery summary does not match full evidence")
    timing = side.get("timing")
    if not isinstance(timing, dict):
        raise ContractError(f"{context}: timing must be an object")
    timing_values = {
        field: _nonnegative_number(
            timing.get(field), f"timing.{field}", context, required=(field == "totalMs")
        )
        for field in TIMING_FIELDS
    }
    timeout = side.get("timeout")
    if not isinstance(timeout, bool):
        raise ContractError(f"{context}: timeout must be boolean")
    timeout_kind = _text(side.get("timeoutKind", ""), "timeoutKind", context, required=False)
    if timeout_kind not in TIMEOUT_KINDS:
        raise ContractError(f"{context}: unsupported timeoutKind {timeout_kind!r}")
    if timeout != bool(timeout_kind):
        raise ContractError(f"{context}: timeout must equal bool(timeoutKind)")
    if label == "old" and timeout_kind not in {"", "legacy_runner_wait"}:
        raise ContractError(f"{context}: old side has an invalid timeoutKind")
    if label == "new" and timeout_kind not in {"", "collector_no_chart_loaded"}:
        raise ContractError(f"{context}: new side has an invalid timeoutKind")
    retry_count = _integer(side.get("retryCount"), "retryCount", context)
    if retry_count not in {0, 1}:
        raise ContractError(f"{context}: retryCount must be 0 or 1")
    expected_attempt_count = retry_count + protocol_pause_count + 1
    if attempt_count != expected_attempt_count:
        raise ContractError(
            f"{context}: collectorIdentity.attemptCount must equal retryCount + protocolPauseCount + 1"
        )
    recovery = side.get("recoveryYield")
    if recovery is not None and not isinstance(recovery, bool):
        raise ContractError(f"{context}: recoveryYield must be boolean or null")
    if retry_count == 0 and recovery is not None:
        raise ContractError(f"{context}: recoveryYield must be null when retryCount is zero")
    if retry_count > 0 and recovery is None:
        raise ContractError(f"{context}: recoveryYield is required when retryCount is positive")
    first_attempt = _parse_attempt(side.get("firstAttempt"), f"{context}.firstAttempt", True)
    second_attempt = _parse_attempt(side.get("secondAttempt"), f"{context}.secondAttempt", retry_count == 1)
    if retry_count == 0 and second_attempt is not None:
        raise ContractError(f"{context}: secondAttempt must be null without retry")
    if retry_count == 1:
        assert first_attempt is not None and second_attempt is not None
        computed_recovery = bool(
            first_attempt["outcome"] == "payload"
            and (first_attempt["status"] != "ok" or first_attempt["weeksRead"] < 3)
            and second_attempt["outcome"] == "payload"
            and second_attempt["status"] == "ok"
            and second_attempt["weeksRead"] >= 3
        )
        if recovery is not computed_recovery:
            raise ContractError(f"{context}: recoveryYield does not match full attempt evidence")
    terminal_reason = side.get("terminalReason", "")
    if terminal_reason is not None and not isinstance(terminal_reason, str):
        raise ContractError(f"{context}: terminalReason must be a string or null")
    source = _text(side.get("source"), "source", context)
    if protocol is not None and terminal_reason and protocol["terminalReason"] != terminal_reason:
        raise ContractError(f"{context}: terminalReason does not match protocol.terminalReason")
    weeks = _week_map(side, context)
    weeks_read = _integer(side.get("weeksRead"), "weeksRead", context)
    measured_weeks = sum(1 for week in weeks.values() if week["naturalSharePct"] is not None)
    if weeks_read != measured_weeks:
        raise ContractError(
            f"{context}: weeksRead={weeks_read} does not match {measured_weeks} weeks with a naturalSharePct"
        )
    read_class = _text(side.get("readClass"), "readClass", context)
    if read_class not in {"non_timeout", "timeout_error"}:
        raise ContractError(f"{context}: readClass is invalid")
    error_text = _text(side.get("error", ""), "error", context, required=False)
    rejection_rule = _text(side.get("rejectionRule", ""), "rejectionRule", context, required=False)
    expected_read_class = "timeout_error" if (
        timeout
        or error_text
        or rejection_rule == "collection_error"
        or status not in {"ok", "pass", "reject"}
    ) else "non_timeout"
    if read_class != expected_read_class:
        raise ContractError(f"{context}: readClass does not match timeout/error evidence")
    return {
        "label": label,
        "pairId": pair_id,
        "asin": pair_asin,
        "gateOutcome": outcome,
        "status": status,
        "runnerVersion": runner_version,
        "collectorVersion": collector_version,
        "p2Enabled": p2_enabled,
        "collectorIdentity": {**expected_identity, "attemptCount": attempt_count, "complete": True},
        "protocol": protocol,
        "timing": timing_values,
        "timeout": timeout,
        "timeoutKind": timeout_kind,
        "retryCount": retry_count,
        "recoveryYield": recovery,
        "firstAttempt": first_attempt,
        "secondAttempt": second_attempt,
        "protocolPauseCount": protocol_pause_count,
        "protocolRecovered": protocol_recovered,
        "protocolRecovery": protocol_recovery,
        "terminalReason": terminal_reason or "",
        "weeksRead": weeks_read,
        "weeks": weeks,
        "readClass": read_class,
        "error": error_text,
        "rejectionRule": rejection_rule,
        "rejectionReason": _text(
            side.get("rejectionReason", ""), "rejectionReason", context, required=False
        ),
        "source": source,
    }


def _has_marker(week: dict[str, Any], marker: str) -> bool:
    return marker in week["markers"] or marker in week["rawText"]


def _side_strata(side: dict[str, Any], slow_threshold: float) -> dict[str, bool]:
    weeks = list(side["weeks"].values())
    explicit_zero = any(
        week["totalTraffic"] is not None
        and week["naturalTraffic"] is not None
        and week["naturalSharePct"] is not None
        and Decimal(week["totalTraffic"]) > 0
        and Decimal(week["naturalTraffic"]) == 0
        and Decimal(week["naturalSharePct"]) == 0
        for week in weeks
    )
    dash_marker = any(_has_marker(week, "--") for week in weeks)
    missing_ratio = any(week["naturalSharePct"] is None for week in weeks)
    partial = side["weeksRead"] in {1, 2}
    timing = side["timing"]
    slow = bool(
        (timing["totalMs"] is not None and timing["totalMs"] >= slow_threshold)
        or (timing["chartMs"] is not None and timing["chartMs"] >= slow_threshold)
    )
    return {
        "explicitZero": explicit_zero,
        "dashMarker": dash_marker,
        "missingRatio": missing_ratio,
        "partial1to2Weeks": partial,
        "slowPage": slow,
    }


def _metric_summary(sides: list[dict[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for field in TIMING_FIELDS:
        values = [side["timing"][field] for side in sides if side["timing"][field] is not None]
        result[field] = _stats(values, len(sides))
    timeout_count = sum(1 for side in sides if side["timeout"])
    retry_sides = [side for side in sides if side["retryCount"] > 0]
    recovered = sum(1 for side in retry_sides if side["recoveryYield"] is True)
    result["timeout"] = {
        "count": timeout_count,
        "ratePct": round(100 * timeout_count / len(sides), 4) if sides else 0.0,
        "byKind": dict(sorted(Counter(side["timeoutKind"] for side in sides if side["timeoutKind"]).items())),
    }
    result["retry"] = {
        "rows": len(retry_sides),
        "attempts": sum(side["retryCount"] for side in retry_sides),
        "recovered": recovered,
        "recoveryYieldPct": round(100 * recovered / len(retry_sides), 4) if retry_sides else None,
    }
    first_attempts = [side["firstAttempt"] for side in sides]
    result["firstAttempt"] = {
        "payloadRows": sum(1 for attempt in first_attempts if attempt and attempt["outcome"] == "payload"),
        "errorRows": sum(1 for attempt in first_attempts if attempt and attempt["outcome"] == "error"),
        "usableTrafficRows": sum(
            1
            for attempt in first_attempts
            if attempt and attempt["outcome"] == "payload" and attempt["status"] == "ok" and attempt["weeksRead"] >= 3
        ),
        "statusCounts": dict(sorted(Counter((attempt or {}).get("status") or (attempt or {}).get("outcome") for attempt in first_attempts).items())),
    }
    protocol_paused = [side for side in sides if side["protocolPauseCount"] > 0]
    protocol_recovered = sum(1 for side in protocol_paused if side["protocolRecovered"])
    result["protocolPause"] = {
        "rows": len(protocol_paused),
        "attempts": sum(side["protocolPauseCount"] for side in protocol_paused),
        "recovered": protocol_recovered,
        "recoveryYieldPct": (
            round(100 * protocol_recovered / len(protocol_paused), 4) if protocol_paused else None
        ),
    }
    return result


def _delta(new_value: float | None, old_value: float | None) -> float | None:
    if new_value is None or old_value is None:
        return None
    return round(new_value - old_value, 3)


def _paired_timing_delta_stats(
    pairs: dict[str, tuple[dict[str, Any], dict[str, Any]]], field: str
) -> dict[str, Any]:
    deltas: list[float] = []
    for old, new in pairs.values():
        old_value = old["timing"][field]
        new_value = new["timing"][field]
        if old_value is not None and new_value is not None:
            deltas.append(new_value - old_value)
    return {
        "count": len(deltas),
        "missing": len(pairs) - len(deltas),
        "p50DeltaMs": _round(_percentile(deltas, 0.5)),
        "p90DeltaMs": _round(_percentile(deltas, 0.9)),
        "minDeltaMs": _round(min(deltas) if deltas else None),
        "maxDeltaMs": _round(max(deltas) if deltas else None),
    }


def _value_recovery_metrics(
    pairs: dict[str, tuple[dict[str, Any], dict[str, Any]]],
    recoveries: list[dict[str, Any]],
) -> dict[str, Any]:
    partial_rows: list[dict[str, Any]] = []
    collection_error_rows: list[dict[str, Any]] = []
    partial_candidates = 0
    partial_verified = 0
    partial_release_validated = 0
    partial_qualified = 0
    partial_first_attempt = 0
    partial_retry_assisted = 0
    collection_candidates = 0
    collection_recovered = 0
    collection_release_validated = 0
    collection_qualified = 0
    recovery_by_pair = {recovery["pairId"]: recovery for recovery in recoveries}

    for pair_id, (old, new) in pairs.items():
        partial_eligible = (
            old["status"] == "ok"
            and old["rejectionRule"] == "traffic_weeks_insufficient"
            and old["weeksRead"] in {1, 2}
        )
        collection_error = old["rejectionRule"] == "collection_error"
        if not partial_eligible and not collection_error:
            continue

        candidate = new["status"] == "ok" and new["weeksRead"] >= 3
        recovery = recovery_by_pair.get(pair_id)
        verified = bool(recovery and recovery["genuine"])
        review_complete = bool(verified and recovery["reviewDecision"]["complete"])
        release_validated_qualified = bool(
            review_complete and recovery["newGateOutcome"] == "pass"
        )
        first_attempt_full = bool(
            verified
            and new["firstAttempt"]
            and new["firstAttempt"]["outcome"] == "payload"
            and new["firstAttempt"]["status"] == "ok"
            and new["firstAttempt"]["weeksRead"] >= 3
        )
        retry_assisted = bool(verified and new["retryCount"] == 1 and new["recoveryYield"] is True)
        row = {
            "pairId": pair_id,
            "asin": old["asin"],
            "oldWeeksRead": old["weeksRead"],
            "newWeeksRead": new["weeksRead"],
            "newFirstAttemptWeeksRead": new["firstAttempt"]["weeksRead"],
            "newRetryCount": new["retryCount"],
            "newGateOutcome": new["gateOutcome"],
            "candidate": candidate,
            "verified": verified,
            "firstAttemptFull": first_attempt_full,
            "retryAssisted": retry_assisted,
            "reviewComplete": review_complete,
            "releaseValidatedQualified": release_validated_qualified,
            "overlapByteExact": recovery.get("overlapByteExact") if recovery else None,
            "addedWeekCount": len(recovery.get("addedWeeks", [])) if recovery else 0,
            "genuineErrors": recovery.get("genuineErrors", []) if recovery else [],
        }
        if partial_eligible:
            partial_rows.append(row)
            partial_candidates += int(candidate)
            partial_verified += int(verified)
            partial_release_validated += int(review_complete)
            partial_qualified += int(release_validated_qualified)
            partial_first_attempt += int(first_attempt_full)
            partial_retry_assisted += int(retry_assisted)
        if collection_error:
            collection_error_rows.append(row)
            collection_candidates += int(candidate)
            collection_recovered += int(verified)
            collection_release_validated += int(review_complete)
            collection_qualified += int(release_validated_qualified)

    partial_count = len(partial_rows)
    collection_count = len(collection_error_rows)
    return {
        "diagnosticOnly": False,
        "recoveryEligible": True,
        "policy": (
            "Partial-to-full is recovery-eligible only when every overlapping old week is byte-exact in "
            "value/provenance evidence and every added week passes genuine-recovery validation. Any overlap "
            "difference remains a hard failure."
        ),
        "oldTrafficWeeksInsufficientPartialRows": partial_count,
        "partialToFullCandidateCount": partial_candidates,
        "partialToFullConversionCount": partial_verified,
        "partialToFullConversionRatePct": (
            round(100 * partial_verified / partial_count, 4) if partial_count else None
        ),
        "partialToFullReleaseValidatedCount": partial_release_validated,
        "partialToFullReleaseValidatedQualifiedCount": partial_qualified,
        "partialToFullReleaseValidatedQualifiedRatePct": (
            round(100 * partial_qualified / partial_count, 4) if partial_count else None
        ),
        "partialToFullOnFirstAttemptCount": partial_first_attempt,
        "partialToFullRetryAssistedCount": partial_retry_assisted,
        "partialRows": partial_rows,
        "oldCollectionErrorRows": collection_count,
        "collectionErrorRecoveryCount": collection_recovered,
        "collectionErrorRecoveryRatePct": (
            round(100 * collection_recovered / collection_count, 4) if collection_count else None
        ),
        "collectionErrorReleaseValidatedCount": collection_release_validated,
        "collectionErrorReleaseValidatedQualifiedCount": collection_qualified,
        "collectionErrorReleaseValidatedQualifiedRatePct": (
            round(100 * collection_qualified / collection_count, 4) if collection_count else None
        ),
        "collectionErrorRows": collection_error_rows,
        "collectionErrorRecoveryCandidateCount": collection_candidates,
    }


def load_representative_gate_logs(paths: list[Path]) -> dict[str, Any]:
    if not paths:
        raise ContractError("representative run requires at least one gate TSV")
    required = {"batchName", "queueHash", "asin", "outcome", "rejectionRule", "weeksRead"}
    seen: set[tuple[str, str, str]] = set()
    outcome_counts = Counter()
    rejection_counts = Counter()
    traffic_weeks_insufficient_by_weeks = Counter()
    source_files: list[dict[str, Any]] = []
    parent_names: set[str] = set()

    for source in paths:
        path = source.resolve()
        if not path.is_file():
            raise ContractError(f"representative gate TSV does not exist: {path}")
        raw = path.read_bytes()
        source_files.append(
            {
                "path": str(path),
                "bytes": len(raw),
                "sha256": hashlib.sha256(raw).hexdigest(),
            }
        )
        parent_names.add(path.parent.name)
        try:
            with path.open("r", encoding="utf-8-sig", newline="") as handle:
                reader = csv.DictReader(handle, delimiter="\t")
                if reader.fieldnames is None or not required.issubset(reader.fieldnames):
                    missing = sorted(required - set(reader.fieldnames or []))
                    raise ContractError(f"{path}: representative gate TSV missing columns {missing}")
                for row_number, row in enumerate(reader, start=2):
                    context = f"{path}:{row_number}"
                    batch_name = _text(row.get("batchName"), "batchName", context)
                    queue_hash = _text(row.get("queueHash"), "queueHash", context)
                    asin = _asin(row.get("asin"), "asin", context)
                    outcome = _text(row.get("outcome"), "outcome", context).lower()
                    if outcome not in OUTCOMES:
                        raise ContractError(f"{context}: outcome must be pass or reject")
                    key = (batch_name, queue_hash, asin)
                    if key in seen:
                        raise ContractError(f"{context}: duplicate representative gate key {key}")
                    seen.add(key)
                    outcome_counts[outcome] += 1
                    rejection_rule = str(row.get("rejectionRule") or "").strip()
                    weeks_read = _integer(row.get("weeksRead"), "weeksRead", context)
                    if outcome == "reject":
                        if not rejection_rule:
                            raise ContractError(f"{context}: rejected row lacks rejectionRule")
                        rejection_counts[rejection_rule] += 1
                        if rejection_rule == "traffic_weeks_insufficient":
                            traffic_weeks_insufficient_by_weeks[str(weeks_read)] += 1
        except UnicodeError as error:
            raise ContractError(f"cannot decode representative gate TSV {path}: {error}") from error

    visits = len(seen)
    qualified = outcome_counts["pass"]
    rejected = outcome_counts["reject"]
    if visits == 0 or qualified == 0 or visits != qualified + rejected:
        raise ContractError("representative gate evidence must contain visits and at least one qualified row")
    if sum(rejection_counts.values()) != rejected:
        raise ContractError("representative rejection buckets do not sum to rejected rows")
    return {
        "schemaVersion": REPRESENTATIVE_RUN_SCHEMA,
        "sourceKind": "raw_gate_tsv_rederived_unmanifested",
        "runId": next(iter(parent_names)) if len(parent_names) == 1 else "multiple_gate_sources",
        "sourceFiles": source_files,
        "browserVisits": visits,
        "qualifiedCount": qualified,
        "rejectedCount": rejected,
        "visitsPerQualified": round(visits / qualified, 4),
        "rejectionCounts": dict(sorted(rejection_counts.items())),
        "trafficWeeksInsufficientByWeeksRead": dict(
            sorted(traffic_weeks_insufficient_by_weeks.items())
        ),
        "projectionCategoryCounts": {
            "traffic_weeks_insufficient_partial_1_2": sum(
                traffic_weeks_insufficient_by_weeks[str(weeks)] for weeks in (1, 2)
            ),
            "collection_error": rejection_counts["collection_error"],
        },
    }


def load_representative_run_dir(run_dir: Path) -> dict[str, Any]:
    directory = run_dir.resolve()
    summary_path = directory / "run_summary.json"
    if not directory.is_dir() or not summary_path.is_file():
        raise ContractError(
            f"representative run directory lacks run_summary.json: {directory}"
        )
    try:
        summary_raw = summary_path.read_bytes()
        summary = json.loads(summary_raw.decode("utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ContractError(f"cannot read representative run summary: {error}") from error
    if not isinstance(summary, dict):
        raise ContractError("representative run summary root must be an object")
    run_id = _text(summary.get("runId"), "runId", "representative run summary")
    if run_id != directory.name:
        raise ContractError("representative run summary runId does not match its directory")
    batch_jsons = summary.get("batchJsons")
    if not isinstance(batch_jsons, list) or not batch_jsons:
        raise ContractError("representative run summary batchJsons must be non-empty")
    expected_gate_names: list[str] = []
    for index, value in enumerate(batch_jsons):
        name = Path(_text(value, "batchJsons", f"representative run summary[{index}]")).name
        match = re.fullmatch(r"integrated_batch_([0-9a-fA-F]+)\.json", name)
        if not match:
            raise ContractError(f"representative run summary has invalid batch filename: {name}")
        expected_gate_names.append(f"gate_log_{match.group(1).lower()}.tsv")
    if len(expected_gate_names) != len(set(expected_gate_names)):
        raise ContractError("representative run summary contains duplicate batch suffixes")
    gate_paths = sorted(directory.glob("gate_log_*.tsv"))
    actual_gate_names = sorted(path.name.lower() for path in gate_paths)
    if actual_gate_names != sorted(expected_gate_names):
        raise ContractError(
            "representative gate TSV set does not exactly match run_summary batchJsons"
        )
    baseline = load_representative_gate_logs(gate_paths)
    max_attempts = _integer(
        summary.get("maxAttempts"), "maxAttempts", "representative run summary"
    )
    qualified = _integer(
        summary.get("qualifiedCount"), "qualifiedCount", "representative run summary"
    )
    if summary.get("completedTarget") is not True:
        raise ContractError("representative run summary must be a completed target run")
    if max_attempts != baseline["browserVisits"] or qualified != baseline["qualifiedCount"]:
        raise ContractError(
            "representative run summary attempts/qualified totals do not match raw gate TSVs"
        )
    baseline.update(
        {
            "sourceKind": "raw_gate_tsv_rederived_complete_run",
            "runManifest": {
                "path": str(summary_path),
                "bytes": len(summary_raw),
                "sha256": hashlib.sha256(summary_raw).hexdigest(),
                "runId": run_id,
                "expectedGateFiles": sorted(expected_gate_names),
                "maxAttempts": max_attempts,
                "qualifiedCount": qualified,
                "completedTarget": True,
            },
        }
    )
    return baseline


def _verify_file_record(value: Any, context: str) -> Path:
    if not isinstance(value, dict):
        raise ContractError(f"{context}: file record must be an object")
    path = Path(_text(value.get("path"), "path", context))
    byte_count = _integer(value.get("bytes"), "bytes", context)
    sha256 = _text(value.get("sha256"), "sha256", context).lower()
    if not path.is_absolute() or not re.fullmatch(r"[0-9a-f]{64}", sha256):
        raise ContractError(f"{context}: path/sha256 is invalid")
    if not path.is_file():
        raise ContractError(f"{context}: source file is missing")
    try:
        raw = path.read_bytes()
    except OSError as error:
        raise ContractError(f"{context}: cannot read source file: {error}") from error
    if len(raw) != byte_count or hashlib.sha256(raw).hexdigest() != sha256:
        raise ContractError(f"{context}: source file bytes/hash mismatch")
    return path


def _verify_complete_representative_run(value: dict[str, Any] | None) -> None:
    if value is None or value.get("sourceKind") != "raw_gate_tsv_rederived_complete_run":
        raise ContractError("formal ROI requires a manifest-complete raw representative run")
    source_files = value.get("sourceFiles")
    manifest = value.get("runManifest")
    if not isinstance(source_files, list) or not source_files or not isinstance(manifest, dict):
        raise ContractError("formal ROI representative source manifest is incomplete")
    source_paths = [
        _verify_file_record(record, f"representative sourceFiles[{index}]")
        for index, record in enumerate(source_files)
    ]
    manifest_path = _verify_file_record(manifest, "representative runManifest")
    try:
        summary = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ContractError(f"formal ROI cannot parse run_summary.json: {error}") from error
    if not isinstance(summary, dict):
        raise ContractError("formal ROI run_summary.json root must be an object")
    summary_batches = summary.get("batchJsons")
    if not isinstance(summary_batches, list) or not summary_batches:
        raise ContractError("formal ROI run_summary.json has no batchJsons")
    expected_from_summary: list[str] = []
    for item in summary_batches:
        match = re.fullmatch(
            r"integrated_batch_([0-9a-fA-F]+)\.json", Path(str(item)).name
        )
        if not match:
            raise ContractError("formal ROI run_summary.json has an invalid batch filename")
        expected_from_summary.append(f"gate_log_{match.group(1).lower()}.tsv")
    if (
        manifest_path.name != "run_summary.json"
        or summary.get("runId") != value.get("runId")
        or manifest.get("runId") != summary.get("runId")
    ):
        raise ContractError("formal ROI representative run manifest identity is invalid")
    expected = manifest.get("expectedGateFiles")
    if (
        not isinstance(expected, list)
        or sorted(expected) != sorted(expected_from_summary)
        or sorted(path.name.lower() for path in source_paths) != sorted(expected_from_summary)
        or any(path.parent != manifest_path.parent for path in source_paths)
    ):
        raise ContractError("formal ROI representative gate files are incomplete")
    if (
        summary.get("completedTarget") is not True
        or manifest.get("completedTarget") is not True
        or manifest.get("maxAttempts") != summary.get("maxAttempts")
        or manifest.get("qualifiedCount") != summary.get("qualifiedCount")
        or summary.get("maxAttempts") != value.get("browserVisits")
        or summary.get("qualifiedCount") != value.get("qualifiedCount")
    ):
        raise ContractError("formal ROI representative manifest totals do not match")


def _representative_run(value: dict[str, Any] | None) -> dict[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, dict) or value.get("schemaVersion") != REPRESENTATIVE_RUN_SCHEMA:
        raise ContractError(f"representative run must use {REPRESENTATIVE_RUN_SCHEMA}")
    visits = _integer(value.get("browserVisits"), "browserVisits", "representative run")
    qualified = _integer(value.get("qualifiedCount"), "qualifiedCount", "representative run")
    rejected = _integer(value.get("rejectedCount"), "rejectedCount", "representative run")
    counts_raw = value.get("rejectionCounts")
    if not isinstance(counts_raw, dict) or any(not isinstance(key, str) or not key for key in counts_raw):
        raise ContractError("representative run: rejectionCounts must be an object")
    counts = {
        key: _integer(count, f"rejectionCounts.{key}", "representative run")
        for key, count in counts_raw.items()
    }
    if visits == 0 or qualified == 0 or visits != qualified + rejected:
        raise ContractError("representative run: visits must equal qualified + rejected and qualified must be positive")
    if sum(counts.values()) != rejected:
        raise ContractError("representative run: rejection buckets must sum exactly to rejectedCount")
    weeks_raw = value.get("trafficWeeksInsufficientByWeeksRead")
    if not isinstance(weeks_raw, dict):
        raise ContractError("representative run: trafficWeeksInsufficientByWeeksRead is required")
    weeks_counts = {
        str(week): _integer(count, f"trafficWeeksInsufficientByWeeksRead.{week}", "representative run")
        for week, count in weeks_raw.items()
    }
    if sum(weeks_counts.values()) != counts.get("traffic_weeks_insufficient", 0):
        raise ContractError(
            "representative run: traffic weeksRead buckets must sum to traffic_weeks_insufficient"
        )
    projection_counts = {
        "traffic_weeks_insufficient_partial_1_2": sum(
            weeks_counts.get(str(week), 0) for week in (1, 2)
        ),
        "collection_error": counts.get("collection_error", 0),
    }
    return {
        **value,
        "browserVisits": visits,
        "qualifiedCount": qualified,
        "rejectedCount": rejected,
        "visitsPerQualified": round(visits / qualified, 4),
        "rejectionCounts": dict(sorted(counts.items())),
        "trafficWeeksInsufficientByWeeksRead": dict(sorted(weeks_counts.items())),
        "projectionCategoryCounts": projection_counts,
    }


def _project_representative_roi(
    value_recovery: dict[str, Any],
    representative_run: dict[str, Any] | None,
    reader_validation_passed: bool,
    release_validation_complete: bool,
) -> dict[str, Any]:
    categories = {
        "traffic_weeks_insufficient": {
            "sampleEligible": value_recovery["oldTrafficWeeksInsufficientPartialRows"],
            "sampleEvidenceRecovered": value_recovery["partialToFullConversionCount"],
            "sampleReleaseValidatedQualified": value_recovery[
                "partialToFullReleaseValidatedQualifiedCount"
            ],
        },
        "collection_error": {
            "sampleEligible": value_recovery["oldCollectionErrorRows"],
            "sampleEvidenceRecovered": value_recovery["collectionErrorRecoveryCount"],
            "sampleReleaseValidatedQualified": value_recovery[
                "collectionErrorReleaseValidatedQualifiedCount"
            ],
        },
    }
    baseline_projection_counts = (representative_run or {}).get("projectionCategoryCounts", {})
    missing_rate_categories: list[str] = []
    projected_incremental_qualified = 0.0
    projected_evidence_recoveries = 0.0
    for category, values in categories.items():
        eligible = values["sampleEligible"]
        evidence_rate = values["sampleEvidenceRecovered"] / eligible if eligible else None
        qualified_rate = values["sampleReleaseValidatedQualified"] / eligible if eligible else None
        projection_key = (
            "traffic_weeks_insufficient_partial_1_2"
            if category == "traffic_weeks_insufficient"
            else category
        )
        baseline_count = baseline_projection_counts.get(projection_key) if representative_run else None
        if baseline_count and eligible == 0:
            missing_rate_categories.append(category)
        projected_evidence = (
            baseline_count * evidence_rate
            if baseline_count is not None and evidence_rate is not None
            else None
        )
        projected_qualified = (
            baseline_count * qualified_rate
            if baseline_count is not None and qualified_rate is not None
            else None
        )
        if projected_evidence is not None:
            projected_evidence_recoveries += projected_evidence
        if projected_qualified is not None:
            projected_incremental_qualified += projected_qualified
        values.update(
            {
                "sampleEvidenceRecoveryRatePct": (
                    round(100 * evidence_rate, 4) if evidence_rate is not None else None
                ),
                "sampleReleaseValidatedQualifiedRatePct": (
                    round(100 * qualified_rate, 4) if qualified_rate is not None else None
                ),
                "representativeRejectCount": baseline_count,
                "projectedEvidenceRecoveries": _round(projected_evidence),
                "projectedIncrementalQualified": _round(projected_qualified),
            }
        )

    available = bool(
        representative_run
        and reader_validation_passed
        and release_validation_complete
        and not missing_rate_categories
    )
    unavailable_reasons: list[str] = []
    if representative_run is None:
        unavailable_reasons.append("representative raw gate TSV baseline was not supplied")
    if not reader_validation_passed:
        unavailable_reasons.append("paired reader validation did not pass")
    if not release_validation_complete:
        unavailable_reasons.append("recovery review/replay/acceptance validation is incomplete")
    if missing_rate_categories:
        unavailable_reasons.append(
            "paired sample has no eligible rows for representative categories: "
            + ", ".join(missing_rate_categories)
        )

    projected_qualified_total = None
    projected_visits_per_qualified = None
    projected_yield_lift_pct = None
    projected_visits_per_qualified_reduction_pct = None
    if available and representative_run is not None:
        projected_qualified_total = representative_run["qualifiedCount"] + projected_incremental_qualified
        projected_visits_per_qualified = representative_run["browserVisits"] / projected_qualified_total
        projected_yield_lift_pct = 100 * (
            projected_qualified_total / representative_run["qualifiedCount"] - 1
        )
        projected_visits_per_qualified_reduction_pct = 100 * (
            1 - projected_visits_per_qualified / representative_run["visitsPerQualified"]
        )

    return {
        "available": available,
        "headlineMetric": "projectedVisitsPerQualified",
        "unavailableReasons": unavailable_reasons,
        "representativeRun": representative_run,
        "categories": categories,
        "projectedEvidenceRecoveries": (
            _round(projected_evidence_recoveries) if representative_run is not None else None
        ),
        "projectedIncrementalQualified": (
            _round(projected_incremental_qualified) if available else None
        ),
        "projectedQualifiedCount": _round(projected_qualified_total),
        "projectedVisitsPerQualified": _round(projected_visits_per_qualified),
        "projectedYieldLiftPct": _round(projected_yield_lift_pct),
        "projectedVisitsPerQualifiedReductionPct": _round(
            projected_visits_per_qualified_reduction_pct
        ),
        "method": (
            "Apply category-specific release-validated qualified recovery rates from the paired sample to "
            "the representative run's raw rejection distribution; keep all other rejection categories unchanged."
        ),
        "stratifiedSampleCaveat": (
            "The 30-ASIN queue is deliberately enriched for timeout and partial cases. Its raw overall yield is "
            "not representative and is never extrapolated directly. Category rates are distribution-adjusted, "
            "but remain conditional on the deliberately selected within-category sample."
        ),
        "sequentialCaptureCaveat": (
            "OFF and ON captures are sequential. SellerSprite drift can contribute to a recovery. Exact overlap "
            "matching mitigates attribution error; a row clearing every evidence and release guardrail is a genuine "
            "qualifier regardless of cause, so this caveat can overstate P2 credit but cannot create a false positive."
        ),
    }


def _compare_weeks(old: dict[str, Any], new: dict[str, Any]) -> dict[str, Any]:
    old_keys = set(old["weeks"])
    new_keys = set(new["weeks"])
    missing_old = sorted(new_keys - old_keys)
    missing_new = sorted(old_keys - new_keys)
    numeric_differences: list[dict[str, Any]] = []
    provenance_differences: list[dict[str, Any]] = []
    overlap_evidence_differences: list[dict[str, Any]] = []
    for key in sorted(old_keys & new_keys):
        old_week = old["weeks"][key]
        new_week = new["weeks"][key]
        for field in NUMERIC_WEEK_FIELDS:
            if old_week[field] != new_week[field]:
                numeric_differences.append(
                    {
                        "weekSort": key[0],
                        "weekLabel": key[1],
                        "field": field,
                        "old": old_week[field],
                        "new": new_week[field],
                    }
                )
        for field in ("naturalShareDerived", "naturalShareSource", "tier2ReaderVersion"):
            if old_week[field] != new_week[field]:
                provenance_differences.append(
                    {
                        "weekSort": key[0],
                        "weekLabel": key[1],
                        "field": field,
                        "old": old_week[field],
                        "new": new_week[field],
                    }
                )
        for field in OVERLAP_EXACT_FIELDS:
            if old_week[field] != new_week[field]:
                overlap_evidence_differences.append(
                    {
                        "weekSort": key[0],
                        "weekLabel": key[1],
                        "field": field,
                        "old": old_week[field],
                        "new": new_week[field],
                    }
                )
    return {
        "oldWeekCount": len(old_keys),
        "newWeekCount": len(new_keys),
        "oldWeeksRead": old["weeksRead"],
        "newWeeksRead": new["weeksRead"],
        "weeksReadMatch": old["weeksRead"] == new["weeksRead"],
        "missingFromOld": [{"weekSort": key[0], "weekLabel": key[1]} for key in missing_old],
        "missingFromNew": [{"weekSort": key[0], "weekLabel": key[1]} for key in missing_new],
        "addedToNew": [{"weekSort": key[0], "weekLabel": key[1]} for key in missing_old],
        "addedWeekCount": len(missing_old),
        "numericDifferences": numeric_differences,
        "provenanceDifferences": provenance_differences,
        "overlapEvidenceDifferences": overlap_evidence_differences,
        "oldWeeksSubsetOfNew": not missing_new,
        "overlapByteExact": not missing_new and not overlap_evidence_differences,
        "exactMatch": (
            not missing_old
            and not missing_new
            and not numeric_differences
            and not provenance_differences
            and old["weeksRead"] == new["weeksRead"]
        ),
    }


def _validate_recovery_weeks(
    weeks: dict[tuple[int, str], dict[str, Any]]
) -> tuple[list[str], list[dict[str, Any]]]:
    errors: list[str] = []
    raw_weeks: list[dict[str, Any]] = []
    for key in sorted(weeks):
        week = weeks[key]
        raw_weeks.append(dict(week))
        if not week["rawText"].strip():
            errors.append(f"{week['weekLabel']}: raw tooltip text is missing")
        if week["tier2ReaderVersion"] != TIER2_READER_VERSION:
            errors.append(f"{week['weekLabel']}: reader provenance is missing or unexpected")
        share = week["naturalSharePct"]
        if share is None:
            if week["naturalShareSource"] != "missing" or week["naturalShareDerived"]:
                errors.append(f"{week['weekLabel']}: missing ratio provenance is invalid")
            continue
        total = week["totalTraffic"]
        natural = week["naturalTraffic"]
        if total is None or natural is None:
            errors.append(f"{week['weekLabel']}: traffic values are incomplete")
            continue
        total_value = Decimal(total)
        natural_value = Decimal(natural)
        share_value = Decimal(share)
        if total_value < 0 or natural_value < 0 or natural_value > total_value or share_value < 0 or share_value > 100:
            errors.append(f"{week['weekLabel']}: traffic values are out of range")
        if week["naturalShareSource"] == "derived_explicit_zero_over_positive_total":
            if not (
                week["naturalShareDerived"]
                and total_value > 0
                and natural_value == 0
                and share_value == 0
            ):
                errors.append(f"{week['weekLabel']}: guarded-zero derivation is invalid")
        elif week["naturalShareSource"] == "sellersprite_explicit":
            if week["naturalShareDerived"] or "%" not in week["rawText"]:
                errors.append(f"{week['weekLabel']}: explicit SellerSprite ratio evidence is invalid")
        else:
            errors.append(f"{week['weekLabel']}: natural-share source is invalid")
    return errors, raw_weeks


def _genuine_recovery(side: dict[str, Any]) -> tuple[bool, list[str], list[dict[str, Any]]]:
    errors: list[str] = []
    if side["status"] != "ok":
        errors.append("new side status is not ok")
    if side["weeksRead"] < 3:
        errors.append("new side weeksRead is below 3")
    week_errors, raw_weeks = _validate_recovery_weeks(side["weeks"])
    errors.extend(week_errors)
    return not errors, errors, raw_weeks


def _partial_recovery_evaluation(
    old: dict[str, Any], new: dict[str, Any], comparison: dict[str, Any]
) -> tuple[bool, list[str], list[dict[str, Any]], list[dict[str, Any]]]:
    errors: list[str] = []
    if new["status"] != "ok":
        errors.append("new side status is not ok")
    if new["weeksRead"] < 3:
        errors.append("new side weeksRead is below 3")
    if not comparison["oldWeeksSubsetOfNew"]:
        errors.append("partial recovery dropped one or more old-side weeks")
    if not comparison["overlapByteExact"]:
        errors.append("partial recovery overlapping weeks differ in byte-exact value/provenance evidence")

    added_keys = sorted(set(new["weeks"]) - set(old["weeks"]))
    added_week_map = {key: new["weeks"][key] for key in added_keys}
    if not added_week_map:
        errors.append("partial recovery did not add any independently observed week")
    added_errors, added_weeks = _validate_recovery_weeks(added_week_map)
    errors.extend(f"added week: {message}" for message in added_errors)
    raw_weeks = [dict(new["weeks"][key]) for key in sorted(new["weeks"])]
    return not errors, errors, raw_weeks, added_weeks


def _review_binding_side(side: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": side["status"],
        "error": side["error"],
        "rejectionRule": side["rejectionRule"],
        "gateOutcome": side["gateOutcome"],
        "weeksRead": side["weeksRead"],
        "weeks": [dict(side["weeks"][key]) for key in sorted(side["weeks"])],
        "protocol": side["protocol"],
        "protocolRecovery": side["protocolRecovery"],
    }


def _review_binding(
    pair_id: str, asin: str, old: dict[str, Any], new: dict[str, Any]
) -> dict[str, Any]:
    evidence = {
        "schemaVersion": REVIEW_BINDING_SCHEMA,
        "pairId": pair_id,
        "asin": asin,
        "old": _review_binding_side(old),
        "new": _review_binding_side(new),
    }
    encoded = json.dumps(
        evidence, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return {
        "schemaVersion": REVIEW_BINDING_SCHEMA,
        "pairId": pair_id,
        "asin": asin,
        "evidenceSha256": hashlib.sha256(encoded).hexdigest(),
    }


def _parse_recovery_review(
    value: Any,
    expected_binding: dict[str, Any],
    context: str,
) -> dict[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, dict) or value.get("schemaVersion") != RECOVERY_REVIEW_SCHEMA:
        raise ContractError(f"{context}: recoveryReview must be {RECOVERY_REVIEW_SCHEMA}")
    asin = expected_binding["asin"]
    if _asin(value.get("asin"), "recoveryReview.asin", context) != asin:
        raise ContractError(f"{context}: recoveryReview ASIN mismatch")
    if value.get("pairId") != expected_binding["pairId"]:
        raise ContractError(f"{context}: recoveryReview pairId mismatch")
    binding = value.get("reviewBinding")
    if not isinstance(binding, dict) or binding != expected_binding:
        raise ContractError(f"{context}: recoveryReview evidence binding mismatch")
    if value.get("artifactsVerifiedByBuilder") is not True:
        raise ContractError(f"{context}: recoveryReview artifacts were not verified by the pair builder")
    manual = value.get("manualTooltipVerified")
    replay = _text(value.get("offlineReplayOutcome"), "offlineReplayOutcome", context)
    acceptance = _text(value.get("acceptanceOutcome"), "acceptanceOutcome", context)
    artifacts = value.get("evidenceArtifacts")
    if not isinstance(manual, bool):
        raise ContractError(f"{context}: manualTooltipVerified must be boolean")
    if replay not in {"pass", "reject", "not_required"} or acceptance not in {"pass", "reject", "not_required"}:
        raise ContractError(f"{context}: recovery review outcomes are invalid")
    if not isinstance(artifacts, list) or not artifacts:
        raise ContractError(f"{context}: recovery review evidenceArtifacts must be non-empty")
    normalized_artifacts: list[dict[str, Any]] = []
    for index, artifact in enumerate(artifacts):
        artifact_context = f"{context}.recoveryReview.evidenceArtifacts[{index}]"
        if not isinstance(artifact, dict):
            raise ContractError(f"{artifact_context}: artifact must be an object")
        path = _text(artifact.get("path"), "path", artifact_context)
        byte_count = _integer(artifact.get("bytes"), "bytes", artifact_context)
        sha256 = _text(artifact.get("sha256"), "sha256", artifact_context).lower()
        if not re.fullmatch(r"[0-9a-f]{64}", sha256):
            raise ContractError(f"{artifact_context}: sha256 is invalid")
        artifact_path = Path(path)
        if not artifact_path.is_absolute() or not artifact_path.is_file():
            raise ContractError(f"{artifact_context}: verified evidence file is missing")
        try:
            raw = artifact_path.read_bytes()
        except OSError as error:
            raise ContractError(
                f"{artifact_context}: cannot read verified evidence file: {error}"
            ) from error
        if len(raw) != byte_count or hashlib.sha256(raw).hexdigest() != sha256:
            raise ContractError(f"{artifact_context}: verified evidence file bytes/hash mismatch")
        normalized_artifacts.append({"path": path, "bytes": byte_count, "sha256": sha256})
    normalized_review = {
        "schemaVersion": RECOVERY_REVIEW_SCHEMA,
        "asin": asin,
        "pairId": expected_binding["pairId"],
        "reviewBinding": expected_binding,
        "artifactsVerifiedByBuilder": True,
        "manualTooltipVerified": manual,
        "offlineReplayOutcome": replay,
        "acceptanceOutcome": acceptance,
        "evidenceArtifacts": normalized_artifacts,
        "verifiedBy": _text(value.get("verifiedBy", ""), "verifiedBy", context, required=False),
        "verifiedAt": _text(value.get("verifiedAt", ""), "verifiedAt", context, required=False),
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
    expected_attestation = hashlib.sha256(
        json.dumps(
            attestation_payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    if value.get("reviewAttestationSha256") != expected_attestation:
        raise ContractError(f"{context}: recoveryReview attestation mismatch")
    normalized_review["reviewAttestationSha256"] = expected_attestation
    return normalized_review


def _review_decision(review: dict[str, Any] | None, gate_outcome: str) -> dict[str, Any]:
    if review is None:
        return {"complete": False, "failed": False, "reasons": ["manual recovery review is missing"]}
    reasons: list[str] = []
    failed = False
    if not review["manualTooltipVerified"]:
        reasons.append("manual tooltip verification did not pass")
        failed = True
    if not review["evidenceArtifacts"] or not review["verifiedBy"] or not review["verifiedAt"]:
        reasons.append("review provenance or verified evidence artifacts are incomplete")
    if gate_outcome == "pass":
        if review["offlineReplayOutcome"] != "pass":
            reasons.append("offline replay did not pass")
            failed = failed or review["offlineReplayOutcome"] == "reject"
        if review["acceptanceOutcome"] != "pass":
            reasons.append("acceptance did not pass")
            failed = failed or review["acceptanceOutcome"] == "reject"
    return {"complete": not reasons, "failed": failed, "reasons": reasons}


def compare_capture(
    capture: dict[str, Any],
    representative_run: dict[str, Any] | None = None,
    *,
    require_roi: bool = False,
) -> dict[str, Any]:
    if not isinstance(capture, dict):
        raise ContractError("capture root must be an object")
    if capture.get("schemaVersion") != INPUT_SCHEMA_VERSION:
        raise ContractError(
            f"expected schemaVersion {INPUT_SCHEMA_VERSION!r}, got {capture.get('schemaVersion')!r}"
        )
    representative = _representative_run(representative_run)
    if require_roi:
        _verify_complete_representative_run(representative)
    pairs = capture.get("pairs")
    sequence_raw = capture.get("sequence")
    if not isinstance(pairs, list) or not isinstance(sequence_raw, list):
        raise ContractError("capture: pairs and sequence must be lists")
    sequence = [_asin(value, "sequence", "capture") for value in sequence_raw]
    if len(sequence) != len(pairs) or len(sequence) != len(set(sequence)):
        raise ContractError("capture: sequence must be unique and match the pair count")

    history_raw = capture.get("historyBaseline")
    if not isinstance(history_raw, dict) or history_raw.get("exactMatch") is not True:
        raise ContractError("capture: historyBaseline exactMatch=true is required")
    old_history = _history_snapshot(history_raw.get("old"), "historyBaseline.old", "capture")
    new_history = _history_snapshot(history_raw.get("new"), "historyBaseline.new", "capture")
    if old_history != new_history:
        raise ContractError("capture: old/new strict-history baselines do not match")
    isolation = _history_isolation(capture.get("historyIsolation"), "capture")
    if isolation["productionSnapshot"] != old_history:
        raise ContractError("capture: sandbox baseline does not match read-only production snapshot")
    if any(asin in set(old_history["asins"]) for asin in sequence):
        raise ContractError("capture: paired sequence contains an ASIN in the strict-history baseline")

    threshold = _nonnegative_number(
        capture.get("slowPageThresholdMs", DEFAULT_SLOW_PAGE_THRESHOLD_MS),
        "slowPageThresholdMs",
        "capture",
    )
    assert threshold is not None

    errors: list[str] = []
    release_pending: list[dict[str, Any]] = []
    recoveries: list[dict[str, Any]] = []
    pair_results: list[dict[str, Any]] = []
    seen_pair_ids: set[str] = set()
    seen_asins: set[str] = set()
    old_sides: list[dict[str, Any]] = []
    new_sides: list[dict[str, Any]] = []
    side_by_pair: dict[str, tuple[dict[str, Any], dict[str, Any]]] = {}
    counters = Counter()

    for index, item in enumerate(pairs):
        context = f"pairs[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{context}: pair must be an object")
            continue
        try:
            pair_id = _text(item.get("pairId"), "pairId", context)
            asin = _asin(item.get("asin"), "asin", context)
        except ContractError as error:
            errors.append(str(error))
            continue
        pair_result: dict[str, Any] = {
            "pairId": pair_id,
            "asin": asin,
            "partition": "unparsed",
            "oldPresent": item.get("old") is not None,
            "newPresent": item.get("new") is not None,
            "missingSideMismatch": item.get("old") is None or item.get("new") is None,
            "gateOutcomeMatch": False,
            "falsePositive": False,
            "weekComparison": None,
            "errors": [],
        }
        if index >= len(sequence) or asin != sequence[index]:
            pair_result["errors"].append("pair order does not match capture.sequence")
            counters["identityMismatch"] += 1
        if pair_id in seen_pair_ids or asin in seen_asins:
            pair_result["errors"].append("pairId and ASIN must be unique")
            counters["identityMismatch"] += 1
        seen_pair_ids.add(pair_id)
        seen_asins.add(asin)
        if pair_result["missingSideMismatch"]:
            pair_result["errors"].append("old and new sides are both required")
            counters["missingSideMismatch"] += 1
            pair_results.append(pair_result)
            continue
        try:
            old = _parse_side(item.get("old"), pair_id, asin, "old")
            new = _parse_side(item.get("new"), pair_id, asin, "new")
            review_binding = _review_binding(pair_id, asin, old, new)
            review = _parse_recovery_review(
                item.get("recoveryReview"), review_binding, context
            )
        except ContractError as error:
            pair_result["errors"].append(str(error))
            pair_results.append(pair_result)
            continue

        old_sides.append(old)
        new_sides.append(new)
        side_by_pair[pair_id] = (old, new)
        week_comparison = _compare_weeks(old, new)
        gate_match = old["gateOutcome"] == new["gateOutcome"]
        pair_result.update(
            {
                "oldStatus": old["status"],
                "newStatus": new["status"],
                "oldGateOutcome": old["gateOutcome"],
                "newGateOutcome": new["gateOutcome"],
                "gateOutcomeMatch": gate_match,
                "weekComparison": week_comparison,
                "oldReadClass": old["readClass"],
                "newReadClass": new["readClass"],
                "oldTimeoutKind": old["timeoutKind"],
                "newTimeoutKind": new["timeoutKind"],
                "oldTiming": old["timing"],
                "newTiming": new["timing"],
                "oldFirstAttempt": {
                    "outcome": old["firstAttempt"]["outcome"],
                    "status": old["firstAttempt"]["status"],
                    "weeksRead": old["firstAttempt"]["weeksRead"],
                },
                "newFirstAttempt": {
                    "outcome": new["firstAttempt"]["outcome"],
                    "status": new["firstAttempt"]["status"],
                    "weeksRead": new["firstAttempt"]["weeksRead"],
                },
                "oldRetryCount": old["retryCount"],
                "newRetryCount": new["retryCount"],
                "oldRecoveryYield": old["recoveryYield"],
                "newRecoveryYield": new["recoveryYield"],
                "newProtocol": new["protocol"],
                "newProtocolRecovery": new["protocolRecovery"],
                "oldSource": old["source"],
                "newSource": new["source"],
                "reviewBinding": review_binding,
            }
        )
        counters["globalGateMismatch"] += int(not gate_match)
        counters["globalWeekMismatch"] += int(not week_comparison["exactMatch"])

        partial_eligible = (
            old["status"] == "ok"
            and old["rejectionRule"] == "traffic_weeks_insufficient"
            and old["weeksRead"] in {1, 2}
        )
        partial_recovery_candidate = bool(
            partial_eligible and new["status"] == "ok" and new["weeksRead"] >= 3
        )
        counters["oldPartialEligible"] += int(partial_eligible)
        recovery_kind = ""
        recovery_candidate = False

        if partial_recovery_candidate:
            pair_result["partition"] = "old_partial_recovery"
            pair_result["partialRecoveryEligible"] = True
            pair_result["recoveryCandidate"] = True
            counters["oldPartialRecovery"] += 1
            recovery_kind = "partial_to_full"
            recovery_candidate = True
        elif old["readClass"] == "non_timeout":
            pair_result["partition"] = "old_non_timeout"
            pair_result["partialRecoveryEligible"] = partial_eligible
            counters["happyPath"] += 1
            if not gate_match:
                counters["happyGateMismatch"] += 1
                pair_result["errors"].append("non-timeout gate outcome mismatch")
            if not week_comparison["exactMatch"]:
                counters["happyWeekMismatch"] += 1
                pair_result["errors"].append("non-timeout per-week value/provenance mismatch")
            if old["gateOutcome"] != "pass" and new["gateOutcome"] == "pass":
                pair_result["falsePositive"] = True
                counters["falsePositive"] += 1
        else:
            pair_result["partition"] = "old_timeout_error"
            counters["oldTimeoutError"] += 1
            recovery_candidate = new["status"] == "ok" and new["weeksRead"] >= 3
            pair_result["recoveryCandidate"] = recovery_candidate
            recovery_kind = "old_timeout_error"

        if recovery_kind:
            if recovery_candidate:
                if recovery_kind == "partial_to_full":
                    genuine, recovery_errors, raw_weeks, added_weeks = _partial_recovery_evaluation(
                        old, new, week_comparison
                    )
                else:
                    genuine, recovery_errors, raw_weeks = _genuine_recovery(new)
                    added_weeks = []
                review_decision = _review_decision(review, new["gateOutcome"])
                recovery_row = {
                    "pairId": pair_id,
                    "asin": asin,
                    "recoveryKind": recovery_kind,
                    "oldStatus": old["status"],
                    "oldError": old["error"],
                    "oldRejectionRule": old["rejectionRule"],
                    "oldTimeoutKind": old["timeoutKind"],
                    "oldWeeksRead": old["weeksRead"],
                    "oldWeeks": [dict(old["weeks"][key]) for key in sorted(old["weeks"])],
                    "newStatus": new["status"],
                    "newGateOutcome": new["gateOutcome"],
                    "weeksRead": new["weeksRead"],
                    "weeks": raw_weeks,
                    "addedWeeks": added_weeks,
                    "overlapByteExact": (
                        week_comparison["overlapByteExact"]
                        if recovery_kind == "partial_to_full"
                        else None
                    ),
                    "overlapEvidenceDifferences": (
                        week_comparison["overlapEvidenceDifferences"]
                        if recovery_kind == "partial_to_full"
                        else []
                    ),
                    "protocol": new["protocol"],
                    "genuine": genuine,
                    "genuineErrors": recovery_errors,
                    "review": review,
                    "reviewBinding": review_binding,
                    "reviewDecision": review_decision,
                }
                recoveries.append(recovery_row)
                pair_result["recovery"] = recovery_row
                if genuine:
                    counters["genuineRecovery"] += 1
                    counters[
                        "genuinePartialRecovery"
                        if recovery_kind == "partial_to_full"
                        else "genuineTimeoutErrorRecovery"
                    ] += 1
                    if review_decision["complete"]:
                        counters["releaseValidatedRecovery"] += 1
                        if new["gateOutcome"] == "pass":
                            counters["releaseValidatedQualifiedRecovery"] += 1
                            counters[
                                "releaseValidatedQualifiedPartialRecovery"
                                if recovery_kind == "partial_to_full"
                                else "releaseValidatedQualifiedTimeoutErrorRecovery"
                            ] += 1
                    else:
                        counters["releasePending"] += 1
                        if review_decision["failed"]:
                            counters["releaseFailed"] += 1
                        release_pending.append(
                            {"asin": asin, "gateOutcome": new["gateOutcome"], "reasons": review_decision["reasons"]}
                        )
                else:
                    counters["invalidRecovery"] += 1
                    if recovery_kind == "partial_to_full":
                        counters["invalidPartialRecovery"] += 1
                    pair_result["errors"].extend(recovery_errors)
                if new["gateOutcome"] == "pass" and (not genuine or review_decision["failed"]):
                    pair_result["falsePositive"] = True
                    counters["falsePositive"] += 1
                if new["gateOutcome"] == "pass" and genuine and not review_decision["complete"]:
                    counters["unreleasedPassPending"] += 1
            elif new["gateOutcome"] == "pass":
                pair_result["falsePositive"] = True
                counters["falsePositive"] += 1
                pair_result["errors"].append("timeout/error row passed without a genuine recovered reading")
        pair_results.append(pair_result)

    if len(pairs) < MIN_PAIRS:
        errors.append(f"sample has {len(pairs)} pairs; at least {MIN_PAIRS} are required")
    if counters["oldTimeoutError"] < MIN_OLD_TIMEOUT_ERROR_PAIRS:
        errors.append(
            f"sample has {counters['oldTimeoutError']} old timeout/error rows; "
            f"at least {MIN_OLD_TIMEOUT_ERROR_PAIRS} are required"
        )
    if counters["genuineRecovery"] < MIN_GENUINE_RECOVERIES:
        errors.append(
            f"sample has {counters['genuineRecovery']} genuine recoveries; "
            f"at least {MIN_GENUINE_RECOVERIES} are required"
        )
    for pair in pair_results:
        errors.extend(f"{pair['pairId']}: {message}" for message in pair.get("errors", []))

    strata_names = ("explicitZero", "dashMarker", "missingRatio", "partial1to2Weeks", "slowPage")
    strata: dict[str, dict[str, Any]] = {}
    for name in strata_names:
        old_count = 0
        new_count = 0
        for old, new in side_by_pair.values():
            old_count += int(_side_strata(old, threshold)[name])
            new_count += int(_side_strata(new, threshold)[name])
        covered = old_count > 0 if name == "slowPage" else (old_count + new_count > 0)
        strata[name] = {
            "oldCount": old_count,
            "newCount": new_count,
            "sampleCount": old_count + new_count,
            "covered": covered,
        }
    stratification_complete = all(value["covered"] for value in strata.values())
    if not stratification_complete:
        errors.append("required explicit-zero/--/missing-ratio/partial/slow-page stratification is incomplete")

    old_metrics = _metric_summary(old_sides)
    new_metrics = _metric_summary(new_sides)
    value_recovery = _value_recovery_metrics(side_by_pair, recoveries)
    metrics_comparison = {
        "totalP50DeltaMs": _delta(new_metrics["totalMs"]["p50Ms"], old_metrics["totalMs"]["p50Ms"]),
        "totalP90DeltaMs": _delta(new_metrics["totalMs"]["p90Ms"], old_metrics["totalMs"]["p90Ms"]),
        "chartP50DeltaMs": _delta(new_metrics["chartMs"]["p50Ms"], old_metrics["chartMs"]["p50Ms"]),
        "chartP90DeltaMs": _delta(new_metrics["chartMs"]["p90Ms"], old_metrics["chartMs"]["p90Ms"]),
        "collectorP50DeltaMs": _delta(
            new_metrics["collectorMs"]["p50Ms"], old_metrics["collectorMs"]["p50Ms"]
        ),
        "collectorP90DeltaMs": _delta(
            new_metrics["collectorMs"]["p90Ms"], old_metrics["collectorMs"]["p90Ms"]
        ),
        "retryRecoveryYieldDeltaPct": _delta(
            new_metrics["retry"]["recoveryYieldPct"], old_metrics["retry"]["recoveryYieldPct"]
        ),
        "pairedDelta": {
            "direction": "new-minus-old; positive values mean P2 is slower",
            **{
                field: _paired_timing_delta_stats(side_by_pair, field)
                for field in TIMING_FIELDS
            },
        },
        "timeoutCountDelta": new_metrics["timeout"]["count"] - old_metrics["timeout"]["count"],
        "retryRowsDelta": new_metrics["retry"]["rows"] - old_metrics["retry"]["rows"],
        "recoveredDelta": new_metrics["retry"]["recovered"] - old_metrics["retry"]["recovered"],
    }
    parsed_pairs = len(side_by_pair)
    happy_count = counters["happyPath"]
    happy_gate_matches = happy_count - counters["happyGateMismatch"]
    happy_week_matches = happy_count - counters["happyWeekMismatch"]
    reader_validation_passed = (
        len(pairs) >= MIN_PAIRS
        and len(errors) == 0
        and counters["identityMismatch"] == 0
        and counters["missingSideMismatch"] == 0
        and counters["happyGateMismatch"] == 0
        and counters["happyWeekMismatch"] == 0
        and counters["invalidRecovery"] == 0
        and counters["falsePositive"] == 0
        and counters["oldTimeoutError"] >= MIN_OLD_TIMEOUT_ERROR_PAIRS
        and counters["genuineRecovery"] >= MIN_GENUINE_RECOVERIES
        and stratification_complete
    )
    release_validation_complete = counters["releasePending"] == 0 and counters["releaseFailed"] == 0
    roi = _project_representative_roi(
        value_recovery,
        representative,
        reader_validation_passed,
        release_validation_complete,
    )
    validation = {
        "inputPairs": len(pairs),
        "uniquePairIds": len(seen_pair_ids),
        "uniqueAsins": len(seen_asins),
        "comparedPairs": parsed_pairs,
        "identityMismatchCount": counters["identityMismatch"],
        "missingSideMismatchCount": counters["missingSideMismatch"],
        "oldNonTimeoutCount": happy_count,
        "oldTimeoutErrorCount": counters["oldTimeoutError"],
        "oldPartialRecoveryEligibleCount": counters["oldPartialEligible"],
        "partialRecoveryCandidateCount": counters["oldPartialRecovery"],
        "happyPathGateAgreementCount": happy_gate_matches,
        "happyPathGateAgreementPct": round(100 * happy_gate_matches / happy_count, 4) if happy_count else 0.0,
        "happyPathGateMismatchCount": counters["happyGateMismatch"],
        "happyPathWeekExactMatchCount": happy_week_matches,
        "happyPathWeekExactMatchPct": round(100 * happy_week_matches / happy_count, 4) if happy_count else 0.0,
        "happyPathWeekMismatchCount": counters["happyWeekMismatch"],
        "globalGateOutcomeMismatchCount": counters["globalGateMismatch"],
        "globalWeekMismatchCount": counters["globalWeekMismatch"],
        "genuineRecoveryCount": counters["genuineRecovery"],
        "genuinePartialRecoveryCount": counters["genuinePartialRecovery"],
        "genuineTimeoutErrorRecoveryCount": counters["genuineTimeoutErrorRecovery"],
        "invalidRecoveryCount": counters["invalidRecovery"],
        "invalidPartialRecoveryCount": counters["invalidPartialRecovery"],
        "releaseValidatedRecoveryCount": counters["releaseValidatedRecovery"],
        "releaseValidatedQualifiedRecoveryCount": counters[
            "releaseValidatedQualifiedRecovery"
        ],
        "releaseValidatedQualifiedPartialRecoveryCount": counters[
            "releaseValidatedQualifiedPartialRecovery"
        ],
        "releaseValidatedQualifiedTimeoutErrorRecoveryCount": counters[
            "releaseValidatedQualifiedTimeoutErrorRecovery"
        ],
        "releasePendingCount": counters["releasePending"],
        "releaseFailedCount": counters["releaseFailed"],
        "unreleasedPassPendingCount": counters["unreleasedPassPending"],
        "falsePositiveCount": counters["falsePositive"],
        "stratificationComplete": stratification_complete,
        "readerValidationPassed": reader_validation_passed,
        "releaseValidationComplete": release_validation_complete,
        "errorCount": len(errors),
    }
    passed = (
        reader_validation_passed
        and release_validation_complete
        and (roi["available"] or not require_roi)
    )
    return {
        "schemaVersion": SCHEMA_VERSION,
        "inputSchemaVersion": INPUT_SCHEMA_VERSION,
        "sampleTarget": MIN_PAIRS,
        "minimumOldTimeoutErrorRows": MIN_OLD_TIMEOUT_ERROR_PAIRS,
        "minimumGenuineRecoveries": MIN_GENUINE_RECOVERIES,
        "slowPageThresholdMs": threshold,
        "candidateVersions": {"runner": EXPECTED_RUNNER_VERSION, "collector": EXPECTED_COLLECTOR_VERSION},
        "historyBaselineCount": len(old_history["asins"]),
        "historyIsolation": isolation,
        "comparisonPolicy": {
            "oldNonTimeout": "exact per-week values/provenance and identical gate outcome",
            "oldTimeoutError": "real recovery may change gate outcome; every recovery requires manual raw-tooltip review",
            "oldPartialRecovery": (
                "weeks_insufficient 1-2 to >=3 is recovery-eligible only with byte-exact overlapping "
                "value/provenance evidence and independently valid added weeks"
            ),
            "recoveredPass": "full gate plus offline replay plus acceptance",
            "zeroFalsePositive": "no release on missing, ambiguous, stale, timed-out, hidden, or unreadable evidence",
            "history": "side-specific sandboxes seeded from one read-only production snapshot",
        },
        "readerValidationPassed": reader_validation_passed,
        "releaseValidationComplete": release_validation_complete,
        "roiRequired": require_roi,
        "passed": passed,
        "validation": validation,
        "metrics": {
            "old": old_metrics,
            "new": new_metrics,
            "comparison": metrics_comparison,
            "valueRecovery": value_recovery,
        },
        "roi": roi,
        "stratification": strata,
        "recoveries": recoveries,
        "releasePending": release_pending,
        "pairs": pair_results,
        "errors": errors,
    }


def load_capture(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as error:
        raise ContractError(f"cannot read capture {path}: {error}") from error
    if not isinstance(value, dict):
        raise ContractError("capture root must be an object")
    return value


def render_markdown(result: dict[str, Any]) -> str:
    validation = result["validation"]
    metrics = result["metrics"]
    roi = result["roi"]
    lines = [
        "# SellerSprite P2 paired evidence comparison",
        "",
        f"- Result: **{'PASS' if result['passed'] else 'FAIL'}**",
        f"- Reader validation: **{'PASS' if result['readerValidationPassed'] else 'FAIL'}**",
        f"- Release validation: **{'COMPLETE' if result['releaseValidationComplete'] else 'PENDING'}**",
        f"- Pairs: {validation['inputPairs']} (minimum {result['sampleTarget']})",
        f"- Old-side non-timeout rows: {validation['oldNonTimeoutCount']}",
        f"- Old-side timeout/error rows: {validation['oldTimeoutErrorCount']} (minimum {result['minimumOldTimeoutErrorRows']})",
        f"- Partial-to-full recovery candidates: {validation['partialRecoveryCandidateCount']}",
        f"- Genuine recoveries: {validation['genuineRecoveryCount']} (minimum {result['minimumGenuineRecoveries']})",
        f"- Happy-path gate mismatches: {validation['happyPathGateMismatchCount']}",
        f"- False positives: {validation['falsePositiveCount']}",
        f"- Release reviews pending: {validation['releasePendingCount']}",
        f"- Missing-side mismatches: {validation['missingSideMismatchCount']}",
        f"- Happy-path per-week mismatches: {validation['happyPathWeekMismatchCount']}",
        "",
        "## Headline ROI verdict",
        "",
    ]
    if roi["available"]:
        representative = roi["representativeRun"]
        lines.extend([
            f"- Baseline visits per qualified: **{representative['visitsPerQualified']}** "
            f"({representative['browserVisits']} visits / {representative['qualifiedCount']} qualified).",
            f"- Projected visits per qualified: **{roi['projectedVisitsPerQualified']}**.",
            f"- Projected incremental qualified items: **{roi['projectedIncrementalQualified']}**.",
            f"- Projected yield lift: **{roi['projectedYieldLiftPct']}%**.",
        ])
    else:
        lines.append("- Projected visits per qualified: **UNAVAILABLE**.")
        lines.extend(f"- Pending: {reason}." for reason in roi["unavailableReasons"])
    if roi["representativeRun"] is not None:
        representative = roi["representativeRun"]
        lines.extend([
            f"- Representative rejection distribution: `{json.dumps(representative['rejectionCounts'], sort_keys=True)}`.",
            f"- `traffic_weeks_insufficient` weeksRead distribution: "
            f"`{json.dumps(representative['trafficWeeksInsufficientByWeeksRead'], sort_keys=True)}`.",
        ])
        if representative.get("sourceFiles"):
            lines.extend([
                "- Representative source manifest:",
                "",
                "```json",
                json.dumps(
                    {
                        "runManifest": representative.get("runManifest"),
                        "gateFiles": representative["sourceFiles"],
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                "```",
            ])
    lines.extend([
        "",
        "| Recovery category | Sample eligible | Evidence recovered | Evidence rate | Release-validated qualified | Qualified rate | Representative rejects | Projected qualified gain |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ])
    for category, values in roi["categories"].items():
        evidence_rate = values["sampleEvidenceRecoveryRatePct"]
        qualified_rate = values["sampleReleaseValidatedQualifiedRatePct"]
        lines.append(
            f"| {category} | {values['sampleEligible']} | {values['sampleEvidenceRecovered']} | "
            f"{evidence_rate if evidence_rate is not None else 'n/a'}"
            f"{'%' if evidence_rate is not None else ''} | "
            f"{values['sampleReleaseValidatedQualified']} | "
            f"{qualified_rate if qualified_rate is not None else 'n/a'}"
            f"{'%' if qualified_rate is not None else ''} | "
            f"{values['representativeRejectCount'] if values['representativeRejectCount'] is not None else 'n/a'} | "
            f"{values['projectedIncrementalQualified'] if values['projectedIncrementalQualified'] is not None else 'n/a'} |"
        )
    lines.extend([
        "",
        roi["stratifiedSampleCaveat"],
        "",
        roi["sequentialCaptureCaveat"],
        "",
        "## Timing and retry metrics",
        "",
        "| Side | Total p50 ms | Total p90 ms | Chart p50 ms | Chart p90 ms | Collector p50 ms | Collector p90 ms | Timeouts | Timeout kinds | Retry rows | Recovered | Recovery yield (recovered/retry rows) | Protocol pauses | Protocol recovered |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---|---:|---:|---:|---:|---:|",
    ])
    for label in ("old", "new"):
        side = metrics[label]
        recovery_yield = side["retry"]["recoveryYieldPct"]
        lines.append(
            f"| {label} | {side['totalMs']['p50Ms']} | {side['totalMs']['p90Ms']} | "
            f"{side['chartMs']['p50Ms']} | {side['chartMs']['p90Ms']} | "
            f"{side['collectorMs']['p50Ms']} | {side['collectorMs']['p90Ms']} | "
            f"{side['timeout']['count']} | {json.dumps(side['timeout']['byKind'], sort_keys=True)} | "
            f"{side['retry']['rows']} | {side['retry']['recovered']} | "
            f"{side['retry']['recovered']}/{side['retry']['rows']} = "
            f"{recovery_yield if recovery_yield is not None else 'n/a'}"
            f"{'%' if recovery_yield is not None else ''} | "
            f"{side['protocolPause']['attempts']} | {side['protocolPause']['recovered']} |"
        )
    paired_delta = metrics["comparison"]["pairedDelta"]
    lines.extend([
        "",
        "Paired timing deltas use `new - old`; positive values mean P2 is slower.",
        "",
        "| Timing field | Paired rows | Missing pairs | p50 delta ms | p90 delta ms | Min delta ms | Max delta ms |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ])
    for field in TIMING_FIELDS:
        values = paired_delta[field]
        lines.append(
            f"| {field} | {values['count']} | {values['missing']} | {values['p50DeltaMs']} | "
            f"{values['p90DeltaMs']} | {values['minDeltaMs']} | {values['maxDeltaMs']} |"
        )
    retry_yield_delta = metrics["comparison"]["retryRecoveryYieldDeltaPct"]
    lines.extend([
        "",
        f"Retry-yield delta (new - old): {retry_yield_delta if retry_yield_delta is not None else 'n/a'}"
        f"{' percentage points' if retry_yield_delta is not None else ''}.",
        "",
        "## Value recovery",
        "",
        metrics["valueRecovery"]["policy"],
        "",
        "| Metric | Eligible old rows | Raw >=3-week rows | Evidence-verified recoveries | Verified rate | Release-validated qualified | Qualified rate | First-attempt full | Retry-assisted |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ])
    value_recovery = metrics["valueRecovery"]
    partial_rate = value_recovery["partialToFullConversionRatePct"]
    collection_rate = value_recovery["collectionErrorRecoveryRatePct"]
    lines.extend([
        f"| traffic_weeks_insufficient with 1-2 weeks -> >=3 weeks | "
        f"{value_recovery['oldTrafficWeeksInsufficientPartialRows']} | "
        f"{value_recovery['partialToFullCandidateCount']} | "
        f"{value_recovery['partialToFullConversionCount']} | "
        f"{partial_rate if partial_rate is not None else 'n/a'}"
        f"{'%' if partial_rate is not None else ''} | "
        f"{value_recovery['partialToFullReleaseValidatedQualifiedCount']} | "
        f"{value_recovery['partialToFullReleaseValidatedQualifiedRatePct'] if value_recovery['partialToFullReleaseValidatedQualifiedRatePct'] is not None else 'n/a'}"
        f"{'%' if value_recovery['partialToFullReleaseValidatedQualifiedRatePct'] is not None else ''} | "
        f"{value_recovery['partialToFullOnFirstAttemptCount']} | "
        f"{value_recovery['partialToFullRetryAssistedCount']} |",
        f"| collection_error -> genuine >=3-week reading | "
        f"{value_recovery['oldCollectionErrorRows']} | "
        f"{value_recovery['collectionErrorRecoveryCandidateCount']} | "
        f"{value_recovery['collectionErrorRecoveryCount']} | "
        f"{collection_rate if collection_rate is not None else 'n/a'}"
        f"{'%' if collection_rate is not None else ''} | "
        f"{value_recovery['collectionErrorReleaseValidatedQualifiedCount']} | "
        f"{value_recovery['collectionErrorReleaseValidatedQualifiedRatePct'] if value_recovery['collectionErrorReleaseValidatedQualifiedRatePct'] is not None else 'n/a'}"
        f"{'%' if value_recovery['collectionErrorReleaseValidatedQualifiedRatePct'] is not None else ''} | n/a | n/a |",
        "",
        "### Partial-to-full row details",
        "",
        "| ASIN | Old weeks | New weeks | Added weeks | Overlap exact | First attempt weeks | Retries | Verified | Review complete | Gate |",
        "|---|---:|---:|---:|:---:|---:|---:|:---:|:---:|---|",
    ])
    for row in value_recovery["partialRows"]:
        lines.append(
            f"| {row['asin']} | {row['oldWeeksRead']} | {row['newWeeksRead']} | "
            f"{row['addedWeekCount']} | {'yes' if row['overlapByteExact'] else 'no'} | "
            f"{row['newFirstAttemptWeeksRead']} | {row['newRetryCount']} | "
            f"{'yes' if row['verified'] else 'no'} | "
            f"{'yes' if row['reviewComplete'] else 'no'} | {row['newGateOutcome']} |"
        )
    if not value_recovery["partialRows"]:
        lines.append("| none | n/a | n/a | n/a | no | n/a | n/a | no | no | n/a |")
    lines.extend([
        "",
        "## Stratification",
        "",
        "Slow-page coverage is anchored to the old baseline; new-side timing remains a comparison metric.",
        "",
        "| Category | Old | New | Sample hits | Covered |",
        "|---|---:|---:|---:|:---:|",
    ])
    for name, values in result["stratification"].items():
        lines.append(
            f"| {name} | {values['oldCount']} | {values['newCount']} | {values['sampleCount']} | "
            f"{'yes' if values['covered'] else 'no'} |"
        )
    if result["recoveries"]:
        lines.extend([
            "",
            "## Recovery-review rows",
            "",
            "| ASIN | Kind | Gate | Old weeks | New weeks | Overlap exact | Genuine | Manual review | Replay | Acceptance |",
            "|---|---|---|---:|---:|:---:|:---:|:---:|---|---|",
        ])
        for recovery in result["recoveries"]:
            review = recovery.get("review") or {}
            lines.append(
                f"| {recovery['asin']} | {recovery['recoveryKind']} | {recovery['newGateOutcome']} | "
                f"{recovery['oldWeeksRead']} | {recovery['weeksRead']} | "
                f"{'n/a' if recovery['overlapByteExact'] is None else ('yes' if recovery['overlapByteExact'] else 'no')} | "
                f"{'yes' if recovery['genuine'] else 'no'} | "
                f"{'yes' if review.get('manualTooltipVerified') else 'pending'} | "
                f"{review.get('offlineReplayOutcome', 'pending')} | "
                f"{review.get('acceptanceOutcome', 'pending')} |"
            )
        for recovery in result["recoveries"]:
            review = recovery.get("review") or {}
            lines.append("")
            lines.append(f"### Bound recovery evidence: `{recovery['asin']}`")
            lines.append("")
            lines.append("```json")
            lines.append(
                json.dumps(
                    {
                        "reviewBinding": recovery["reviewBinding"],
                        "oldWeeks": recovery["oldWeeks"],
                        "newWeeks": recovery["weeks"],
                        "addedWeeks": recovery["addedWeeks"],
                        "overlapEvidenceDifferences": recovery[
                            "overlapEvidenceDifferences"
                        ],
                        "evidenceArtifacts": review.get("evidenceArtifacts", []),
                        "reviewAttestationSha256": review.get(
                            "reviewAttestationSha256", ""
                        ),
                        "verifiedBy": review.get("verifiedBy", ""),
                        "verifiedAt": review.get("verifiedAt", ""),
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            lines.append("```")
    if result["errors"]:
        lines.extend(["", "## Errors", ""])
        lines.extend(f"- {error}" for error in result["errors"])
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compare paired old/new SellerSprite P2 live evidence.")
    parser.add_argument("capture", type=Path)
    parser.add_argument("--format", choices=("json", "markdown", "both"), default="both")
    parser.add_argument("--json-out", type=Path)
    parser.add_argument("--markdown-out", type=Path)
    parser.add_argument(
        "--representative-run-dir",
        type=Path,
        required=True,
        help="Directory containing raw gate_log_*.tsv files for distribution-adjusted ROI",
    )
    args = parser.parse_args(argv)
    try:
        representative = load_representative_run_dir(args.representative_run_dir)
        result = compare_capture(load_capture(args.capture), representative, require_roi=True)
        base = args.capture.resolve().parent
        if args.format in {"json", "both"}:
            output = (args.json_out or (base / "p2_pair_validation.json")).resolve()
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            print(output)
        if args.format in {"markdown", "both"}:
            output = (args.markdown_out or (base / "p2_pair_validation.md")).resolve()
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(render_markdown(result), encoding="utf-8")
            print(output)
        return 0 if result["passed"] else 1
    except ContractError as error:
        print(f"[ERROR] {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
