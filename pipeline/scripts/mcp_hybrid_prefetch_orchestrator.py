#!/usr/bin/env python3
"""Build and reconcile durable, non-authoritative MCP prefetch workflows.

This module deliberately does not contain an MCP client or read any Codex
credential. An external Codex task executes the declared packets and records a
hash-only result envelope here. The existing browser/replay acceptance path
remains the only final authority.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import secrets
import sys
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_SCHEMA = "sellerSpriteMcpPrefetchWorkflow/v1"
CANDIDATE_SCHEMA = "sellerSpriteMcpPrefilteredCandidates/v1"
PACKET_SCHEMA = "sellerSpriteMcpWorkflowPacket/v1"
PACKET_RESULT_SCHEMA = "sellerSpriteMcpPacketResult/v1"
BUNDLE_SCHEMA = "sellerSpriteMcpEvidenceBundle/v1"
EVIDENCE_SCHEMA = "sellerSpriteMcpEvidence/v1"
VALIDATION_TASK_SCHEMA = "sellerSpriteMcpValidationTask/v1"
VALIDATION_TASK_REQUEST_SCHEMA = "sellerSpriteMcpValidationTaskRequest/v1"
VALIDATION_TASK_RESULT_SCHEMA = "sellerSpriteMcpValidationTaskResult/v1"
VALIDATION_TASK_FINAL_SUMMARY_SCHEMA = "sellerSpriteMcpValidationTaskFinalSummary/v1"
SHADOW_PLAN_SCHEMA = "sellerSpriteMcpShadowPlan/v1"
ASIN_RE = re.compile(r"^B0[A-Z0-9]{8}$")
SHA256_RE = re.compile(r"^[a-fA-F0-9]{64}$")
SAFE_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,160}$")
PLACEHOLDER_RE = re.compile(r"__[A-Z0-9_]+__")
TERMINAL_PACKET_STATUSES = {"succeeded", "partial", "failed"}
HARD_DAILY_LIMIT = 500
MAX_PRIMARY_CALLS = 300
VALIDATION_SAMPLE_SIZE = 30
VALIDATION_TASK_BUDGET = 100
VALIDATION_AUTHORIZED_CALLS = 91
VALIDATION_RUN_PREFIX = "mcp-validate-task-"
VALIDATION_TOOLS = ("asin_detail", "asin_sales_trend", "traffic_listing_stat")
MAX_VALIDATION_RAW_RESPONSE_BYTES = 50 * 1024 * 1024

DETAIL_FIELDS = (
    "title",
    "brand",
    "price",
    "rating",
    "reviews",
    "variations",
    "imageUrl",
    "categoryPath",
    "dimensions",
    "packageDimensions",
    "itemWeight",
    "packageWeight",
    "parentAsin",
)

SALES_TREND_FIELDS = (
    "priceTrendClass",
    "pricePointCount",
)

TRAFFIC_LISTING_STAT_FIELDS = (
    "freeTrafficCount",
    "paidTrafficCount",
    "freeTrafficShare",
    "paidTrafficShare",
    "relationCounts",
)

KEEPA_FIELDS = (
    "title",
    "brand",
    "price",
    "rating",
    "reviews",
    "variations",
    "imageUrl",
    "categoryPath",
    "dimensions",
    "packageDimensions",
    "itemWeight",
    "packageWeight",
    "parentAsin",
    "priceTrendClass",
    "pricePointCount",
)

TOOL_ROUTES: dict[str, dict[str, Any]] = {
    "keepa_info": {
        "state": "validated_shadow",
        "reservationEligible": True,
        "ttlHours": 6,
        "fields": KEEPA_FIELDS,
    },
    "asin_detail": {
        "state": "pending",
        "reservationEligible": False,
        "ttlHours": 6,
        "fields": DETAIL_FIELDS,
    },
    "asin_sales_trend": {
        "state": "pending",
        "reservationEligible": False,
        "ttlHours": 6,
        "fields": SALES_TREND_FIELDS,
    },
    "traffic_listing_stat": {
        "state": "pending",
        "reservationEligible": False,
        "ttlHours": 24,
        "fields": TRAFFIC_LISTING_STAT_FIELDS,
    },
    "product_research": {
        "state": "discovery_only",
        "reservationEligible": False,
        "reason": "candidate prefetch cannot synthesize product_research discovery pages",
        "ttlHours": 6,
        "fields": (),
    },
    "competitor_lookup": {
        "state": "disabled",
        "reservationEligible": False,
        "reason": "exact ASIN binding contract is not validated",
        "fields": (),
    },
    "traffic_extend": {
        "state": "disabled",
        "reservationEligible": False,
        "reason": "does not provide strict Gate C weekly natural-share evidence",
        "fields": (),
    },
}

_WORKFLOW_LOCKS: dict[str, threading.RLock] = {}
_WORKFLOW_LOCKS_GUARD = threading.Lock()


class OrchestratorError(ValueError):
    """Structured fail-closed error raised by the offline orchestrator."""

    def __init__(self, code: str, message: str, *, details: Any = None) -> None:
        super().__init__(message)
        self.code = code
        self.details = details


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def iso_z(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def now_iso() -> str:
    return iso_z(now_utc())


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


def atomic_write_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{secrets.token_hex(6)}.tmp")
    try:
        temporary.write_bytes(payload)
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _workflow_process_lock(path: Path) -> threading.RLock:
    key = os.path.normcase(str(path.resolve()))
    with _WORKFLOW_LOCKS_GUARD:
        lock = _WORKFLOW_LOCKS.get(key)
        if lock is None:
            lock = threading.RLock()
            _WORKFLOW_LOCKS[key] = lock
        return lock


@contextmanager
def workflow_file_lock(path: Path) -> Iterator[None]:
    """Serialize workflow read-modify-write operations across processes."""

    lock_path = path.with_name(f"{path.name}.lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with _workflow_process_lock(lock_path):
        handle = lock_path.open("a+b")
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
            else:  # pragma: no cover - non-Windows CI only
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                handle.seek(0)
                if os.name == "nt":
                    import msvcrt

                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:  # pragma: no cover - non-Windows CI only
                    import fcntl

                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()


def require_object(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise OrchestratorError("invalid_schema", f"{field} must be an object")
    return value


def require_integer(value: Any, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise OrchestratorError("invalid_schema", f"{field} must be an integer")
    return value


def require_false(value: Any, field: str) -> None:
    if value is not False:
        raise OrchestratorError("authority_violation", f"{field} must be false")


def reject_embedded_authority_claims(value: Any, field: str = "payload") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if key in {"finalAuthority", "usableForFinal"} and child is not False:
                raise OrchestratorError("authority_violation", f"{field}.{key} must be false")
            reject_embedded_authority_claims(child, f"{field}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            reject_embedded_authority_claims(child, f"{field}[{index}]")


def require_sha256(value: Any, field: str) -> str:
    text = str(value or "").strip().lower()
    if not SHA256_RE.fullmatch(text):
        raise OrchestratorError("invalid_hash", f"{field} must be a SHA-256 hex digest")
    return text


def require_safe_id(value: Any, field: str) -> str:
    text = str(value or "").strip()
    if not SAFE_ID_RE.fullmatch(text):
        raise OrchestratorError("invalid_id", f"{field} must contain only safe identifier characters")
    return text


def normalize_asin(value: Any, field: str = "asin") -> str:
    text = str(value or "").strip().upper()
    if not ASIN_RE.fullmatch(text):
        raise OrchestratorError("invalid_asin", f"{field} must be a valid Amazon ASIN")
    return text


def parse_timestamp(value: Any, field: str) -> datetime:
    text = str(value or "").strip()
    if not text:
        raise OrchestratorError("invalid_timestamp", f"{field} is required")
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as error:
        raise OrchestratorError("invalid_timestamp", f"{field} must be ISO-8601") from error
    if parsed.tzinfo is None:
        raise OrchestratorError("invalid_timestamp", f"{field} must include a timezone")
    return parsed.astimezone(timezone.utc)


def validate_source_provenance(value: Any, field: str) -> dict[str, Any]:
    source = require_object(value, field)
    source_id = require_safe_id(source.get("sourceId"), f"{field}.sourceId")
    source_path = str(source.get("sourcePath") or "").strip()
    if not source_path or len(source_path) > 2048:
        raise OrchestratorError("missing_provenance", f"{field}.sourcePath is required")
    source_hash = require_sha256(source.get("sourceSha256"), f"{field}.sourceSha256")
    normalized: dict[str, Any] = {
        "sourceId": source_id,
        "sourcePath": source_path,
        "sourceSha256": source_hash,
    }
    if source.get("capturedAt") is not None:
        normalized["capturedAt"] = iso_z(parse_timestamp(source.get("capturedAt"), f"{field}.capturedAt"))
    return normalized


def validate_candidate_document(payload: Any) -> dict[str, Any]:
    document = require_object(payload, "candidate document")
    if document.get("schemaVersion") != CANDIDATE_SCHEMA:
        raise OrchestratorError("invalid_schema", f"candidate document must use {CANDIDATE_SCHEMA}")
    if document.get("marketplace") != "US":
        raise OrchestratorError("marketplace_mismatch", "candidate document must be US marketplace")
    require_false(document.get("finalAuthority"), "candidate document finalAuthority")
    run_id = require_safe_id(document.get("runId"), "runId")
    generated_at = iso_z(parse_timestamp(document.get("generatedAt"), "generatedAt"))
    source = validate_source_provenance(document.get("sourceProvenance"), "sourceProvenance")
    rows = document.get("candidates")
    if not isinstance(rows, list) or not rows or len(rows) > HARD_DAILY_LIMIT:
        raise OrchestratorError("invalid_candidates", f"candidates must contain 1-{HARD_DAILY_LIMIT} rows")
    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, raw in enumerate(rows):
        row = require_object(raw, f"candidates[{index}]")
        asin = normalize_asin(row.get("asin"), f"candidates[{index}].asin")
        if asin in seen:
            raise OrchestratorError("duplicate_asin", f"duplicate candidate ASIN: {asin}")
        seen.add(asin)
        if row.get("prefilterStatus") != "pass":
            raise OrchestratorError(
                "prefilter_not_passed",
                f"{asin} lacks an explicit prefilterStatus=pass proof",
            )
        provenance = validate_source_provenance(
            row.get("sourceProvenance"), f"candidates[{index}].sourceProvenance"
        )
        candidates.append(
            {
                "asin": asin,
                "prefilterStatus": "pass",
                "sourceProvenance": provenance,
            }
        )
    return {
        "schemaVersion": CANDIDATE_SCHEMA,
        "runId": run_id,
        "marketplace": "US",
        "generatedAt": generated_at,
        "sourceProvenance": source,
        "candidates": candidates,
        "finalAuthority": False,
    }


def resolve_tool(tool: str, *, allow_pending: bool = False, for_reservation: bool = False) -> dict[str, Any]:
    route = TOOL_ROUTES.get(str(tool or ""))
    if route is None:
        raise OrchestratorError("unknown_tool", f"unknown MCP tool: {tool}")
    if route["state"] == "discovery_only":
        raise OrchestratorError(
            "tool_requires_discovery_planner",
            f"{tool} requires a dedicated discovery workflow and cannot use candidate-prefetch packets",
        )
    if route["state"] == "disabled":
        raise OrchestratorError("tool_disabled", f"{tool} is disabled: {route['reason']}")
    if route["state"] != "validated_shadow" and not allow_pending:
        raise OrchestratorError("tool_pending", f"{tool} is pending provider-contract validation")
    if for_reservation and not route["reservationEligible"]:
        raise OrchestratorError("tool_not_reservable", f"{tool} cannot be formally reserved")
    return route


def tool_request(tool: str, asin: str) -> dict[str, Any]:
    if tool == "keepa_info":
        return {
            "marketplace": "US",
            "asin": asin,
            "dailyLatest": True,
            "returnFields": ",".join(("asin",) + KEEPA_FIELDS),
        }
    if tool == "asin_detail":
        return {
            "marketplace": "US",
            "asin": asin,
            "returnFields": ",".join(("asin",) + DETAIL_FIELDS),
        }
    if tool in {"asin_sales_trend", "traffic_listing_stat"}:
        return {"marketplace": "US", "asin": asin}
    raise OrchestratorError("tool_request_unsupported", f"no executable MCP request contract for {tool}")


def validate_shadow_sample_plan(value: Any) -> dict[str, Any]:
    document = require_object(value, "shadow sample plan")
    if document.get("schemaVersion") != SHADOW_PLAN_SCHEMA:
        raise OrchestratorError("invalid_schema", f"shadow sample plan must use {SHADOW_PLAN_SCHEMA}")
    if document.get("marketplace") != "US":
        raise OrchestratorError("marketplace_mismatch", "shadow sample plan must be US marketplace")
    plan_id = require_safe_id(document.get("planId"), "shadow sample plan.planId")
    rows = document.get("sample")
    if not isinstance(rows, list) or len(rows) != VALIDATION_SAMPLE_SIZE:
        raise OrchestratorError(
            "invalid_validation_sample",
            f"validation task requires exactly {VALIDATION_SAMPLE_SIZE} real-browser ASINs",
        )
    sample: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, raw in enumerate(rows):
        row = require_object(raw, f"sample[{index}]")
        asin = normalize_asin(row.get("asin"), f"sample[{index}].asin")
        if asin in seen:
            raise OrchestratorError("duplicate_asin", f"duplicate validation ASIN: {asin}")
        seen.add(asin)
        outcome = str(row.get("expectedOutcome") or "")
        if outcome not in {"pass", "reject"}:
            raise OrchestratorError("invalid_validation_sample", f"{asin} lacks pass/reject browser outcome")
        source_class = require_safe_id(row.get("sourceClass"), f"sample[{index}].sourceClass")
        source_root = str(row.get("sourceRoot") or "").strip()
        if not source_root or len(source_root) > 2048:
            raise OrchestratorError("missing_provenance", f"sample[{index}].sourceRoot is required")
        sample.append(
            {
                "asin": asin,
                "expectedOutcome": outcome,
                "sourceClass": source_class,
                "sourceRoot": source_root,
            }
        )
    return {
        "schemaVersion": SHADOW_PLAN_SCHEMA,
        "planId": plan_id,
        "marketplace": "US",
        "sample": sample,
    }


def validate_product_research_request(value: Any) -> dict[str, Any]:
    outer = require_object(value, "product_research request")
    if set(outer) != {"request"}:
        raise OrchestratorError(
            "invalid_discovery_request",
            "product_research arguments must contain exactly one request object",
        )
    request = require_object(outer.get("request"), "product_research request.request")
    if request.get("marketplace") != "US" or len(request) < 2:
        raise OrchestratorError(
            "invalid_discovery_request",
            "product_research request must be US-only and include explicit discovery criteria",
        )
    if any(PLACEHOLDER_RE.search(text) for text in _iter_string_values(request)):
        raise OrchestratorError("invalid_discovery_request", "product_research request contains a placeholder")
    reject_embedded_authority_claims(outer, "product_research request")
    return {"request": request}


def _iter_string_values(value: Any) -> Iterator[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for child in value.values():
            yield from _iter_string_values(child)
    elif isinstance(value, list):
        for child in value:
            yield from _iter_string_values(child)


def _validation_task_request(
    *,
    task_id: str,
    run_id: str,
    tool: str,
    request: dict[str, Any],
    target_asin: str | None,
    source_evidence: dict[str, Any],
    created_at: str,
) -> dict[str, Any]:
    request_id_suffix = target_asin or "001"
    request_id = f"task-{tool.replace('_', '-')}-{request_id_suffix}"
    return {
        "schemaVersion": VALIDATION_TASK_REQUEST_SCHEMA,
        "requestId": request_id,
        "taskId": task_id,
        "runId": run_id,
        "marketplace": "US",
        "mode": "shadow_test",
        "finalAuthority": False,
        "targetAsin": target_asin,
        "tool": tool,
        "toolContractState": "discovery_only" if tool == "product_research" else "pending",
        "pool": "primary",
        "calls": 1,
        "request": request,
        "requestHash": payload_sha256(request),
        "sourceEvidence": source_evidence,
        "status": "planned",
        "attemptPolicy": {"maxAttempts": 1, "automaticRetry": False},
        "attemptsStarted": 0,
        "attemptsRecorded": 0,
        "createdAt": created_at,
    }


def plan_validation_task(
    sample_payload: Any,
    *,
    sample_sha256: str,
    discovery_request: Any,
    run_id: str,
    created_at: datetime | None = None,
) -> dict[str, Any]:
    sample_plan = validate_shadow_sample_plan(sample_payload)
    sample_hash = require_sha256(sample_sha256, "sampleSha256")
    normalized_discovery = validate_product_research_request(discovery_request)
    normalized_run_id = require_safe_id(run_id, "runId")
    if not normalized_run_id.startswith(VALIDATION_RUN_PREFIX):
        raise OrchestratorError(
            "run_isolation_required",
            f"validation task runId must start with {VALIDATION_RUN_PREFIX}",
        )
    timestamp = iso_z(created_at or now_utc())
    task_seed = {
        "runId": normalized_run_id,
        "sampleSha256": sample_hash,
        "discoveryRequestHash": payload_sha256(normalized_discovery),
        "taskBudget": VALIDATION_TASK_BUDGET,
        "authorizedCalls": VALIDATION_AUTHORIZED_CALLS,
    }
    task_id = f"validation-{payload_sha256(task_seed)[:24]}"
    requests = [
        _validation_task_request(
            task_id=task_id,
            run_id=normalized_run_id,
            tool="product_research",
            request=normalized_discovery,
            target_asin=None,
            source_evidence={"samplePlanId": sample_plan["planId"], "samplePlanSha256": sample_hash},
            created_at=timestamp,
        )
    ]
    for tool in VALIDATION_TOOLS:
        for row in sample_plan["sample"]:
            requests.append(
                _validation_task_request(
                    task_id=task_id,
                    run_id=normalized_run_id,
                    tool=tool,
                    request=tool_request(tool, row["asin"]),
                    target_asin=row["asin"],
                    source_evidence=row,
                    created_at=timestamp,
                )
            )
    task = {
        "schemaVersion": VALIDATION_TASK_SCHEMA,
        "taskId": task_id,
        "runId": normalized_run_id,
        "marketplace": "US",
        "mode": "shadow_test",
        "testModeRequired": True,
        "finalAuthority": False,
        "outboundMcpClientIncluded": False,
        "createdAt": timestamp,
        "updatedAt": timestamp,
        "status": "planned",
        "source": {
            "samplePlanId": sample_plan["planId"],
            "samplePlanSha256": sample_hash,
            "sampleAsins": [row["asin"] for row in sample_plan["sample"]],
        },
        "isolation": {
            "runNamespace": VALIDATION_RUN_PREFIX,
            "dedicatedBridgeRequired": True,
            "legacyRunBudget": 50,
            "legacyRunReuseForbidden": True,
            "sharedQuotaLedgerRequired": True,
        },
        "storage": {"rawResponseDirectory": "raw_responses"},
        "budget": {
            "taskBudget": VALIDATION_TASK_BUDGET,
            "authorizedCalls": VALIDATION_AUTHORIZED_CALLS,
            "plannedCalls": len(requests),
            "sealedReserveCalls": VALIDATION_TASK_BUDGET - len(requests),
            "plannedByTool": {
                "product_research": 1,
                "asin_detail": VALIDATION_SAMPLE_SIZE,
                "asin_sales_trend": VALIDATION_SAMPLE_SIZE,
                "traffic_listing_stat": VALIDATION_SAMPLE_SIZE,
            },
            "plannedByPool": {"primary": len(requests), "conditional": 0, "emergency": 0},
        },
        "reservation": None,
        "finalization": None,
        "requests": requests,
        "history": [{"at": timestamp, "event": "planned", "requestCount": len(requests)}],
    }
    return validate_validation_task(task)


def validate_validation_task_claim(
    value: Any,
    *,
    task_id: str,
    run_id: str,
    request_id: str,
    request_hash: str,
    tool: str,
    field: str,
) -> dict[str, Any]:
    claim = require_object(value, field)
    claim_id = require_safe_id(claim.get("claimId"), f"{field}.claimId")
    require_safe_id(claim.get("executorId"), f"{field}.executorId")
    require_sha256(claim.get("tokenSha256"), f"{field}.tokenSha256")
    claimed_at = iso_z(parse_timestamp(claim.get("claimedAt"), f"{field}.claimedAt"))
    if claim.get("automaticRetry") is not False or claim.get("finalAuthority") is not False:
        raise OrchestratorError("retry_forbidden", "validation claim must remain non-authoritative and non-retryable")
    receipt = require_object(claim.get("bridgeReceipt"), f"{field}.bridgeReceipt")
    event = require_object(receipt.get("event"), f"{field}.bridgeReceipt.event")
    if (
        receipt.get("executionAllowed") is not True
        or receipt.get("idempotent") is not False
        or receipt.get("finalAuthority") is not False
        or event.get("eventType") != "claimed"
        or event.get("runId") != run_id
        or event.get("planId") != task_id
        or event.get("requestId") != request_id
        or event.get("claimId") != claim_id
        or event.get("requestHash") != request_hash
        or event.get("tool") != tool
        or event.get("executionAllowed") is not True
        or event.get("automaticRetry") is not False
        or event.get("finalAuthority") is not False
        or iso_z(parse_timestamp(event.get("at"), f"{field}.bridgeReceipt.event.at")) != claimed_at
    ):
        raise OrchestratorError("claim_mismatch", "stored Bridge claim receipt does not match the validation request")
    return claim


def validate_validation_task(value: Any) -> dict[str, Any]:
    task = require_object(value, "validation task")
    if task.get("schemaVersion") != VALIDATION_TASK_SCHEMA:
        raise OrchestratorError("invalid_schema", f"validation task must use {VALIDATION_TASK_SCHEMA}")
    require_false(task.get("finalAuthority"), "validation task.finalAuthority")
    reject_embedded_authority_claims(task, "validation task")
    if (
        task.get("marketplace") != "US"
        or task.get("mode") != "shadow_test"
        or task.get("testModeRequired") is not True
        or task.get("outboundMcpClientIncluded") is not False
    ):
        raise OrchestratorError("invalid_validation_task", "validation task must remain US-only shadow test mode")
    task_id = require_safe_id(task.get("taskId"), "taskId")
    run_id = require_safe_id(task.get("runId"), "runId")
    if not run_id.startswith(VALIDATION_RUN_PREFIX):
        raise OrchestratorError("run_isolation_required", "validation task cannot reuse a legacy run namespace")
    source = require_object(task.get("source"), "source")
    require_safe_id(source.get("samplePlanId"), "source.samplePlanId")
    require_sha256(source.get("samplePlanSha256"), "source.samplePlanSha256")
    sample_asins = source.get("sampleAsins")
    if not isinstance(sample_asins, list) or len(sample_asins) != VALIDATION_SAMPLE_SIZE:
        raise OrchestratorError("invalid_validation_sample", "validation task must retain exactly 30 sample ASINs")
    normalized_asins = [normalize_asin(asin, "source.sampleAsins") for asin in sample_asins]
    if len(set(normalized_asins)) != VALIDATION_SAMPLE_SIZE:
        raise OrchestratorError("duplicate_asin", "validation task sample ASINs must be unique")
    isolation = require_object(task.get("isolation"), "isolation")
    if isolation != {
        "runNamespace": VALIDATION_RUN_PREFIX,
        "dedicatedBridgeRequired": True,
        "legacyRunBudget": 50,
        "legacyRunReuseForbidden": True,
        "sharedQuotaLedgerRequired": True,
    }:
        raise OrchestratorError("run_isolation_required", "validation task isolation contract changed")
    if task.get("storage") != {"rawResponseDirectory": "raw_responses"}:
        raise OrchestratorError("invalid_validation_task", "validation task raw response storage contract changed")
    budget = require_object(task.get("budget"), "budget")
    expected_by_tool = {
        "product_research": 1,
        "asin_detail": VALIDATION_SAMPLE_SIZE,
        "asin_sales_trend": VALIDATION_SAMPLE_SIZE,
        "traffic_listing_stat": VALIDATION_SAMPLE_SIZE,
    }
    if (
        int(budget.get("taskBudget") or 0) != VALIDATION_TASK_BUDGET
        or int(budget.get("authorizedCalls") or 0) != VALIDATION_AUTHORIZED_CALLS
        or int(budget.get("plannedCalls") or 0) != VALIDATION_AUTHORIZED_CALLS
        or int(budget.get("sealedReserveCalls") or -1)
        != VALIDATION_TASK_BUDGET - VALIDATION_AUTHORIZED_CALLS
        or budget.get("plannedByTool") != expected_by_tool
        or budget.get("plannedByPool")
        != {"primary": VALIDATION_AUTHORIZED_CALLS, "conditional": 0, "emergency": 0}
    ):
        raise OrchestratorError("invalid_task_budget", "validation task must remain sealed at 91 of 100 calls")
    requests = task.get("requests")
    if not isinstance(requests, list) or len(requests) != VALIDATION_AUTHORIZED_CALLS:
        raise OrchestratorError("invalid_task_budget", "validation task must contain exactly 91 requests")
    request_ids: set[str] = set()
    asins_by_tool = {tool: set() for tool in VALIDATION_TOOLS}
    tool_counts = {tool: 0 for tool in expected_by_tool}
    claimed_count = 0
    terminal_count = 0
    outcome_counts = {status: 0 for status in TERMINAL_PACKET_STATUSES}
    for index, raw in enumerate(requests):
        item = require_object(raw, f"requests[{index}]")
        if item.get("schemaVersion") != VALIDATION_TASK_REQUEST_SCHEMA:
            raise OrchestratorError("invalid_schema", "validation task request schema mismatch")
        require_false(item.get("finalAuthority"), f"requests[{index}].finalAuthority")
        request_id = require_safe_id(item.get("requestId"), f"requests[{index}].requestId")
        if request_id in request_ids:
            raise OrchestratorError("duplicate_packet", "validation task request IDs must be unique")
        request_ids.add(request_id)
        if item.get("taskId") != task_id or item.get("runId") != run_id:
            raise OrchestratorError("invalid_validation_task", "request taskId or runId mismatch")
        if item.get("marketplace") != "US" or item.get("mode") != "shadow_test":
            raise OrchestratorError("invalid_validation_task", "request must remain US shadow test mode")
        tool = str(item.get("tool") or "")
        if tool not in expected_by_tool:
            raise OrchestratorError("unknown_tool", f"unexpected validation task tool: {tool}")
        tool_counts[tool] += 1
        if item.get("pool") != "primary" or item.get("calls") != 1:
            raise OrchestratorError("invalid_task_budget", "every validation request must consume one primary call")
        if item.get("attemptPolicy") != {"maxAttempts": 1, "automaticRetry": False}:
            raise OrchestratorError("retry_forbidden", "validation requests allow exactly one attempt")
        request = require_object(item.get("request"), f"requests[{index}].request")
        if require_sha256(item.get("requestHash"), f"requests[{index}].requestHash") != payload_sha256(request):
            raise OrchestratorError("request_hash_mismatch", "validation request hash failed integrity validation")
        if tool == "product_research":
            if item.get("targetAsin") is not None or item.get("toolContractState") != "discovery_only":
                raise OrchestratorError("invalid_discovery_request", "discovery request cannot bind an ASIN")
            if validate_product_research_request(request) != request:
                raise OrchestratorError("invalid_discovery_request", "discovery request is not canonical")
        else:
            asin = normalize_asin(item.get("targetAsin"), f"requests[{index}].targetAsin")
            if item.get("toolContractState") != "pending" or request != tool_request(tool, asin):
                raise OrchestratorError("request_contract_mismatch", "ASIN request contract changed")
            if asin in asins_by_tool[tool]:
                raise OrchestratorError("duplicate_packet", f"duplicate {tool} request for {asin}")
            asins_by_tool[tool].add(asin)
        status = str(item.get("status") or "")
        attempts_started = int(item.get("attemptsStarted") or 0)
        attempts_recorded = int(item.get("attemptsRecorded") or 0)
        claim = item.get("claim")
        if status == "planned":
            if (
                attempts_started != 0
                or attempts_recorded != 0
                or claim is not None
                or item.get("result") is not None
                or item.get("rawResponseArchive") is not None
            ):
                raise OrchestratorError("invalid_validation_task", "planned request cannot contain claim state")
        elif status == "claimed":
            if (
                attempts_started != 1
                or attempts_recorded != 0
                or not isinstance(claim, dict)
                or item.get("result") is not None
                or item.get("rawResponseArchive") is not None
            ):
                raise OrchestratorError("invalid_validation_task", "claimed request must retain one attempt")
            validate_validation_task_claim(
                claim,
                task_id=task_id,
                run_id=run_id,
                request_id=request_id,
                request_hash=item["requestHash"],
                tool=tool,
                field=f"requests[{index}].claim",
            )
            claimed_count += 1
        elif status in TERMINAL_PACKET_STATUSES:
            if attempts_started != 1 or attempts_recorded != 1 or not isinstance(claim, dict):
                raise OrchestratorError("invalid_validation_task", "terminal request must retain exactly one attempt")
            validate_validation_task_claim(
                claim,
                task_id=task_id,
                run_id=run_id,
                request_id=request_id,
                request_hash=item["requestHash"],
                tool=tool,
                field=f"requests[{index}].claim",
            )
            result_hash = require_sha256(item.get("resultSha256"), f"requests[{index}].resultSha256")
            stored_result = require_object(item.get("result"), f"requests[{index}].result")
            normalized_result = validate_validation_task_result(stored_result, item, task)
            if (
                normalized_result != stored_result
                or normalized_result["status"] != status
                or payload_sha256(normalized_result) != result_hash
            ):
                raise OrchestratorError("result_integrity", "validation result failed canonical integrity validation")
            archive = require_object(item.get("rawResponseArchive"), f"requests[{index}].rawResponseArchive")
            archive_path = str(archive.get("path") or "").strip()
            if not archive_path or len(archive_path) > 4096:
                raise OrchestratorError("raw_response_missing", "terminal request lacks an immutable raw response path")
            if (
                require_sha256(archive.get("sha256"), f"requests[{index}].rawResponseArchive.sha256")
                != normalized_result["rawResponse"]["sha256"]
                or int(archive.get("byteLength") or -1) != normalized_result["rawResponse"]["byteLength"]
            ):
                raise OrchestratorError("raw_response_mismatch", "raw response archive metadata does not match result")
            recorded_at = parse_timestamp(item.get("recordedAt"), f"requests[{index}].recordedAt")
            if recorded_at < parse_timestamp(normalized_result["completedAt"], "result.completedAt"):
                raise OrchestratorError("invalid_timestamp", "recordedAt cannot precede completedAt")
            terminal_count += 1
            outcome_counts[status] += 1
        else:
            raise OrchestratorError("invalid_validation_task", f"invalid request status: {status}")
    if tool_counts != expected_by_tool:
        raise OrchestratorError("invalid_task_budget", "validation task tool counts changed")
    expected_asins = set(normalized_asins)
    if any(asins_by_tool[tool] != expected_asins for tool in VALIDATION_TOOLS):
        raise OrchestratorError("invalid_validation_sample", "each ASIN must have all three validation requests")
    reservation = task.get("reservation")
    finalization = task.get("finalization")
    if reservation is None:
        if claimed_count or terminal_count or finalization is not None or task.get("status") != "planned":
            raise OrchestratorError("reservation_required", "claims require an attached sealed reservation")
    else:
        reservation_object = require_object(reservation, "reservation")
        if reservation_object.get("status") != "reserved":
            raise OrchestratorError("invalid_validation_task", "validation task reservation must remain reserved")
        if terminal_count == VALIDATION_AUTHORIZED_CALLS:
            if finalization is None:
                expected_status = "ready_to_finalize"
            else:
                finalization_object = require_object(finalization, "finalization")
                require_false(finalization_object.get("finalAuthority"), "finalization.finalAuthority")
                require_false(finalization_object.get("usableForFinal"), "finalization.usableForFinal")
                parse_timestamp(finalization_object.get("at"), "finalization.at")
                require_sha256(finalization_object.get("summarySha256"), "finalization.summarySha256")
                manifest_hashes = require_object(finalization_object.get("manifestHashes"), "finalization.manifestHashes")
                for name in ("claimManifestSha256", "resultManifestSha256", "rawManifestSha256"):
                    require_sha256(manifest_hashes.get(name), f"finalization.manifestHashes.{name}")
                expected_manifest_hashes = validation_task_manifest_hashes(
                    task,
                    [
                        {
                            "requestId": item["requestId"],
                            "path": item["rawResponseArchive"]["path"],
                            "sha256": item["rawResponseArchive"]["sha256"],
                            "byteLength": item["rawResponseArchive"]["byteLength"],
                        }
                        for item in task["requests"]
                    ],
                )
                if manifest_hashes != expected_manifest_hashes:
                    raise OrchestratorError("result_integrity", "finalization manifest hashes do not match task results")
                summary_path = str(finalization_object.get("summaryPath") or "").strip()
                if not summary_path or int(finalization_object.get("requestCount") or 0) != VALIDATION_AUTHORIZED_CALLS:
                    raise OrchestratorError("invalid_validation_task", "finalization summary metadata is incomplete")
                ledger_status = "failed" if outcome_counts["failed"] or outcome_counts["partial"] else "succeeded"
                if (
                    finalization_object.get("outcomeCounts") != outcome_counts
                    or finalization_object.get("ledgerStatus") != ledger_status
                    or not isinstance(finalization_object.get("ledgerResult"), dict)
                ):
                    raise OrchestratorError("invalid_validation_task", "finalization outcome or ledger receipt mismatch")
                expected_status = (
                    "finalized_with_failures"
                    if outcome_counts["failed"] or outcome_counts["partial"]
                    else "finalized"
                )
        else:
            if finalization is not None:
                raise OrchestratorError("workflow_incomplete", "validation task cannot finalize before 91 terminal results")
            expected_status = (
                "all_claimed"
                if claimed_count == VALIDATION_AUTHORIZED_CALLS
                else "in_progress"
                if claimed_count or terminal_count
                else "reserved"
            )
        if task.get("status") != expected_status:
            raise OrchestratorError("invalid_validation_task", "task status does not match claim count")
    return task


def _validation_task_reservation_requests_unchecked(task: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "id": item["requestId"],
            "tool": item["tool"],
            "requestHash": item["requestHash"],
            "asinCount": 0 if item["tool"] == "product_research" else 1,
            "calls": 1,
            "pool": "primary",
        }
        for item in task["requests"]
    ]


def validation_task_reservation_requests(task: dict[str, Any]) -> list[dict[str, Any]]:
    validate_validation_task(task)
    return _validation_task_reservation_requests_unchecked(task)


def reserve_validation_task_with_bridge_ledger(ledger: Any, task: dict[str, Any]) -> Any:
    validate_validation_task(task)
    if not bool(getattr(ledger, "test_mode", False)):
        raise OrchestratorError("test_mode_required", "validation task reservation requires Bridge test mode")
    run_budget = getattr(ledger, "run_budget", VALIDATION_TASK_BUDGET)
    if int(run_budget) != VALIDATION_TASK_BUDGET:
        raise OrchestratorError("run_isolation_required", "validation task requires a dedicated runBudget=100 ledger")
    reserve_plan = getattr(ledger, "reserve_plan", None)
    if not callable(reserve_plan):
        raise OrchestratorError("reserve_plan_unavailable", "Bridge ledger lacks atomic sealed plan support")
    try:
        return reserve_plan(
            plan_id=task["taskId"],
            requests=validation_task_reservation_requests(task),
            allow_emergency=False,
            seal_run=True,
        )
    except OrchestratorError:
        raise
    except Exception as error:
        raise OrchestratorError(
            "bridge_reservation_failed",
            str(error),
            details={"stage": getattr(error, "stage", None), "status": getattr(error, "status", None)},
        ) from error


def attach_validation_task_reservation(
    task: dict[str, Any],
    reservation: Any,
    *,
    ledger_path: Path | None = None,
    policy_path: Path | None = None,
    at: datetime | None = None,
) -> dict[str, Any]:
    validate_validation_task(task)
    result = require_object(reservation, "reservation result")
    event = require_object(result.get("event"), "reservation result.event")
    if result.get("idempotent") is not False or result.get("currentStatus") != "reserved":
        raise OrchestratorError("reservation_not_new", "only a new sealed reservation may be attached")
    if (
        event.get("eventType") != "reserved"
        or event.get("runId") != task["runId"]
        or event.get("planId") != task["taskId"]
        or event.get("sealedRun") is not True
        or int(event.get("calls") or 0) != VALIDATION_AUTHORIZED_CALLS
        or int(event.get("authorizedCalls") or 0) != VALIDATION_AUTHORIZED_CALLS
        or int(event.get("taskBudget") or 0) != VALIDATION_TASK_BUDGET
        or int(event.get("sealedReserveCalls") or -1)
        != VALIDATION_TASK_BUDGET - VALIDATION_AUTHORIZED_CALLS
        or event.get("automaticRetry") is not False
        or event.get("requests") != _validation_task_reservation_requests_unchecked(task)
    ):
        raise OrchestratorError("reservation_mismatch", "Bridge sealed reservation differs from validation task")
    timestamp = iso_z(at or now_utc())
    task["reservation"] = {
        "status": "reserved",
        "at": timestamp,
        "result": result,
        "ledgerPath": str(ledger_path.resolve()) if ledger_path else None,
        "policyPath": str(policy_path.resolve()) if policy_path else None,
    }
    task["status"] = "reserved"
    task["updatedAt"] = timestamp
    task["history"].append({"at": timestamp, "event": "reserved", "calls": VALIDATION_AUTHORIZED_CALLS})
    return validate_validation_task(task)


def load_validation_task_ledger(
    bridge_path: Path,
    policy_path: Path,
    ledger_path: Path,
    task: dict[str, Any],
    *,
    test_mode: bool,
) -> Any:
    validate_validation_task(task)
    if test_mode is not True:
        raise OrchestratorError("test_mode_required", "validation task ledger must use explicit test mode")
    spec = importlib.util.spec_from_file_location("mcp_hybrid_bridge_validation_task_adapter", bridge_path)
    if spec is None or spec.loader is None:
        raise OrchestratorError("bridge_unavailable", f"cannot load Bridge module: {bridge_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    policy = module.load_policy(policy_path)
    return module.CallLedger(
        ledger_path,
        run_id=task["runId"],
        policy=policy,
        run_budget=VALIDATION_TASK_BUDGET,
        test_mode=True,
    )


def claim_validation_task_request(
    ledger: Any,
    task: dict[str, Any],
    *,
    request_id: str,
    executor_id: str,
    claim_token: str | None = None,
    at: datetime | None = None,
) -> tuple[dict[str, Any], str]:
    validate_validation_task(task)
    if task.get("reservation") is None:
        raise OrchestratorError("reservation_required", "request claim requires a sealed reservation")
    normalized_request_id = require_safe_id(request_id, "requestId")
    normalized_executor = require_safe_id(executor_id, "executorId")
    item = next((row for row in task["requests"] if row["requestId"] == normalized_request_id), None)
    if item is None:
        raise OrchestratorError("request_not_found", "request is not part of the sealed 91-call task")
    if item.get("status") != "planned" or int(item.get("attemptsStarted") or 0) != 0:
        raise OrchestratorError("attempt_already_started", "validation request cannot be claimed twice")
    token = str(claim_token or secrets.token_hex(32))
    if len(token) < 32 or len(token) > 160 or not SAFE_ID_RE.fullmatch(token):
        raise OrchestratorError("invalid_claim_token", "claim token must be a 32-160 character safe value")
    current = at or now_utc()
    claim_id = f"claim-{payload_sha256({'taskId': task['taskId'], 'requestId': normalized_request_id, 'token': token})[:32]}"
    claimant = getattr(ledger, "claim_plan_request", None)
    if not callable(claimant):
        raise OrchestratorError("claim_unavailable", "Bridge ledger does not expose one-time claims")
    try:
        result = claimant(
            plan_id=task["taskId"],
            request_id=normalized_request_id,
            claim_id=claim_id,
            at=current,
        )
    except OrchestratorError:
        raise
    except Exception as error:
        raise OrchestratorError(
            "bridge_claim_failed",
            str(error),
            details={"stage": getattr(error, "stage", None), "status": getattr(error, "status", None)},
        ) from error
    event = require_object(require_object(result, "claim result").get("event"), "claim result.event")
    if (
        result.get("executionAllowed") is not True
        or result.get("idempotent") is not False
        or result.get("finalAuthority") is not False
        or event.get("planId") != task["taskId"]
        or event.get("requestId") != normalized_request_id
        or event.get("claimId") != claim_id
        or event.get("runId") != task["runId"]
        or event.get("requestHash") != item["requestHash"]
        or event.get("tool") != item["tool"]
        or event.get("automaticRetry") is not False
    ):
        raise OrchestratorError("claim_mismatch", "Bridge claim did not grant the exact sealed request")
    claimed_at = iso_z(parse_timestamp(event.get("at"), "claim event.at"))
    item["status"] = "claimed"
    item["attemptsStarted"] = 1
    item["claim"] = {
        "claimId": claim_id,
        "executorId": normalized_executor,
        "tokenSha256": hashlib.sha256(token.encode("utf-8")).hexdigest(),
        "claimedAt": claimed_at,
        "automaticRetry": False,
        "finalAuthority": False,
        "bridgeReceipt": result,
    }
    claimed_count = sum(row.get("status") == "claimed" for row in task["requests"])
    task["status"] = "all_claimed" if claimed_count == VALIDATION_AUTHORIZED_CALLS else "in_progress"
    task["updatedAt"] = claimed_at
    task["history"].append(
        {"at": claimed_at, "event": "claimed", "requestId": normalized_request_id, "claimId": claim_id}
    )
    return validate_validation_task(task), token


def validation_task_summary(task: dict[str, Any]) -> dict[str, Any]:
    validate_validation_task(task)
    status_counts = {
        status: sum(item.get("status") == status for item in task["requests"])
        for status in ("planned", "claimed", "succeeded", "partial", "failed")
    }
    finalization = task.get("finalization")
    return {
        "schemaVersion": VALIDATION_TASK_SCHEMA,
        "taskId": task["taskId"],
        "runId": task["runId"],
        "status": task["status"],
        "taskBudget": VALIDATION_TASK_BUDGET,
        "authorizedCalls": VALIDATION_AUTHORIZED_CALLS,
        "sealedReserveCalls": VALIDATION_TASK_BUDGET - VALIDATION_AUTHORIZED_CALLS,
        "plannedByTool": task["budget"]["plannedByTool"],
        "requestStatuses": status_counts,
        "claimed": status_counts["claimed"],
        "recorded": status_counts["succeeded"] + status_counts["partial"] + status_counts["failed"],
        "remaining": status_counts["planned"] + status_counts["claimed"],
        "rawResponsesArchived": sum(item.get("rawResponseArchive") is not None for item in task["requests"]),
        "outcomeCounts": {
            status: status_counts[status] for status in ("succeeded", "partial", "failed")
        },
        "finalization": None
        if finalization is None
        else {
            "at": finalization["at"],
            "summaryPath": finalization["summaryPath"],
            "summarySha256": finalization["summarySha256"],
            "ledgerStatus": finalization["ledgerStatus"],
        },
        "finalAuthority": False,
    }


def validation_task_bridge_state(
    ledger: Any,
    task: dict[str, Any],
    *,
    allow_terminal: bool,
) -> dict[str, Any]:
    getter = getattr(ledger, "plan_state", None)
    if not callable(getter):
        raise OrchestratorError("plan_state_unavailable", "Bridge ledger does not expose validation plan state")
    try:
        state = require_object(getter(task["taskId"]), "Bridge validation plan state")
    except OrchestratorError:
        raise
    except Exception as error:
        raise OrchestratorError(
            "bridge_plan_state_failed",
            str(error),
            details={"stage": getattr(error, "stage", None), "status": getattr(error, "status", None)},
        ) from error
    if (
        state.get("runId") != task["runId"]
        or state.get("planId") != task["taskId"]
        or state.get("finalAuthority") is not False
        or state.get("requests") != _validation_task_reservation_requests_unchecked(task)
    ):
        raise OrchestratorError("plan_state_mismatch", "Bridge validation plan differs from the task manifest")
    status = str(state.get("status") or "")
    if status != "reserved" and not (allow_terminal and status in {"succeeded", "failed"}):
        raise OrchestratorError("plan_state_terminal", "validation result cannot be recorded after plan closure")
    return state


def verify_validation_task_bridge_claims(
    ledger: Any,
    task: dict[str, Any],
    *,
    request_id: str | None = None,
    require_all: bool = False,
    allow_terminal: bool = False,
) -> dict[str, Any]:
    state = validation_task_bridge_state(ledger, task, allow_terminal=allow_terminal)
    claim_events = [item for item in state.get("claimEvents") or [] if isinstance(item, dict)]
    local_requests = task["requests"] if require_all else [
        item for item in task["requests"] if item.get("requestId") == request_id
    ]
    if not local_requests:
        raise OrchestratorError("request_not_found", "request is not part of the validation task")
    for item in local_requests:
        claim = require_object(item.get("claim"), f"{item['requestId']}.claim")
        matching = [
            event
            for event in claim_events
            if event.get("requestId") == item["requestId"] and event.get("claimId") == claim.get("claimId")
        ]
        if len(matching) != 1:
            raise OrchestratorError("claim_mismatch", "Bridge does not contain the exact validation request claim")
        event = matching[0]
        if (
            event.get("runId") != task["runId"]
            or event.get("planId") != task["taskId"]
            or event.get("requestHash") != item["requestHash"]
            or event.get("tool") != item["tool"]
            or event.get("executionAllowed") is not True
            or event.get("automaticRetry") is not False
            or event.get("finalAuthority") is not False
            or iso_z(parse_timestamp(event.get("at"), "Bridge claim event.at")) != claim.get("claimedAt")
        ):
            raise OrchestratorError("claim_mismatch", "Bridge claim fields do not match the local validation claim")
    if require_all:
        claimed_ids = [str(event.get("requestId") or "") for event in claim_events]
        expected_ids = [item["requestId"] for item in task["requests"]]
        if (
            len(claimed_ids) != VALIDATION_AUTHORIZED_CALLS
            or len(set(claimed_ids)) != VALIDATION_AUTHORIZED_CALLS
            or set(claimed_ids) != set(expected_ids)
        ):
            raise OrchestratorError("workflow_incomplete", "Bridge must contain all 91 unique claims before finalization")
    return state


def validate_validation_task_result(
    value: Any,
    request_item: dict[str, Any],
    task: dict[str, Any],
) -> dict[str, Any]:
    result = require_object(value, "validation task result")
    reject_embedded_authority_claims(result, "validation task result")
    if result.get("schemaVersion") != VALIDATION_TASK_RESULT_SCHEMA:
        raise OrchestratorError("invalid_schema", f"validation result must use {VALIDATION_TASK_RESULT_SCHEMA}")
    require_false(result.get("finalAuthority"), "validation result.finalAuthority")
    require_false(result.get("usableForFinal"), "validation result.usableForFinal")
    if result.get("taskId") != task["taskId"] or result.get("runId") != task["runId"]:
        raise OrchestratorError("workflow_mismatch", "validation result taskId or runId mismatch")
    if result.get("requestId") != request_item["requestId"]:
        raise OrchestratorError("request_mismatch", "validation result requestId mismatch")
    if require_sha256(result.get("requestHash"), "requestHash") != request_item["requestHash"]:
        raise OrchestratorError("request_hash_mismatch", "validation result requestHash mismatch")
    claim = require_object(request_item.get("claim"), "request claim")
    claim_id = require_safe_id(result.get("claimId"), "claimId")
    if claim_id != claim.get("claimId"):
        raise OrchestratorError("claim_mismatch", "validation result claimId mismatch")
    tool = require_object(result.get("tool"), "tool")
    tool_name = str(tool.get("name") or "")
    tool_version = str(tool.get("version") or "").strip()
    if tool_name != request_item["tool"] or not tool_version:
        raise OrchestratorError("tool_mismatch", "validation result tool name/version mismatch")
    status = str(result.get("status") or "")
    if status not in TERMINAL_PACKET_STATUSES:
        raise OrchestratorError("invalid_status", "validation result must be succeeded, partial, or failed")
    started_at = parse_timestamp(result.get("startedAt"), "startedAt")
    completed_at = parse_timestamp(result.get("completedAt"), "completedAt")
    claimed_at = parse_timestamp(claim.get("claimedAt"), "request claim.claimedAt")
    if started_at < claimed_at:
        raise OrchestratorError("execution_before_claim", "validation execution started before the Bridge claim")
    if completed_at < started_at:
        raise OrchestratorError("invalid_timestamp", "completedAt cannot precede startedAt")
    raw = require_object(result.get("rawResponse"), "rawResponse")
    response_hash = require_sha256(raw.get("sha256"), "rawResponse.sha256")
    byte_length = require_integer(raw.get("byteLength"), "rawResponse.byteLength")
    captured_at = parse_timestamp(raw.get("capturedAt"), "rawResponse.capturedAt")
    if byte_length < 1 or byte_length > MAX_VALIDATION_RAW_RESPONSE_BYTES:
        raise OrchestratorError("raw_response_invalid", "raw response byteLength is outside the allowed range")
    if captured_at < started_at or captured_at > completed_at:
        raise OrchestratorError("invalid_timestamp", "rawResponse.capturedAt must be within the attempt window")
    target = request_item.get("targetAsin")
    result_target = result.get("targetAsin")
    actual_raw = str(result.get("actualAsin") or "").strip()
    if target is None:
        if result_target is not None or actual_raw:
            raise OrchestratorError("asin_mismatch", "product_research result cannot bind a single ASIN")
        normalized_target = None
        normalized_actual = None
    else:
        normalized_target = normalize_asin(result_target, "targetAsin")
        if normalized_target != target:
            raise OrchestratorError("asin_mismatch", "validation result targetAsin mismatch")
        if status == "failed":
            if actual_raw:
                raise OrchestratorError("asin_mismatch", "failed validation result cannot claim an actualAsin")
            normalized_actual = None
        else:
            normalized_actual = normalize_asin(actual_raw, "actualAsin")
            if normalized_actual != target:
                raise OrchestratorError("asin_mismatch", "validation result actualAsin mismatch")
    metadata_value = result.get("responseMetadata")
    metadata = {} if metadata_value is None else require_object(metadata_value, "responseMetadata")
    reject_embedded_authority_claims(metadata, "responseMetadata")
    if status == "failed":
        error = require_object(result.get("error"), "error")
        code = str(error.get("code") or "").strip()
        message = str(error.get("message") or "").strip()
        if not code or not message or error.get("retryable") is not False:
            raise OrchestratorError("invalid_failure", "failed validation result must be explicitly non-retryable")
        normalized_error = {"code": code, "message": message, "retryable": False}
    else:
        if result.get("error") is not None:
            raise OrchestratorError("invalid_status", "successful or partial validation result cannot contain error")
        normalized_error = None
    return {
        "schemaVersion": VALIDATION_TASK_RESULT_SCHEMA,
        "taskId": task["taskId"],
        "runId": task["runId"],
        "requestId": request_item["requestId"],
        "requestHash": request_item["requestHash"],
        "claimId": claim_id,
        "targetAsin": normalized_target,
        "actualAsin": normalized_actual,
        "tool": {"name": tool_name, "version": tool_version},
        "status": status,
        "startedAt": iso_z(started_at),
        "completedAt": iso_z(completed_at),
        "rawResponse": {
            "sha256": response_hash,
            "byteLength": byte_length,
            "capturedAt": iso_z(captured_at),
        },
        "responseMetadata": metadata,
        "error": normalized_error,
        "usableForFinal": False,
        "finalAuthority": False,
    }


def archive_validation_raw_response(
    source_path: Path,
    archive_root: Path,
    *,
    request_id: str,
    expected_sha256: str,
    expected_byte_length: int,
) -> dict[str, Any]:
    if not source_path.is_file():
        raise OrchestratorError("raw_response_missing", f"raw response file not found: {source_path}")
    source_size = source_path.stat().st_size
    if source_size != expected_byte_length or source_size > MAX_VALIDATION_RAW_RESPONSE_BYTES:
        raise OrchestratorError("raw_response_mismatch", "raw response byte length does not match result envelope")
    payload = source_path.read_bytes()
    if len(payload) != source_size:
        raise OrchestratorError("raw_response_mismatch", "raw response byte length does not match result envelope")
    actual_hash = hashlib.sha256(payload).hexdigest()
    if actual_hash != expected_sha256:
        raise OrchestratorError("raw_response_mismatch", "raw response SHA-256 does not match result envelope")
    try:
        json.loads(payload.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise OrchestratorError("raw_response_invalid", "raw response must be valid UTF-8 JSON") from error
    destination = archive_root.resolve() / f"{require_safe_id(request_id, 'requestId')}.{actual_hash}.json"
    if destination.exists():
        if destination.is_symlink():
            raise OrchestratorError("raw_response_conflict", "immutable raw response archive cannot be a symlink")
        if file_sha256(destination) != actual_hash or destination.stat().st_size != expected_byte_length:
            raise OrchestratorError("raw_response_conflict", "immutable raw response archive has conflicting content")
    else:
        atomic_write_bytes(destination, payload)
    return {
        "path": str(destination),
        "sha256": actual_hash,
        "byteLength": expected_byte_length,
        "finalAuthority": False,
    }


def record_validation_task_result(
    ledger: Any,
    task: dict[str, Any],
    result_value: Any,
    *,
    raw_response_path: Path,
    archive_root: Path,
    claim_token: str,
    recorded_at: datetime | None = None,
) -> tuple[dict[str, Any], bool]:
    validate_validation_task(task)
    result_object = require_object(result_value, "validation result")
    request_id = require_safe_id(result_object.get("requestId"), "requestId")
    item = next((row for row in task["requests"] if row["requestId"] == request_id), None)
    if item is None:
        raise OrchestratorError("request_not_found", "validation result request is not part of the task")
    if item.get("status") == "planned":
        raise OrchestratorError("claim_required", "validation result cannot be recorded before Bridge claim")
    claim = require_object(item.get("claim"), "request claim")
    token_hash = hashlib.sha256(str(claim_token or "").encode("utf-8")).hexdigest()
    if token_hash != claim.get("tokenSha256"):
        raise OrchestratorError("claim_token_mismatch", "validation result does not hold the request claim token")
    normalized = validate_validation_task_result(result_object, item, task)
    result_hash = payload_sha256(normalized)
    if item.get("status") in TERMINAL_PACKET_STATUSES:
        if item.get("resultSha256") != result_hash:
            raise OrchestratorError("retry_forbidden", "validation request already has a different terminal result")
        verify_validation_task_bridge_claims(ledger, task, request_id=request_id)
        archived = archive_validation_raw_response(
            raw_response_path,
            archive_root,
            request_id=request_id,
            expected_sha256=normalized["rawResponse"]["sha256"],
            expected_byte_length=normalized["rawResponse"]["byteLength"],
        )
        if archived != item.get("rawResponseArchive"):
            raise OrchestratorError("raw_response_conflict", "idempotent result points to a different raw archive")
        return task, False
    if item.get("status") != "claimed" or int(item.get("attemptsRecorded") or 0) != 0:
        raise OrchestratorError("invalid_validation_task", "only one claimed attempt may record a result")
    verify_validation_task_bridge_claims(ledger, task, request_id=request_id)
    archived = archive_validation_raw_response(
        raw_response_path,
        archive_root,
        request_id=request_id,
        expected_sha256=normalized["rawResponse"]["sha256"],
        expected_byte_length=normalized["rawResponse"]["byteLength"],
    )
    completed_at = parse_timestamp(normalized["completedAt"], "completedAt")
    timestamp = iso_z(max((recorded_at or now_utc()).astimezone(timezone.utc), completed_at))
    item["status"] = normalized["status"]
    item["attemptsRecorded"] = 1
    item["result"] = normalized
    item["resultSha256"] = result_hash
    item["rawResponseArchive"] = archived
    item["recordedAt"] = timestamp
    terminal_count = sum(row.get("status") in TERMINAL_PACKET_STATUSES for row in task["requests"])
    task["status"] = "ready_to_finalize" if terminal_count == VALIDATION_AUTHORIZED_CALLS else "in_progress"
    task["updatedAt"] = timestamp
    task["history"].append(
        {"at": timestamp, "event": "result_recorded", "requestId": request_id, "status": normalized["status"]}
    )
    return validate_validation_task(task), True


def verify_validation_raw_archives(task: dict[str, Any], archive_root: Path) -> list[dict[str, Any]]:
    root = archive_root.resolve()
    manifest: list[dict[str, Any]] = []
    for item in task["requests"]:
        if item.get("status") not in TERMINAL_PACKET_STATUSES:
            raise OrchestratorError("workflow_incomplete", "raw archive verification requires terminal results")
        archive = require_object(item.get("rawResponseArchive"), "rawResponseArchive")
        response_hash = require_sha256(archive.get("sha256"), "rawResponseArchive.sha256")
        byte_length = require_integer(archive.get("byteLength"), "rawResponseArchive.byteLength")
        expected = root / f"{item['requestId']}.{response_hash}.json"
        stored = Path(str(archive.get("path") or "")).resolve()
        if stored != expected or not stored.is_file():
            raise OrchestratorError("raw_response_missing", "raw response archive is missing or outside task storage")
        if stored.stat().st_size != byte_length or file_sha256(stored) != response_hash:
            raise OrchestratorError("raw_response_mismatch", "raw response archive failed final integrity validation")
        manifest.append(
            {
                "requestId": item["requestId"],
                "path": str(stored),
                "sha256": response_hash,
                "byteLength": byte_length,
            }
        )
    return manifest


def validation_task_manifest_hashes(
    task: dict[str, Any],
    raw_manifest: list[dict[str, Any]],
) -> dict[str, str]:
    claim_manifest = [
        {
            "requestId": item["requestId"],
            "claimId": item["claim"]["claimId"],
            "tokenSha256": item["claim"]["tokenSha256"],
            "claimedAt": item["claim"]["claimedAt"],
        }
        for item in task["requests"]
    ]
    result_manifest = [
        {
            "requestId": item["requestId"],
            "status": item["status"],
            "resultSha256": item["resultSha256"],
        }
        for item in task["requests"]
    ]
    return {
        "claimManifestSha256": payload_sha256(claim_manifest),
        "resultManifestSha256": payload_sha256(result_manifest),
        "rawManifestSha256": payload_sha256(raw_manifest),
    }


def finalize_validation_task(
    ledger: Any,
    task: dict[str, Any],
    *,
    summary_path: Path,
    archive_root: Path,
    generated_at: datetime | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    validate_validation_task(task)
    if str(task.get("status") or "").startswith("finalized"):
        raise OrchestratorError("workflow_finalized", "validation task is already finalized")
    incomplete = [
        item["requestId"] for item in task["requests"] if item.get("status") not in TERMINAL_PACKET_STATUSES
    ]
    if incomplete:
        raise OrchestratorError("workflow_incomplete", "all 91 validation requests need terminal results", details=incomplete)
    state = verify_validation_task_bridge_claims(
        ledger,
        task,
        require_all=True,
        allow_terminal=True,
    )
    raw_manifest = verify_validation_raw_archives(task, archive_root)
    manifest_hashes = validation_task_manifest_hashes(task, raw_manifest)
    timestamp = iso_z(generated_at or now_utc())
    outcome_counts = {
        status: sum(item.get("status") == status for item in task["requests"])
        for status in TERMINAL_PACKET_STATUSES
    }
    tool_outcomes = {
        tool: {
            status: sum(item.get("tool") == tool and item.get("status") == status for item in task["requests"])
            for status in TERMINAL_PACKET_STATUSES
        }
        for tool in ("product_research",) + VALIDATION_TOOLS
    }
    outcomes = [
        {
            "requestId": item["requestId"],
            "tool": item["tool"],
            "targetAsin": item.get("targetAsin"),
            "status": item["status"],
            "requestHash": item["requestHash"],
            "resultSha256": item["resultSha256"],
            "rawResponseArchive": item["rawResponseArchive"],
            "error": item["result"].get("error"),
            "usableForFinal": False,
            "finalAuthority": False,
        }
        for item in task["requests"]
    ]
    summary = {
        "schemaVersion": VALIDATION_TASK_FINAL_SUMMARY_SCHEMA,
        "taskId": task["taskId"],
        "runId": task["runId"],
        "generatedAt": timestamp,
        "preFinalizationTaskSha256": payload_sha256(task),
        "taskBudget": VALIDATION_TASK_BUDGET,
        "authorizedCalls": VALIDATION_AUTHORIZED_CALLS,
        "sealedReserveCalls": VALIDATION_TASK_BUDGET - VALIDATION_AUTHORIZED_CALLS,
        "requestCount": VALIDATION_AUTHORIZED_CALLS,
        "outcomeCounts": outcome_counts,
        "toolOutcomes": tool_outcomes,
        "manifestHashes": manifest_hashes,
        "requests": outcomes,
        "usableForFinal": False,
        "finalAuthority": False,
    }
    ledger_status = "failed" if outcome_counts["failed"] or outcome_counts["partial"] else "succeeded"
    details = {
        "requestCount": VALIDATION_AUTHORIZED_CALLS,
        "authorizedCalls": VALIDATION_AUTHORIZED_CALLS,
        "rawResponseArchiveCount": VALIDATION_AUTHORIZED_CALLS,
        "outcomeCounts": outcome_counts,
        **manifest_hashes,
    }
    marker = getattr(ledger, "mark_plan_status", None)
    if not callable(marker):
        raise OrchestratorError("mark_plan_status_unavailable", "Bridge ledger cannot close validation plan")
    try:
        ledger_result = marker(plan_id=task["taskId"], status=ledger_status, details=details)
    except OrchestratorError:
        raise
    except Exception as error:
        raise OrchestratorError(
            "bridge_status_failed",
            str(error),
            details={"stage": getattr(error, "stage", None), "status": getattr(error, "status", None)},
        ) from error
    if state.get("status") in {"succeeded", "failed"} and state.get("status") != ledger_status:
        raise OrchestratorError("ledger_conflict", "Bridge terminal status conflicts with validation outcomes")
    task["status"] = (
        "finalized_with_failures" if outcome_counts["failed"] or outcome_counts["partial"] else "finalized"
    )
    task["updatedAt"] = timestamp
    task["finalization"] = {
        "at": timestamp,
        "summaryPath": str(summary_path.resolve()),
        "summarySha256": payload_sha256(summary),
        "requestCount": VALIDATION_AUTHORIZED_CALLS,
        "outcomeCounts": outcome_counts,
        "manifestHashes": manifest_hashes,
        "ledgerStatus": ledger_status,
        "ledgerResult": ledger_result,
        "usableForFinal": False,
        "finalAuthority": False,
    }
    task["history"].append(
        {"at": timestamp, "event": "finalized", "status": task["status"], "outcomeCounts": outcome_counts}
    )
    return validate_validation_task(task), summary


def allocate_pools(
    count: int,
    *,
    primary_limit: int = MAX_PRIMARY_CALLS,
    conditional_limit: int = 100,
    emergency_limit: int = 100,
    enable_conditional: bool = False,
    enable_emergency: bool = False,
) -> list[str]:
    if primary_limit < 1 or primary_limit > MAX_PRIMARY_CALLS:
        raise OrchestratorError("invalid_budget", f"primary limit must be between 1 and {MAX_PRIMARY_CALLS}")
    if conditional_limit < 0 or emergency_limit < 0:
        raise OrchestratorError("invalid_budget", "conditional and emergency limits cannot be negative")
    if enable_emergency and not enable_conditional:
        raise OrchestratorError("invalid_budget", "emergency pool requires the conditional pool to be enabled")
    enabled_conditional = conditional_limit if enable_conditional else 0
    enabled_emergency = emergency_limit if enable_emergency else 0
    if primary_limit + enabled_conditional + enabled_emergency > HARD_DAILY_LIMIT:
        raise OrchestratorError("invalid_budget", f"enabled pools cannot exceed {HARD_DAILY_LIMIT} calls")
    capacity = primary_limit + enabled_conditional + enabled_emergency
    if count > capacity:
        raise OrchestratorError(
            "budget_exceeded",
            f"{count} candidates exceed explicitly enabled capacity {capacity}",
            details={"candidateCount": count, "capacity": capacity},
        )
    pools: list[str] = []
    pools.extend(["primary"] * min(count, primary_limit))
    remaining = count - len(pools)
    pools.extend(["conditional"] * min(remaining, enabled_conditional))
    remaining = count - len(pools)
    pools.extend(["emergency"] * min(remaining, enabled_emergency))
    return pools


def plan_workflow(
    candidate_payload: Any,
    *,
    input_sha256: str,
    tool: str = "keepa_info",
    primary_limit: int = MAX_PRIMARY_CALLS,
    conditional_limit: int = 100,
    emergency_limit: int = 100,
    enable_conditional: bool = False,
    enable_emergency: bool = False,
    test_only_allow_pending_tool: bool = False,
    test_only_reserve_pending: bool = False,
    created_at: datetime | None = None,
) -> dict[str, Any]:
    document = validate_candidate_document(candidate_payload)
    route = resolve_tool(tool, allow_pending=test_only_allow_pending_tool)
    if test_only_reserve_pending and not test_only_allow_pending_tool:
        raise OrchestratorError(
            "test_mode_required",
            "pending reservation requires the explicit test-only pending-tool flag",
        )
    if test_only_reserve_pending and route["state"] != "pending":
        raise OrchestratorError(
            "invalid_test_reservation",
            "test-only reservation is restricted to pending tools",
        )
    reservation_eligible = bool(route["reservationEligible"] or test_only_reserve_pending)
    input_hash = require_sha256(input_sha256, "inputSha256")
    pools = allocate_pools(
        len(document["candidates"]),
        primary_limit=primary_limit,
        conditional_limit=conditional_limit,
        emergency_limit=emergency_limit,
        enable_conditional=enable_conditional,
        enable_emergency=enable_emergency,
    )
    workflow_seed = {
        "runId": document["runId"],
        "inputSha256": input_hash,
        "tool": tool,
        "candidateAsins": [row["asin"] for row in document["candidates"]],
        "pools": pools,
        "testOnlyReservation": bool(test_only_reserve_pending),
    }
    workflow_id = f"prefetch-{payload_sha256(workflow_seed)[:24]}"
    timestamp = iso_z(created_at or now_utc())
    packets: list[dict[str, Any]] = []
    for candidate, pool in zip(document["candidates"], pools, strict=True):
        request = tool_request(tool, candidate["asin"])
        packet_id = f"pkt-{payload_sha256({'workflowId': workflow_id, 'tool': tool, 'asin': candidate['asin']})[:24]}"
        packets.append(
            {
                "schemaVersion": PACKET_SCHEMA,
                "packetId": packet_id,
                "workflowId": workflow_id,
                "runId": document["runId"],
                "marketplace": "US",
                "mode": "shadow",
                "finalAuthority": False,
                "targetAsin": candidate["asin"],
                "tool": tool,
                "toolContractState": route["state"],
                "pool": pool,
                "calls": 1,
                "request": request,
                "requestHash": payload_sha256(request),
                "sourceProvenance": candidate["sourceProvenance"],
                "status": "planned",
                "attemptPolicy": {"maxAttempts": 1, "automaticRetry": False},
                "attemptsStarted": 0,
                "attemptsRecorded": 0,
                "createdAt": timestamp,
            }
        )
    by_pool = {pool: pools.count(pool) for pool in ("primary", "conditional", "emergency")}
    return {
        "schemaVersion": WORKFLOW_SCHEMA,
        "workflowId": workflow_id,
        "runId": document["runId"],
        "marketplace": "US",
        "mode": "shadow",
        "finalAuthority": False,
        "outboundMcpClientIncluded": False,
        "createdAt": timestamp,
        "updatedAt": timestamp,
        "status": "planned",
        "toolRouting": {
            "tool": tool,
            "contractState": route["state"],
            "reservationEligible": reservation_eligible,
            "testOnly": route["state"] != "validated_shadow",
            "testOnlyReservation": bool(test_only_reserve_pending),
        },
        "source": {
            "candidateDocumentSha256": input_hash,
            "sourceProvenance": document["sourceProvenance"],
            "candidateGeneratedAt": document["generatedAt"],
        },
        "budget": {
            "hardDailyLimit": HARD_DAILY_LIMIT,
            "primaryLimit": primary_limit,
            "conditionalLimit": conditional_limit,
            "emergencyLimit": emergency_limit,
            "conditionalEnabled": enable_conditional,
            "emergencyEnabled": enable_emergency,
            "plannedCalls": len(packets),
            "plannedByPool": by_pool,
        },
        "control": {"pausedFrom": None, "pauseReason": None},
        "reservation": None,
        "packets": packets,
        "history": [{"at": timestamp, "event": "planned", "packetCount": len(packets)}],
    }


def validate_workflow(value: Any) -> dict[str, Any]:
    workflow = require_object(value, "workflow")
    if workflow.get("schemaVersion") != WORKFLOW_SCHEMA:
        raise OrchestratorError("invalid_schema", f"workflow must use {WORKFLOW_SCHEMA}")
    require_false(workflow.get("finalAuthority"), "workflow.finalAuthority")
    if workflow.get("mode") != "shadow" or workflow.get("marketplace") != "US":
        raise OrchestratorError("invalid_workflow", "workflow must be US shadow mode")
    require_safe_id(workflow.get("workflowId"), "workflowId")
    require_safe_id(workflow.get("runId"), "runId")
    routing = require_object(workflow.get("toolRouting"), "toolRouting")
    route_tool = str(routing.get("tool") or "")
    route = TOOL_ROUTES.get(route_tool)
    if route is None or routing.get("contractState") != route["state"]:
        raise OrchestratorError("invalid_workflow", "workflow tool routing does not match the local contract registry")
    test_only_reservation = routing.get("testOnlyReservation") is True
    if test_only_reservation and route["state"] != "pending":
        raise OrchestratorError("invalid_workflow", "test-only reservation can only target a pending tool")
    expected_eligible = bool(route["reservationEligible"] or test_only_reservation)
    if routing.get("reservationEligible") is not expected_eligible:
        raise OrchestratorError("invalid_workflow", "workflow reservation eligibility is inconsistent")
    packets = workflow.get("packets")
    if not isinstance(packets, list) or not packets:
        raise OrchestratorError("invalid_workflow", "workflow packets are required")
    packet_ids: set[str] = set()
    asins: set[str] = set()
    for index, raw in enumerate(packets):
        packet = require_object(raw, f"packets[{index}]")
        require_false(packet.get("finalAuthority"), f"packets[{index}].finalAuthority")
        packet_id = require_safe_id(packet.get("packetId"), f"packets[{index}].packetId")
        asin = normalize_asin(packet.get("targetAsin"), f"packets[{index}].targetAsin")
        if packet.get("workflowId") != workflow["workflowId"] or packet.get("runId") != workflow["runId"]:
            raise OrchestratorError("invalid_workflow", "packet workflowId or runId mismatch")
        tool = str(packet.get("tool") or "")
        if tool != route_tool or tool not in TOOL_ROUTES or TOOL_ROUTES[tool]["state"] in {"disabled", "discovery_only"}:
            raise OrchestratorError("invalid_workflow", f"packet has unavailable tool: {tool}")
        if packet.get("toolContractState") != route["state"]:
            raise OrchestratorError("invalid_workflow", "packet tool contract state mismatches workflow routing")
        request_hash = require_sha256(packet.get("requestHash"), f"packets[{index}].requestHash")
        request = require_object(packet.get("request"), f"packets[{index}].request")
        if request != tool_request(tool, asin):
            raise OrchestratorError("request_contract_mismatch", "stored packet is not an executable MCP request")
        if request_hash != payload_sha256(request):
            raise OrchestratorError("request_hash_mismatch", "stored packet requestHash failed integrity validation")
        if packet.get("pool") not in {"primary", "conditional", "emergency"} or packet.get("calls") != 1:
            raise OrchestratorError("invalid_workflow", "packet pool or call count is invalid")
        if packet.get("attemptPolicy") != {"maxAttempts": 1, "automaticRetry": False}:
            raise OrchestratorError("retry_forbidden", "packet attempt policy must remain one attempt with no automatic retry")
        status = str(packet.get("status") or "")
        attempts_started = int(packet.get("attemptsStarted") or 0)
        attempts_recorded = int(packet.get("attemptsRecorded") or 0)
        claim = packet.get("claim")
        if status == "planned":
            if attempts_started != 0 or attempts_recorded != 0 or claim is not None:
                raise OrchestratorError("invalid_workflow", "planned packet cannot contain attempt state")
        elif status == "claimed":
            if attempts_started != 1 or attempts_recorded != 0 or not isinstance(claim, dict):
                raise OrchestratorError("invalid_workflow", "claimed packet attempt state is incomplete")
            require_safe_id(claim.get("claimId"), f"packets[{index}].claim.claimId")
            require_safe_id(claim.get("executorId"), f"packets[{index}].claim.executorId")
            require_sha256(claim.get("tokenSha256"), f"packets[{index}].claim.tokenSha256")
            parse_timestamp(claim.get("claimedAt"), f"packets[{index}].claim.claimedAt")
        elif status in TERMINAL_PACKET_STATUSES:
            if attempts_started != 1 or attempts_recorded != 1 or not isinstance(claim, dict):
                raise OrchestratorError("invalid_workflow", "terminal packet must retain exactly one claimed attempt")
            require_safe_id(claim.get("claimId"), f"packets[{index}].claim.claimId")
            require_safe_id(claim.get("executorId"), f"packets[{index}].claim.executorId")
            require_sha256(claim.get("tokenSha256"), f"packets[{index}].claim.tokenSha256")
            parse_timestamp(claim.get("claimedAt"), f"packets[{index}].claim.claimedAt")
            result_hash = require_sha256(packet.get("resultSha256"), f"packets[{index}].resultSha256")
            stored_result = require_object(packet.get("result"), f"packets[{index}].result")
            normalized_result = validate_packet_result(stored_result, packet, workflow)
            if normalized_result != stored_result or payload_sha256(normalized_result) != result_hash:
                raise OrchestratorError("result_integrity", "terminal packet result failed canonical integrity validation")
        else:
            raise OrchestratorError("invalid_workflow", f"packet status is invalid: {status}")
        if packet_id in packet_ids or asin in asins:
            raise OrchestratorError("duplicate_packet", "workflow packets must have unique IDs and ASINs")
        packet_ids.add(packet_id)
        asins.add(asin)
    reservation = workflow.get("reservation")
    started = any(int(packet.get("attemptsStarted") or 0) for packet in packets)
    if started and not (isinstance(reservation, dict) and reservation.get("status") == "reserved"):
        raise OrchestratorError("reservation_required", "packet execution requires an attached atomic reservation")
    return workflow


def _reservation_requests_unchecked(workflow: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "id": packet["packetId"],
            "tool": packet["tool"],
            "requestHash": packet["requestHash"],
            "asinCount": 1,
            "calls": int(packet["calls"]),
            "pool": packet["pool"],
        }
        for packet in workflow["packets"]
    ]


def reservation_requests(workflow: dict[str, Any]) -> list[dict[str, Any]]:
    validate_workflow(workflow)
    return _reservation_requests_unchecked(workflow)


def validate_reservation_result(
    workflow: dict[str, Any],
    reservation: Any,
    *,
    allow_idempotent_reconcile: bool = False,
) -> dict[str, Any]:
    result = require_object(reservation, "reservation result")
    allowed_idempotency = result.get("idempotent") is False or (
        allow_idempotent_reconcile and result.get("idempotent") is True
    )
    if not allowed_idempotency or result.get("currentStatus") != "reserved":
        raise OrchestratorError(
            "reservation_not_new",
            "only a newly created reserved plan may be attached; reconcile any prior plan manually",
        )
    event = require_object(result.get("event"), "reservation result.event")
    if event.get("eventType") != "reserved" or event.get("runId") != workflow["runId"]:
        raise OrchestratorError("reservation_mismatch", "Bridge reservation event does not match the workflow run")
    if event.get("planId") != workflow["workflowId"] or int(event.get("calls") or 0) != workflow["budget"]["plannedCalls"]:
        raise OrchestratorError("reservation_mismatch", "Bridge reservation plan ID or call count mismatch")
    if event.get("automaticRetry") is not False:
        raise OrchestratorError("retry_forbidden", "Bridge reservation must prohibit automatic retries")
    if event.get("requests") != _reservation_requests_unchecked(workflow):
        raise OrchestratorError("reservation_mismatch", "Bridge reservation requests differ from workflow packets")
    return result


def reserve_with_bridge_ledger(ledger: Any, workflow: dict[str, Any]) -> Any:
    """Isolated adapter for the Bridge atomic plan API (or a duck-typed fake)."""

    validate_workflow(workflow)
    routing = workflow["toolRouting"]
    route = TOOL_ROUTES[routing["tool"]]
    test_only_reservation = routing.get("testOnlyReservation") is True
    if test_only_reservation:
        if not bool(getattr(ledger, "test_mode", False)):
            raise OrchestratorError(
                "test_mode_required",
                "pending tool reservation requires a Bridge ledger created with test_mode=True",
            )
    elif not route["reservationEligible"]:
        raise OrchestratorError("tool_not_reservable", "workflow tool is not eligible for reservation")
    reserve_plan = getattr(ledger, "reserve_plan", None)
    if not callable(reserve_plan):
        raise OrchestratorError(
            "reserve_plan_unavailable",
            "Bridge ledger does not expose atomic reserve_plan; no per-packet fallback is allowed",
        )
    try:
        return reserve_plan(
            plan_id=workflow["workflowId"],
            requests=reservation_requests(workflow),
            allow_emergency=bool(workflow["budget"]["emergencyEnabled"]),
        )
    except OrchestratorError:
        raise
    except Exception as error:
        raise OrchestratorError(
            "bridge_reservation_failed",
            str(error),
            details={"stage": getattr(error, "stage", None), "status": getattr(error, "status", None)},
        ) from error


def attach_reservation(
    workflow: dict[str, Any],
    reservation: Any,
    *,
    ledger_path: Path | None = None,
    policy_path: Path | None = None,
    allow_idempotent_reconcile: bool = False,
    at: datetime | None = None,
) -> dict[str, Any]:
    validate_workflow(workflow)
    validated = validate_reservation_result(
        workflow,
        reservation,
        allow_idempotent_reconcile=allow_idempotent_reconcile,
    )
    if workflow.get("reservation") is not None or workflow.get("status") != "planned":
        raise OrchestratorError("reservation_conflict", "workflow already has reservation state")
    timestamp = iso_z(at or now_utc())
    workflow["reservation"] = {
        "status": "reserved",
        "at": timestamp,
        "result": validated,
        "ledgerPath": str(ledger_path.resolve()) if ledger_path else None,
        "policyPath": str(policy_path.resolve()) if policy_path else None,
        "reconciled": bool(allow_idempotent_reconcile),
    }
    workflow["status"] = "reserved"
    workflow["updatedAt"] = timestamp
    workflow["history"].append({"at": timestamp, "event": "reserved"})
    return workflow


def bridge_plan_state(ledger: Any, workflow: dict[str, Any]) -> dict[str, Any]:
    getter = getattr(ledger, "plan_state", None)
    if not callable(getter):
        raise OrchestratorError("plan_state_unavailable", "Bridge ledger does not expose plan_state")
    try:
        state = require_object(getter(workflow["workflowId"]), "Bridge plan state")
    except OrchestratorError:
        raise
    except Exception as error:
        raise OrchestratorError(
            "bridge_plan_state_failed",
            str(error),
            details={"stage": getattr(error, "stage", None), "status": getattr(error, "status", None)},
        ) from error
    if (
        state.get("runId") != workflow["runId"]
        or state.get("planId") != workflow["workflowId"]
        or state.get("finalAuthority") is not False
        or state.get("requests") != _reservation_requests_unchecked(workflow)
    ):
        raise OrchestratorError("plan_state_mismatch", "Bridge plan state does not match the workflow")
    return state


def reconcile_reservation(
    ledger: Any,
    workflow: dict[str, Any],
    *,
    ledger_path: Path | None = None,
    policy_path: Path | None = None,
    at: datetime | None = None,
) -> dict[str, Any]:
    validate_workflow(workflow)
    if workflow.get("status") != "planned" or workflow.get("reservation") is not None:
        raise OrchestratorError("reconcile_not_applicable", "only an un-attached planned workflow can reconcile")
    state = bridge_plan_state(ledger, workflow)
    if state.get("phase") != "reserved" or state.get("status") != "reserved" or state.get("claimedRequestIds"):
        raise OrchestratorError("reconcile_unsafe", "reservation reconciliation requires an unclaimed reserved plan")
    reservation = {
        "event": state.get("reservation"),
        "idempotent": True,
        "currentStatus": "reserved",
    }
    attach_reservation(
        workflow,
        reservation,
        ledger_path=ledger_path,
        policy_path=policy_path,
        allow_idempotent_reconcile=True,
        at=at,
    )
    workflow["history"].append({"at": workflow["updatedAt"], "event": "reservation_reconciled"})
    return workflow


def _require_attached_reservation(workflow: dict[str, Any]) -> dict[str, Any]:
    reservation = workflow.get("reservation")
    if not isinstance(reservation, dict) or reservation.get("status") != "reserved":
        raise OrchestratorError("reservation_required", "reserve the workflow atomically before claiming a packet")
    result = require_object(reservation.get("result"), "reservation.result")
    event = require_object(result.get("event"), "reservation.result.event")
    if event.get("planId") != workflow["workflowId"] or event.get("runId") != workflow["runId"]:
        raise OrchestratorError("reservation_mismatch", "attached reservation no longer matches the workflow")
    return reservation


def claim_packet(
    ledger: Any,
    workflow: dict[str, Any],
    *,
    packet_id: str,
    executor_id: str,
    claim_token: str | None = None,
    at: datetime | None = None,
) -> tuple[dict[str, Any], str]:
    validate_workflow(workflow)
    _require_attached_reservation(workflow)
    if workflow.get("status") == "paused":
        raise OrchestratorError("workflow_paused", "resume the workflow before claiming a packet")
    if str(workflow.get("status") or "").startswith("finalized"):
        raise OrchestratorError("workflow_finalized", "cannot claim a finalized workflow")
    normalized_packet_id = require_safe_id(packet_id, "packetId")
    normalized_executor_id = require_safe_id(executor_id, "executorId")
    matches = [packet for packet in workflow["packets"] if packet.get("packetId") == normalized_packet_id]
    if len(matches) != 1:
        raise OrchestratorError("packet_not_found", f"workflow does not contain packet {normalized_packet_id}")
    packet = matches[0]
    if packet.get("status") != "planned" or int(packet.get("attemptsStarted") or 0) != 0:
        raise OrchestratorError("attempt_already_started", "packet already has its single execution attempt")
    token = str(claim_token or secrets.token_hex(32))
    if len(token) < 32:
        raise OrchestratorError("invalid_claim_token", "claim token must contain at least 32 characters")
    marker = getattr(ledger, "claim_plan_request", None)
    if not callable(marker):
        raise OrchestratorError("claim_api_unavailable", "Bridge ledger does not expose claim_plan_request")
    claim_id = f"claim-{secrets.token_hex(12)}"
    try:
        bridge_claim = marker(
            plan_id=workflow["workflowId"],
            request_id=normalized_packet_id,
            claim_id=claim_id,
            at=at,
        )
    except OrchestratorError:
        raise
    except Exception as error:
        raise OrchestratorError(
            "bridge_claim_failed",
            str(error),
            details={"stage": getattr(error, "stage", None), "status": getattr(error, "status", None)},
        ) from error
    bridge_claim_obj = require_object(bridge_claim, "Bridge claim result")
    event = require_object(bridge_claim_obj.get("event"), "Bridge claim result.event")
    if (
        bridge_claim_obj.get("idempotent") is not False
        or bridge_claim_obj.get("executionAllowed") is not True
        or bridge_claim_obj.get("finalAuthority") is not False
        or event.get("executionAllowed") is not True
        or event.get("finalAuthority") is not False
        or event.get("planId") != workflow["workflowId"]
    ):
        raise OrchestratorError("claim_conflict", "Bridge did not grant a new exclusive packet claim")
    if event.get("requestId") != normalized_packet_id or event.get("claimId") != claim_id:
        raise OrchestratorError("claim_mismatch", "Bridge claim receipt does not match the requested packet")
    bridge_claimed_at = parse_timestamp(event.get("at"), "Bridge claim event.at")
    timestamp = iso_z(bridge_claimed_at)
    packet["status"] = "claimed"
    packet["attemptsStarted"] = 1
    packet["claim"] = {
        "claimId": claim_id,
        "executorId": normalized_executor_id,
        "tokenSha256": hashlib.sha256(token.encode("utf-8")).hexdigest(),
        "claimedAt": timestamp,
        "bridgeReceipt": bridge_claim_obj,
    }
    workflow["status"] = "running"
    workflow["updatedAt"] = timestamp
    workflow["history"].append(
        {"at": timestamp, "event": "packet_claimed", "packetId": normalized_packet_id, "claimId": claim_id}
    )
    return workflow, token


def reconcile_claim_as_failed(
    ledger: Any,
    workflow: dict[str, Any],
    *,
    packet_id: str,
    at: datetime | None = None,
) -> dict[str, Any]:
    """Recover a Bridge claim that was not durably attached; never re-execute it."""

    validate_workflow(workflow)
    _require_attached_reservation(workflow)
    normalized_packet_id = require_safe_id(packet_id, "packetId")
    matches = [packet for packet in workflow["packets"] if packet.get("packetId") == normalized_packet_id]
    if len(matches) != 1:
        raise OrchestratorError("packet_not_found", f"workflow does not contain packet {normalized_packet_id}")
    packet = matches[0]
    local_status = packet.get("status")
    if local_status not in {"planned", "claimed"} or int(packet.get("attemptsRecorded") or 0) != 0:
        raise OrchestratorError("reconcile_not_applicable", "only an unrecorded packet can reconcile")
    if local_status == "planned" and int(packet.get("attemptsStarted") or 0) != 0:
        raise OrchestratorError("reconcile_not_applicable", "planned recovery packet has invalid attempt state")
    if local_status == "claimed" and int(packet.get("attemptsStarted") or 0) != 1:
        raise OrchestratorError("reconcile_not_applicable", "claimed recovery packet has invalid attempt state")
    state = bridge_plan_state(ledger, workflow)
    if state.get("phase") != "claimed" or state.get("status") != "reserved":
        raise OrchestratorError("reconcile_unsafe", "Bridge plan must have an open claim and no terminal status")
    claim_events = [
        item
        for item in state.get("claimEvents") or []
        if isinstance(item, dict) and item.get("requestId") == normalized_packet_id
    ]
    if len(claim_events) != 1:
        raise OrchestratorError("reconcile_unsafe", "Bridge must contain exactly one claim for this packet")
    event = claim_events[0]
    if event.get("executionAllowed") is not True or event.get("finalAuthority") is not False:
        raise OrchestratorError("reconcile_unsafe", "Bridge claim is not an allowed non-authoritative claim")
    claimed_at = parse_timestamp(event.get("at"), "Bridge claim event.at")
    timestamp = iso_z(at or now_utc())
    completed_at = max(parse_timestamp(timestamp, "recovery.at"), claimed_at)
    completed_text = iso_z(completed_at)
    claim_id = require_safe_id(event.get("claimId"), "Bridge claim event.claimId")
    prior_claim = packet.get("claim") if local_status == "claimed" else None
    if prior_claim is not None:
        prior_claim = require_object(prior_claim, "packet.claim")
        if prior_claim.get("claimId") != claim_id or iso_z(
            parse_timestamp(prior_claim.get("claimedAt"), "packet.claim.claimedAt")
        ) != iso_z(claimed_at):
            raise OrchestratorError("reconcile_unsafe", "local and Bridge claim records do not match")
    packet["status"] = "failed"
    packet["attemptsStarted"] = 1
    packet["attemptsRecorded"] = 1
    packet["claim"] = prior_claim or {
            "claimId": claim_id,
            "executorId": "recovery-discard",
            "tokenSha256": hashlib.sha256(f"discard:{claim_id}".encode("utf-8")).hexdigest(),
            "claimedAt": iso_z(claimed_at),
            "bridgeReceipt": {"event": event, "executionAllowed": True, "finalAuthority": False},
        }
    allowed_fields = list(TOOL_ROUTES[packet["tool"]]["fields"])
    raw_hash = payload_sha256(
        {"workflowId": workflow["workflowId"], "packetId": normalized_packet_id, "claimId": claim_id, "discarded": True}
    )
    result = {
        "schemaVersion": PACKET_RESULT_SCHEMA,
        "workflowId": workflow["workflowId"],
        "runId": workflow["runId"],
        "packetId": normalized_packet_id,
        "requestHash": packet["requestHash"],
        "targetAsin": packet["targetAsin"],
        "actualAsin": None,
        "tool": {"name": packet["tool"], "version": "orchestrator-recovery-v1"},
        "status": "failed",
        "startedAt": iso_z(claimed_at),
        "completedAt": completed_text,
        "rawResponse": {"sha256": raw_hash, "capturedAt": completed_text},
        "fields": {},
        "fieldProvenance": {},
        "missingFields": allowed_fields,
        "fallbackRequired": True,
        "error": {
            "code": "claim_recovery_discarded",
            "message": "Bridge claim existed without a durable local claim; response discarded and retry forbidden",
            "retryable": False,
        },
        "finalAuthority": False,
    }
    normalized = validate_packet_result(result, packet, workflow)
    packet["result"] = normalized
    packet["resultSha256"] = payload_sha256(normalized)
    packet["recordedAt"] = completed_text
    remaining = [item for item in workflow["packets"] if item.get("status") not in TERMINAL_PACKET_STATUSES]
    workflow["status"] = "running" if remaining else "ready_to_finalize"
    workflow["updatedAt"] = completed_text
    workflow["history"].append(
        {
            "at": completed_text,
            "event": "claim_reconciled_as_failed",
            "packetId": normalized_packet_id,
            "claimId": claim_id,
        }
    )
    return workflow


def validate_field_provenance(
    value: Any,
    *,
    fields: dict[str, Any],
    missing_fields: list[str],
    tool: str,
) -> dict[str, Any]:
    provenance = require_object(value, "fieldProvenance")
    allowed = set(TOOL_ROUTES[tool]["fields"])
    normalized: dict[str, Any] = {}
    for key, detail_raw in provenance.items():
        if key not in fields or key not in allowed:
            raise OrchestratorError("invalid_provenance", f"unexpected provenance field: {key}")
        if fields[key] is None or key in missing_fields:
            raise OrchestratorError("invalid_provenance", f"missing field cannot claim provenance: {key}")
        detail = require_object(detail_raw, f"fieldProvenance.{key}")
        if detail.get("sourceTool") != tool:
            raise OrchestratorError("invalid_provenance", f"fieldProvenance.{key}.sourceTool mismatch")
        source_path = str(detail.get("sourcePath") or "").strip()
        semantics = str(detail.get("semantics") or "").strip()
        if not source_path or not semantics:
            raise OrchestratorError("invalid_provenance", f"fieldProvenance.{key} is incomplete")
        normalized[key] = {"sourceTool": tool, "sourcePath": source_path, "semantics": semantics}
    present = {key for key, item in fields.items() if key != "asin" and item is not None}
    if present != set(normalized):
        raise OrchestratorError(
            "invalid_provenance",
            "every non-null field must have exactly one provenance record",
            details={"present": sorted(present), "provenance": sorted(normalized)},
        )
    return normalized


def validate_packet_result(value: Any, packet: dict[str, Any], workflow: dict[str, Any]) -> dict[str, Any]:
    result = require_object(value, "packet result")
    reject_embedded_authority_claims(result, "packet result")
    if result.get("schemaVersion") != PACKET_RESULT_SCHEMA:
        raise OrchestratorError("invalid_schema", f"packet result must use {PACKET_RESULT_SCHEMA}")
    require_false(result.get("finalAuthority"), "packet result finalAuthority")
    if result.get("workflowId") != workflow["workflowId"] or result.get("runId") != workflow["runId"]:
        raise OrchestratorError("workflow_mismatch", "packet result workflowId or runId mismatch")
    if result.get("packetId") != packet["packetId"]:
        raise OrchestratorError("packet_mismatch", "packet result packetId mismatch")
    request_hash = require_sha256(result.get("requestHash"), "requestHash")
    if request_hash != packet["requestHash"]:
        raise OrchestratorError("request_hash_mismatch", "packet result requestHash does not match declared request")
    target_asin = normalize_asin(result.get("targetAsin"), "targetAsin")
    if target_asin != packet["targetAsin"]:
        raise OrchestratorError("asin_mismatch", "packet result targetAsin mismatch")
    tool = require_object(result.get("tool"), "tool")
    tool_name = str(tool.get("name") or "")
    tool_version = str(tool.get("version") or "").strip()
    if tool_name != packet["tool"] or not tool_version:
        raise OrchestratorError("tool_mismatch", "packet result tool name/version mismatch")
    status = str(result.get("status") or "")
    if status not in TERMINAL_PACKET_STATUSES:
        raise OrchestratorError("invalid_status", "packet result status must be succeeded, partial, or failed")
    started_at = parse_timestamp(result.get("startedAt"), "startedAt")
    completed_at = parse_timestamp(result.get("completedAt"), "completedAt")
    claim = require_object(packet.get("claim"), "packet.claim")
    claimed_at = parse_timestamp(claim.get("claimedAt"), "packet.claim.claimedAt")
    if started_at < claimed_at:
        raise OrchestratorError("execution_before_claim", "MCP execution started before the exclusive packet claim")
    if completed_at < started_at:
        raise OrchestratorError("invalid_timestamp", "completedAt cannot precede startedAt")
    raw_response = require_object(result.get("rawResponse"), "rawResponse")
    response_hash = require_sha256(raw_response.get("sha256"), "rawResponse.sha256")
    captured_at = parse_timestamp(raw_response.get("capturedAt"), "rawResponse.capturedAt")
    if captured_at < started_at or captured_at > completed_at:
        raise OrchestratorError("invalid_timestamp", "rawResponse.capturedAt must be within the attempt window")
    actual_raw = str(result.get("actualAsin") or "").strip()
    actual_asin = normalize_asin(actual_raw, "actualAsin") if actual_raw else ""
    if actual_asin and actual_asin != target_asin:
        raise OrchestratorError("asin_mismatch", "actualAsin does not exactly match targetAsin")
    fields = require_object(result.get("fields"), "fields")
    allowed_fields = set(TOOL_ROUTES[tool_name]["fields"])
    unknown_fields = set(fields) - allowed_fields - {"asin"}
    if unknown_fields:
        raise OrchestratorError("invalid_fields", f"unexpected fields: {sorted(unknown_fields)}")
    if fields.get("asin") is not None and normalize_asin(fields.get("asin"), "fields.asin") != actual_asin:
        raise OrchestratorError("asin_mismatch", "fields.asin does not match actualAsin")
    missing_raw = result.get("missingFields")
    if not isinstance(missing_raw, list) or any(not isinstance(item, str) for item in missing_raw):
        raise OrchestratorError("invalid_fields", "missingFields must be a string array")
    missing_fields = list(dict.fromkeys(missing_raw))
    if len(missing_fields) != len(missing_raw) or not set(missing_fields).issubset(allowed_fields):
        raise OrchestratorError("invalid_fields", "missingFields must be unique recognized fields")
    expected_missing = {key for key in allowed_fields if fields.get(key) is None}
    if set(missing_fields) != expected_missing:
        raise OrchestratorError(
            "invalid_fields",
            "missingFields must enumerate every absent or null routed field",
            details={"expected": sorted(expected_missing), "actual": sorted(missing_fields)},
        )
    provenance = validate_field_provenance(
        result.get("fieldProvenance"), fields=fields, missing_fields=missing_fields, tool=tool_name
    )
    normalized_raw: dict[str, Any] = {
        "sha256": response_hash,
        "capturedAt": iso_z(captured_at),
    }
    if status in {"succeeded", "partial"}:
        if not actual_asin:
            raise OrchestratorError("asin_mismatch", "successful or partial result requires actualAsin")
        expires_at = parse_timestamp(raw_response.get("expiresAt"), "rawResponse.expiresAt")
        if expires_at <= captured_at:
            raise OrchestratorError("invalid_timestamp", "rawResponse.expiresAt must follow capturedAt")
        maximum_expiry = captured_at + timedelta(hours=int(TOOL_ROUTES[tool_name]["ttlHours"]))
        if expires_at > maximum_expiry:
            raise OrchestratorError(
                "ttl_exceeded",
                f"{tool_name} evidence exceeds its {TOOL_ROUTES[tool_name]['ttlHours']}-hour TTL",
            )
        normalized_raw["expiresAt"] = iso_z(expires_at)
        if not any(value is not None for key, value in fields.items() if key != "asin"):
            raise OrchestratorError("invalid_fields", "successful or partial result must contain at least one field")
        if status == "succeeded" and missing_fields:
            raise OrchestratorError("invalid_status", "a result with missing fields must use partial status")
        if status == "partial" and not missing_fields:
            raise OrchestratorError("invalid_status", "partial result must declare missing fields")
        error_payload = None
    else:
        if actual_asin:
            raise OrchestratorError("invalid_failure", "failed result must not claim an actualAsin")
        if fields or provenance or set(missing_fields) != allowed_fields:
            raise OrchestratorError("invalid_failure", "failed result must contain no fields and declare every field missing")
        error_payload = require_object(result.get("error"), "error")
        code = str(error_payload.get("code") or "").strip()
        message = str(error_payload.get("message") or "").strip()
        retryable = error_payload.get("retryable")
        if not code or not message or not isinstance(retryable, bool):
            raise OrchestratorError("invalid_failure", "failed result requires code, message, and retryable boolean")
        error_payload = {"code": code, "message": message, "retryable": retryable}
    return {
        "schemaVersion": PACKET_RESULT_SCHEMA,
        "workflowId": workflow["workflowId"],
        "runId": workflow["runId"],
        "packetId": packet["packetId"],
        "requestHash": request_hash,
        "targetAsin": target_asin,
        "actualAsin": actual_asin or None,
        "tool": {"name": tool_name, "version": tool_version},
        "status": status,
        "startedAt": iso_z(started_at),
        "completedAt": iso_z(completed_at),
        "rawResponse": normalized_raw,
        "fields": fields,
        "fieldProvenance": provenance,
        "missingFields": missing_fields,
        "fallbackRequired": status != "succeeded" or bool(missing_fields),
        "error": error_payload,
        "finalAuthority": False,
    }


def _packet_for_result(workflow: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    packet_id = str(result.get("packetId") or "")
    matches = [packet for packet in workflow["packets"] if packet.get("packetId") == packet_id]
    if len(matches) != 1:
        raise OrchestratorError("packet_not_found", f"workflow does not contain packet {packet_id}")
    return matches[0]


def record_result(
    workflow: dict[str, Any],
    result_payload: Any,
    *,
    claim_token: str,
    recorded_at: datetime | None = None,
) -> tuple[dict[str, Any], bool]:
    validate_workflow(workflow)
    _require_attached_reservation(workflow)
    if workflow.get("status") == "paused":
        raise OrchestratorError("workflow_paused", "resume the workflow before recording a packet result")
    if str(workflow.get("status") or "").startswith("finalized"):
        raise OrchestratorError("workflow_finalized", "cannot record into a finalized workflow")
    raw_result = require_object(result_payload, "packet result")
    packet = _packet_for_result(workflow, raw_result)
    claim = require_object(packet.get("claim"), "packet.claim")
    token_hash = hashlib.sha256(str(claim_token or "").encode("utf-8")).hexdigest()
    if not secrets.compare_digest(token_hash, require_sha256(claim.get("tokenSha256"), "packet.claim.tokenSha256")):
        raise OrchestratorError("claim_token_mismatch", "packet result does not hold the one-time claim token")
    if packet.get("status") not in {"claimed", *TERMINAL_PACKET_STATUSES}:
        raise OrchestratorError("packet_not_claimed", "claim the reserved packet before executing MCP")
    normalized = validate_packet_result(raw_result, packet, workflow)
    result_hash = payload_sha256(normalized)
    if packet.get("attemptsRecorded"):
        if packet.get("resultSha256") == result_hash:
            return workflow, False
        raise OrchestratorError(
            "retry_forbidden",
            "packet already has its single terminal result; automatic or replacement retry is forbidden",
        )
    timestamp = iso_z(recorded_at or now_utc())
    packet["attemptsRecorded"] = 1
    packet["status"] = normalized["status"]
    packet["result"] = normalized
    packet["resultSha256"] = result_hash
    packet["recordedAt"] = timestamp
    remaining = [item for item in workflow["packets"] if item.get("status") not in TERMINAL_PACKET_STATUSES]
    workflow["status"] = "running" if remaining else "ready_to_finalize"
    workflow["updatedAt"] = timestamp
    workflow["history"].append(
        {"at": timestamp, "event": "packet_recorded", "packetId": packet["packetId"], "status": packet["status"]}
    )
    return workflow, True


def pause_workflow(workflow: dict[str, Any], reason: str, *, at: datetime | None = None) -> dict[str, Any]:
    validate_workflow(workflow)
    if workflow.get("status") == "paused":
        return workflow
    if str(workflow.get("status") or "").startswith("finalized"):
        raise OrchestratorError("workflow_finalized", "cannot pause a finalized workflow")
    reason_text = str(reason or "").strip()
    if not reason_text:
        raise OrchestratorError("pause_reason_required", "pause reason is required")
    timestamp = iso_z(at or now_utc())
    workflow["control"] = {"pausedFrom": workflow["status"], "pauseReason": reason_text}
    workflow["status"] = "paused"
    workflow["updatedAt"] = timestamp
    workflow["history"].append({"at": timestamp, "event": "paused", "reason": reason_text})
    return workflow


def resume_workflow(workflow: dict[str, Any], *, at: datetime | None = None) -> dict[str, Any]:
    validate_workflow(workflow)
    if workflow.get("status") != "paused":
        raise OrchestratorError("workflow_not_paused", "only a paused workflow can be resumed")
    timestamp = iso_z(at or now_utc())
    resume_status = str((workflow.get("control") or {}).get("pausedFrom") or "planned")
    workflow["control"] = {"pausedFrom": None, "pauseReason": None}
    workflow["status"] = resume_status
    workflow["updatedAt"] = timestamp
    workflow["history"].append({"at": timestamp, "event": "resumed", "status": resume_status})
    return workflow


def evidence_from_packet(workflow: dict[str, Any], packet: dict[str, Any]) -> dict[str, Any]:
    result = packet["result"]
    if result["status"] not in {"succeeded", "partial"}:
        raise OrchestratorError("invalid_evidence", "failed packets cannot be converted into evidence")
    evidence_id = f"ev-{payload_sha256({'packetId': packet['packetId'], 'response': result['rawResponse']['sha256']})[:32]}"
    return {
        "schemaVersion": EVIDENCE_SCHEMA,
        "evidenceId": evidence_id,
        "runId": workflow["runId"],
        "marketplace": "US",
        "mode": "shadow",
        "finalAuthority": False,
        "usableForFinal": False,
        "usableForRanking": True,
        "browserFallbackRequired": bool(result["fallbackRequired"]),
        "targetAsin": result["targetAsin"],
        "actualAsin": result["actualAsin"],
        "tool": result["tool"],
        "request": {"sha256": result["requestHash"], "asinCount": 1},
        "response": {
            "sha256": result["rawResponse"]["sha256"],
            "capturedAt": result["rawResponse"]["capturedAt"],
            "expiresAt": result["rawResponse"]["expiresAt"],
        },
        "fields": result["fields"],
        "fieldProvenance": result["fieldProvenance"],
        "missingFields": result["missingFields"],
        "fallbackRequired": bool(result["fallbackRequired"]),
    }


def mark_ledger_plan(ledger: Any, workflow: dict[str, Any], *, status: str, details: dict[str, Any]) -> Any:
    marker = getattr(ledger, "mark_plan_status", None)
    if not callable(marker):
        raise OrchestratorError("mark_plan_status_unavailable", "Bridge ledger does not expose mark_plan_status")
    try:
        return marker(plan_id=workflow["workflowId"], status=status, details=details)
    except OrchestratorError:
        raise
    except Exception as error:
        raise OrchestratorError(
            "bridge_status_failed",
            str(error),
            details={"stage": getattr(error, "stage", None), "status": getattr(error, "status", None)},
        ) from error


def finalize_workflow(
    workflow: dict[str, Any], *, ledger: Any = None, generated_at: datetime | None = None
) -> tuple[dict[str, Any], dict[str, Any]]:
    validate_workflow(workflow)
    _require_attached_reservation(workflow)
    if ledger is None:
        raise OrchestratorError("ledger_required", "finalization must close the reserved plan in the shared ledger")
    if str(workflow.get("status") or "").startswith("finalized"):
        raise OrchestratorError("workflow_finalized", "workflow has already been finalized")
    if workflow.get("status") == "paused":
        raise OrchestratorError("workflow_paused", "resume the workflow before finalizing")
    incomplete = [packet["packetId"] for packet in workflow["packets"] if packet.get("status") not in TERMINAL_PACKET_STATUSES]
    if incomplete:
        raise OrchestratorError("workflow_incomplete", "every packet needs one terminal result", details=incomplete)
    timestamp = iso_z(generated_at or now_utc())
    evidence = [
        evidence_from_packet(workflow, packet)
        for packet in workflow["packets"]
        if packet["status"] in {"succeeded", "partial"}
    ]
    outcomes = [
        {
            "packetId": packet["packetId"],
            "targetAsin": packet["targetAsin"],
            "tool": packet["tool"],
            "pool": packet["pool"],
            "status": packet["status"],
            "resultSha256": packet["resultSha256"],
            "error": packet["result"].get("error"),
            "finalAuthority": False,
        }
        for packet in workflow["packets"]
    ]
    counts = {status: sum(item["status"] == status for item in outcomes) for status in TERMINAL_PACKET_STATUSES}
    bundle = {
        "schemaVersion": BUNDLE_SCHEMA,
        "runId": workflow["runId"],
        "marketplace": "US",
        "generatedAt": timestamp,
        "source": "mcp-hybrid-prefetch-orchestrator/v1",
        "workflowId": workflow["workflowId"],
        "workflowSha256": payload_sha256(workflow),
        "finalAuthority": False,
        "importEligible": bool(evidence),
        "evidence": evidence,
        "packetOutcomes": outcomes,
        "outcomeCounts": counts,
    }
    ledger_status = "failed" if counts["failed"] else "succeeded"
    ledger_result = mark_ledger_plan(ledger, workflow, status=ledger_status, details=counts)
    workflow["status"] = "finalized_with_failures" if counts["failed"] else "finalized"
    workflow["updatedAt"] = timestamp
    workflow["finalization"] = {
        "at": timestamp,
        "bundleSha256": payload_sha256(bundle),
        "evidenceCount": len(evidence),
        "outcomeCounts": counts,
        "ledgerStatus": ledger_status,
        "ledgerResult": ledger_result,
        "finalAuthority": False,
    }
    workflow["history"].append(
        {"at": timestamp, "event": "finalized", "status": workflow["status"], "outcomeCounts": counts}
    )
    return workflow, bundle


def load_bridge_ledger(
    bridge_path: Path,
    policy_path: Path,
    ledger_path: Path,
    workflow: dict[str, Any],
    *,
    test_mode: bool = False,
) -> Any:
    """Load only the local Bridge ledger. This never loads a credential or MCP client."""

    spec = importlib.util.spec_from_file_location("mcp_hybrid_bridge_prefetch_adapter", bridge_path)
    if spec is None or spec.loader is None:
        raise OrchestratorError("bridge_unavailable", f"cannot load Bridge module: {bridge_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    policy = module.load_policy(policy_path)
    return module.CallLedger(
        ledger_path,
        run_id=workflow["runId"],
        policy=policy,
        run_budget=int(workflow["budget"]["plannedCalls"]),
        test_mode=test_mode,
    )


def workflow_summary(workflow: dict[str, Any]) -> dict[str, Any]:
    return {
        "schemaVersion": WORKFLOW_SCHEMA,
        "workflowId": workflow["workflowId"],
        "runId": workflow["runId"],
        "status": workflow["status"],
        "plannedCalls": workflow["budget"]["plannedCalls"],
        "plannedByPool": workflow["budget"]["plannedByPool"],
        "packetStatuses": {
            status: sum(packet.get("status") == status for packet in workflow["packets"])
            for status in ("planned", "claimed", "succeeded", "partial", "failed")
        },
        "finalAuthority": False,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Offline SellerSprite MCP prefetch workflow orchestrator")
    sub = parser.add_subparsers(dest="command", required=True)

    validation_plan = sub.add_parser(
        "plan-validation-task",
        help="create the sealed 91-request validation task without reserving or calling MCP",
    )
    validation_plan.add_argument("--sample-plan", type=Path, required=True)
    validation_plan.add_argument("--discovery-request", type=Path, required=True)
    validation_plan.add_argument("--task", type=Path, required=True)
    validation_plan.add_argument("--run-id", required=True)

    validation_reserve = sub.add_parser(
        "reserve-validation-task",
        help="atomically reserve the complete 91-request task in explicit test mode",
    )
    validation_reserve.add_argument("--task", type=Path, required=True)
    validation_reserve.add_argument("--test-mode", action="store_true")
    validation_reserve.add_argument("--bridge", type=Path, default=ROOT / "scripts" / "mcp_hybrid_bridge.py")
    validation_reserve.add_argument("--policy", type=Path, default=ROOT / "config" / "mcp_hybrid_policy.json")
    validation_reserve.add_argument("--ledger", type=Path, default=ROOT / "cache" / "mcp_hybrid_call_ledger.jsonl")

    validation_claim = sub.add_parser(
        "claim-validation-task",
        help="claim one request from the sealed task exactly once",
    )
    validation_claim.add_argument("--task", type=Path, required=True)
    validation_claim.add_argument("--request-id", required=True)
    validation_claim.add_argument("--executor-id", required=True)
    validation_claim.add_argument("--test-mode", action="store_true")
    validation_claim.add_argument("--bridge", type=Path, default=ROOT / "scripts" / "mcp_hybrid_bridge.py")
    validation_claim.add_argument("--policy", type=Path, default=ROOT / "config" / "mcp_hybrid_policy.json")
    validation_claim.add_argument("--ledger", type=Path, default=ROOT / "cache" / "mcp_hybrid_call_ledger.jsonl")

    validation_record = sub.add_parser(
        "record-validation-task",
        help="record one claimed validation result and immutably archive its raw JSON response",
    )
    validation_record.add_argument("--task", type=Path, required=True)
    validation_record.add_argument("--result", type=Path, required=True)
    validation_record.add_argument("--raw-response", type=Path, required=True)
    validation_record.add_argument("--claim-token", required=True)
    validation_record.add_argument("--test-mode", action="store_true")
    validation_record.add_argument("--bridge", type=Path, default=ROOT / "scripts" / "mcp_hybrid_bridge.py")
    validation_record.add_argument("--policy", type=Path, default=ROOT / "config" / "mcp_hybrid_policy.json")
    validation_record.add_argument("--ledger", type=Path, default=ROOT / "cache" / "mcp_hybrid_call_ledger.jsonl")

    validation_finalize = sub.add_parser(
        "finalize-validation-task",
        help="verify all 91 claims and raw archives, then close the sealed validation plan",
    )
    validation_finalize.add_argument("--task", type=Path, required=True)
    validation_finalize.add_argument("--summary", type=Path, required=True)
    validation_finalize.add_argument("--test-mode", action="store_true")
    validation_finalize.add_argument("--bridge", type=Path, default=ROOT / "scripts" / "mcp_hybrid_bridge.py")
    validation_finalize.add_argument("--policy", type=Path, default=ROOT / "config" / "mcp_hybrid_policy.json")
    validation_finalize.add_argument("--ledger", type=Path, default=ROOT / "cache" / "mcp_hybrid_call_ledger.jsonl")

    validation_inspect = sub.add_parser("inspect-validation-task", help="print sealed validation task status")
    validation_inspect.add_argument("--task", type=Path, required=True)

    plan = sub.add_parser("plan", help="validate prefiltered candidates and create durable MCP packets")
    plan.add_argument("--input", type=Path, required=True)
    plan.add_argument("--workflow", type=Path, required=True)
    plan.add_argument("--run-id", default="")
    plan.add_argument("--tool", default="keepa_info")
    plan.add_argument("--primary-limit", type=int, default=MAX_PRIMARY_CALLS)
    plan.add_argument("--conditional-limit", type=int, default=100)
    plan.add_argument("--emergency-limit", type=int, default=100)
    plan.add_argument("--enable-conditional", action="store_true")
    plan.add_argument("--enable-emergency", action="store_true")
    plan.add_argument("--test-only-allow-pending-tool", action="store_true")
    plan.add_argument("--reserve", action="store_true")
    plan.add_argument(
        "--reserve-test-only",
        action="store_true",
        help="atomically reserve a pending tool through a Bridge ledger in explicit test mode",
    )
    plan.add_argument("--bridge", type=Path, default=ROOT / "scripts" / "mcp_hybrid_bridge.py")
    plan.add_argument("--policy", type=Path, default=ROOT / "config" / "mcp_hybrid_policy.json")
    plan.add_argument("--ledger", type=Path, default=ROOT / "cache" / "mcp_hybrid_call_ledger.jsonl")

    claim = sub.add_parser("claim", help="atomically claim one reserved packet before the MCP call")
    claim.add_argument("--workflow", type=Path, required=True)
    claim.add_argument("--packet-id", required=True)
    claim.add_argument("--executor-id", required=True)
    claim.add_argument("--bridge", type=Path, default=ROOT / "scripts" / "mcp_hybrid_bridge.py")
    claim.add_argument("--policy", type=Path, default=ROOT / "config" / "mcp_hybrid_policy.json")
    claim.add_argument("--ledger", type=Path, default=ROOT / "cache" / "mcp_hybrid_call_ledger.jsonl")

    reconcile_reserve = sub.add_parser(
        "reconcile-reservation",
        help="attach an exact unclaimed Bridge reservation after a local write interruption",
    )
    reconcile_reserve.add_argument("--workflow", type=Path, required=True)
    reconcile_reserve.add_argument("--bridge", type=Path, default=ROOT / "scripts" / "mcp_hybrid_bridge.py")
    reconcile_reserve.add_argument("--policy", type=Path, default=ROOT / "config" / "mcp_hybrid_policy.json")
    reconcile_reserve.add_argument("--ledger", type=Path, default=ROOT / "cache" / "mcp_hybrid_call_ledger.jsonl")

    reconcile_claim = sub.add_parser(
        "reconcile-claim",
        help="mark an interrupted Bridge claim failed without retrying the MCP call",
    )
    reconcile_claim.add_argument("--workflow", type=Path, required=True)
    reconcile_claim.add_argument("--packet-id", required=True)
    reconcile_claim.add_argument("--bridge", type=Path, default=ROOT / "scripts" / "mcp_hybrid_bridge.py")
    reconcile_claim.add_argument("--policy", type=Path, default=ROOT / "config" / "mcp_hybrid_policy.json")
    reconcile_claim.add_argument("--ledger", type=Path, default=ROOT / "cache" / "mcp_hybrid_call_ledger.jsonl")

    record = sub.add_parser("record", help="record one claimed terminal packet result; retries are forbidden")
    record.add_argument("--workflow", type=Path, required=True)
    record.add_argument("--result", type=Path, required=True)
    record.add_argument("--claim-token", required=True)

    pause = sub.add_parser("pause", help="pause a durable workflow")
    pause.add_argument("--workflow", type=Path, required=True)
    pause.add_argument("--reason", required=True)

    resume = sub.add_parser("resume", help="resume a paused workflow")
    resume.add_argument("--workflow", type=Path, required=True)

    finalize = sub.add_parser("finalize", help="build a non-authoritative evidence bundle")
    finalize.add_argument("--workflow", type=Path, required=True)
    finalize.add_argument("--bundle", type=Path, required=True)
    finalize.add_argument("--bridge", type=Path, default=ROOT / "scripts" / "mcp_hybrid_bridge.py")
    finalize.add_argument("--policy", type=Path, default=ROOT / "config" / "mcp_hybrid_policy.json")
    finalize.add_argument("--ledger", type=Path, default=ROOT / "cache" / "mcp_hybrid_call_ledger.jsonl")

    inspect = sub.add_parser("inspect", help="print a compact workflow status")
    inspect.add_argument("--workflow", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        if args.command == "plan-validation-task":
            with workflow_file_lock(args.task):
                if args.task.exists():
                    raise OrchestratorError("task_exists", f"refusing to overwrite validation task: {args.task}")
                task = plan_validation_task(
                    read_json(args.sample_plan),
                    sample_sha256=file_sha256(args.sample_plan),
                    discovery_request=read_json(args.discovery_request),
                    run_id=args.run_id,
                )
                atomic_write_json(args.task, task)
            print(json.dumps(validation_task_summary(task), ensure_ascii=False, indent=2))
            return 0

        if args.command == "reserve-validation-task":
            if not args.test_mode:
                raise OrchestratorError("test_mode_required", "--test-mode is required for validation reservation")
            with workflow_file_lock(args.task):
                task = validate_validation_task(read_json(args.task))
                if task.get("reservation") is not None:
                    raise OrchestratorError("reservation_conflict", "validation task is already reserved")
                ledger = load_validation_task_ledger(
                    args.bridge,
                    args.policy,
                    args.ledger,
                    task,
                    test_mode=True,
                )
                reservation = reserve_validation_task_with_bridge_ledger(ledger, task)
                task = attach_validation_task_reservation(
                    task,
                    reservation,
                    ledger_path=args.ledger,
                    policy_path=args.policy,
                )
                atomic_write_json(args.task, task)
            print(json.dumps(validation_task_summary(task), ensure_ascii=False, indent=2))
            return 0

        if args.command == "claim-validation-task":
            if not args.test_mode:
                raise OrchestratorError("test_mode_required", "--test-mode is required for validation claims")
            with workflow_file_lock(args.task):
                task = validate_validation_task(read_json(args.task))
                ledger = load_validation_task_ledger(
                    args.bridge,
                    args.policy,
                    args.ledger,
                    task,
                    test_mode=True,
                )
                task, claim_token = claim_validation_task_request(
                    ledger,
                    task,
                    request_id=args.request_id,
                    executor_id=args.executor_id,
                )
                atomic_write_json(args.task, task)
            summary = validation_task_summary(task)
            summary["requestId"] = args.request_id
            summary["claimToken"] = claim_token
            print(json.dumps(summary, ensure_ascii=False, indent=2))
            return 0

        if args.command == "record-validation-task":
            if not args.test_mode:
                raise OrchestratorError("test_mode_required", "--test-mode is required for validation results")
            with workflow_file_lock(args.task):
                task = validate_validation_task(read_json(args.task))
                ledger = load_validation_task_ledger(
                    args.bridge,
                    args.policy,
                    args.ledger,
                    task,
                    test_mode=True,
                )
                archive_root = args.task.parent / task["storage"]["rawResponseDirectory"]
                result_value = read_json(args.result)
                task, changed = record_validation_task_result(
                    ledger,
                    task,
                    result_value,
                    raw_response_path=args.raw_response,
                    archive_root=archive_root,
                    claim_token=args.claim_token,
                )
                if changed:
                    atomic_write_json(args.task, task)
            summary = validation_task_summary(task)
            summary["requestId"] = result_value.get("requestId") if isinstance(result_value, dict) else None
            summary["changed"] = changed
            print(json.dumps(summary, ensure_ascii=False, indent=2))
            return 0

        if args.command == "finalize-validation-task":
            if not args.test_mode:
                raise OrchestratorError("test_mode_required", "--test-mode is required for validation finalization")
            with workflow_file_lock(args.task):
                task = validate_validation_task(read_json(args.task))
                ledger = load_validation_task_ledger(
                    args.bridge,
                    args.policy,
                    args.ledger,
                    task,
                    test_mode=True,
                )
                archive_root = args.task.parent / task["storage"]["rawResponseDirectory"]
                task, final_summary = finalize_validation_task(
                    ledger,
                    task,
                    summary_path=args.summary,
                    archive_root=archive_root,
                )
                atomic_write_json(args.summary, final_summary)
                atomic_write_json(args.task, task)
            summary = validation_task_summary(task)
            summary["summary"] = str(args.summary.resolve())
            print(json.dumps(summary, ensure_ascii=False, indent=2))
            return 0

        if args.command == "inspect-validation-task":
            with workflow_file_lock(args.task):
                task = validate_validation_task(read_json(args.task))
            print(json.dumps(validation_task_summary(task), ensure_ascii=False, indent=2))
            return 0

        if args.command == "plan":
            with workflow_file_lock(args.workflow):
                if args.workflow.exists():
                    raise OrchestratorError("workflow_exists", f"refusing to overwrite workflow: {args.workflow}")
                candidate_payload = read_json(args.input)
                if args.run_id and candidate_payload.get("runId") != args.run_id:
                    raise OrchestratorError("workflow_mismatch", "--run-id does not match candidate document")
                if args.reserve_test_only and not args.test_only_allow_pending_tool:
                    raise OrchestratorError(
                        "test_mode_required",
                        "--reserve-test-only requires --test-only-allow-pending-tool",
                    )
                if args.reserve and args.reserve_test_only:
                    raise OrchestratorError("invalid_reservation", "choose either --reserve or --reserve-test-only")
                workflow = plan_workflow(
                    candidate_payload,
                    input_sha256=file_sha256(args.input),
                    tool=args.tool,
                    primary_limit=args.primary_limit,
                    conditional_limit=args.conditional_limit,
                    emergency_limit=args.emergency_limit,
                    enable_conditional=args.enable_conditional,
                    enable_emergency=args.enable_emergency,
                    test_only_allow_pending_tool=args.test_only_allow_pending_tool,
                    test_only_reserve_pending=args.reserve_test_only,
                )
                atomic_write_json(args.workflow, workflow)
                if args.reserve or args.reserve_test_only:
                    try:
                        ledger = load_bridge_ledger(
                            args.bridge,
                            args.policy,
                            args.ledger,
                            workflow,
                            test_mode=args.reserve_test_only,
                        )
                        reservation = reserve_with_bridge_ledger(ledger, workflow)
                        attach_reservation(
                            workflow,
                            reservation,
                            ledger_path=args.ledger,
                            policy_path=args.policy,
                        )
                        atomic_write_json(args.workflow, workflow)
                    except OrchestratorError as error:
                        timestamp = now_iso()
                        workflow["status"] = "reservation_failed"
                        workflow["updatedAt"] = timestamp
                        workflow["reservation"] = {
                            "status": "failed",
                            "at": timestamp,
                            "error": {"code": error.code, "message": str(error), "details": error.details},
                        }
                        workflow["history"].append(
                            {"at": timestamp, "event": "reservation_failed", "code": error.code}
                        )
                        atomic_write_json(args.workflow, workflow)
                        raise
            print(json.dumps(workflow_summary(workflow), ensure_ascii=False, indent=2))
            return 0

        if args.command == "reconcile-reservation":
            with workflow_file_lock(args.workflow):
                workflow = validate_workflow(read_json(args.workflow))
                ledger = load_bridge_ledger(
                    args.bridge,
                    args.policy,
                    args.ledger,
                    workflow,
                    test_mode=bool(workflow["toolRouting"].get("testOnlyReservation")),
                )
                workflow = reconcile_reservation(
                    ledger,
                    workflow,
                    ledger_path=args.ledger,
                    policy_path=args.policy,
                )
                atomic_write_json(args.workflow, workflow)
            print(json.dumps(workflow_summary(workflow), ensure_ascii=False, indent=2))
            return 0

        if args.command == "claim":
            with workflow_file_lock(args.workflow):
                workflow = validate_workflow(read_json(args.workflow))
                ledger = load_bridge_ledger(
                    args.bridge,
                    args.policy,
                    args.ledger,
                    workflow,
                    test_mode=bool(workflow["toolRouting"].get("testOnlyReservation")),
                )
                workflow, claim_token = claim_packet(
                    ledger,
                    workflow,
                    packet_id=args.packet_id,
                    executor_id=args.executor_id,
                )
                atomic_write_json(args.workflow, workflow)
            summary = workflow_summary(workflow)
            summary["packetId"] = args.packet_id
            summary["claimToken"] = claim_token
            print(json.dumps(summary, ensure_ascii=False, indent=2))
            return 0

        if args.command == "reconcile-claim":
            with workflow_file_lock(args.workflow):
                workflow = validate_workflow(read_json(args.workflow))
                ledger = load_bridge_ledger(
                    args.bridge,
                    args.policy,
                    args.ledger,
                    workflow,
                    test_mode=bool(workflow["toolRouting"].get("testOnlyReservation")),
                )
                workflow = reconcile_claim_as_failed(
                    ledger,
                    workflow,
                    packet_id=args.packet_id,
                )
                atomic_write_json(args.workflow, workflow)
            print(json.dumps(workflow_summary(workflow), ensure_ascii=False, indent=2))
            return 0

        if args.command == "record":
            with workflow_file_lock(args.workflow):
                workflow = validate_workflow(read_json(args.workflow))
                workflow, changed = record_result(
                    workflow,
                    read_json(args.result),
                    claim_token=args.claim_token,
                )
                if changed:
                    atomic_write_json(args.workflow, workflow)
            summary = workflow_summary(workflow)
            summary["changed"] = changed
            print(json.dumps(summary, ensure_ascii=False, indent=2))
            return 0
        if args.command == "pause":
            with workflow_file_lock(args.workflow):
                workflow = validate_workflow(read_json(args.workflow))
                workflow = pause_workflow(workflow, args.reason)
                atomic_write_json(args.workflow, workflow)
            print(json.dumps(workflow_summary(workflow), ensure_ascii=False, indent=2))
            return 0
        if args.command == "resume":
            with workflow_file_lock(args.workflow):
                workflow = validate_workflow(read_json(args.workflow))
                workflow = resume_workflow(workflow)
                atomic_write_json(args.workflow, workflow)
            print(json.dumps(workflow_summary(workflow), ensure_ascii=False, indent=2))
            return 0
        if args.command == "finalize":
            with workflow_file_lock(args.workflow):
                workflow = validate_workflow(read_json(args.workflow))
                ledger = load_bridge_ledger(
                    args.bridge,
                    args.policy,
                    args.ledger,
                    workflow,
                    test_mode=bool(workflow["toolRouting"].get("testOnlyReservation")),
                )
                workflow, bundle = finalize_workflow(workflow, ledger=ledger)
                atomic_write_json(args.bundle, bundle)
                workflow["finalization"]["bundlePath"] = str(args.bundle.resolve())
                atomic_write_json(args.workflow, workflow)
            print(json.dumps({**workflow_summary(workflow), "bundle": str(args.bundle), "evidence": len(bundle["evidence"])}, ensure_ascii=False, indent=2))
            return 0
        with workflow_file_lock(args.workflow):
            workflow = validate_workflow(read_json(args.workflow))
        print(json.dumps(workflow_summary(workflow), ensure_ascii=False, indent=2))
        return 0
    except (OSError, json.JSONDecodeError, OrchestratorError) as error:
        code = error.code if isinstance(error, OrchestratorError) else "io_error"
        details = error.details if isinstance(error, OrchestratorError) else None
        print(
            json.dumps(
                {
                    "schemaVersion": "sellerSpriteMcpPrefetchError/v1",
                    "ok": False,
                    "code": code,
                    "message": str(error),
                    "details": details,
                    "finalAuthority": False,
                },
                ensure_ascii=False,
                indent=2,
            ),
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
