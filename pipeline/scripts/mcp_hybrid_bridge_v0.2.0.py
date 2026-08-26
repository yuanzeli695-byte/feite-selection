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
from dataclasses import dataclass
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_PROJECT_ROOT = SCRIPT_DIR.parent
POLICY_SCHEMA = "sellerSpriteMcpHybridPolicy/v1"
BUNDLE_SCHEMA = "sellerSpriteMcpEvidenceBundle/v1"
EVIDENCE_SCHEMA = "sellerSpriteMcpEvidence/v1"
LEDGER_SCHEMA = "sellerSpriteMcpCallLedgerEvent/v1"
RESPONSE_SCHEMA = "sellerSpriteMcpHybridResponse/v1"
MANIFEST_SCHEMA = "sellerSpriteMcpHybridManifest/v1"
BATCH_LOOKUP_SCHEMA = "sellerSpriteMcpBatchLookup/v1"
MAX_REQUEST_BYTES = 8 * 1024 * 1024
ASIN_RE = re.compile(r"^B0[A-Z0-9]{8}$")
SHA256_RE = re.compile(r"^[a-fA-F0-9]{64}$")
SAFE_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,160}$")
ALLOWED_ORIGINS = {"https://www.amazon.com", "https://amazon.com"}


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


def load_policy(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise BridgeError(f"policy file not found: {path}", stage="startup")
    policy = read_json(path)
    if not isinstance(policy, dict) or policy.get("schemaVersion") != POLICY_SCHEMA:
        raise BridgeError("unsupported MCP hybrid policy schema", stage="startup")
    if policy.get("mode") != "shadow" or policy.get("outboundMcpEnabled") is not False:
        raise BridgeError("version 0.1.0 requires shadow mode with outbound MCP disabled", stage="startup")
    if policy.get("finalAuthority") is not False or policy.get("marketplace") != "US":
        raise BridgeError("policy must be US-only and non-authoritative", stage="startup")
    official = int(policy.get("officialMonthlyLimit") or 0)
    operational = int(policy.get("operationalMonthlyCap") or 0)
    run_budget = int(policy.get("defaultRunBudget") or 0)
    if official < 1 or operational < 1 or operational > official or run_budget < 1:
        raise BridgeError("invalid MCP call-budget policy", stage="startup")
    tools = policy.get("tools")
    if not isinstance(tools, dict) or not tools:
        raise BridgeError("policy must define supported tools", stage="startup")
    for name, tool in tools.items():
        if not SAFE_ID_RE.fullmatch(str(name)) or not isinstance(tool, dict):
            raise BridgeError("invalid tool policy", stage="startup")
        if tool.get("finalGateEligible") is not False:
            raise BridgeError(f"tool {name} must not be final-gate eligible in shadow mode", stage="startup")
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


class CallLedger:
    def __init__(self, path: Path, *, run_id: str, policy: dict[str, Any], run_budget: int | None = None) -> None:
        self.path = path
        self.run_id = run_id
        self.official_limit = int(policy["officialMonthlyLimit"])
        self.operational_cap = int(policy["operationalMonthlyCap"])
        self.run_budget = int(run_budget or policy["defaultRunBudget"])
        if self.run_budget < 1:
            raise BridgeError("run budget must be positive", stage="startup")
        self.lock = threading.Lock()

    def _events(self) -> list[dict[str, Any]]:
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

    def summary(self, at: datetime | None = None) -> dict[str, Any]:
        current = (at or now_utc()).astimezone(timezone.utc)
        month = current.strftime("%Y-%m")
        events = self._events()
        monthly_used = sum(
            int(event.get("calls") or 0)
            for event in events
            if event.get("eventType") == "reserved" and event.get("month") == month
        )
        run_used = sum(
            int(event.get("calls") or 0)
            for event in events
            if event.get("eventType") == "reserved" and event.get("runId") == self.run_id
        )
        official_pct = 100.0 * monthly_used / self.official_limit
        if monthly_used >= self.operational_cap:
            state = "operational_cap"
        elif official_pct >= 75:
            state = "warning"
        else:
            state = "normal"
        return {
            "schemaVersion": "sellerSpriteMcpCallLedgerSummary/v1",
            "runId": self.run_id,
            "month": month,
            "monthlyUsed": monthly_used,
            "officialMonthlyLimit": self.official_limit,
            "operationalMonthlyCap": self.operational_cap,
            "runUsed": run_used,
            "runBudget": self.run_budget,
            "state": state,
        }

    def reserve(
        self,
        *,
        tool: str,
        request_hash: str,
        asin_count: int,
        calls: int = 1,
        at: datetime | None = None,
    ) -> dict[str, Any]:
        if calls < 1 or asin_count < 1:
            raise BridgeError("calls and asinCount must be positive", stage="budget")
        request_hash = require_sha256(request_hash, "requestHash")
        current = (at or now_utc()).astimezone(timezone.utc)
        with self.lock:
            summary = self.summary(current)
            if summary["runUsed"] + calls > self.run_budget:
                raise BridgeError(
                    "run MCP call budget exceeded",
                    status=429,
                    stage="budget",
                    details=summary,
                )
            if summary["monthlyUsed"] + calls > self.operational_cap:
                raise BridgeError(
                    "operational monthly MCP cap exceeded",
                    status=429,
                    stage="budget",
                    details=summary,
                )
            timestamp = current.isoformat(timespec="microseconds").replace("+00:00", "Z")
            event_seed = f"{self.run_id}|{timestamp}|{tool}|{request_hash}|{calls}|{summary['runUsed']}"
            event = {
                "schemaVersion": LEDGER_SCHEMA,
                "eventId": hashlib.sha256(event_seed.encode("utf-8")).hexdigest()[:32],
                "eventType": "reserved",
                "runId": self.run_id,
                "month": current.strftime("%Y-%m"),
                "at": timestamp,
                "tool": tool,
                "requestHash": request_hash,
                "asinCount": asin_count,
                "calls": calls,
            }
            append_jsonl(self.path, event)
            return {"event": event, "summary": self.summary(current)}


class EvidenceStore:
    def __init__(self, root: Path, *, run_id: str, policy: dict[str, Any]) -> None:
        self.root = root
        self.run_id = run_id
        self.policy = policy
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
        if not isinstance(evidence.get("fields"), dict) or not isinstance(evidence.get("fieldProvenance"), dict):
            raise BridgeError("fields and fieldProvenance must be objects")
        missing = evidence.get("missingFields")
        if not isinstance(missing, list) or any(not isinstance(item, str) for item in missing):
            raise BridgeError("missingFields must be a string array")
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
        results: list[dict[str, Any]] = []
        for entry in entries:
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
            fallback_reasons: list[str] = []
            if not fresh:
                fallback_reasons.append("stale")
            if not asin_match:
                fallback_reasons.append("asin_mismatch")
            if evidence.get("fallbackRequired"):
                fallback_reasons.append("source_requested_fallback")
            results.append(
                {
                    "evidence": evidence,
                    "fresh": fresh,
                    "asinMatch": asin_match,
                    "usableForShadow": fresh and asin_match,
                    "usableForFinal": False,
                    "fallbackRequired": bool(fallback_reasons),
                    "fallbackReasons": fallback_reasons,
                }
            )
        return {
            "asin": target,
            "tool": tool or None,
            "checkedAt": current.isoformat(timespec="seconds").replace("+00:00", "Z"),
            "evidenceCount": len(results),
            "results": results,
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
        self.store = EvidenceStore(self.root, run_id=config.run_id, policy=self.policy)
        ledger_path = config.ledger_path or (config.project_root.resolve() / "cache" / "mcp_hybrid_call_ledger.jsonl")
        self.ledger = CallLedger(
            ledger_path,
            run_id=config.run_id,
            policy=self.policy,
            run_budget=config.run_budget,
        )

    def authenticate(self, token: str) -> None:
        if not token or not secrets.compare_digest(token, self.config.token):
            raise BridgeError("invalid bridge token", status=401, stage="auth")

    def health(self) -> dict[str, Any]:
        return {
            "schemaVersion": RESPONSE_SCHEMA,
            "ok": True,
            "version": "0.2.0",
            "runId": self.config.run_id,
            "mode": "shadow",
            "outboundMcpEnabled": False,
            "finalAuthority": False,
            "evidenceCount": self.store.count(),
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
                )
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
    )
    bridge = McpHybridBridge(config)
    server = BridgeHttpServer(("127.0.0.1", args.port), BridgeHandler)
    server.bridge = bridge
    print("SellerSprite MCP Hybrid Bridge 0.1.0 started in SHADOW mode")
    print(f"Service URL: http://127.0.0.1:{args.port}")
    print(f"Session token: {token}")
    print(f"runId: {config.run_id}; runBudget: {bridge.ledger.run_budget}")
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
