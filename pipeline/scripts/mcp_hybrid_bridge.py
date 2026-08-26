#!/usr/bin/env python3
"""Loopback-only MCP shadow evidence store and call-budget ledger."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import secrets
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Iterator
from urllib.parse import parse_qs, urlparse

try:
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
except ImportError:  # pragma: no cover - Python 3.9+ is required in production
    ZoneInfo = None  # type: ignore[assignment]
    ZoneInfoNotFoundError = Exception  # type: ignore[assignment]


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_PROJECT_ROOT = SCRIPT_DIR.parent
BRIDGE_VERSION = "0.3.2"
POLICY_SCHEMA = "sellerSpriteMcpHybridPolicy/v1"
BUNDLE_SCHEMA = "sellerSpriteMcpEvidenceBundle/v1"
EVIDENCE_SCHEMA = "sellerSpriteMcpEvidence/v1"
LEDGER_SCHEMA = "sellerSpriteMcpCallLedgerEvent/v1"
RESPONSE_SCHEMA = "sellerSpriteMcpHybridResponse/v1"
MANIFEST_SCHEMA = "sellerSpriteMcpHybridManifest/v1"
BATCH_LOOKUP_SCHEMA = "sellerSpriteMcpBatchLookup/v1"
MERGED_RANKING_SCHEMA = "sellerSpriteMcpMergedRanking/v1"
AUDIT_EVENT_SCHEMA = "sellerSpriteMcpAuditEvent/v1"
AUDIT_RECEIPT_SCHEMA = "sellerSpriteMcpAuditReceipt/v1"
PLAN_STATE_SCHEMA = "sellerSpriteMcpPlanState/v1"
MAX_REQUEST_BYTES = 8 * 1024 * 1024
ASIN_RE = re.compile(r"^B0[A-Z0-9]{8}$")
SHA256_RE = re.compile(r"^[a-fA-F0-9]{64}$")
SAFE_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,160}$")
# Audit IDs are JSON values and are never used as filesystem paths. The
# userscript event protocol uses colon-separated request/audit IDs.
AUDIT_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
ALLOWED_ORIGINS = {"https://www.amazon.com", "https://amazon.com"}
POOL_NAMES = ("primary", "conditional", "emergency")

try:
    SHANGHAI_TZ = ZoneInfo("Asia/Shanghai") if ZoneInfo is not None else None
except ZoneInfoNotFoundError:  # pragma: no cover - Windows can lack the tzdata wheel
    SHANGHAI_TZ = None
if SHANGHAI_TZ is None:
    SHANGHAI_TZ = timezone(timedelta(hours=8), name="Asia/Shanghai")

_PROCESS_LOCKS_GUARD = threading.Lock()
_PROCESS_LOCKS: dict[str, threading.RLock] = {}


class BridgeError(RuntimeError):
    def __init__(self, message: str, *, status: int = 400, stage: str = "validation", details: Any = None):
        super().__init__(message)
        self.status = status
        self.stage = stage
        self.details = details


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def now_iso() -> str:
    return now_utc().isoformat(timespec="seconds").replace("+00:00", "Z")


def canonical_json_bytes(payload: Any) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def payload_sha256(payload: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def atomic_write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{secrets.token_hex(6)}.tmp")
    try:
        temporary.write_bytes(canonical_json_bytes(payload))
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def append_jsonl(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("ab") as handle:
        handle.write(canonical_json_bytes(payload))
        handle.flush()
        os.fsync(handle.fileno())


def _process_lock(path: Path) -> threading.RLock:
    key = os.path.normcase(str(path.resolve()))
    with _PROCESS_LOCKS_GUARD:
        lock = _PROCESS_LOCKS.get(key)
        if lock is None:
            lock = threading.RLock()
            _PROCESS_LOCKS[key] = lock
        return lock


@contextmanager
def interprocess_file_lock(path: Path) -> Iterator[None]:
    """Serialize JSONL read-modify-write sections across threads and processes."""

    path.parent.mkdir(parents=True, exist_ok=True)
    thread_lock = _process_lock(path)
    with thread_lock:
        handle = path.open("a+b")
        try:
            handle.seek(0, os.SEEK_END)
            if handle.tell() == 0:
                handle.write(b"\0")
                handle.flush()
                os.fsync(handle.fileno())
            handle.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
            else:  # pragma: no cover - exercised on non-Windows CI only
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                handle.seek(0)
                if os.name == "nt":
                    import msvcrt

                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:  # pragma: no cover - exercised on non-Windows CI only
                    import fcntl

                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()


def parse_timestamp(value: Any, field: str) -> datetime:
    text = str(value or "").strip()
    if not text:
        raise BridgeError(f"{field} is required")
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as error:
        raise BridgeError(f"{field} must be an ISO-8601 timestamp") from error
    if parsed.tzinfo is None:
        raise BridgeError(f"{field} must include a timezone")
    return parsed.astimezone(timezone.utc)


def normalize_asin(value: Any) -> str:
    text = str(value or "").strip().upper()
    return text if ASIN_RE.fullmatch(text) else ""


def require_sha256(value: Any, field: str) -> str:
    text = str(value or "").strip().lower()
    if not SHA256_RE.fullmatch(text):
        raise BridgeError(f"{field} must be a SHA-256 hex digest")
    return text


def contains_final_authority_claim(value: Any) -> bool:
    if isinstance(value, dict):
        for key, nested in value.items():
            if key in {"finalAuthority", "usableForFinal"} and nested is True:
                return True
            if contains_final_authority_claim(nested):
                return True
    elif isinstance(value, list):
        return any(contains_final_authority_claim(item) for item in value)
    return False


def load_policy(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise BridgeError(f"policy file not found: {path}", stage="startup")
    policy = read_json(path)
    if not isinstance(policy, dict) or policy.get("schemaVersion") != POLICY_SCHEMA:
        raise BridgeError("unsupported MCP hybrid policy schema", stage="startup")
    if policy.get("mode") != "shadow" or policy.get("outboundMcpEnabled") is not False:
        raise BridgeError("MCP Hybrid Bridge requires shadow mode with outbound MCP disabled", stage="startup")
    if policy.get("finalAuthority") is not False or policy.get("marketplace") != "US":
        raise BridgeError("policy must be US-only and non-authoritative", stage="startup")
    official = int(policy.get("officialMonthlyLimit") or 0)
    operational = int(policy.get("operationalMonthlyCap") or 0)
    run_budget = int(policy.get("defaultRunBudget") or 0)
    if official < 1 or operational < 1 or operational > official or run_budget < 1:
        raise BridgeError("invalid MCP call-budget policy", stage="startup")
    daily = policy.get("dailyQuota")
    if not isinstance(daily, dict) or daily.get("timezone") != "Asia/Shanghai":
        raise BridgeError("dailyQuota must use Asia/Shanghai", stage="startup")
    hard_limit = int(daily.get("hardLimit") or 0)
    pools = daily.get("pools")
    if not isinstance(pools, dict) or set(pools) != set(POOL_NAMES):
        raise BridgeError("dailyQuota must define primary, conditional, and emergency pools", stage="startup")
    pool_limits = {name: int(pools.get(name) or 0) for name in POOL_NAMES}
    if hard_limit != 500 or pool_limits != {"primary": 300, "conditional": 100, "emergency": 100}:
        raise BridgeError("dailyQuota must preserve the approved 300/100/100 allocation", stage="startup")
    if sum(pool_limits.values()) != hard_limit or daily.get("allowEmergencyByDefault") is not False:
        raise BridgeError("invalid daily MCP quota allocation", stage="startup")
    if operational != 12000 or run_budget > hard_limit:
        raise BridgeError("operational cap must be 12000 and run budget must fit the daily limit", stage="startup")
    tools = policy.get("tools")
    if not isinstance(tools, dict) or not tools:
        raise BridgeError("policy must define supported tools", stage="startup")
    for name, tool in tools.items():
        if not SAFE_ID_RE.fullmatch(str(name)) or not isinstance(tool, dict):
            raise BridgeError("invalid tool policy", stage="startup")
        if tool.get("finalGateEligible") is not False:
            raise BridgeError(f"tool {name} must not be final-gate eligible in shadow mode", stage="startup")
        if not isinstance(tool.get("enabled"), bool):
            raise BridgeError(f"tool {name} must declare enabled", stage="startup")
        if tool.get("validationStatus") not in {"validated_shadow", "pending", "blocked"}:
            raise BridgeError(f"tool {name} has an invalid validationStatus", stage="startup")
        if not isinstance(tool.get("reservationEnabled"), bool):
            raise BridgeError(f"tool {name} must declare reservationEnabled", stage="startup")
        if tool.get("validationStatus") == "blocked" and (
            tool.get("enabled") is not False or tool.get("reservationEnabled") is not False
        ):
            raise BridgeError(f"blocked tool {name} must be disabled", stage="startup")
        if tool.get("validationStatus") == "pending" and tool.get("reservationEnabled") is not False:
            raise BridgeError(f"pending tool {name} cannot be enabled for formal reservations", stage="startup")
        if float(tool.get("ttlHours") or 0) <= 0:
            raise BridgeError(f"tool {name} must declare a positive ttlHours", stage="startup")
    source_priority = policy.get("fieldSourcePriority") or {}
    if not isinstance(source_priority, dict):
        raise BridgeError("fieldSourcePriority must be an object", stage="startup")
    for field, names in source_priority.items():
        if not isinstance(field, str) or not isinstance(names, list) or any(name not in tools for name in names):
            raise BridgeError("fieldSourcePriority references an invalid field or tool", stage="startup")
    return policy


@dataclass(frozen=True)
class BridgeConfig:
    project_root: Path
    output_root: Path
    run_id: str
    token: str
    policy_path: Path
    run_budget: int | None = None
    ledger_path: Path | None = None
    audit_path: Path | None = None
    test_mode: bool = False


class CallLedger:
    def __init__(
        self,
        path: Path,
        *,
        run_id: str,
        policy: dict[str, Any],
        run_budget: int | None = None,
        test_mode: bool = False,
    ) -> None:
        self.path = path
        self.run_id = run_id
        self.official_limit = int(policy["officialMonthlyLimit"])
        self.operational_cap = int(policy["operationalMonthlyCap"])
        self.run_budget = int(run_budget or policy["defaultRunBudget"])
        daily = policy.get("dailyQuota") or {}
        pools = daily.get("pools") or {}
        self.daily_hard_limit = int(daily.get("hardLimit") or 500)
        self.pool_limits = {
            "primary": int(pools.get("primary") or 300),
            "conditional": int(pools.get("conditional") or 100),
            "emergency": int(pools.get("emergency") or 100),
        }
        self.allow_emergency_by_default = bool(daily.get("allowEmergencyByDefault", False))
        self.tools = policy.get("tools") or {}
        self.test_mode = bool(test_mode)
        self.lock_path = path.with_name(f"{path.name}.lock")
        if self.run_budget < 1:
            raise BridgeError("run budget must be positive", stage="startup")
        if self.run_budget > self.daily_hard_limit:
            raise BridgeError("run budget exceeds the daily hard limit", stage="startup")

    def _events_unlocked(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        events: list[dict[str, Any]] = []
        for line_number, raw in enumerate(self.path.read_text(encoding="utf-8").splitlines(), start=1):
            if not raw.strip():
                continue
            try:
                event = json.loads(raw)
            except json.JSONDecodeError as error:
                raise BridgeError(
                    f"invalid call ledger JSON at line {line_number}", status=500, stage="ledger"
                ) from error
            if not isinstance(event, dict) or event.get("schemaVersion") != LEDGER_SCHEMA:
                raise BridgeError(f"invalid call ledger event at line {line_number}", status=500, stage="ledger")
            events.append(event)
        return events

    def _events(self) -> list[dict[str, Any]]:
        with interprocess_file_lock(self.lock_path):
            return self._events_unlocked()

    @staticmethod
    def _is_reservation(event: dict[str, Any]) -> bool:
        return event.get("eventType") == "reserved" and int(event.get("calls") or 0) > 0

    def _sealed_run_reservation(self, events: list[dict[str, Any]]) -> dict[str, Any] | None:
        return next(
            (
                event
                for event in events
                if self._is_reservation(event)
                and event.get("runId") == self.run_id
                and event.get("sealedRun") is True
            ),
            None,
        )

    @staticmethod
    def _period_for_event(event: dict[str, Any]) -> tuple[str, str]:
        try:
            local = parse_timestamp(event.get("at"), "ledger.at").astimezone(SHANGHAI_TZ)
            return local.strftime("%Y-%m"), local.strftime("%Y-%m-%d")
        except BridgeError:
            return str(event.get("month") or ""), str(event.get("day") or "")

    @staticmethod
    def _pool_calls(event: dict[str, Any]) -> dict[str, int]:
        raw = event.get("poolCalls")
        if isinstance(raw, dict):
            return {name: max(0, int(raw.get(name) or 0)) for name in POOL_NAMES}
        pool = str(event.get("pool") or "primary")
        result = {name: 0 for name in POOL_NAMES}
        if pool in result:
            result[pool] = max(0, int(event.get("calls") or 0))
        return result

    @staticmethod
    def _reservation_states(events: list[dict[str, Any]]) -> dict[str, str]:
        states = {
            str(event.get("eventId")): "reserved"
            for event in events
            if CallLedger._is_reservation(event) and event.get("eventId")
        }
        for event in events:
            if event.get("eventType") not in {"succeeded", "failed"}:
                continue
            reservation_id = str(event.get("reservationEventId") or "")
            if reservation_id in states:
                states[reservation_id] = str(event["eventType"])
        return states

    def _summary_from_events(self, events: list[dict[str, Any]], current: datetime) -> dict[str, Any]:
        local = current.astimezone(SHANGHAI_TZ)
        month = local.strftime("%Y-%m")
        day = local.strftime("%Y-%m-%d")
        reservations = [event for event in events if self._is_reservation(event)]
        monthly_events = [event for event in reservations if self._period_for_event(event)[0] == month]
        daily_events = [event for event in reservations if self._period_for_event(event)[1] == day]
        monthly_used = sum(int(event.get("calls") or 0) for event in monthly_events)
        daily_used = sum(int(event.get("calls") or 0) for event in daily_events)
        run_reservations = [event for event in reservations if event.get("runId") == self.run_id]
        run_used = sum(int(event.get("calls") or 0) for event in run_reservations)
        daily_pool_used = {name: 0 for name in POOL_NAMES}
        for event in daily_events:
            for name, calls in self._pool_calls(event).items():
                daily_pool_used[name] += calls
        official_pct = 100.0 * monthly_used / self.official_limit
        if monthly_used >= self.operational_cap:
            state = "operational_cap"
        elif daily_used >= self.daily_hard_limit:
            state = "daily_cap"
        elif official_pct >= 75:
            state = "warning"
        else:
            state = "normal"
        reservation_states = self._reservation_states(events)
        status_counts = {name: 0 for name in ("reserved", "succeeded", "failed")}
        status_calls = {name: 0 for name in ("reserved", "succeeded", "failed")}
        for event in run_reservations:
            status = reservation_states.get(str(event.get("eventId")), "reserved")
            status_counts[status] += 1
            status_calls[status] += int(event.get("calls") or 0)
        claimed_count = sum(
            1
            for event in events
            if event.get("eventType") == "claimed" and event.get("runId") == self.run_id
        )
        sealed_reservation = self._sealed_run_reservation(events)
        return {
            "schemaVersion": "sellerSpriteMcpCallLedgerSummary/v1",
            "runId": self.run_id,
            "month": month,
            "day": day,
            "timezone": "Asia/Shanghai",
            "monthlyUsed": monthly_used,
            "officialMonthlyLimit": self.official_limit,
            "operationalMonthlyCap": self.operational_cap,
            "dailyUsed": daily_used,
            "dailyHardLimit": self.daily_hard_limit,
            "dailyPools": {
                name: {
                    "used": daily_pool_used[name],
                    "limit": self.pool_limits[name],
                    "remaining": max(0, self.pool_limits[name] - daily_pool_used[name]),
                }
                for name in POOL_NAMES
            },
            "runUsed": run_used,
            "runBudget": self.run_budget,
            "sealedRun": sealed_reservation is not None,
            "sealedPlanId": sealed_reservation.get("planId") if sealed_reservation else None,
            "authorizedCalls": int(sealed_reservation.get("authorizedCalls") or 0) if sealed_reservation else 0,
            "sealedReserveCalls": int(sealed_reservation.get("sealedReserveCalls") or 0)
            if sealed_reservation
            else 0,
            "statusCounts": status_counts,
            "statusCalls": status_calls,
            "claimedCount": claimed_count,
            "state": state,
        }

    def summary(self, at: datetime | None = None) -> dict[str, Any]:
        current = (at or now_utc()).astimezone(timezone.utc)
        with interprocess_file_lock(self.lock_path):
            return self._summary_from_events(self._events_unlocked(), current)

    def _tool_policy(self, tool: str) -> dict[str, Any] | None:
        if not self.tools:
            return None
        value = self.tools.get(tool)
        if not isinstance(value, dict):
            raise BridgeError("unknown MCP tool", stage="budget")
        return value

    def _tool_reservation_allowed(self, tool: str) -> dict[str, Any] | None:
        tool_policy = self._tool_policy(tool)
        if tool_policy is None:
            return None
        status = tool_policy.get("validationStatus")
        if status == "blocked" or tool_policy.get("enabled") is not True:
            raise BridgeError(f"MCP tool {tool} is blocked", status=409, stage="tool_policy")
        if tool_policy.get("reservationEnabled") is True and status == "validated_shadow":
            return tool_policy
        if self.test_mode and status == "pending" and tool_policy.get("testReservationEnabled") is True:
            return tool_policy
        raise BridgeError(
            f"MCP tool {tool} is not approved for formal reservation",
            status=409,
            stage="tool_policy",
        )

    def _normalize_request(self, item: Any, *, default_pool: str = "primary") -> dict[str, Any]:
        if not isinstance(item, dict):
            raise BridgeError("plan requests must be objects", stage="budget")
        request_id = str(item.get("id") or "")
        if not SAFE_ID_RE.fullmatch(request_id):
            raise BridgeError("plan request id is invalid", stage="budget")
        tool = str(item.get("tool") or "")
        tool_policy = self._tool_reservation_allowed(tool)
        request_hash = require_sha256(item.get("requestHash"), "requestHash")
        calls = int(item.get("calls") or 1)
        asin_count = int(item.get("asinCount") if item.get("asinCount") is not None else 0)
        pool = str(item.get("pool") or default_pool)
        if calls < 1 or pool not in POOL_NAMES:
            raise BridgeError("calls must be positive and pool must be declared", stage="budget")
        allow_zero_asins = bool(tool_policy and tool_policy.get("allowZeroAsins"))
        if asin_count < 0 or (asin_count == 0 and not allow_zero_asins):
            raise BridgeError("asinCount must be positive for this MCP tool", stage="budget")
        if tool_policy is not None:
            maximum = int(tool_policy.get("maxAsinsPerCall") or 0)
            if asin_count > 0 and (maximum < 1 or asin_count > maximum * calls):
                raise BridgeError(f"request {request_id} exceeds maxAsinsPerCall", stage="budget")
        return {
            "id": request_id,
            "tool": tool,
            "requestHash": request_hash,
            "asinCount": asin_count,
            "calls": calls,
            "pool": pool,
        }

    def _validate_quota(
        self,
        summary: dict[str, Any],
        *,
        calls: int,
        pool_calls: dict[str, int],
        allow_emergency: bool,
    ) -> None:
        if pool_calls["emergency"] and not (allow_emergency or self.allow_emergency_by_default):
            raise BridgeError(
                "emergency pool requires explicit authorization",
                status=409,
                stage="budget",
                details=summary,
            )
        if summary["runUsed"] + calls > self.run_budget:
            raise BridgeError("run MCP call budget exceeded", status=429, stage="budget", details=summary)
        if summary["monthlyUsed"] + calls > self.operational_cap:
            raise BridgeError("operational monthly MCP cap exceeded", status=429, stage="budget", details=summary)
        if summary["monthlyUsed"] + calls > self.official_limit:
            raise BridgeError("official monthly MCP limit exceeded", status=429, stage="budget", details=summary)
        if summary["dailyUsed"] + calls > self.daily_hard_limit:
            raise BridgeError("Asia/Shanghai daily MCP hard limit exceeded", status=429, stage="budget", details=summary)
        for name in POOL_NAMES:
            if summary["dailyPools"][name]["used"] + pool_calls[name] > self.pool_limits[name]:
                raise BridgeError(
                    f"daily MCP {name} pool exceeded",
                    status=429,
                    stage="budget",
                    details=summary,
                )

    def reserve(
        self,
        *,
        tool: str,
        request_hash: str,
        asin_count: int,
        calls: int = 1,
        at: datetime | None = None,
        pool: str = "primary",
        allow_emergency: bool = False,
    ) -> dict[str, Any]:
        normalized = self._normalize_request(
            {
                "id": f"legacy-{secrets.token_hex(8)}",
                "tool": tool,
                "requestHash": request_hash,
                "asinCount": asin_count,
                "calls": calls,
                "pool": pool,
            }
        )
        current = (at or now_utc()).astimezone(timezone.utc)
        with interprocess_file_lock(self.lock_path):
            events = self._events_unlocked()
            sealed = self._sealed_run_reservation(events)
            if sealed is not None:
                raise BridgeError(
                    "sealed run cannot accept legacy reservations",
                    status=409,
                    stage="budget_sealed",
                    details={"planId": sealed.get("planId"), "executionAllowed": False},
                )
            summary = self._summary_from_events(events, current)
            pool_calls = {name: (calls if name == pool else 0) for name in POOL_NAMES}
            self._validate_quota(
                summary,
                calls=calls,
                pool_calls=pool_calls,
                allow_emergency=allow_emergency,
            )
            timestamp = current.isoformat(timespec="microseconds").replace("+00:00", "Z")
            event_seed = f"{self.run_id}|{timestamp}|{tool}|{request_hash}|{calls}|{summary['runUsed']}"
            local = current.astimezone(SHANGHAI_TZ)
            event = {
                "schemaVersion": LEDGER_SCHEMA,
                "eventId": hashlib.sha256(event_seed.encode("utf-8")).hexdigest()[:32],
                "eventType": "reserved",
                "status": "reserved",
                "runId": self.run_id,
                "month": local.strftime("%Y-%m"),
                "day": local.strftime("%Y-%m-%d"),
                "timezone": "Asia/Shanghai",
                "at": timestamp,
                "tool": tool,
                "requestHash": normalized["requestHash"],
                "asinCount": asin_count,
                "calls": calls,
                "pool": pool,
                "poolCalls": pool_calls,
                "automaticRetry": False,
            }
            append_jsonl(self.path, event)
            events.append(event)
            return {"event": event, "summary": self._summary_from_events(events, current), "idempotent": False}

    def reserve_plan(
        self,
        *,
        plan_id: str,
        requests: Any,
        allow_emergency: bool = False,
        seal_run: bool = False,
        at: datetime | None = None,
    ) -> dict[str, Any]:
        if not SAFE_ID_RE.fullmatch(str(plan_id or "")):
            raise BridgeError("planId is invalid", stage="budget")
        if not isinstance(requests, list) or not requests or len(requests) > 1000:
            raise BridgeError("reserve_plan requires 1-1000 requests", stage="budget")
        if not isinstance(seal_run, bool):
            raise BridgeError("sealRun must be boolean", stage="budget")
        normalized = [self._normalize_request(item) for item in requests]
        request_ids = [item["id"] for item in normalized]
        if len(set(request_ids)) != len(request_ids):
            raise BridgeError("plan request ids must be unique", stage="budget")
        pool_calls = {
            name: sum(item["calls"] for item in normalized if item["pool"] == name) for name in POOL_NAMES
        }
        total_calls = sum(item["calls"] for item in normalized)
        plan_payload = {
            "runId": self.run_id,
            "planId": plan_id,
            "requests": normalized,
            "allowEmergency": bool(allow_emergency),
        }
        if seal_run:
            plan_payload["sealedRun"] = True
            plan_payload["taskBudget"] = self.run_budget
        plan_hash = payload_sha256(plan_payload)
        current = (at or now_utc()).astimezone(timezone.utc)
        with interprocess_file_lock(self.lock_path):
            events = self._events_unlocked()
            existing = next(
                (
                    event
                    for event in events
                    if self._is_reservation(event)
                    and event.get("runId") == self.run_id
                    and event.get("planId") == plan_id
                ),
                None,
            )
            if existing is not None:
                if existing.get("requestHash") != plan_hash:
                    raise BridgeError(
                        "planId already exists with different content",
                        status=409,
                        stage="budget_conflict",
                        details={"planId": plan_id, "eventId": existing.get("eventId")},
                    )
                states = self._reservation_states(events)
                return {
                    "event": existing,
                    "summary": self._summary_from_events(events, current),
                    "idempotent": True,
                    "currentStatus": states.get(str(existing.get("eventId")), "reserved"),
                }
            sealed = self._sealed_run_reservation(events)
            if sealed is not None:
                raise BridgeError(
                    "sealed run cannot accept another plan",
                    status=409,
                    stage="budget_sealed",
                    details={"planId": sealed.get("planId"), "executionAllowed": False},
                )
            run_reservations = [
                event
                for event in events
                if self._is_reservation(event) and event.get("runId") == self.run_id
            ]
            if seal_run and run_reservations:
                raise BridgeError(
                    "sealed plan requires a fresh runId",
                    status=409,
                    stage="budget_sealed",
                    details={"executionAllowed": False},
                )
            summary = self._summary_from_events(events, current)
            self._validate_quota(
                summary,
                calls=total_calls,
                pool_calls=pool_calls,
                allow_emergency=allow_emergency,
            )
            timestamp = current.isoformat(timespec="microseconds").replace("+00:00", "Z")
            local = current.astimezone(SHANGHAI_TZ)
            event = {
                "schemaVersion": LEDGER_SCHEMA,
                "eventId": hashlib.sha256(f"{self.run_id}|{plan_id}|{plan_hash}".encode("utf-8")).hexdigest()[:32],
                "eventType": "reserved",
                "status": "reserved",
                "runId": self.run_id,
                "planId": plan_id,
                "month": local.strftime("%Y-%m"),
                "day": local.strftime("%Y-%m-%d"),
                "timezone": "Asia/Shanghai",
                "at": timestamp,
                "tool": "__plan__",
                "requestHash": plan_hash,
                "asinCount": sum(item["asinCount"] for item in normalized),
                "calls": total_calls,
                "poolCalls": pool_calls,
                "requests": normalized,
                "allowEmergency": bool(allow_emergency),
                "sealedRun": seal_run,
                "authorizedCalls": total_calls if seal_run else 0,
                "taskBudget": self.run_budget if seal_run else None,
                "sealedReserveCalls": self.run_budget - total_calls if seal_run else 0,
                "automaticRetry": False,
            }
            append_jsonl(self.path, event)
            events.append(event)
            return {
                "event": event,
                "summary": self._summary_from_events(events, current),
                "idempotent": False,
                "currentStatus": "reserved",
            }

    def mark_plan_status(
        self,
        *,
        plan_id: str,
        status: str,
        details: Any = None,
        at: datetime | None = None,
    ) -> dict[str, Any]:
        if not SAFE_ID_RE.fullmatch(str(plan_id or "")):
            raise BridgeError("planId is invalid", stage="ledger")
        if status not in {"succeeded", "failed"}:
            raise BridgeError("status must be succeeded or failed", stage="ledger")
        normalized_details = {} if details is None else details
        if not isinstance(normalized_details, dict):
            raise BridgeError("status details must be an object", stage="ledger")
        details_hash = payload_sha256(normalized_details)
        current = (at or now_utc()).astimezone(timezone.utc)
        with interprocess_file_lock(self.lock_path):
            events = self._events_unlocked()
            reservation = next(
                (
                    event
                    for event in events
                    if self._is_reservation(event)
                    and event.get("runId") == self.run_id
                    and event.get("planId") == plan_id
                ),
                None,
            )
            if reservation is None:
                raise BridgeError("plan reservation not found", status=404, stage="ledger")
            if reservation.get("sealedRun") is True:
                request_ids = [
                    str(item.get("id") or "")
                    for item in reservation.get("requests") or []
                    if isinstance(item, dict)
                ]
                claims = [
                    event
                    for event in events
                    if event.get("eventType") == "claimed"
                    and event.get("runId") == self.run_id
                    and event.get("reservationEventId") == reservation.get("eventId")
                ]
                claimed_ids = [str(event.get("requestId") or "") for event in claims]
                if (
                    len(claimed_ids) != len(request_ids)
                    or len(set(claimed_ids)) != len(request_ids)
                    or set(claimed_ids) != set(request_ids)
                ):
                    raise BridgeError(
                        "sealed plan requires every reserved request to be claimed before closure",
                        status=409,
                        stage="ledger_incomplete",
                        details={"claimed": len(claimed_ids), "required": len(request_ids)},
                    )
                requests_by_id = {
                    str(item.get("id") or ""): item
                    for item in reservation.get("requests") or []
                    if isinstance(item, dict)
                }
                for claim in claims:
                    expected = requests_by_id.get(str(claim.get("requestId") or ""))
                    if expected is None or (
                        claim.get("requestHash") != expected.get("requestHash")
                        or claim.get("tool") != expected.get("tool")
                        or claim.get("pool") != expected.get("pool")
                        or claim.get("executionAllowed") is not True
                        or claim.get("automaticRetry") is not False
                        or claim.get("finalAuthority") is not False
                    ):
                        raise BridgeError("sealed plan claim does not match its reserved request", stage="ledger")
                outcome_counts = normalized_details.get("outcomeCounts")
                if not isinstance(outcome_counts, dict) or set(outcome_counts) != {
                    "succeeded",
                    "partial",
                    "failed",
                }:
                    raise BridgeError("sealed plan outcomeCounts are invalid", stage="ledger")
                if any(
                    not isinstance(outcome_counts.get(name), int)
                    or isinstance(outcome_counts.get(name), bool)
                    or outcome_counts[name] < 0
                    for name in outcome_counts
                ):
                    raise BridgeError("sealed plan outcomeCounts are invalid", stage="ledger")
                normalized_counts = {name: outcome_counts[name] for name in outcome_counts}
                authorized_calls = int(reservation.get("authorizedCalls") or 0)
                count_fields = ("requestCount", "authorizedCalls", "rawResponseArchiveCount")
                if any(
                    not isinstance(normalized_details.get(field), int)
                    or isinstance(normalized_details.get(field), bool)
                    for field in count_fields
                ):
                    raise BridgeError("sealed plan finalization counts are invalid", stage="ledger")
                if (
                    normalized_details["requestCount"] != authorized_calls
                    or normalized_details["authorizedCalls"] != authorized_calls
                    or normalized_details["rawResponseArchiveCount"] != authorized_calls
                    or sum(normalized_counts.values()) != authorized_calls
                ):
                    raise BridgeError("sealed plan finalization is incomplete", stage="ledger")
                for field in ("claimManifestSha256", "resultManifestSha256", "rawManifestSha256"):
                    require_sha256(normalized_details.get(field), f"details.{field}")
                expected_status = "failed" if normalized_counts["partial"] or normalized_counts["failed"] else "succeeded"
                if status != expected_status:
                    raise BridgeError(
                        "sealed plan status conflicts with validation outcomes",
                        status=409,
                        stage="ledger_conflict",
                    )
            prior_status_events = [
                event
                for event in events
                if event.get("reservationEventId") == reservation.get("eventId")
                and event.get("eventType") in {"succeeded", "failed"}
            ]
            if prior_status_events:
                prior = prior_status_events[-1]
                if prior.get("eventType") == status and prior.get("detailsHash") == details_hash:
                    return {
                        "event": prior,
                        "summary": self._summary_from_events(events, current),
                        "idempotent": True,
                    }
                raise BridgeError(
                    "plan already has a terminal status",
                    status=409,
                    stage="ledger_conflict",
                    details={"planId": plan_id, "status": prior.get("eventType")},
                )
            timestamp = current.isoformat(timespec="microseconds").replace("+00:00", "Z")
            event = {
                "schemaVersion": LEDGER_SCHEMA,
                "eventId": hashlib.sha256(
                    f"{reservation['eventId']}|{status}|{details_hash}".encode("utf-8")
                ).hexdigest()[:32],
                "eventType": status,
                "status": status,
                "runId": self.run_id,
                "planId": plan_id,
                "reservationEventId": reservation["eventId"],
                "at": timestamp,
                "calls": 0,
                "details": normalized_details,
                "detailsHash": details_hash,
                "automaticRetry": False,
            }
            append_jsonl(self.path, event)
            events.append(event)
            return {"event": event, "summary": self._summary_from_events(events, current), "idempotent": False}

    def claim_plan_request(
        self,
        *,
        plan_id: str,
        request_id: str,
        claim_id: str,
        at: datetime | None = None,
    ) -> dict[str, Any]:
        if not SAFE_ID_RE.fullmatch(str(plan_id or "")):
            raise BridgeError("planId is invalid", stage="claim")
        if not SAFE_ID_RE.fullmatch(str(request_id or "")):
            raise BridgeError("requestId is invalid", stage="claim")
        if not SAFE_ID_RE.fullmatch(str(claim_id or "")):
            raise BridgeError("claimId is invalid", stage="claim")
        current = (at or now_utc()).astimezone(timezone.utc)
        with interprocess_file_lock(self.lock_path):
            events = self._events_unlocked()
            reservation = next(
                (
                    event
                    for event in events
                    if self._is_reservation(event)
                    and event.get("runId") == self.run_id
                    and event.get("planId") == plan_id
                ),
                None,
            )
            if reservation is None:
                raise BridgeError(
                    "plan reservation not found",
                    status=404,
                    stage="claim",
                    details={"executionAllowed": False},
                )
            states = self._reservation_states(events)
            plan_status = states.get(str(reservation.get("eventId")), "reserved")
            if plan_status != "reserved":
                raise BridgeError(
                    "terminal plan cannot issue execution claims",
                    status=409,
                    stage="claim_terminal",
                    details={"planId": plan_id, "status": plan_status, "executionAllowed": False},
                )
            request = next(
                (
                    item
                    for item in reservation.get("requests") or []
                    if isinstance(item, dict) and item.get("id") == request_id
                ),
                None,
            )
            if request is None:
                raise BridgeError(
                    "requestId is not part of the reserved plan",
                    status=404,
                    stage="claim",
                    details={"planId": plan_id, "requestId": request_id, "executionAllowed": False},
                )
            claims = [
                event
                for event in events
                if event.get("eventType") == "claimed" and event.get("runId") == self.run_id
            ]
            prior_request_claim = next(
                (
                    event
                    for event in claims
                    if event.get("reservationEventId") == reservation.get("eventId")
                    and event.get("requestId") == request_id
                ),
                None,
            )
            if prior_request_claim is not None:
                raise BridgeError(
                    "plan request has already been claimed",
                    status=409,
                    stage="claim_conflict",
                    details={
                        "planId": plan_id,
                        "requestId": request_id,
                        "claimId": prior_request_claim.get("claimId"),
                        "sameClaimId": prior_request_claim.get("claimId") == claim_id,
                        "executionAllowed": False,
                    },
                )
            prior_claim_id = next((event for event in claims if event.get("claimId") == claim_id), None)
            if prior_claim_id is not None:
                raise BridgeError(
                    "claimId has already been used",
                    status=409,
                    stage="claim_conflict",
                    details={
                        "claimId": claim_id,
                        "planId": prior_claim_id.get("planId"),
                        "requestId": prior_claim_id.get("requestId"),
                        "executionAllowed": False,
                    },
                )
            timestamp = current.isoformat(timespec="microseconds").replace("+00:00", "Z")
            event = {
                "schemaVersion": LEDGER_SCHEMA,
                "eventId": hashlib.sha256(
                    f"{reservation['eventId']}|{request_id}|{claim_id}".encode("utf-8")
                ).hexdigest()[:32],
                "eventType": "claimed",
                "status": "claimed",
                "runId": self.run_id,
                "planId": plan_id,
                "requestId": request_id,
                "claimId": claim_id,
                "reservationEventId": reservation["eventId"],
                "requestHash": request.get("requestHash"),
                "tool": request.get("tool"),
                "pool": request.get("pool"),
                "at": timestamp,
                "calls": 0,
                "executionAllowed": True,
                "automaticRetry": False,
                "finalAuthority": False,
            }
            append_jsonl(self.path, event)
            events.append(event)
            return {
                "event": event,
                "executionAllowed": True,
                "idempotent": False,
                "summary": self._summary_from_events(events, current),
                "finalAuthority": False,
            }

    def plan_state(self, plan_id: str) -> dict[str, Any]:
        if not SAFE_ID_RE.fullmatch(str(plan_id or "")):
            raise BridgeError("planId is invalid", stage="plan_state")
        with interprocess_file_lock(self.lock_path):
            events = self._events_unlocked()
            reservation = next(
                (
                    event
                    for event in events
                    if self._is_reservation(event)
                    and event.get("runId") == self.run_id
                    and event.get("planId") == plan_id
                ),
                None,
            )
            if reservation is None:
                raise BridgeError(
                    "plan reservation not found",
                    status=404,
                    stage="plan_state",
                    details={"planId": plan_id, "finalAuthority": False},
                )
            reservation_id = str(reservation.get("eventId") or "")
            claims = [
                event
                for event in events
                if event.get("eventType") == "claimed"
                and event.get("runId") == self.run_id
                and event.get("reservationEventId") == reservation_id
            ]
            terminal_events = [
                event
                for event in events
                if event.get("eventType") in {"succeeded", "failed"}
                and event.get("runId") == self.run_id
                and event.get("reservationEventId") == reservation_id
            ]
            terminal = terminal_events[-1] if terminal_events else None
            status = str(terminal.get("eventType")) if terminal is not None else "reserved"
            if terminal is not None:
                phase = "terminal"
            elif claims:
                phase = "claimed"
            else:
                phase = "reserved"

            def event_copy(event: dict[str, Any] | None) -> dict[str, Any] | None:
                if event is None:
                    return None
                return {**event, "finalAuthority": False}

            reservation_copy = event_copy(reservation)
            if reservation_copy is not None:
                reservation_copy["currentStatus"] = status
            return {
                "schemaVersion": PLAN_STATE_SCHEMA,
                "runId": self.run_id,
                "planId": plan_id,
                "phase": phase,
                "status": status,
                "reservation": reservation_copy,
                "requests": list(reservation.get("requests") or []),
                "claimEvents": [event_copy(event) for event in claims],
                "claimedRequestIds": [str(event.get("requestId")) for event in claims],
                "terminalEvent": event_copy(terminal),
                "finalAuthority": False,
            }


class AuditLog:
    def __init__(self, path: Path, *, run_id: str) -> None:
        self.path = path
        self.run_id = run_id
        self.lock_path = path.with_name(f"{path.name}.lock")

    def _events_unlocked(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        events: list[dict[str, Any]] = []
        for line_number, raw in enumerate(self.path.read_text(encoding="utf-8").splitlines(), start=1):
            if not raw.strip():
                continue
            try:
                event = json.loads(raw)
            except json.JSONDecodeError as error:
                raise BridgeError(
                    f"invalid audit JSON at line {line_number}", status=500, stage="audit"
                ) from error
            if not isinstance(event, dict) or event.get("schemaVersion") != AUDIT_EVENT_SCHEMA:
                raise BridgeError(f"invalid audit event at line {line_number}", status=500, stage="audit")
            events.append(event)
        return events

    def append(self, payload: Any) -> dict[str, Any]:
        if not isinstance(payload, dict) or payload.get("schemaVersion") != AUDIT_EVENT_SCHEMA:
            raise BridgeError("unsupported MCP audit event schema", stage="audit")
        request_id = str(payload.get("requestId") or "")
        audit_id = str(payload.get("auditId") or "")
        event_type = str(payload.get("eventType") or "")
        if not AUDIT_ID_RE.fullmatch(request_id) or not AUDIT_ID_RE.fullmatch(audit_id):
            raise BridgeError("requestId and auditId must be safe identifiers", stage="audit")
        if not SAFE_ID_RE.fullmatch(event_type):
            raise BridgeError("eventType must be a safe identifier", stage="audit")
        body = payload.get("payload")
        if not isinstance(body, dict):
            raise BridgeError("audit payload must be an object", stage="audit")
        if payload.get("runId") not in {None, self.run_id}:
            raise BridgeError("audit runId mismatch", stage="audit")
        if payload.get("finalAuthority") is True or contains_final_authority_claim(body):
            raise BridgeError("audit events cannot claim final authority", stage="audit")
        canonical = {
            "schemaVersion": AUDIT_EVENT_SCHEMA,
            "requestId": request_id,
            "auditId": audit_id,
            "eventType": event_type,
            "payload": body,
            "runId": self.run_id,
            "finalAuthority": False,
        }
        content_hash = payload_sha256(canonical)
        with interprocess_file_lock(self.lock_path):
            events = self._events_unlocked()
            prior = next(
                (
                    event
                    for event in events
                    if event.get("runId") == self.run_id and event.get("auditId") == audit_id
                ),
                None,
            )
            if prior is not None:
                if prior.get("contentSha256") != content_hash:
                    raise BridgeError(
                        "auditId already exists with different content",
                        status=409,
                        stage="audit_conflict",
                        details={"auditId": audit_id},
                    )
                return {
                    "schemaVersion": AUDIT_RECEIPT_SCHEMA,
                    "requestId": request_id,
                    "auditId": audit_id,
                    "persisted": True,
                    "idempotent": True,
                    "finalAuthority": False,
                }
            event = {
                **canonical,
                "recordedAt": now_iso(),
                "contentSha256": content_hash,
            }
            append_jsonl(self.path, event)
            return {
                "schemaVersion": AUDIT_RECEIPT_SCHEMA,
                "requestId": request_id,
                "auditId": audit_id,
                "persisted": True,
                "idempotent": False,
                "finalAuthority": False,
            }

    def count(self) -> int:
        with interprocess_file_lock(self.lock_path):
            return len(self._events_unlocked())


class EvidenceStore:
    def __init__(
        self,
        root: Path,
        *,
        run_id: str,
        policy: dict[str, Any],
        ranking_test_mode: bool = False,
    ) -> None:
        self.root = root
        self.run_id = run_id
        self.policy = policy
        self.ranking_test_mode = bool(ranking_test_mode)
        self.evidence_dir = root / "evidence"
        self.manifest_path = root / "manifest.json"
        self.lock = threading.Lock()
        self.evidence_dir.mkdir(parents=True, exist_ok=True)

    def _load_manifest(self) -> dict[str, Any]:
        if not self.manifest_path.exists():
            return {
                "schemaVersion": MANIFEST_SCHEMA,
                "runId": self.run_id,
                "mode": "shadow",
                "finalAuthority": False,
                "createdAt": now_iso(),
                "updatedAt": now_iso(),
                "evidence": [],
                "imports": [],
            }
        manifest = read_json(self.manifest_path)
        if not isinstance(manifest, dict) or manifest.get("schemaVersion") != MANIFEST_SCHEMA:
            raise BridgeError("unsupported evidence manifest schema", status=500, stage="manifest")
        if manifest.get("runId") != self.run_id or manifest.get("finalAuthority") is not False:
            raise BridgeError("evidence manifest does not match the configured run", status=500, stage="manifest")
        return manifest

    def _validate_evidence(self, evidence: Any) -> dict[str, Any]:
        if not isinstance(evidence, dict) or evidence.get("schemaVersion") != EVIDENCE_SCHEMA:
            raise BridgeError("unsupported MCP evidence schema")
        if evidence.get("runId") != self.run_id or evidence.get("marketplace") != "US":
            raise BridgeError("evidence runId or marketplace mismatch")
        if evidence.get("mode") != "shadow" or evidence.get("finalAuthority") is not False:
            raise BridgeError("evidence must be shadow-only and non-authoritative")
        evidence_id = str(evidence.get("evidenceId") or "")
        if not SAFE_ID_RE.fullmatch(evidence_id):
            raise BridgeError("invalid evidenceId")
        target_asin = normalize_asin(evidence.get("targetAsin"))
        actual_asin = normalize_asin(evidence.get("actualAsin"))
        if not target_asin or not actual_asin:
            raise BridgeError("targetAsin and actualAsin must be valid")
        tool = evidence.get("tool")
        if not isinstance(tool, dict) or str(tool.get("name") or "") not in self.policy["tools"]:
            raise BridgeError("unknown or missing MCP tool")
        request = evidence.get("request")
        response = evidence.get("response")
        if not isinstance(request, dict) or not isinstance(response, dict):
            raise BridgeError("request and response metadata are required")
        require_sha256(request.get("sha256"), "request.sha256")
        require_sha256(response.get("sha256"), "response.sha256")
        captured_at = parse_timestamp(response.get("capturedAt"), "response.capturedAt")
        expires_at = parse_timestamp(response.get("expiresAt"), "response.expiresAt")
        if expires_at <= captured_at:
            raise BridgeError("response.expiresAt must be after response.capturedAt")
        ttl_hours = float(self.policy["tools"][str(tool["name"])]["ttlHours"])
        if expires_at - captured_at > timedelta(hours=ttl_hours):
            raise BridgeError(
                "response expiry exceeds the tool TTL policy",
                details={"tool": tool["name"], "ttlHours": ttl_hours},
            )
        if not isinstance(evidence.get("fields"), dict) or not isinstance(evidence.get("fieldProvenance"), dict):
            raise BridgeError("fields and fieldProvenance must be objects")
        fields = evidence["fields"]
        provenance = evidence["fieldProvenance"]
        if any(not isinstance(field, str) or not SAFE_ID_RE.fullmatch(field) for field in fields):
            raise BridgeError("field names must be safe identifiers")
        if any(field not in fields for field in provenance):
            raise BridgeError("fieldProvenance cannot reference an absent field")
        tool_name = str(tool["name"])
        for field, source in provenance.items():
            if not isinstance(source, dict) or source.get("sourceTool") != tool_name:
                raise BridgeError(f"fieldProvenance sourceTool mismatch for {field}")
            source_asin = source.get("sourceAsin")
            if source_asin is not None and normalize_asin(source_asin) != actual_asin:
                raise BridgeError(f"fieldProvenance sourceAsin mismatch for {field}")
        missing = evidence.get("missingFields")
        if not isinstance(missing, list) or any(not isinstance(item, str) for item in missing):
            raise BridgeError("missingFields must be a string array")
        if len(set(missing)) != len(missing) or any(not SAFE_ID_RE.fullmatch(item) for item in missing):
            raise BridgeError("missingFields must contain unique safe identifiers")
        overlapping = sorted(field for field in missing if field in fields and fields[field] is not None)
        if overlapping:
            raise BridgeError(
                "missingFields conflicts with populated fields",
                details={"fields": overlapping},
            )
        if not isinstance(evidence.get("fallbackRequired"), bool):
            raise BridgeError("fallbackRequired must be boolean")
        return evidence

    def import_bundle(self, bundle: Any) -> dict[str, Any]:
        if not isinstance(bundle, dict) or bundle.get("schemaVersion") != BUNDLE_SCHEMA:
            raise BridgeError("unsupported MCP evidence bundle schema")
        if bundle.get("runId") != self.run_id or bundle.get("marketplace") != "US":
            raise BridgeError("bundle runId or marketplace mismatch")
        parse_timestamp(bundle.get("generatedAt"), "generatedAt")
        rows = bundle.get("evidence")
        if not isinstance(rows, list) or not rows or len(rows) > 1000:
            raise BridgeError("evidence bundle must contain 1-1000 rows")
        validated = [self._validate_evidence(row) for row in rows]
        bundle_hash = payload_sha256(bundle)
        imported = 0
        duplicates = 0
        with self.lock:
            manifest = self._load_manifest()
            existing = {str(row.get("evidenceId")): row for row in manifest["evidence"]}
            pending: list[tuple[dict[str, Any], str, str]] = []
            for evidence in validated:
                evidence_id = str(evidence["evidenceId"])
                content_hash = payload_sha256(evidence)
                prior = existing.get(evidence_id)
                if prior:
                    if prior.get("contentSha256") != content_hash:
                        raise BridgeError(
                            "immutable MCP evidence conflict",
                            status=409,
                            stage="evidence_conflict",
                            details={"evidenceId": evidence_id},
                        )
                    duplicates += 1
                    continue
                pending.append((evidence, evidence_id, content_hash))
            for evidence, evidence_id, content_hash in pending:
                tool_name = str(evidence["tool"]["name"])
                id_hash = hashlib.sha256(evidence_id.encode("utf-8")).hexdigest()[:20]
                file_name = f"{evidence['targetAsin']}_{tool_name}_{id_hash}.json"
                path = self.evidence_dir / file_name
                atomic_write_json(path, evidence)
                entry = {
                    "evidenceId": evidence_id,
                    "targetAsin": evidence["targetAsin"],
                    "actualAsin": evidence["actualAsin"],
                    "tool": tool_name,
                    "capturedAt": evidence["response"]["capturedAt"],
                    "expiresAt": evidence["response"]["expiresAt"],
                    "path": str(path),
                    "contentSha256": content_hash,
                    "fileSha256": file_sha256(path),
                    "importedAt": now_iso(),
                }
                manifest["evidence"].append(entry)
                existing[evidence_id] = entry
                imported += 1
            manifest["imports"].append(
                {
                    "bundleSha256": bundle_hash,
                    "source": str(bundle.get("source") or "unknown"),
                    "generatedAt": bundle["generatedAt"],
                    "importedAt": now_iso(),
                    "rowCount": len(rows),
                    "newCount": imported,
                    "duplicateCount": duplicates,
                }
            )
            manifest["updatedAt"] = now_iso()
            atomic_write_json(self.manifest_path, manifest)
        return {
            "bundleSha256": bundle_hash,
            "rowCount": len(rows),
            "imported": imported,
            "duplicates": duplicates,
            "finalAuthority": False,
        }

    def _tool_rankable(self, tool_name: str) -> bool:
        tool = self.policy["tools"].get(tool_name) or {}
        if tool.get("enabled") is not True or tool.get("validationStatus") == "blocked":
            return False
        if tool.get("validationStatus") == "validated_shadow":
            return True
        return bool(
            self.ranking_test_mode
            and tool.get("validationStatus") == "pending"
            and tool.get("testReservationEnabled") is True
        )

    def _source_rank(self, field: str, tool_name: str) -> tuple[int, int]:
        declared = (self.policy.get("fieldSourcePriority") or {}).get(field) or []
        try:
            listed_rank = declared.index(tool_name)
        except ValueError:
            listed_rank = len(declared) + 100
        tool_priority = int((self.policy["tools"].get(tool_name) or {}).get("rankingPriority") or 0)
        return listed_rank, -tool_priority

    def _result_for_entry(
        self,
        entry: dict[str, Any],
        *,
        current: datetime,
    ) -> dict[str, Any]:
        path = Path(str(entry.get("path") or ""))
        if not path.is_file() or file_sha256(path) != entry.get("fileSha256"):
            raise BridgeError("stored MCP evidence failed integrity validation", status=500, stage="evidence_integrity")
        evidence = read_json(path)
        if payload_sha256(evidence) != entry.get("contentSha256"):
            raise BridgeError("stored MCP evidence content hash mismatch", status=500, stage="evidence_integrity")
        captured_at = parse_timestamp(evidence["response"]["capturedAt"], "response.capturedAt")
        expires_at = parse_timestamp(evidence["response"]["expiresAt"], "response.expiresAt")
        fresh = captured_at <= current < expires_at
        asin_match = evidence["targetAsin"] == evidence["actualAsin"]
        tool_name = str(evidence["tool"]["name"])
        tool_rankable = self._tool_rankable(tool_name)
        row_reasons: list[str] = []
        if not fresh:
            row_reasons.append("stale")
        if not asin_match:
            row_reasons.append("asin_mismatch")
        if not tool_rankable:
            status = str((self.policy["tools"].get(tool_name) or {}).get("validationStatus") or "unknown")
            row_reasons.append(f"tool_not_rankable:{status}")
        if evidence.get("fallbackRequired"):
            row_reasons.append("source_requested_fallback")
        missing = set(evidence.get("missingFields") or [])
        row_reasons.extend(f"missing_field:{field}" for field in sorted(missing))
        ranking_fields: dict[str, Any] = {}
        field_sources: dict[str, dict[str, Any]] = {}
        field_usability: dict[str, dict[str, Any]] = {}
        for field, value in evidence["fields"].items():
            reasons: list[str] = []
            if not fresh:
                reasons.append("stale")
            if not asin_match:
                reasons.append("asin_mismatch")
            if not tool_rankable:
                reasons.append("tool_not_rankable")
            if field in missing or value is None:
                reasons.append("missing_value")
            provenance = evidence["fieldProvenance"].get(field)
            if not isinstance(provenance, dict):
                reasons.append("missing_provenance")
            elif provenance.get("sourceTool") != tool_name:
                reasons.append("source_tool_mismatch")
            elif provenance.get("sourceAsin") is not None and normalize_asin(provenance.get("sourceAsin")) != evidence["actualAsin"]:
                reasons.append("source_asin_mismatch")
            usable = not reasons
            field_usability[field] = {"usableForRanking": usable, "reasonCodes": reasons}
            if not usable:
                row_reasons.extend(f"field_unusable:{field}:{reason}" for reason in reasons)
                continue
            ranking_fields[field] = value
            field_sources[field] = {
                "evidenceId": evidence["evidenceId"],
                "tool": tool_name,
                "capturedAt": evidence["response"]["capturedAt"],
                "expiresAt": evidence["response"]["expiresAt"],
                "sourcePath": provenance.get("sourcePath"),
                "semantics": provenance.get("semantics"),
            }
        usable_for_ranking = bool(ranking_fields)
        browser_fallback_required = bool(row_reasons) or not usable_for_ranking
        return {
            "evidence": evidence,
            "fresh": fresh,
            "asinMatch": asin_match,
            "usableForRanking": usable_for_ranking,
            "browserFallbackRequired": browser_fallback_required,
            "usableForFinal": False,
            "usableForShadow": usable_for_ranking,
            "fallbackRequired": browser_fallback_required,
            "fallbackReasons": sorted(set(row_reasons)),
            "rankingFields": ranking_fields,
            "fieldSources": field_sources,
            "fieldUsability": field_usability,
        }

    def _merge_ranking(self, results: list[dict[str, Any]]) -> dict[str, Any]:
        candidates: dict[str, list[tuple[tuple[int, int], float, Any, dict[str, Any], dict[str, Any]]]] = {}
        for result in results:
            if result.get("usableForRanking") is not True:
                continue
            evidence = result["evidence"]
            tool_name = str(evidence["tool"]["name"])
            captured_at = parse_timestamp(evidence["response"]["capturedAt"], "response.capturedAt")
            for field, value in result["rankingFields"].items():
                candidates.setdefault(field, []).append(
                    (
                        self._source_rank(field, tool_name),
                        -captured_at.timestamp(),
                        value,
                        result["fieldSources"][field],
                        result,
                    )
                )
        fields: dict[str, Any] = {}
        field_sources: dict[str, Any] = {}
        selected_results: dict[str, dict[str, Any]] = {}
        for field, options in candidates.items():
            source_rank, captured_rank, value, source, result = min(options, key=lambda item: (item[0], item[1]))
            del source_rank, captured_rank
            fields[field] = value
            field_sources[field] = source
            selected_results[str(source["evidenceId"])] = result
        evidence_ids = sorted(selected_results)
        reason_codes = sorted(
            {
                reason
                for result in selected_results.values()
                for reason in result.get("fallbackReasons") or []
            }
        )
        selected_sources = list(field_sources.values())
        captured_values = [parse_timestamp(source["capturedAt"], "fieldSource.capturedAt") for source in selected_sources]
        expiry_values = [parse_timestamp(source["expiresAt"], "fieldSource.expiresAt") for source in selected_sources]
        captured_at = (
            max(captured_values).isoformat(timespec="seconds").replace("+00:00", "Z") if captured_values else None
        )
        expires_at = (
            min(expiry_values).isoformat(timespec="seconds").replace("+00:00", "Z") if expiry_values else None
        )
        usable_for_ranking = bool(fields)
        browser_fallback_required = (
            not usable_for_ranking
            or any(result.get("browserFallbackRequired") is True for result in selected_results.values())
        )
        return {
            "schemaVersion": MERGED_RANKING_SCHEMA,
            "fields": fields,
            "fieldSources": field_sources,
            "usableForRanking": usable_for_ranking,
            "browserFallbackRequired": browser_fallback_required,
            "reasonCodes": reason_codes,
            "evidenceIds": evidence_ids,
            "capturedAt": captured_at,
            "expiresAt": expires_at,
            "usableForFinal": False,
            "finalAuthority": False,
        }

    def lookup(self, asin: str, *, tool: str = "", at: datetime | None = None) -> dict[str, Any]:
        target = normalize_asin(asin)
        if not target:
            raise BridgeError("invalid ASIN")
        if tool and tool not in self.policy["tools"]:
            raise BridgeError("unknown MCP tool")
        current = (at or now_utc()).astimezone(timezone.utc)
        manifest = self._load_manifest()
        entries = [
            entry
            for entry in manifest["evidence"]
            if entry.get("targetAsin") == target and (not tool or entry.get("tool") == tool)
        ]
        entries.sort(key=lambda item: str(item.get("capturedAt") or ""), reverse=True)
        results = [self._result_for_entry(entry, current=current) for entry in entries]
        return {
            "asin": target,
            "tool": tool or None,
            "checkedAt": current.isoformat(timespec="seconds").replace("+00:00", "Z"),
            "evidenceCount": len(results),
            "results": results,
            "mergedRanking": self._merge_ranking(results),
            "finalAuthority": False,
        }

    def count(self) -> int:
        return len(self._load_manifest()["evidence"])


class McpHybridBridge:
    def __init__(self, config: BridgeConfig) -> None:
        self.config = config
        self.policy = load_policy(config.policy_path)
        self.root = config.output_root.resolve() / "mcp_hybrid_bridge"
        self.root.mkdir(parents=True, exist_ok=True)
        self.store = EvidenceStore(
            self.root,
            run_id=config.run_id,
            policy=self.policy,
            ranking_test_mode=config.test_mode,
        )
        ledger_path = config.ledger_path or (config.project_root.resolve() / "cache" / "mcp_hybrid_call_ledger.jsonl")
        self.ledger = CallLedger(
            ledger_path,
            run_id=config.run_id,
            policy=self.policy,
            run_budget=config.run_budget,
            test_mode=config.test_mode,
        )
        audit_path = config.audit_path or (self.root / "audit_events.jsonl")
        self.audit = AuditLog(audit_path, run_id=config.run_id)

    def authenticate(self, token: str) -> None:
        if not token or not secrets.compare_digest(token, self.config.token):
            raise BridgeError("invalid bridge token", status=401, stage="auth")

    def health(self) -> dict[str, Any]:
        return {
            "schemaVersion": RESPONSE_SCHEMA,
            "ok": True,
            "version": BRIDGE_VERSION,
            "policyVersion": self.policy.get("policyVersion"),
            "policySha256": file_sha256(self.config.policy_path),
            "runId": self.config.run_id,
            "mode": "shadow",
            "testMode": self.config.test_mode,
            "outboundMcpEnabled": False,
            "finalAuthority": False,
            "evidenceCount": self.store.count(),
            "auditEventCount": self.audit.count(),
            "budget": self.ledger.summary(),
        }


class BridgeHttpServer(ThreadingHTTPServer):
    bridge: McpHybridBridge


class BridgeHandler(BaseHTTPRequestHandler):
    server: BridgeHttpServer

    def log_message(self, fmt: str, *args: Any) -> None:
        print(f"[mcp-hybrid] {self.address_string()} {fmt % args}")

    def _origin(self) -> str:
        return str(self.headers.get("Origin") or "")

    def _require_allowed_origin(self) -> None:
        origin = self._origin()
        if origin and origin not in ALLOWED_ORIGINS:
            raise BridgeError("browser origin is not allowed", status=403, stage="origin")

    def _cors_headers(self) -> None:
        origin = self._origin()
        if origin in ALLOWED_ORIGINS:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-MCP-Hybrid-Token")
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
                "ok": False,
                "stage": error.stage,
                "message": str(error),
                "details": error.details,
                "finalAuthority": False,
            },
        )

    def _token(self) -> str:
        return str(self.headers.get("X-MCP-Hybrid-Token") or "")

    def _read_json_body(self) -> Any:
        size = int(self.headers.get("Content-Length") or "0")
        if size < 1 or size > MAX_REQUEST_BYTES:
            raise BridgeError("invalid request size", status=413, stage="request")
        try:
            return json.loads(self.rfile.read(size).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise BridgeError("request body is not valid UTF-8 JSON", stage="request") from error

    def do_OPTIONS(self) -> None:  # noqa: N802
        try:
            self._require_allowed_origin()
            self.send_response(HTTPStatus.NO_CONTENT)
            self._cors_headers()
            self.send_header("Content-Length", "0")
            self.end_headers()
        except BridgeError as error:
            self._error(error)

    def do_GET(self) -> None:  # noqa: N802
        try:
            self._require_allowed_origin()
            parsed = urlparse(self.path)
            if parsed.path == "/api/v1/health":
                self._send_json(200, self.server.bridge.health())
                return
            self.server.bridge.authenticate(self._token())
            if parsed.path == "/api/v1/evidence":
                query = parse_qs(parsed.query)
                asin = (query.get("asin") or [""])[0]
                tool = (query.get("tool") or [""])[0]
                payload = self.server.bridge.store.lookup(asin, tool=tool)
                payload["schemaVersion"] = RESPONSE_SCHEMA
                payload["ok"] = True
                self._send_json(200, payload)
                return
            if parsed.path == "/api/v1/ledger":
                self._send_json(
                    200,
                    {
                        "schemaVersion": RESPONSE_SCHEMA,
                        "ok": True,
                        "budget": self.server.bridge.ledger.summary(),
                        "finalAuthority": False,
                    },
                )
                return
            if parsed.path == "/api/v1/calls/plan-state":
                query = parse_qs(parsed.query)
                plan_id = (query.get("planId") or [""])[0]
                result = self.server.bridge.ledger.plan_state(plan_id)
                self._send_json(
                    200,
                    {
                        "schemaVersion": RESPONSE_SCHEMA,
                        "ok": True,
                        "result": result,
                        "finalAuthority": False,
                    },
                )
                return
            raise BridgeError("endpoint not found", status=404, stage="routing")
        except BridgeError as error:
            self._error(error)
        except Exception as error:
            self._error(BridgeError(f"internal bridge error: {error}", status=500, stage="internal"))

    def do_POST(self) -> None:  # noqa: N802
        try:
            self._require_allowed_origin()
            self.server.bridge.authenticate(self._token())
            parsed = urlparse(self.path)
            payload = self._read_json_body()
            if parsed.path == "/api/v1/evidence/import":
                result = self.server.bridge.store.import_bundle(payload)
            elif parsed.path == "/api/v1/evidence/batch":
                if not isinstance(payload, dict):
                    raise BridgeError("batch lookup body must be an object")
                raw_asins = payload.get("asins")
                tool = str(payload.get("tool") or "")
                if not isinstance(raw_asins, list) or not raw_asins or len(raw_asins) > 40:
                    raise BridgeError("batch lookup requires 1-40 ASINs")
                asins = [normalize_asin(value) for value in raw_asins]
                if any(not asin for asin in asins) or len(set(asins)) != len(asins):
                    raise BridgeError("batch lookup ASINs must be valid and unique")
                if tool and tool not in self.server.bridge.policy["tools"]:
                    raise BridgeError("unknown MCP tool")
                result = {
                    "schemaVersion": BATCH_LOOKUP_SCHEMA,
                    "rows": [self.server.bridge.store.lookup(asin, tool=tool) for asin in asins],
                    "rowCount": len(asins),
                    "finalAuthority": False,
                }
            elif parsed.path == "/api/v1/calls/reserve":
                if not isinstance(payload, dict):
                    raise BridgeError("reservation body must be an object")
                tool = str(payload.get("tool") or "")
                if tool not in self.server.bridge.policy["tools"]:
                    raise BridgeError("unknown MCP tool")
                result = self.server.bridge.ledger.reserve(
                    tool=tool,
                    request_hash=str(payload.get("requestHash") or ""),
                    asin_count=int(payload.get("asinCount") or 0),
                    calls=int(payload.get("calls") or 1),
                    pool=str(payload.get("pool") or "primary"),
                    allow_emergency=payload.get("allowEmergency") is True,
                )
            elif parsed.path == "/api/v1/calls/reserve-plan":
                if not isinstance(payload, dict):
                    raise BridgeError("plan reservation body must be an object")
                result = self.server.bridge.ledger.reserve_plan(
                    plan_id=str(payload.get("planId") or ""),
                    requests=payload.get("requests"),
                    allow_emergency=payload.get("allowEmergency") is True,
                    seal_run=payload.get("sealRun", False),
                )
            elif parsed.path == "/api/v1/calls/status":
                if not isinstance(payload, dict):
                    raise BridgeError("plan status body must be an object")
                result = self.server.bridge.ledger.mark_plan_status(
                    plan_id=str(payload.get("planId") or ""),
                    status=str(payload.get("status") or ""),
                    details=payload.get("details"),
                )
            elif parsed.path == "/api/v1/calls/claim":
                if not isinstance(payload, dict):
                    raise BridgeError("plan claim body must be an object")
                result = self.server.bridge.ledger.claim_plan_request(
                    plan_id=str(payload.get("planId") or ""),
                    request_id=str(payload.get("requestId") or ""),
                    claim_id=str(payload.get("claimId") or ""),
                )
            elif parsed.path == "/api/v1/audit/events":
                result = self.server.bridge.audit.append(payload)
            else:
                raise BridgeError("endpoint not found", status=404, stage="routing")
            self._send_json(
                200,
                {
                    "schemaVersion": RESPONSE_SCHEMA,
                    "ok": True,
                    "result": result,
                    "finalAuthority": False,
                },
            )
        except (TypeError, ValueError):
            self._error(BridgeError("request contains invalid numeric values", stage="request"))
        except BridgeError as error:
            self._error(error)
        except Exception as error:
            self._error(BridgeError(f"internal bridge error: {error}", status=500, stage="internal"))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the loopback-only SellerSprite MCP shadow bridge.")
    parser.add_argument("--project-root", type=Path, default=DEFAULT_PROJECT_ROOT)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--policy", type=Path, default=DEFAULT_PROJECT_ROOT / "config" / "mcp_hybrid_policy.json")
    parser.add_argument("--run-budget", type=int, default=None)
    parser.add_argument("--token", default="")
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--test-mode", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    project_root = args.project_root.resolve()
    token = args.token or secrets.token_urlsafe(24)
    config = BridgeConfig(
        project_root=project_root,
        output_root=args.output_root.resolve(),
        run_id=str(args.run_id),
        token=token,
        policy_path=args.policy.resolve(),
        run_budget=args.run_budget,
        test_mode=args.test_mode,
    )
    bridge = McpHybridBridge(config)
    server = BridgeHttpServer(("127.0.0.1", args.port), BridgeHandler)
    server.bridge = bridge
    print(f"SellerSprite MCP Hybrid Bridge {BRIDGE_VERSION} started in SHADOW mode")
    print(f"Service URL: http://127.0.0.1:{args.port}")
    print(f"Session token: {token}")
    print(f"runId: {config.run_id}; runBudget: {bridge.ledger.run_budget}")
    print(f"testMode: {config.test_mode}; daily quota: 300 primary + 100 conditional + 100 emergency")
    print("Outbound MCP is disabled. Evidence is non-authoritative and must be imported offline.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nMCP Hybrid Bridge stopped")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
