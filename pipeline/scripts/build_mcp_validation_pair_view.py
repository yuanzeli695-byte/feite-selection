#!/usr/bin/env python3
"""Build a fail-closed paired-analysis view from official validation artifacts.

This program is intentionally offline. It does not import the MCP Bridge, touch
the quota ledger, reserve calls, or invoke any provider tool. The output is a
derived, non-authoritative view for ``analyze_mcp_validation_task_pair.py``.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
ORCHESTRATOR_PATH = ROOT / "scripts" / "mcp_hybrid_prefetch_orchestrator.py"

PLAN_SCHEMA = "sellerSpriteMcpShadowPlan/v1"
BASELINE_SCHEMA = "sellerSpriteMcpShadowBaseline/v1"
TASK_SCHEMA = "sellerSpriteMcpValidationTask/v1"
OFFICIAL_RESULT_SCHEMA = "sellerSpriteMcpValidationTaskResult/v1"
OFFICIAL_SUMMARY_SCHEMA = "sellerSpriteMcpValidationTaskFinalSummary/v1"
VIEW_SCHEMA = "sellerSpriteMcpValidationPairedView/v1"
ROW_SCHEMA = "sellerSpriteMcpValidationNormalizedView/v1"
PAIRED_OUTCOMES_SCHEMA = "sellerSpriteMcpHybridPairedOutcomes/v1"
SMOKE_SCHEMA = "sellerSpriteMcpHybridBrowserSmoke/v1"

ASIN_RE = re.compile(r"^B0[A-Z0-9]{8}$")
SHA256_RE = re.compile(r"^[a-f0-9]{64}$")
TERMINAL_STATUSES = {"succeeded", "partial", "failed"}
TOOL_COUNTS = {
    "product_research": 1,
    "asin_detail": 30,
    "asin_sales_trend": 30,
    "traffic_listing_stat": 30,
}
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


class BuildError(ValueError):
    pass


def load_module(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise BuildError(f"cannot load module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def read_json_value(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise BuildError(f"cannot read JSON {path}: {error}") from error


def read_json_object(path: Path) -> dict[str, Any]:
    value = read_json_value(path)
    if not isinstance(value, dict):
        raise BuildError(f"top-level JSON must be an object: {path}")
    return value


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as error:
        raise BuildError(f"cannot hash file {path}: {error}") from error
    return digest.hexdigest()


def payload_sha256(value: Any) -> str:
    payload = (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode(
        "utf-8"
    )
    return hashlib.sha256(payload).hexdigest()


def file_record(path: Path) -> dict[str, Any]:
    resolved = path.resolve()
    if not resolved.is_file():
        raise BuildError(f"required file is missing: {resolved}")
    return {
        "path": str(resolved),
        "sha256": file_sha256(resolved),
        "byteLength": resolved.stat().st_size,
    }


def normalize_asin(value: Any, field: str = "asin") -> str:
    asin = str(value or "").strip().upper()
    if not ASIN_RE.fullmatch(asin):
        raise BuildError(f"{field} is not a valid ASIN: {value!r}")
    return asin


def number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def nonempty(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, dict)):
        return bool(value)
    return True


def unwrap_text_content(value: Any) -> Any:
    if not isinstance(value, list):
        return None
    decoded: list[Any] = []
    for item in value:
        if not isinstance(item, dict) or item.get("type") != "text":
            continue
        text = item.get("text")
        if not isinstance(text, str) or not text.strip():
            continue
        try:
            decoded.append(json.loads(text))
        except json.JSONDecodeError as error:
            raise BuildError("MCP text content is not valid JSON") from error
    if len(decoded) != 1:
        raise BuildError("raw MCP response must contain exactly one JSON text block")
    return decoded[0]


def provider_payload(raw: Any) -> dict[str, Any]:
    """Unwrap known MCP capture envelopes without guessing provider fields."""
    if not isinstance(raw, dict):
        raise BuildError("raw response must be a JSON object")
    candidates: list[Any] = []
    if isinstance(raw.get("payload"), dict):
        candidates.append(raw["payload"])
    if isinstance(raw.get("structuredContent"), dict):
        candidates.append(raw["structuredContent"])
    result = raw.get("result")
    if isinstance(result, dict):
        if result.get("isError") is True:
            raise BuildError("MCP result is marked isError=true")
        if isinstance(result.get("structuredContent"), dict):
            candidates.append(result["structuredContent"])
        if result.get("content") is not None:
            candidates.append(unwrap_text_content(result.get("content")))
    if raw.get("content") is not None:
        if raw.get("isError") is True:
            raise BuildError("MCP result is marked isError=true")
        candidates.append(unwrap_text_content(raw.get("content")))
    if "code" in raw or "data" in raw:
        candidates.append(raw)
    candidates = [item for item in candidates if isinstance(item, dict)]
    unique = {payload_sha256(item): item for item in candidates}
    if len(unique) != 1:
        raise BuildError("raw response has no unique supported provider payload")
    payload = next(iter(unique.values()))
    if str(payload.get("code") or "").upper() != "OK":
        raise BuildError(f"provider response code is not OK: {payload.get('code')!r}")
    return payload


def response_data(payload: dict[str, Any]) -> Any:
    if "data" not in payload:
        raise BuildError("provider payload is missing data")
    return payload["data"]


def find_candidate_list(value: Any, depth: int = 0) -> list[Any] | None:
    if depth > 5:
        return None
    if isinstance(value, list):
        if not value or all(isinstance(item, dict) for item in value):
            return value
        return None
    if not isinstance(value, dict):
        return None
    for key in ("candidates", "products", "items", "results", "records", "list", "rows"):
        child = value.get(key)
        if isinstance(child, list):
            return child
    for key in ("data", "result", "page", "content"):
        found = find_candidate_list(value.get(key), depth + 1)
        if found is not None:
            return found
    return None


def candidate_asin(value: dict[str, Any]) -> str:
    for key in ("asin", "childAsin", "productAsin"):
        if nonempty(value.get(key)):
            return normalize_asin(value[key], f"candidate.{key}")
    raise BuildError("product_research candidate is missing ASIN")


def normalize_product_research(data: Any) -> tuple[dict[str, Any], dict[str, Any], str | None]:
    candidates = find_candidate_list(data)
    if candidates is None:
        raise BuildError("product_research response has no recognized candidate list")
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    aliases = {
        "reviews": ("reviews", "ratings", "reviewCount", "ratingsCount"),
        "variations": ("variations", "variationCount", "variants"),
        "amzUnit": ("amzUnit", "totalUnits", "monthlySales", "sales"),
    }
    for index, item in enumerate(candidates):
        if not isinstance(item, dict):
            raise BuildError(f"product_research candidate[{index}] is not an object")
        asin = candidate_asin(item)
        if asin in seen:
            raise BuildError(f"product_research contains duplicate ASIN: {asin}")
        seen.add(asin)
        row = {"asin": asin}
        for field in ("title", "brand", "price", "rating", "imageUrl", "categoryPath", "parentAsin"):
            if field in item:
                row[field] = item.get(field)
        for target, source_keys in aliases.items():
            for key in source_keys:
                if key in item:
                    row[target] = item.get(key)
                    break
        normalized.append(row)
    fields = {"candidates": normalized}
    provenance = {
        "candidates": {
            "sourceTool": "product_research",
            "sourcePath": "data.[candidates|products|items|results|records|list|rows]",
            "semantics": "discovery_only_candidate_page_not_a_f_authority",
        }
    }
    return fields, provenance, None


def normalize_detail(data: Any, target: str) -> tuple[dict[str, Any], dict[str, Any], str]:
    if not isinstance(data, dict):
        raise BuildError("asin_detail data must be an object")
    actual = normalize_asin(data.get("asin"), "asin_detail.data.asin")
    if actual != target:
        raise BuildError(f"asin_detail ASIN mismatch: target={target}, actual={actual}")
    fields = {"asin": actual, **{field: data.get(field) for field in DETAIL_FIELDS}}
    provenance = {
        field: {
            "sourceTool": "asin_detail",
            "sourcePath": f"data.{field}",
            "semantics": "shadow_advisory_exact_provider_value",
        }
        for field in DETAIL_FIELDS
        if nonempty(fields.get(field))
    }
    return fields, provenance, actual


def classify_price_samples(points: list[dict[str, Any]]) -> str:
    clean = []
    for index, row in enumerate(points):
        if not isinstance(row, dict):
            continue
        price = number(row.get("price", row.get("averagePrice")))
        label = str(row.get("month") or row.get("date") or index)
        if price is not None and price > 0:
            clean.append({"label": label, "price": price})
    if len(clean) < 3:
        return "no_data"
    prices = [row["price"] for row in clean]
    group_size = max(1, math.ceil(len(prices) / 3))
    first_average = sum(prices[:group_size]) / group_size
    last_average = sum(prices[-group_size:]) / group_size
    current = prices[-1]
    minimum = min(prices)
    maximum = max(prices)
    change_pct = (last_average - first_average) / first_average if first_average else 0
    range_pct = (maximum - minimum) / minimum if minimum else 0
    peak_to_current = (maximum - current) / maximum if maximum else 0
    reversals = 0
    previous_direction = 0
    for index in range(1, len(prices)):
        base = prices[index - 1] or 1
        delta_pct = (prices[index] - prices[index - 1]) / base
        direction = 0 if abs(delta_pct) < 0.01 else (1 if delta_pct > 0 else -1)
        if direction and previous_direction and direction != previous_direction:
            reversals += 1
        if direction:
            previous_direction = direction
    if change_pct <= -0.08 or (peak_to_current >= 0.12 and current <= minimum * 1.03):
        return "declining"
    if range_pct >= 0.35 and reversals >= 2:
        return "volatile"
    if change_pct >= 0.05 or (current >= maximum * 0.97 and current > first_average * 1.03):
        return "rising"
    if range_pct <= 0.20 or abs(change_pct) < 0.05:
        return "stable"
    return "volatile"


def normalize_sales_trend(data: Any, target: str) -> tuple[dict[str, Any], dict[str, Any], str]:
    if not isinstance(data, dict):
        raise BuildError("asin_sales_trend data must be an object")
    identity = data.get("asin")
    actual_value = identity.get("asin") if isinstance(identity, dict) else identity
    actual = normalize_asin(actual_value, "asin_sales_trend.data.asin")
    if actual != target:
        raise BuildError(f"asin_sales_trend ASIN mismatch: target={target}, actual={actual}")
    points = data.get("salesTrendPoints")
    if not isinstance(points, list):
        raise BuildError("asin_sales_trend data.salesTrendPoints must be an array")
    price_point_count = sum(
        isinstance(row, dict) and (number(row.get("price", row.get("averagePrice"))) or 0) > 0
        for row in points
    )
    fields = {
        "asin": actual,
        "priceTrendClass": classify_price_samples(points),
        "pricePointCount": price_point_count,
    }
    provenance = {
        "priceTrendClass": {
            "sourceTool": "asin_sales_trend",
            "sourcePath": "data.salesTrendPoints[].price",
            "semantics": "shadow_advisory_existing_runner_price_classifier_v1",
        },
        "pricePointCount": {
            "sourceTool": "asin_sales_trend",
            "sourcePath": "data.salesTrendPoints",
            "semantics": "shadow_advisory_positive_price_point_count",
        },
    }
    return fields, provenance, actual


def normalize_traffic(data: Any, target: str) -> tuple[dict[str, Any], dict[str, Any], str]:
    if not isinstance(data, dict):
        raise BuildError("traffic_listing_stat data must be an object")
    actual = normalize_asin(data.get("asin"), "traffic_listing_stat.data.asin")
    if actual != target:
        raise BuildError(f"traffic_listing_stat ASIN mismatch: target={target}, actual={actual}")
    free_count = number(data.get("freeRelations"))
    paid_count = number(data.get("paidRelations"))
    total = number(data.get("relations"))
    if free_count is None or paid_count is None or free_count < 0 or paid_count < 0:
        raise BuildError("traffic_listing_stat is missing non-negative free/paid relation counts")
    if total is None:
        total = free_count + paid_count
    if total < 0 or abs(total - (free_count + paid_count)) > 0.001:
        raise BuildError("traffic_listing_stat relation total does not equal free + paid")
    items = data.get("items")
    if not isinstance(items, list):
        raise BuildError("traffic_listing_stat data.items must be an array")
    relation_counts: dict[str, float] = {}
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise BuildError(f"traffic_listing_stat items[{index}] is not an object")
        relation = str(item.get("relation") or "").strip().casefold()
        count = number(item.get("count"))
        if not relation or count is None or count < 0 or relation in relation_counts:
            raise BuildError(f"traffic_listing_stat items[{index}] is invalid or duplicate")
        relation_counts[relation] = count
    if abs(sum(relation_counts.values()) - total) > 0.001:
        raise BuildError("traffic_listing_stat relation code counts do not equal total")
    fields = {
        "asin": actual,
        "freeTrafficCount": free_count,
        "paidTrafficCount": paid_count,
        "freeTrafficShare": free_count / total if total else 0.0,
        "paidTrafficShare": paid_count / total if total else 0.0,
        "relationCounts": relation_counts,
    }
    paths = {
        "freeTrafficCount": "data.freeRelations",
        "paidTrafficCount": "data.paidRelations",
        "freeTrafficShare": "data.freeRelations/data.relations",
        "paidTrafficShare": "data.paidRelations/data.relations",
        "relationCounts": "data.items[{relation,count}]",
    }
    provenance = {
        field: {
            "sourceTool": "traffic_listing_stat",
            "sourcePath": paths[field],
            "semantics": "traffic_structure_advisory_not_gate_c",
        }
        for field in paths
    }
    return fields, provenance, actual


def normalize_official_result(item: dict[str, Any], raw: Any) -> dict[str, Any]:
    official = item["result"]
    tool = item["tool"]
    target = item.get("targetAsin")
    status = official["status"]
    fields: dict[str, Any] = {}
    provenance: dict[str, Any] = {}
    actual = official.get("actualAsin")
    normalization_error = None
    if status == "failed":
        if actual is not None:
            raise BuildError(f"failed result cannot claim actualAsin: {item['requestId']}")
    else:
        try:
            data = response_data(provider_payload(raw))
            if tool == "product_research":
                fields, provenance, actual = normalize_product_research(data)
            elif tool == "asin_detail":
                fields, provenance, actual = normalize_detail(data, target)
            elif tool == "asin_sales_trend":
                fields, provenance, actual = normalize_sales_trend(data, target)
            elif tool == "traffic_listing_stat":
                fields, provenance, actual = normalize_traffic(data, target)
            else:
                raise BuildError(f"unsupported validation tool: {tool}")
        except BuildError as error:
            normalization_error = str(error)
            fields = {}
            provenance = {}
    effective_status = status
    error = official.get("error")
    if normalization_error:
        effective_status = "failed"
        actual = None if tool != "product_research" else None
        error = {
            "code": "normalization_failed",
            "message": normalization_error,
            "retryable": False,
        }
    archive = item["rawResponseArchive"]
    return {
        "schemaVersion": ROW_SCHEMA,
        "taskId": official["taskId"],
        "runId": official["runId"],
        "requestId": official["requestId"],
        "requestHash": official["requestHash"],
        "claimId": official["claimId"],
        "targetAsin": target,
        "actualAsin": actual,
        "tool": official["tool"],
        "status": effective_status,
        "officialStatus": status,
        "startedAt": official["startedAt"],
        "completedAt": official["completedAt"],
        "sourceResultSchema": OFFICIAL_RESULT_SCHEMA,
        "sourceResultSha256": item["resultSha256"],
        "derivedFromOfficialTaskResult": True,
        "rawResponse": {
            "path": str(Path(archive["path"]).resolve()),
            "sha256": archive["sha256"],
            "byteLength": archive["byteLength"],
            "capturedAt": official["rawResponse"]["capturedAt"],
        },
        "fields": fields,
        "fieldProvenance": provenance,
        "normalizationError": normalization_error,
        "error": error,
        "browserFallbackRequired": True,
        "usableForFinal": False,
        "finalAuthority": False,
    }


def validate_plan_and_baseline(
    plan: dict[str, Any], baseline: dict[str, Any], *, plan_hash: str
) -> tuple[list[str], dict[str, dict[str, Any]]]:
    if plan.get("schemaVersion") != PLAN_SCHEMA or plan.get("marketplace") != "US":
        raise BuildError("shadow plan must use sellerSpriteMcpShadowPlan/v1 for US")
    sample = plan.get("sample")
    if not isinstance(sample, list) or len(sample) != 30:
        raise BuildError("shadow plan must contain exactly 30 rows")
    expected: dict[str, str] = {}
    ordered = []
    for index, row in enumerate(sample):
        if not isinstance(row, dict):
            raise BuildError(f"plan sample[{index}] is not an object")
        asin = normalize_asin(row.get("asin"), f"plan sample[{index}].asin")
        outcome = str(row.get("expectedOutcome") or "")
        if asin in expected or outcome not in {"pass", "reject"}:
            raise BuildError(f"plan sample[{index}] has duplicate ASIN or invalid outcome")
        expected[asin] = outcome
        ordered.append(asin)
    if baseline.get("schemaVersion") != BASELINE_SCHEMA or baseline.get("planId") != plan.get("planId"):
        raise BuildError("browser baseline is not bound to the shadow plan")
    rows = baseline.get("rows")
    if not isinstance(rows, list) or len(rows) != 30:
        raise BuildError("browser baseline must contain exactly 30 rows")
    baseline_by_asin: dict[str, dict[str, Any]] = {}
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise BuildError(f"browser baseline row[{index}] is not an object")
        asin = normalize_asin(row.get("asin"), f"baseline row[{index}].asin")
        browser_outcome = str((((row.get("browser") or {}).get("gate") or {}).get("outcome") or ""))
        if asin not in expected or asin in baseline_by_asin or browser_outcome != expected[asin]:
            raise BuildError(f"browser baseline row mismatch: {asin}")
        baseline_by_asin[asin] = row
    if list(baseline_by_asin) != ordered:
        raise BuildError("browser baseline ASIN order differs from plan")
    if not SHA256_RE.fullmatch(plan_hash):
        raise BuildError("shadow plan hash is invalid")
    return ordered, baseline_by_asin


def validate_official_chain(
    task: dict[str, Any],
    summary: dict[str, Any],
    *,
    task_path: Path,
    summary_path: Path,
) -> tuple[Any, list[dict[str, Any]], dict[str, str]]:
    orchestrator = load_module("mcp_hybrid_prefetch_orchestrator_pair_builder", ORCHESTRATOR_PATH)
    try:
        normalized = orchestrator.validate_validation_task(task)
    except Exception as error:
        raise BuildError(f"official validation task failed orchestrator validation: {error}") from error
    if normalized != task:
        raise BuildError("official validation task is not canonical")
    if task.get("schemaVersion") != TASK_SCHEMA or task.get("status") not in {
        "finalized",
        "finalized_with_failures",
    }:
        raise BuildError("validation task must be officially finalized before paired analysis")
    finalization = task.get("finalization") or {}
    if summary.get("schemaVersion") != OFFICIAL_SUMMARY_SCHEMA:
        raise BuildError("validation summary schema mismatch")
    if summary.get("taskId") != task.get("taskId") or summary.get("runId") != task.get("runId"):
        raise BuildError("validation summary task/run mismatch")
    summary_hash = orchestrator.payload_sha256(summary)
    if finalization.get("summarySha256") != summary_hash:
        raise BuildError("validation summary SHA does not match task finalization")
    if Path(str(finalization.get("summaryPath") or "")).resolve() != summary_path.resolve():
        raise BuildError("validation summary path does not match task finalization")
    if summary.get("finalAuthority") is not False or summary.get("usableForFinal") is not False:
        raise BuildError("validation summary must remain non-authoritative")
    if (
        summary.get("taskBudget") != 100
        or summary.get("authorizedCalls") != 91
        or summary.get("sealedReserveCalls") != 9
        or summary.get("requestCount") != 91
    ):
        raise BuildError("validation summary budget/count contract changed")
    archive_root = task_path.parent / str((task.get("storage") or {}).get("rawResponseDirectory") or "")
    try:
        raw_manifest = orchestrator.verify_validation_raw_archives(task, archive_root)
        manifests = orchestrator.validation_task_manifest_hashes(task, raw_manifest)
    except Exception as error:
        raise BuildError(f"official raw archive verification failed: {error}") from error
    if summary.get("manifestHashes") != manifests or finalization.get("manifestHashes") != manifests:
        raise BuildError("validation manifest hashes disagree")
    requests = task.get("requests") or []
    counts = {status: sum(item.get("status") == status for item in requests) for status in TERMINAL_STATUSES}
    tool_outcomes = {
        tool: {status: sum(item.get("tool") == tool and item.get("status") == status for item in requests) for status in TERMINAL_STATUSES}
        for tool in TOOL_COUNTS
    }
    if summary.get("outcomeCounts") != counts or summary.get("toolOutcomes") != tool_outcomes:
        raise BuildError("validation summary outcome counts disagree with task results")
    expected_summary_rows = [
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
        for item in requests
    ]
    if summary.get("requests") != expected_summary_rows:
        raise BuildError("validation summary request manifest differs from task results")
    return orchestrator, raw_manifest, manifests


def row_asin(row: Any, field: str) -> str:
    if not isinstance(row, dict):
        raise BuildError(f"{field} row is not an object")
    value = row.get("asin")
    if not value and isinstance(row.get("product"), dict):
        value = row["product"].get("asin")
    return normalize_asin(value, field)


def indexed_outcomes(value: Any, *, outcome: str, label: str) -> dict[str, dict[str, Any]]:
    if not isinstance(value, list):
        raise BuildError(f"{label} must be a JSON array")
    indexed: dict[str, dict[str, Any]] = {}
    for index, row in enumerate(value):
        asin = row_asin(row, f"{label}[{index}].asin")
        if asin in indexed:
            raise BuildError(f"{label} contains duplicate ASIN: {asin}")
        indexed[asin] = {"outcome": outcome, "row": row}
    return indexed


def derive_paired_outcomes(
    *,
    plan: dict[str, Any],
    ordered_asins: list[str],
    baseline_by_asin: dict[str, dict[str, Any]],
    final_value: Any,
    rejected_value: Any,
    run_summary: dict[str, Any],
    source_files: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    final_rows = indexed_outcomes(final_value, outcome="pass", label="final candidates")
    rejected_rows = indexed_outcomes(rejected_value, outcome="reject", label="rejected audit")
    overlap = set(final_rows) & set(rejected_rows)
    combined = {**final_rows, **rejected_rows}
    expected = set(ordered_asins)
    if overlap:
        raise BuildError(f"replay ASIN appears in pass and reject artifacts: {sorted(overlap)}")
    if set(combined) != expected:
        raise BuildError(
            f"replay must cover exactly the frozen 30 ASINs; missing={sorted(expected - set(combined))}, "
            f"extra={sorted(set(combined) - expected)}"
        )
    if (
        run_summary.get("attempts") != 30
        or run_summary.get("qualifiedCount") != len(final_rows)
        or run_summary.get("rejectedCount") != len(rejected_rows)
    ):
        raise BuildError("replay run_summary must report attempts=30 with matching pass/reject counts")
    rows = []
    for asin in ordered_asins:
        baseline = baseline_by_asin[asin]
        replay = combined[asin]
        rows.append(
            {
                "asin": asin,
                "baselineOutcome": str((((baseline.get("browser") or {}).get("gate") or {}).get("outcome") or "")),
                "hybridOutcome": replay["outcome"],
                "baselineEvidenceSha256": payload_sha256(baseline),
                "hybridEvidenceSha256": payload_sha256(replay["row"]),
                "outcomeDerivedFrom": "final_candidates_data" if replay["outcome"] == "pass" else "rejected_audit_data",
                "mcpFinalAuthority": False,
                "browserReplayAuthoritative": True,
            }
        )
    return {
        "schemaVersion": PAIRED_OUTCOMES_SCHEMA,
        "planId": plan["planId"],
        "authoritySource": "current_replay_and_acceptance",
        "aToFReplayed": True,
        "derivedFromReplayArtifacts": True,
        "sourceFiles": source_files,
        "finalAuthority": False,
        "rows": rows,
    }


def artifact_lookup(hashes: dict[str, Any]) -> dict[str, dict[str, Any]]:
    indexed = {}
    for section in ("activeCandidate", "validationArtifacts", "rollback"):
        for row in hashes.get(section) or []:
            if isinstance(row, dict) and nonempty(row.get("path")):
                indexed[str(row["path"]).replace("\\", "/")] = row
    return indexed


def verify_declared_artifact(path: Path, declared: dict[str, Any], label: str) -> None:
    if not path.is_file():
        raise BuildError(f"{label} is missing: {path}")
    if declared.get("sha256") != file_sha256(path) or declared.get("bytes") != path.stat().st_size:
        raise BuildError(f"{label} hash/byte declaration does not match the file")


def derive_live_smoke(
    *,
    smoke: dict[str, Any],
    hashes: dict[str, Any],
    smoke_path: Path,
    hashes_path: Path,
    sample_asins: set[str],
    task: dict[str, Any],
    expected_bridge: str,
    expected_assist: str,
    expected_adapter: str,
    expected_collector: str,
    expected_runners: set[str],
) -> dict[str, Any]:
    if smoke.get("schemaVersion") != SMOKE_SCHEMA:
        raise BuildError("browser smoke schema mismatch")
    lookup = artifact_lookup(hashes)
    smoke_relative = smoke_path.resolve().relative_to(ROOT.resolve()).as_posix()
    declared_smoke = lookup.get(smoke_relative)
    if not isinstance(declared_smoke, dict):
        raise BuildError("artifact hash manifest does not declare the browser smoke JSON")
    verify_declared_artifact(smoke_path, declared_smoke, "browser smoke JSON")
    screenshot_name = str(smoke.get("screenshot") or "").strip()
    if not screenshot_name or Path(screenshot_name).name != screenshot_name:
        raise BuildError("browser smoke screenshot must be a sibling filename")
    screenshot_path = smoke_path.parent / screenshot_name
    screenshot_relative = screenshot_path.resolve().relative_to(ROOT.resolve()).as_posix()
    declared_screenshot = lookup.get(screenshot_relative)
    if not isinstance(declared_screenshot, dict):
        raise BuildError("artifact hash manifest does not declare the browser smoke screenshot")
    verify_declared_artifact(screenshot_path, declared_screenshot, "browser smoke screenshot")
    asin = normalize_asin(smoke.get("asin"), "browser smoke.asin")
    versions = smoke.get("versions") if isinstance(smoke.get("versions"), dict) else {}
    current_versions = (
        versions.get("bridge") == expected_bridge
        and versions.get("assist") == expected_assist
        and versions.get("adapter") == expected_adapter
        and str(versions.get("runner") or "") in expected_runners
        and str(versions.get("collector") or "") == expected_collector
    )
    final_attempt = smoke.get("finalAttempt") if isinstance(smoke.get("finalAttempt"), dict) else {}
    preconditions = smoke.get("preconditions") if isinstance(smoke.get("preconditions"), dict) else {}
    budget = smoke.get("budget") if isinstance(smoke.get("budget"), dict) else {}
    authority = smoke.get("authority") if isinstance(smoke.get("authority"), dict) else {}
    before_queue = final_attempt.get("queueBefore")
    after_queue = final_attempt.get("queueAfter")
    queue_unchanged = isinstance(before_queue, list) and before_queue == after_queue
    history_before = preconditions.get("strictQualifiedHistory")
    history_after = final_attempt.get("strictQualifiedHistory")
    provider_before = budget.get("providerCallsBefore")
    provider_after = budget.get("providerCallsAfter")
    task_bound = smoke.get("taskId") == task.get("taskId") and smoke.get("validationRunId") == task.get("runId")
    passed = (
        final_attempt.get("result") == "passed"
        and queue_unchanged
        and final_attempt.get("batchGenerated") is False
        and final_attempt.get("rankingAuditPersisted") is True
        and final_attempt.get("applicationAuditPersisted") is True
        and isinstance(history_before, int)
        and history_before == history_after
        and isinstance(provider_before, int)
        and provider_before == provider_after
        and authority.get("finalAuthority") is False
        and authority.get("formalRunAuthorized") is False
        and authority.get("gateBypassAuthorized") is False
    )
    return {
        "completed": final_attempt.get("result") == "passed",
        "passed": passed,
        "sourceDerived": True,
        "evidenceHashVerified": True,
        "screenshotHashVerified": True,
        "asin": asin,
        "asinInSample": asin in sample_asins,
        "taskBound": task_bound,
        "currentCombination": current_versions,
        "collectorEnabled": str(versions.get("collector") or "") == expected_collector,
        "runnerEnabled": str(versions.get("runner") or "") in expected_runners,
        "browserReplayRequired": True,
        "batchGenerated": final_attempt.get("batchGenerated"),
        "strictHistoryBefore": history_before,
        "strictHistoryAfter": history_after,
        "providerCallsBefore": provider_before,
        "providerCallsAfter": provider_after,
        "queueUnchanged": queue_unchanged,
        "auditsPersisted": (
            final_attempt.get("rankingAuditPersisted") is True
            and final_attempt.get("applicationAuditPersisted") is True
        ),
        "versions": versions,
        "expectedVersions": {
            "bridge": expected_bridge,
            "assist": expected_assist,
            "adapter": expected_adapter,
            "collector": expected_collector,
            "runners": sorted(expected_runners),
        },
        "sourceFiles": {
            "smoke": file_record(smoke_path),
            "hashManifest": file_record(hashes_path),
            "screenshot": file_record(screenshot_path),
        },
        "finalAuthority": False,
        "gateBypassAuthorized": False,
    }


def build_view(
    *,
    plan_path: Path,
    task_path: Path,
    summary_path: Path,
    baseline_path: Path,
    hybrid_final_path: Path,
    hybrid_rejected_path: Path,
    hybrid_run_summary_path: Path,
    smoke_path: Path,
    smoke_hashes_path: Path,
    expected_bridge: str,
    expected_assist: str,
    expected_adapter: str,
    expected_collector: str,
    expected_runners: set[str],
) -> dict[str, Any]:
    plan = read_json_object(plan_path)
    task = read_json_object(task_path)
    summary = read_json_object(summary_path)
    baseline = read_json_object(baseline_path)
    final_value = read_json_value(hybrid_final_path)
    rejected_value = read_json_value(hybrid_rejected_path)
    run_summary = read_json_object(hybrid_run_summary_path)
    smoke = read_json_object(smoke_path)
    smoke_hashes = read_json_object(smoke_hashes_path)
    plan_record = file_record(plan_path)
    ordered_asins, baseline_by_asin = validate_plan_and_baseline(
        plan, baseline, plan_hash=plan_record["sha256"]
    )
    if (task.get("source") or {}).get("samplePlanId") != plan.get("planId"):
        raise BuildError("official task samplePlanId differs from shadow plan")
    if (task.get("source") or {}).get("samplePlanSha256") != plan_record["sha256"]:
        raise BuildError("official task samplePlanSha256 differs from the exact shadow plan file")
    if (task.get("source") or {}).get("sampleAsins") != ordered_asins:
        raise BuildError("official task sample ASIN order differs from the frozen plan")
    orchestrator, raw_manifest, manifests = validate_official_chain(
        task, summary, task_path=task_path, summary_path=summary_path
    )
    normalized_results = []
    for item in task["requests"]:
        raw_path = Path(item["rawResponseArchive"]["path"])
        raw = read_json_value(raw_path)
        normalized_results.append(normalize_official_result(item, raw))
    replay_sources = {
        "finalCandidates": file_record(hybrid_final_path),
        "rejectedAudit": file_record(hybrid_rejected_path),
        "runSummary": file_record(hybrid_run_summary_path),
        "browserBaseline": file_record(baseline_path),
    }
    paired = derive_paired_outcomes(
        plan=plan,
        ordered_asins=ordered_asins,
        baseline_by_asin=baseline_by_asin,
        final_value=final_value,
        rejected_value=rejected_value,
        run_summary=run_summary,
        source_files=replay_sources,
    )
    live_smoke = derive_live_smoke(
        smoke=smoke,
        hashes=smoke_hashes,
        smoke_path=smoke_path,
        hashes_path=smoke_hashes_path,
        sample_asins=set(ordered_asins),
        task=task,
        expected_bridge=expected_bridge,
        expected_assist=expected_assist,
        expected_adapter=expected_adapter,
        expected_collector=expected_collector,
        expected_runners=expected_runners,
    )
    return {
        "schemaVersion": VIEW_SCHEMA,
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "builder": {
            "name": Path(__file__).name,
            "mode": "offline_read_only",
            "mcpCalls": 0,
            "quotaReservations": 0,
        },
        "taskId": task["taskId"],
        "runId": task["runId"],
        "finalAuthority": False,
        "usableForFinal": False,
        "sourceIntegrity": {
            "officialTaskValidated": True,
            "taskFinalized": True,
            "officialSummaryVerified": True,
            "rawArchiveCount": len(raw_manifest),
            "rawArchivesVerified": len(raw_manifest) == 91,
            "officialManifestHashes": manifests,
            "pairedOutcomesDerived": True,
            "liveSmokeDerived": True,
            "files": {
                "plan": plan_record,
                "task": file_record(task_path),
                "summary": file_record(summary_path),
                "baseline": file_record(baseline_path),
                **replay_sources,
            },
            "finalAuthority": False,
        },
        "results": normalized_results,
        "pairedOutcomes": paired,
        "liveSmoke": live_smoke,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build an offline paired view from the official finalized 91-result task"
    )
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--task", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--hybrid-final", type=Path, required=True)
    parser.add_argument("--hybrid-rejected", type=Path, required=True)
    parser.add_argument("--hybrid-run-summary", type=Path, required=True)
    parser.add_argument("--smoke", type=Path, required=True)
    parser.add_argument("--smoke-hashes", type=Path, required=True)
    parser.add_argument("--expected-bridge", default="0.3.2")
    parser.add_argument("--expected-assist", default="0.3.0")
    parser.add_argument("--expected-adapter", default="0.2.0")
    parser.add_argument("--expected-collector", default="0.4.6")
    parser.add_argument("--expected-runner", action="append", default=["0.3.7", "0.3.8.2"])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        view = build_view(
            plan_path=args.plan,
            task_path=args.task,
            summary_path=args.summary,
            baseline_path=args.baseline,
            hybrid_final_path=args.hybrid_final,
            hybrid_rejected_path=args.hybrid_rejected,
            hybrid_run_summary_path=args.hybrid_run_summary,
            smoke_path=args.smoke,
            smoke_hashes_path=args.smoke_hashes,
            expected_bridge=args.expected_bridge,
            expected_assist=args.expected_assist,
            expected_adapter=args.expected_adapter,
            expected_collector=args.expected_collector,
            expected_runners=set(args.expected_runner),
        )
    except BuildError as error:
        print(json.dumps({"schemaVersion": VIEW_SCHEMA, "error": str(error)}, ensure_ascii=False, indent=2))
        return 2
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(view, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "output": str(args.output.resolve()),
                "results": len(view["results"]),
                "rawArchivesVerified": view["sourceIntegrity"]["rawArchiveCount"],
                "pairedRows": len(view["pairedOutcomes"]["rows"]),
                "currentSmoke": view["liveSmoke"]["currentCombination"],
                "mcpCalls": 0,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
