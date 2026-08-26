#!/usr/bin/env python3
"""Fail-closed acceptance analysis for the sealed 91-call MCP validation task.

The analyzer is deliberately offline. It never imports the Bridge, reserves
quota, or calls MCP. A result bundle is accepted only for shadow/reorder use;
MCP evidence never becomes A-F authority and traffic_listing_stat never
becomes Gate C evidence.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


PLAN_SCHEMA = "sellerSpriteMcpShadowPlan/v1"
TASK_SCHEMA = "sellerSpriteMcpValidationTask/v1"
TASK_REQUEST_SCHEMA = "sellerSpriteMcpValidationTaskRequest/v1"
BASELINE_SCHEMA = "sellerSpriteMcpShadowBaseline/v1"
RESULTS_SCHEMA = "sellerSpriteMcpValidationPairedView/v1"
RESULT_SCHEMA = "sellerSpriteMcpValidationNormalizedView/v1"
OFFICIAL_RESULT_SCHEMA = "sellerSpriteMcpValidationTaskResult/v1"
PAIRED_OUTCOMES_SCHEMA = "sellerSpriteMcpHybridPairedOutcomes/v1"
REPORT_SCHEMA = "sellerSpriteMcpValidationAcceptance/v1"

ASIN_RE = re.compile(r"^B0[A-Z0-9]{8}$")
SHA256_RE = re.compile(r"^[a-f0-9]{64}$")
EXPECTED_TOOL_COUNTS = {
    "product_research": 1,
    "asin_detail": 30,
    "asin_sales_trend": 30,
    "traffic_listing_stat": 30,
}
ASIN_TOOLS = {"asin_detail", "asin_sales_trend", "traffic_listing_stat"}
TERMINAL_STATUSES = {"succeeded", "partial", "failed"}
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
DETAIL_IDENTITY_FIELDS = ("title", "brand", "imageUrl")
DETAIL_THRESHOLD_FIELDS = ("price", "rating", "reviews", "variations")
TRAFFIC_FIELDS = (
    "freeTrafficCount",
    "paidTrafficCount",
    "freeTrafficShare",
    "paidTrafficShare",
    "relationCounts",
)
TRAFFIC_GATE_C_KEYS = {
    "gatec",
    "gatecdecision",
    "gatecstatus",
    "weeksread",
    "latestnaturalsharepct",
    "recent4avgnaturalsharepct",
    "recent4minnaturalsharepct",
    "pass70",
    "naturaltrafficgate",
}
TRUE_AUTHORITY_KEYS = {
    "finalauthority",
    "usableforfinal",
    "formalrunauthorized",
    "gatebypassauthorized",
    "browserstepbypassauthorized",
    "strictqualified",
    "authoritative",
}
FINAL_DECISION_KEYS = {
    "finaloutcome",
    "qualificationstatus",
    "strictoutcome",
    "afoutcome",
}
POSITIVE_DECISIONS = {"pass", "passed", "qualified", "accept", "accepted", "eligible"}


class AnalysisError(ValueError):
    pass


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as error:
        raise AnalysisError(f"cannot read JSON {path}: {error}") from error
    if not isinstance(value, dict):
        raise AnalysisError(f"top-level JSON must be an object: {path}")
    return value


def read_json_value(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as error:
        raise AnalysisError(f"cannot read JSON {path}: {error}") from error


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def payload_sha256(value: Any) -> str:
    payload = (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def pct(numerator: int, denominator: int) -> float:
    return round(100 * numerator / denominator, 2) if denominator else 0.0


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
    if isinstance(value, (list, dict, tuple, set)):
        return bool(value)
    return True


def normalize_text(value: Any) -> str:
    return " ".join(str(value or "").casefold().split())


def image_key(value: Any) -> str:
    text = str(value or "").strip()
    match = re.search(r"/I/([^./]+)", text, re.IGNORECASE)
    return match.group(1).split("._", 1)[0].casefold() if match else normalize_text(text)


def measurement_numbers(value: Any) -> tuple[float, ...]:
    text = str(value or "")
    values = []
    for token in re.findall(r"(?<![A-Za-z0-9])\d+(?:\.\d+)?", text):
        parsed = number(token)
        if parsed is not None:
            values.append(round(parsed, 3))
    return tuple(values)


def same_number(left: Any, right: Any, tolerance: float) -> bool | None:
    a, b = number(left), number(right)
    if a is None or b is None:
        return None
    return abs(a - b) <= tolerance


def same_text(left: Any, right: Any) -> bool | None:
    a, b = normalize_text(left), normalize_text(right)
    if not a or not b:
        return None
    return a == b


def same_image(left: Any, right: Any) -> bool | None:
    a, b = image_key(left), image_key(right)
    if not a or not b:
        return None
    return a == b


def same_measurement(left: Any, right: Any) -> bool | None:
    a_text, b_text = normalize_text(left), normalize_text(right)
    if not a_text or not b_text:
        return None
    if a_text in b_text or b_text in a_text:
        return True
    a_numbers, b_numbers = measurement_numbers(left), measurement_numbers(right)
    if not a_numbers or not b_numbers:
        return False
    width = min(3, len(a_numbers), len(b_numbers))
    return width >= 2 and all(abs(a_numbers[index] - b_numbers[index]) <= 0.05 for index in range(width))


def parse_time(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def tool_name(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("name") or "")
    return str(value or "")


def check_authority(value: Any, path: str = "results") -> list[str]:
    violations: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            lowered = str(key).casefold()
            child_path = f"{path}.{key}"
            if lowered in TRUE_AUTHORITY_KEYS and child is not False and child is not None:
                violations.append(f"{child_path} must be false or absent")
            if lowered in FINAL_DECISION_KEYS and normalize_text(child) in POSITIVE_DECISIONS:
                violations.append(f"{child_path} must not claim a positive A-F outcome")
            violations.extend(check_authority(child, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            violations.extend(check_authority(child, f"{path}[{index}]"))
    return violations


def validate_plan(plan: dict[str, Any]) -> list[dict[str, Any]]:
    if plan.get("schemaVersion") != PLAN_SCHEMA or plan.get("marketplace") != "US":
        raise AnalysisError("shadow plan must be sellerSpriteMcpShadowPlan/v1 for US")
    sample = plan.get("sample")
    if not isinstance(sample, list) or len(sample) != 30:
        raise AnalysisError("shadow plan must contain exactly 30 sample rows")
    seen: set[str] = set()
    normalized = []
    for index, row in enumerate(sample):
        if not isinstance(row, dict):
            raise AnalysisError(f"sample[{index}] must be an object")
        asin = str(row.get("asin") or "").upper()
        outcome = str(row.get("expectedOutcome") or "")
        if not ASIN_RE.fullmatch(asin) or asin in seen:
            raise AnalysisError(f"sample[{index}] has invalid or duplicate ASIN")
        if outcome not in {"pass", "reject"}:
            raise AnalysisError(f"sample[{index}] has invalid expectedOutcome")
        seen.add(asin)
        normalized.append({**row, "asin": asin, "expectedOutcome": outcome})
    if not any(row["expectedOutcome"] == "pass" for row in normalized):
        raise AnalysisError("sample must contain positive and negative controls")
    if not any(row["expectedOutcome"] == "reject" for row in normalized):
        raise AnalysisError("sample must contain positive and negative controls")
    return normalized


def validate_task(
    task: dict[str, Any],
    sample: list[dict[str, Any]],
    *,
    plan_id: str,
    plan_sha256: str,
) -> dict[str, dict[str, Any]]:
    if task.get("schemaVersion") != TASK_SCHEMA:
        raise AnalysisError("validation task schema mismatch")
    if task.get("finalAuthority") is not False:
        raise AnalysisError("validation task must keep finalAuthority=false")
    if task.get("status") not in {"finalized", "finalized_with_failures"} or not isinstance(
        task.get("finalization"), dict
    ):
        raise AnalysisError("paired analysis requires the officially finalized validation task")
    source = task.get("source") or {}
    sample_asins = [row["asin"] for row in sample]
    if source.get("samplePlanId") != plan_id or source.get("samplePlanSha256") != plan_sha256:
        raise AnalysisError("validation task is not bound to the exact shadow plan")
    if source.get("sampleAsins") != sample_asins:
        raise AnalysisError("validation task ASIN order differs from the shadow plan")
    budget = task.get("budget") or {}
    required_budget = {
        "taskBudget": 100,
        "authorizedCalls": 91,
        "sealedReserveCalls": 9,
        "plannedCalls": 91,
        "plannedByTool": EXPECTED_TOOL_COUNTS,
        "plannedByPool": {"primary": 91, "conditional": 0, "emergency": 0},
    }
    for key, expected in required_budget.items():
        if budget.get(key) != expected:
            raise AnalysisError(f"validation task budget mismatch: {key}")
    requests = task.get("requests")
    if not isinstance(requests, list) or len(requests) != 91:
        raise AnalysisError("validation task must contain exactly 91 requests")
    counts: dict[str, int] = {}
    by_id: dict[str, dict[str, Any]] = {}
    targets: dict[str, set[str]] = {tool: set() for tool in ASIN_TOOLS}
    for index, row in enumerate(requests):
        if not isinstance(row, dict):
            raise AnalysisError(f"task request[{index}] must be an object")
        request_id = str(row.get("requestId") or "")
        tool = str(row.get("tool") or "")
        target = str(row.get("targetAsin") or "").upper() or None
        if row.get("schemaVersion") != TASK_REQUEST_SCHEMA or not request_id or request_id in by_id:
            raise AnalysisError(f"task request[{index}] has invalid schema or requestId")
        if tool not in EXPECTED_TOOL_COUNTS:
            raise AnalysisError(f"task request[{index}] has unsupported tool")
        if (
            row.get("taskId") != task.get("taskId")
            or row.get("runId") != task.get("runId")
            or row.get("marketplace") != "US"
            or row.get("mode") != "shadow_test"
            or row.get("finalAuthority") is not False
            or row.get("pool") != "primary"
            or row.get("calls") != 1
            or row.get("attemptPolicy") != {"maxAttempts": 1, "automaticRetry": False}
        ):
            raise AnalysisError(f"task request contract mismatch: {request_id}")
        if row.get("requestHash") != payload_sha256(row.get("request")):
            raise AnalysisError(f"task request hash mismatch: {request_id}")
        if tool == "product_research":
            if target is not None or row.get("toolContractState") != "discovery_only":
                raise AnalysisError("product_research must remain targetless discovery_only")
        else:
            if not ASIN_RE.fullmatch(str(target or "")) or row.get("toolContractState") != "pending":
                raise AnalysisError(f"pending ASIN tool request is invalid: {request_id}")
            targets[tool].add(str(target))
        if row.get("status") not in TERMINAL_STATUSES or row.get("attemptsRecorded") != 1:
            raise AnalysisError(f"validation request is not terminal: {request_id}")
        official_result = row.get("result")
        result_sha = str(row.get("resultSha256") or "").casefold()
        archive = row.get("rawResponseArchive")
        if (
            not isinstance(official_result, dict)
            or official_result.get("schemaVersion") != OFFICIAL_RESULT_SCHEMA
            or not SHA256_RE.fullmatch(result_sha)
            or payload_sha256(official_result) != result_sha
            or not isinstance(archive, dict)
            or archive.get("sha256") != ((official_result.get("rawResponse") or {}).get("sha256"))
            or archive.get("byteLength") != ((official_result.get("rawResponse") or {}).get("byteLength"))
        ):
            raise AnalysisError(f"official validation result integrity mismatch: {request_id}")
        counts[tool] = counts.get(tool, 0) + 1
        by_id[request_id] = {**row, "tool": tool, "targetAsin": target}
    if counts != EXPECTED_TOOL_COUNTS:
        raise AnalysisError("validation task tool counts differ from 1+30+30+30")
    expected_targets = set(sample_asins)
    if any(targets[tool] != expected_targets for tool in ASIN_TOOLS):
        raise AnalysisError("each ASIN tool must cover the exact same 30 ASINs")
    return by_id


def validate_baseline(
    baseline: dict[str, Any],
    sample: list[dict[str, Any]],
    *,
    plan_id: str,
) -> dict[str, dict[str, Any]]:
    if baseline.get("schemaVersion") != BASELINE_SCHEMA or baseline.get("planId") != plan_id:
        raise AnalysisError("browser baseline is not bound to the shadow plan")
    rows = baseline.get("rows")
    if not isinstance(rows, list) or len(rows) != 30:
        raise AnalysisError("browser baseline must contain exactly 30 rows")
    expected = {row["asin"]: row for row in sample}
    by_asin: dict[str, dict[str, Any]] = {}
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise AnalysisError(f"baseline row[{index}] must be an object")
        asin = str(row.get("asin") or "").upper()
        if asin not in expected or asin in by_asin:
            raise AnalysisError(f"baseline row[{index}] has unexpected or duplicate ASIN")
        outcome = str(row.get("expectedOutcome") or "")
        browser_outcome = str((((row.get("browser") or {}).get("gate") or {}).get("outcome") or ""))
        if outcome != expected[asin]["expectedOutcome"] or browser_outcome != outcome:
            raise AnalysisError(f"baseline outcome mismatch for {asin}")
        by_asin[asin] = row
    if set(by_asin) != set(expected):
        raise AnalysisError("baseline ASIN set differs from the shadow plan")
    return by_asin


def baseline_field(row: dict[str, Any], field: str) -> Any:
    product = row.get("productSnapshot") or {}
    gate = (row.get("browser") or {}).get("gate") or {}
    mapping = {
        "title": product.get("title"),
        "brand": product.get("brand"),
        "price": product.get("price"),
        "rating": product.get("rating"),
        "reviews": product.get("reviews"),
        "variations": product.get("variationsCount"),
        "imageUrl": product.get("imageUrl"),
        "categoryPath": product.get("categoryPath"),
        "dimensions": product.get("itemDimensions") or product.get("dimensions") or gate.get("dimensions"),
        "packageDimensions": product.get("packageDimensions"),
        "itemWeight": product.get("itemWeight"),
        "packageWeight": product.get("packageWeight"),
        "parentAsin": product.get("parentAsin"),
        "priceTrendClass": gate.get("priceTrendClass") or product.get("priceTrendClass"),
    }
    return mapping.get(field)


def comparator(field: str) -> Callable[[Any, Any], bool | None]:
    if field == "price":
        return lambda left, right: same_number(left, right, 0.01)
    if field == "rating":
        return lambda left, right: same_number(left, right, 0.05)
    if field in {"reviews", "variations"}:
        return lambda left, right: same_number(left, right, 0)
    if field == "imageUrl":
        return same_image
    if field in {"dimensions", "packageDimensions", "itemWeight", "packageWeight"}:
        return same_measurement
    return same_text


def threshold_state(field: str, value: Any) -> bool | None:
    parsed = number(value)
    if parsed is None:
        return None
    if field == "price":
        return 9.90 <= parsed <= 50.00
    if field == "rating":
        return parsed >= 4.0
    if field == "reviews":
        return parsed <= 100
    if field == "variations":
        return parsed <= 25
    return None


def result_fields(row: dict[str, Any]) -> dict[str, Any]:
    value = row.get("fields")
    return value if isinstance(value, dict) else {}


def result_provenance(row: dict[str, Any]) -> dict[str, Any]:
    value = row.get("fieldProvenance")
    return value if isinstance(value, dict) else {}


def validate_result_pair(result: dict[str, Any], request: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    request_id = request["requestId"]
    tool = request["tool"]
    target = request["targetAsin"]
    actual = str(result.get("actualAsin") or "").upper() or None
    if result.get("schemaVersion") != RESULT_SCHEMA:
        issues.append("schema")
    if result.get("sourceResultSchema") != OFFICIAL_RESULT_SCHEMA:
        issues.append("sourceResultSchema")
    if result.get("sourceResultSha256") != request.get("resultSha256"):
        issues.append("sourceResultSha256")
    if result.get("derivedFromOfficialTaskResult") is not True:
        issues.append("derivedFromOfficialTaskResult")
    official_result = request.get("result") or {}
    if result.get("officialStatus") != official_result.get("status"):
        issues.append("officialStatus")
    if result.get("tool") != official_result.get("tool"):
        issues.append("officialTool")
    if tool_name(result.get("tool")) != tool:
        issues.append("tool")
    if (str(result.get("targetAsin") or "").upper() or None) != target:
        issues.append("targetAsin")
    if result.get("requestHash") != request.get("requestHash"):
        issues.append("requestHash")
    if result.get("status") not in TERMINAL_STATUSES:
        issues.append("status")
    if result.get("status") != result.get("officialStatus") and not (
        result.get("status") == "failed" and nonempty(result.get("normalizationError"))
    ):
        issues.append("derivedStatus")
    if result.get("finalAuthority") is not False:
        issues.append("finalAuthority")
    if result.get("usableForFinal") is not False:
        issues.append("usableForFinal")
    if result.get("browserFallbackRequired") is not True:
        issues.append("browserFallbackRequired")
    if tool in ASIN_TOOLS and result.get("status") in {"succeeded", "partial"} and actual != target:
        issues.append("actualAsin")
    raw = result.get("rawResponse") or {}
    raw_sha = str(raw.get("sha256") or "").casefold()
    raw_bytes = raw.get("byteLength")
    raw_path = Path(str(raw.get("path") or ""))
    if not SHA256_RE.fullmatch(raw_sha):
        issues.append("rawResponse.sha256")
    if not isinstance(raw_bytes, int) or raw_bytes < 1:
        issues.append("rawResponse.byteLength")
    if not raw_path.is_file():
        issues.append("rawResponse.path")
    elif (
        not isinstance(raw_bytes, int)
        or raw_path.stat().st_size != raw_bytes
        or file_sha256(raw_path) != raw_sha
    ):
        issues.append("rawResponse.integrity")
    started, completed = parse_time(result.get("startedAt")), parse_time(result.get("completedAt"))
    if started is None or completed is None or completed < started:
        issues.append("timestamps")
    fields = result_fields(result)
    provenance = result_provenance(result)
    for key, value in fields.items():
        if key == "asin" or not nonempty(value):
            continue
        source = provenance.get(key)
        if not isinstance(source, dict) or source.get("sourceTool") != tool or not nonempty(source.get("sourcePath")):
            issues.append(f"provenance.{key}")
    if result.get("status") == "failed" and not nonempty(result.get("error")):
        issues.append("failedWithoutError")
    if result.get("status") in {"succeeded", "partial"} and result.get("error") not in {None, ""}:
        issues.append("successWithError")
    if result.get("requestId") != request_id:
        issues.append("requestId")
    return sorted(set(issues))


def tool_metrics(
    expected: dict[str, dict[str, Any]],
    results: dict[str, dict[str, Any]],
    issues: dict[str, list[str]],
) -> dict[str, dict[str, Any]]:
    metrics: dict[str, dict[str, Any]] = {}
    for tool, planned in EXPECTED_TOOL_COUNTS.items():
        request_ids = [request_id for request_id, row in expected.items() if row["tool"] == tool]
        received_rows = [results[request_id] for request_id in request_ids if request_id in results]
        missing = [request_id for request_id in request_ids if request_id not in results]
        invalid = [request_id for request_id in request_ids if issues.get(request_id)]
        failed = [row for row in received_rows if row.get("status") == "failed"]
        succeeded = [row for row in received_rows if row.get("status") == "succeeded"]
        partial = [row for row in received_rows if row.get("status") == "partial"]
        terminal = [row for row in received_rows if row.get("status") in TERMINAL_STATUSES]
        exact_asin = 0
        if tool in ASIN_TOOLS:
            exact_asin = sum(
                (str(row.get("actualAsin") or "").upper() or None) == expected[row["requestId"]]["targetAsin"]
                for row in received_rows
                if row.get("status") in {"succeeded", "partial"}
            )
        error_ids = set(missing) | set(invalid) | {row["requestId"] for row in failed}
        latencies = []
        for row in received_rows:
            started, completed = parse_time(row.get("startedAt")), parse_time(row.get("completedAt"))
            if started is not None and completed is not None and completed >= started:
                latencies.append((completed - started).total_seconds() * 1000)
        metrics[tool] = {
            "planned": planned,
            "received": len(received_rows),
            "terminal": len(terminal),
            "succeeded": len(succeeded),
            "partial": len(partial),
            "failed": len(failed),
            "missing": len(missing),
            "invalidPairing": len(invalid),
            "terminalCoveragePct": pct(len(terminal), planned),
            "successPct": pct(len(succeeded), planned),
            "partialPct": pct(len(partial), planned),
            "errorPct": pct(len(error_ids), planned),
            "exactAsinPct": pct(exact_asin, planned) if tool in ASIN_TOOLS else None,
            "latencyMs": {
                "count": len(latencies),
                "mean": round(statistics.fmean(latencies), 2) if latencies else None,
                "median": round(statistics.median(latencies), 2) if latencies else None,
                "max": round(max(latencies), 2) if latencies else None,
            },
            "executionContractPass": (
                len(received_rows) == planned
                and len(terminal) == planned
                and not error_ids
                and (tool not in ASIN_TOOLS or exact_asin == planned)
            ),
        }
    return metrics


def detail_field_metrics(
    baseline: dict[str, dict[str, Any]],
    detail_by_asin: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    output: dict[str, dict[str, Any]] = {}
    for field in DETAIL_FIELDS:
        compare = comparator(field)
        expected_count = provided_count = comparable = matches = missing_expected = mismatches = 0
        threshold_comparable = threshold_matches = unsafe_false_positive = conservative_false_negative = 0
        for asin, baseline_row in baseline.items():
            expected = baseline_field(baseline_row, field)
            observed = result_fields(detail_by_asin.get(asin, {})).get(field)
            if nonempty(expected):
                expected_count += 1
            if nonempty(observed):
                provided_count += 1
            if nonempty(expected) and not nonempty(observed):
                missing_expected += 1
            match = compare(expected, observed)
            if match is not None:
                comparable += 1
                matches += int(match)
                mismatches += int(not match)
            expected_state = threshold_state(field, expected)
            observed_state = threshold_state(field, observed)
            if expected_state is not None and observed_state is not None:
                threshold_comparable += 1
                threshold_matches += int(expected_state == observed_state)
                unsafe_false_positive += int(observed_state and not expected_state)
                conservative_false_negative += int(expected_state and not observed_state)
        output[field] = {
            "expected": expected_count,
            "provided": provided_count,
            "providedCoveragePct": pct(provided_count, len(baseline)),
            "missingWhenBaselinePresent": missing_expected,
            "comparable": comparable,
            "literalMatch": matches,
            "literalMismatch": mismatches,
            "literalMatchPct": pct(matches, comparable),
            "thresholdComparable": threshold_comparable,
            "thresholdAgreement": threshold_matches,
            "thresholdAgreementPct": pct(threshold_matches, threshold_comparable),
            "unsafeFalsePositive": unsafe_false_positive,
            "conservativeFalseNegative": conservative_false_negative,
        }
    return output


def detail_quality_pass(fields: dict[str, dict[str, Any]]) -> bool:
    identity_ok = all(
        fields[field]["expected"] > 0
        and fields[field]["missingWhenBaselinePresent"] == 0
        and fields[field]["literalMismatch"] == 0
        for field in DETAIL_IDENTITY_FIELDS
    )
    threshold_ok = all(
        fields[field]["thresholdComparable"] == fields[field]["expected"]
        and fields[field]["thresholdAgreement"] == fields[field]["thresholdComparable"]
        and fields[field]["unsafeFalsePositive"] == 0
        for field in DETAIL_THRESHOLD_FIELDS
    )
    return identity_ok and threshold_ok


def gate_d_metrics(
    baseline: dict[str, dict[str, Any]],
    detail_by_asin: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    evaluated = comparable = agreement = unsafe = conservative = 0
    baseline_pass = baseline_reject = 0
    for asin, baseline_row in baseline.items():
        gate = ((baseline_row.get("browser") or {}).get("gate") or {}).get("gateD")
        if gate not in {"pass", "reject"}:
            continue
        evaluated += 1
        baseline_pass += int(gate == "pass")
        baseline_reject += int(gate == "reject")
        fields = result_fields(detail_by_asin.get(asin, {}))
        observed = any(nonempty(fields.get(field)) for field in ("dimensions", "packageDimensions", "itemWeight", "packageWeight"))
        comparable += 1
        expected = gate == "pass"
        agreement += int(observed == expected)
        unsafe += int(observed and not expected)
        conservative += int(expected and not observed)
    return {
        "baselineEvaluated": evaluated,
        "baselinePass": baseline_pass,
        "baselineReject": baseline_reject,
        "mcpComparable": comparable,
        "agreement": agreement,
        "agreementPct": pct(agreement, comparable),
        "unsafeFalsePositive": unsafe,
        "conservativeFalseNegative": conservative,
        "advisoryAgreementPass": evaluated > 0 and agreement == evaluated and unsafe == 0,
        "substitutionCoveragePass": baseline_pass > 0 and baseline_reject > 0,
        "substitutionAuthorized": False,
    }


def gate_e_metrics(
    baseline: dict[str, dict[str, Any]],
    detail_by_asin: dict[str, dict[str, Any]],
    trend_by_asin: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    evaluated = comparable = agreement = unsafe = conservative = incomplete = 0
    baseline_pass = baseline_reject = 0
    price_points_valid = 0
    for asin, baseline_row in baseline.items():
        gate = ((baseline_row.get("browser") or {}).get("gate") or {}).get("gateE")
        trend_fields = result_fields(trend_by_asin.get(asin, {}))
        point_count = number(trend_fields.get("pricePointCount"))
        price_points_valid += int(point_count is not None and point_count >= 3)
        if gate not in {"pass", "reject"}:
            continue
        evaluated += 1
        baseline_pass += int(gate == "pass")
        baseline_reject += int(gate == "reject")
        price = number(result_fields(detail_by_asin.get(asin, {})).get("price"))
        trend = normalize_text(trend_fields.get("priceTrendClass"))
        if price is None or trend not in {"stable", "rising", "declining", "volatile", "no_data"}:
            incomplete += 1
            conservative += int(gate == "pass")
            continue
        observed = 9.90 <= price <= 50.00 and trend in {"stable", "rising"}
        expected = gate == "pass"
        comparable += 1
        agreement += int(observed == expected)
        unsafe += int(observed and not expected)
        conservative += int(expected and not observed)
    return {
        "baselineEvaluated": evaluated,
        "baselinePass": baseline_pass,
        "baselineReject": baseline_reject,
        "mcpComparable": comparable,
        "incomplete": incomplete,
        "agreement": agreement,
        "agreementPct": pct(agreement, comparable),
        "unsafeFalsePositive": unsafe,
        "conservativeFalseNegative": conservative,
        "pricePointCountAtLeast3": price_points_valid,
        "pricePointCoveragePct": pct(price_points_valid, len(baseline)),
        "advisoryAgreementPass": (
            evaluated > 0
            and comparable == evaluated
            and agreement == evaluated
            and unsafe == 0
            and price_points_valid == len(baseline)
        ),
        "substitutionAuthorized": False,
    }


def traffic_structure(fields: dict[str, Any]) -> tuple[bool, list[str]]:
    issues = []
    free_count = number(fields.get("freeTrafficCount"))
    paid_count = number(fields.get("paidTrafficCount"))
    free_share = number(fields.get("freeTrafficShare"))
    paid_share = number(fields.get("paidTrafficShare"))
    relations = fields.get("relationCounts")
    if free_count is None or free_count < 0 or int(free_count) != free_count:
        issues.append("freeTrafficCount")
    if paid_count is None or paid_count < 0 or int(paid_count) != paid_count:
        issues.append("paidTrafficCount")
    if free_share is None or not 0 <= free_share <= 1:
        issues.append("freeTrafficShare")
    if paid_share is None or not 0 <= paid_share <= 1:
        issues.append("paidTrafficShare")
    if not isinstance(relations, dict) or not relations:
        issues.append("relationCounts")
    relation_total = 0.0
    if isinstance(relations, dict):
        for key, value in relations.items():
            parsed = number(value)
            if not str(key).strip() or parsed is None or parsed < 0 or int(parsed) != parsed:
                issues.append("relationCounts")
                continue
            relation_total += parsed
    if None not in {free_count, paid_count, free_share, paid_share}:
        total = float(free_count) + float(paid_count)
        if total > 0:
            if abs(float(free_share) + float(paid_share) - 1.0) > 0.001:
                issues.append("shareSum")
            if abs(float(free_share) - float(free_count) / total) > 0.001:
                issues.append("freeShareRatio")
            if abs(float(paid_share) - float(paid_count) / total) > 0.001:
                issues.append("paidShareRatio")
        elif abs(float(free_share)) > 0.001 or abs(float(paid_share)) > 0.001:
            issues.append("zeroCountShares")
        if isinstance(relations, dict) and abs(relation_total - total) > 0.001:
            issues.append("relationTotal")
    return not issues, sorted(set(issues))


def traffic_metrics(results: list[dict[str, Any]]) -> dict[str, Any]:
    valid = 0
    gate_c_claims: list[dict[str, Any]] = []
    structure_errors: list[dict[str, Any]] = []
    provenance_errors: list[dict[str, Any]] = []
    for row in results:
        fields = result_fields(row)
        ok, issues = traffic_structure(fields)
        valid += int(ok)
        if issues:
            structure_errors.append({"requestId": row.get("requestId"), "issues": issues})
        forbidden = sorted(key for key in fields if str(key).casefold() in TRAFFIC_GATE_C_KEYS)
        if forbidden:
            gate_c_claims.append({"requestId": row.get("requestId"), "keys": forbidden})
        provenance = result_provenance(row)
        bad_provenance = []
        for field in TRAFFIC_FIELDS:
            source = provenance.get(field) or {}
            if "not_gate_c" not in normalize_text(source.get("semantics")):
                bad_provenance.append(field)
        if bad_provenance:
            provenance_errors.append({"requestId": row.get("requestId"), "fields": bad_provenance})
    return {
        "structureValid": valid,
        "structureCoveragePct": pct(valid, len(results)),
        "structureErrors": structure_errors,
        "gateCClaimCount": len(gate_c_claims),
        "gateCClaims": gate_c_claims,
        "provenanceErrorCount": len(provenance_errors),
        "provenanceErrors": provenance_errors,
        "gateCComparable": 0,
        "gateCProvided": False,
        "gateCSubstitutionAuthorized": False,
        "structureAdvisoryPass": (
            len(results) == 30
            and valid == 30
            and not gate_c_claims
            and not provenance_errors
        ),
    }


def discovery_candidates(fields: dict[str, Any]) -> list[Any] | None:
    for key in ("candidates", "products", "items", "results"):
        value = fields.get(key)
        if isinstance(value, list):
            return value
    return None


def product_research_metrics(
    row: dict[str, Any] | None,
    request: dict[str, Any],
    sample: list[dict[str, Any]],
) -> dict[str, Any]:
    if row is None:
        return {
            "candidateCount": 0,
            "validAsinCount": 0,
            "duplicateAsinCount": 0,
            "filterComparable": 0,
            "filterViolationCount": 0,
            "sampleOverlap": 0,
            "knownPassOverlap": 0,
            "knownRejectOverlap": 0,
            "discoveryOnly": True,
            "discoveryContractPass": False,
        }
    candidates = discovery_candidates(result_fields(row))
    if candidates is None:
        candidates = []
    request_body = ((request.get("request") or {}).get("request") or {})
    valid_asins = []
    invalid = 0
    filter_comparable = 0
    filter_violations = 0
    authority_violations = []
    for index, candidate in enumerate(candidates):
        if not isinstance(candidate, dict):
            invalid += 1
            continue
        asin = str(candidate.get("asin") or "").upper()
        if not ASIN_RE.fullmatch(asin):
            invalid += 1
        else:
            valid_asins.append(asin)
        authority_violations.extend(check_authority(candidate, f"product_research.candidates[{index}]"))
        checks = (
            (candidate.get("price"), request_body.get("minPrice"), request_body.get("maxPrice")),
            (candidate.get("rating"), request_body.get("minRating"), None),
            (candidate.get("reviews"), None, request_body.get("maxRatings")),
            (candidate.get("variations"), request_body.get("minVariations"), request_body.get("maxVariations")),
            (candidate.get("amzUnit", candidate.get("totalUnits")), request_body.get("minAmzUnit"), request_body.get("maxAmzUnit")),
        )
        for value, minimum, maximum in checks:
            parsed = number(value)
            if parsed is None:
                continue
            filter_comparable += 1
            if minimum is not None and parsed < float(minimum):
                filter_violations += 1
            elif maximum is not None and parsed > float(maximum):
                filter_violations += 1
    duplicate_count = len(valid_asins) - len(set(valid_asins))
    sample_outcomes = {item["asin"]: item["expectedOutcome"] for item in sample}
    overlap = [asin for asin in set(valid_asins) if asin in sample_outcomes]
    provenance = result_provenance(row).get("candidates") or {}
    provenance_ok = (
        provenance.get("sourceTool") == "product_research"
        and "discovery" in normalize_text(provenance.get("semantics"))
    )
    return {
        "candidateCount": len(candidates),
        "validAsinCount": len(valid_asins),
        "invalidCandidateCount": invalid,
        "duplicateAsinCount": duplicate_count,
        "filterComparable": filter_comparable,
        "filterViolationCount": filter_violations,
        "sampleOverlap": len(overlap),
        "knownPassOverlap": sum(sample_outcomes[asin] == "pass" for asin in overlap),
        "knownRejectOverlap": sum(sample_outcomes[asin] == "reject" for asin in overlap),
        "candidateAuthorityViolationCount": len(authority_violations),
        "candidateAuthorityViolations": authority_violations,
        "discoveryOnly": True,
        "discoveryContractPass": (
            row.get("status") == "succeeded"
            and len(candidates) > 0
            and invalid == 0
            and duplicate_count == 0
            and filter_violations == 0
            and not authority_violations
            and provenance_ok
        ),
    }


def paired_outcome_metrics(
    value: Any,
    sample: list[dict[str, Any]],
    *,
    plan_id: str,
) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {
            "coverage": 0,
            "agreement": 0,
            "falsePositive": 0,
            "conservativeMismatch": 0,
            "agreementPct": 0.0,
            "pass": False,
            "issues": ["pairedOutcomes missing"],
        }
    issues = []
    if (
        value.get("schemaVersion") != PAIRED_OUTCOMES_SCHEMA
        or value.get("planId") != plan_id
        or value.get("authoritySource") != "current_replay_and_acceptance"
        or value.get("aToFReplayed") is not True
        or value.get("derivedFromReplayArtifacts") is not True
        or value.get("finalAuthority") is not False
    ):
        issues.append("paired outcome header contract")
    source_files = value.get("sourceFiles")
    derived_outcomes: dict[str, tuple[str, dict[str, Any]]] = {}
    source_baseline: dict[str, dict[str, Any]] = {}
    if not isinstance(source_files, dict):
        issues.append("paired outcome sourceFiles")
        source_files = {}
    required_sources = ("finalCandidates", "rejectedAudit", "runSummary", "browserBaseline")
    if any(name not in source_files for name in required_sources):
        issues.append("paired outcome source file coverage")
    else:
        try:
            loaded: dict[str, Any] = {}
            for name in required_sources:
                record = source_files[name]
                if not isinstance(record, dict):
                    raise AnalysisError(f"paired source {name} is not an object")
                path = Path(str(record.get("path") or ""))
                sha = str(record.get("sha256") or "").casefold()
                byte_length = record.get("byteLength")
                if (
                    not path.is_file()
                    or not SHA256_RE.fullmatch(sha)
                    or not isinstance(byte_length, int)
                    or path.stat().st_size != byte_length
                    or file_sha256(path) != sha
                ):
                    raise AnalysisError(f"paired source integrity failed: {name}")
                loaded[name] = read_json_value(path)
            for name, outcome in (("finalCandidates", "pass"), ("rejectedAudit", "reject")):
                source_rows = loaded[name]
                if not isinstance(source_rows, list):
                    raise AnalysisError(f"paired source {name} must be an array")
                for source_index, source_row in enumerate(source_rows):
                    if not isinstance(source_row, dict):
                        raise AnalysisError(f"paired source {name}[{source_index}] must be an object")
                    product = source_row.get("product") if isinstance(source_row.get("product"), dict) else {}
                    asin = str(source_row.get("asin") or product.get("asin") or "").upper()
                    if not ASIN_RE.fullmatch(asin) or asin in derived_outcomes:
                        raise AnalysisError(f"paired source {name} has invalid or duplicate ASIN")
                    derived_outcomes[asin] = (outcome, source_row)
            run_summary = loaded["runSummary"]
            if (
                not isinstance(run_summary, dict)
                or run_summary.get("attempts") != 30
                or run_summary.get("qualifiedCount") != sum(row[0] == "pass" for row in derived_outcomes.values())
                or run_summary.get("rejectedCount") != sum(row[0] == "reject" for row in derived_outcomes.values())
            ):
                raise AnalysisError("paired run summary count mismatch")
            baseline_source = loaded["browserBaseline"]
            baseline_rows = baseline_source.get("rows") if isinstance(baseline_source, dict) else None
            if not isinstance(baseline_rows, list):
                raise AnalysisError("paired browser baseline rows are missing")
            for source_row in baseline_rows:
                if not isinstance(source_row, dict):
                    raise AnalysisError("paired browser baseline row is invalid")
                asin = str(source_row.get("asin") or "").upper()
                if not ASIN_RE.fullmatch(asin) or asin in source_baseline:
                    raise AnalysisError("paired browser baseline ASIN is invalid or duplicate")
                source_baseline[asin] = source_row
        except AnalysisError as error:
            issues.append(str(error))
    rows = value.get("rows")
    if not isinstance(rows, list):
        rows = []
        issues.append("paired outcome rows")
    expected = {row["asin"]: row["expectedOutcome"] for row in sample}
    seen: set[str] = set()
    agreement = false_positive = conservative = 0
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            issues.append(f"rows[{index}]")
            continue
        asin = str(row.get("asin") or "").upper()
        baseline_outcome = str(row.get("baselineOutcome") or "")
        hybrid_outcome = str(row.get("hybridOutcome") or "")
        if asin not in expected or asin in seen:
            issues.append(f"rows[{index}].asin")
            continue
        seen.add(asin)
        if baseline_outcome != expected[asin] or hybrid_outcome not in {"pass", "reject"}:
            issues.append(f"rows[{index}].outcome")
            continue
        if row.get("mcpFinalAuthority") is not False or row.get("browserReplayAuthoritative") is not True:
            issues.append(f"rows[{index}].authority")
        if row.get("outcomeDerivedFrom") not in {"final_candidates_data", "rejected_audit_data"}:
            issues.append(f"rows[{index}].outcomeDerivedFrom")
        if not SHA256_RE.fullmatch(str(row.get("baselineEvidenceSha256") or "").casefold()):
            issues.append(f"rows[{index}].baselineEvidenceSha256")
        if not SHA256_RE.fullmatch(str(row.get("hybridEvidenceSha256") or "").casefold()):
            issues.append(f"rows[{index}].hybridEvidenceSha256")
        derived = derived_outcomes.get(asin)
        baseline_source_row = source_baseline.get(asin)
        if derived is None or derived[0] != hybrid_outcome:
            issues.append(f"rows[{index}].derivedOutcome")
        else:
            expected_source = "final_candidates_data" if derived[0] == "pass" else "rejected_audit_data"
            if row.get("outcomeDerivedFrom") != expected_source:
                issues.append(f"rows[{index}].derivedSource")
            if row.get("hybridEvidenceSha256") != payload_sha256(derived[1]):
                issues.append(f"rows[{index}].hybridEvidence")
        if baseline_source_row is None or row.get("baselineEvidenceSha256") != payload_sha256(
            baseline_source_row
        ):
            issues.append(f"rows[{index}].baselineEvidence")
        agreement += int(baseline_outcome == hybrid_outcome)
        false_positive += int(baseline_outcome == "reject" and hybrid_outcome == "pass")
        conservative += int(baseline_outcome == "pass" and hybrid_outcome == "reject")
    coverage = len(seen)
    if set(seen) != set(expected):
        issues.append("paired outcome ASIN coverage")
    if set(derived_outcomes) != set(expected) or set(source_baseline) != set(expected):
        issues.append("paired source ASIN coverage")
    return {
        "coverage": coverage,
        "agreement": agreement,
        "falsePositive": false_positive,
        "conservativeMismatch": conservative,
        "agreementPct": pct(agreement, len(sample)),
        "pass": coverage == 30 and agreement == 30 and false_positive == 0 and not issues,
        "issues": sorted(set(issues)),
    }


def live_smoke_metrics(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {"pass": False, "issues": ["liveSmoke missing"]}
    required_true = (
        "completed",
        "passed",
        "sourceDerived",
        "evidenceHashVerified",
        "screenshotHashVerified",
        "asinInSample",
        "taskBound",
        "currentCombination",
        "collectorEnabled",
        "runnerEnabled",
        "browserReplayRequired",
        "queueUnchanged",
        "auditsPersisted",
    )
    issues = [key for key in required_true if value.get(key) is not True]
    if value.get("finalAuthority") is not False:
        issues.append("finalAuthority")
    if value.get("gateBypassAuthorized") is not False:
        issues.append("gateBypassAuthorized")
    if value.get("batchGenerated") is not False:
        issues.append("batchGenerated")
    before, after = value.get("strictHistoryBefore"), value.get("strictHistoryAfter")
    if not isinstance(before, int) or before != after:
        issues.append("strictHistoryUnchanged")
    provider_before, provider_after = value.get("providerCallsBefore"), value.get("providerCallsAfter")
    if not isinstance(provider_before, int) or provider_before != provider_after:
        issues.append("providerCallsUnchanged")
    source_files = value.get("sourceFiles")
    if not isinstance(source_files, dict) or not {"smoke", "hashManifest", "screenshot"}.issubset(source_files):
        issues.append("sourceFiles")
    else:
        for name in ("smoke", "hashManifest", "screenshot"):
            record = source_files[name]
            path = Path(str(record.get("path") or "")) if isinstance(record, dict) else Path("")
            sha = str(record.get("sha256") or "").casefold() if isinstance(record, dict) else ""
            byte_length = record.get("byteLength") if isinstance(record, dict) else None
            if (
                not path.is_file()
                or not SHA256_RE.fullmatch(sha)
                or not isinstance(byte_length, int)
                or path.stat().st_size != byte_length
                or file_sha256(path) != sha
            ):
                issues.append(f"sourceFiles.{name}")
    return {"pass": not issues, "issues": sorted(set(issues)), "evidence": value}


def source_integrity_metrics(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {"pass": False, "issues": ["sourceIntegrity missing"]}
    required_true = (
        "officialTaskValidated",
        "taskFinalized",
        "officialSummaryVerified",
        "rawArchivesVerified",
        "pairedOutcomesDerived",
        "liveSmokeDerived",
    )
    issues = [key for key in required_true if value.get(key) is not True]
    if value.get("rawArchiveCount") != 91:
        issues.append("rawArchiveCount")
    if value.get("finalAuthority") is not False:
        issues.append("finalAuthority")
    manifests = value.get("officialManifestHashes")
    if not isinstance(manifests, dict) or any(
        not SHA256_RE.fullmatch(str(manifests.get(key) or "").casefold())
        for key in ("claimManifestSha256", "resultManifestSha256", "rawManifestSha256")
    ):
        issues.append("officialManifestHashes")
    files = value.get("files")
    if not isinstance(files, dict):
        issues.append("files")
        files = {}
    required_files = {
        "plan",
        "task",
        "summary",
        "baseline",
        "finalCandidates",
        "rejectedAudit",
        "runSummary",
    }
    if not required_files.issubset(files):
        issues.append("requiredFiles")
    for name, record in files.items():
        if not isinstance(record, dict):
            issues.append(f"files.{name}")
            continue
        path = Path(str(record.get("path") or ""))
        sha = str(record.get("sha256") or "").casefold()
        byte_length = record.get("byteLength")
        if (
            not path.is_file()
            or not SHA256_RE.fullmatch(sha)
            or not isinstance(byte_length, int)
            or path.stat().st_size != byte_length
            or file_sha256(path) != sha
        ):
            issues.append(f"files.{name}.integrity")
    return {"pass": not issues, "issues": sorted(set(issues)), "evidence": value}


def baseline_gate_coverage(baseline: dict[str, dict[str, Any]]) -> dict[str, Any]:
    result = {}
    for gate_name in "ABCDEF":
        states = [
            str((((row.get("browser") or {}).get("gate") or {}).get(f"gate{gate_name}") or ""))
            for row in baseline.values()
        ]
        result[gate_name] = {
            "evaluated": sum(state in {"pass", "reject"} for state in states),
            "pass": states.count("pass"),
            "reject": states.count("reject"),
        }
    return result


def build_report(
    plan: dict[str, Any],
    task: dict[str, Any],
    baseline: dict[str, Any],
    execution: dict[str, Any],
    *,
    plan_sha256: str,
) -> dict[str, Any]:
    sample = validate_plan(plan)
    plan_id = str(plan.get("planId") or "")
    expected = validate_task(task, sample, plan_id=plan_id, plan_sha256=plan_sha256)
    baseline_by_asin = validate_baseline(baseline, sample, plan_id=plan_id)
    if (
        execution.get("schemaVersion") != RESULTS_SCHEMA
        or execution.get("taskId") != task.get("taskId")
        or execution.get("runId") != task.get("runId")
        or execution.get("finalAuthority") is not False
    ):
        raise AnalysisError("validation result bundle header mismatch")
    integrity = source_integrity_metrics(execution.get("sourceIntegrity"))
    raw_results = execution.get("results")
    if not isinstance(raw_results, list):
        raise AnalysisError("validation result bundle must contain results[]")
    results: dict[str, dict[str, Any]] = {}
    duplicate_ids = []
    unexpected_ids = []
    for index, row in enumerate(raw_results):
        if not isinstance(row, dict):
            unexpected_ids.append(f"index:{index}")
            continue
        request_id = str(row.get("requestId") or "")
        if request_id in results:
            duplicate_ids.append(request_id)
            continue
        results[request_id] = row
        if request_id not in expected:
            unexpected_ids.append(request_id or f"index:{index}")
    request_issues = {
        request_id: validate_result_pair(results[request_id], request)
        for request_id, request in expected.items()
        if request_id in results
    }
    authority_violations = check_authority(execution)
    metrics = tool_metrics(expected, results, request_issues)
    valid_results = {
        request_id: row
        for request_id, row in results.items()
        if request_id in expected and not request_issues.get(request_id)
    }
    by_tool: dict[str, list[dict[str, Any]]] = {tool: [] for tool in EXPECTED_TOOL_COUNTS}
    by_tool_asin: dict[str, dict[str, dict[str, Any]]] = {tool: {} for tool in ASIN_TOOLS}
    for request_id, row in valid_results.items():
        tool = expected[request_id]["tool"]
        by_tool[tool].append(row)
        target = expected[request_id]["targetAsin"]
        if tool in ASIN_TOOLS and target:
            by_tool_asin[tool][target] = row
    detail_fields = detail_field_metrics(baseline_by_asin, by_tool_asin["asin_detail"])
    gate_d = gate_d_metrics(baseline_by_asin, by_tool_asin["asin_detail"])
    gate_e = gate_e_metrics(
        baseline_by_asin,
        by_tool_asin["asin_detail"],
        by_tool_asin["asin_sales_trend"],
    )
    traffic = traffic_metrics(by_tool["traffic_listing_stat"])
    research_request = next(row for row in expected.values() if row["tool"] == "product_research")
    research = product_research_metrics(
        by_tool["product_research"][0] if len(by_tool["product_research"]) == 1 else None,
        research_request,
        sample,
    )
    paired = paired_outcome_metrics(execution.get("pairedOutcomes"), sample, plan_id=plan_id)
    smoke = live_smoke_metrics(execution.get("liveSmoke"))
    detail_role_pass = (
        metrics["asin_detail"]["executionContractPass"]
        and detail_quality_pass(detail_fields)
        and gate_d["advisoryAgreementPass"]
    )
    trend_role_pass = (
        metrics["asin_sales_trend"]["executionContractPass"]
        and gate_e["advisoryAgreementPass"]
    )
    traffic_role_pass = (
        metrics["traffic_listing_stat"]["executionContractPass"]
        and traffic["structureAdvisoryPass"]
    )
    research_role_pass = (
        metrics["product_research"]["executionContractPass"]
        and research["discoveryContractPass"]
    )
    unsafe_false_positive = (
        sum(detail_fields[field]["unsafeFalsePositive"] for field in DETAIL_THRESHOLD_FIELDS)
        + gate_d["unsafeFalsePositive"]
        + gate_e["unsafeFalsePositive"]
        + paired["falsePositive"]
    )
    result_set_pass = (
        len(raw_results) == 91
        and not duplicate_ids
        and not unexpected_ids
        and set(results) == set(expected)
        and all(not value for value in request_issues.values())
    )
    zero_false_positive = unsafe_false_positive == 0 and not authority_violations
    checks = {
        "officialSourceIntegrity": integrity["pass"],
        "exact91ResultSet": result_set_pass,
        "zeroToolErrors": all(value["errorPct"] == 0 for value in metrics.values()),
        "zeroAuthorityViolations": not authority_violations,
        "zeroFalsePositive": zero_false_positive,
        "productResearchDiscoveryOnly": research_role_pass,
        "asinDetailAdvisoryFields": detail_role_pass,
        "asinSalesTrendAdvisory": trend_role_pass,
        "trafficStructureOnly": traffic_role_pass,
        "pairedFinalOutcomes30Of30": paired["pass"],
        "liveSmoke": smoke["pass"],
    }
    shadow_pass = all(checks.values())
    gate_coverage = baseline_gate_coverage(baseline_by_asin)
    formal_blockers = [
        "MCP policy and every result remain finalAuthority=false",
        "product_research is discovery-only and cannot grant A-F eligibility",
        "traffic_listing_stat is structural advisory only and provides zero Gate C comparisons",
        "Gate A, complete Gate B, and Gate F are not supplied by the 91-call tool set",
        "the current 30-row baseline has no authoritative Gate A/B/F evaluations and no Gate D reject control",
        "approved Collector, Runner, replay/filter, workbook, and acceptance layers remain mandatory",
    ]
    return {
        "schemaVersion": REPORT_SCHEMA,
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "planId": plan_id,
        "taskId": task.get("taskId"),
        "runId": task.get("runId"),
        "sample": {
            "size": len(sample),
            "pass": sum(row["expectedOutcome"] == "pass" for row in sample),
            "reject": sum(row["expectedOutcome"] == "reject" for row in sample),
        },
        "checks": checks,
        "shadowPairedAcceptance": "PASS" if shadow_pass else "FAIL",
        "allowedAction": "reorder_and_advisory_only" if shadow_pass else "blocked_pending_evidence",
        "toolMetrics": metrics,
        "toolRoles": {
            "product_research": {
                "accepted": research_role_pass,
                "role": "discovery_only",
                "finalGateEligible": False,
            },
            "asin_detail": {
                "accepted": detail_role_pass,
                "role": "field_and_ranking_advisory_only",
                "finalGateEligible": False,
            },
            "asin_sales_trend": {
                "accepted": trend_role_pass,
                "role": "price_trend_advisory_only",
                "finalGateEligible": False,
            },
            "traffic_listing_stat": {
                "accepted": traffic_role_pass,
                "role": "traffic_structure_advisory_only_not_gate_c",
                "finalGateEligible": False,
            },
        },
        "fieldAgreement": detail_fields,
        "gateAdvisoryChecks": {"D": gate_d, "E": gate_e},
        "trafficListingStat": traffic,
        "productResearch": research,
        "sourceIntegrity": integrity,
        "pairedOutcomes": paired,
        "liveSmoke": smoke,
        "zeroFalsePositive": {
            "pass": zero_false_positive,
            "unsafeFalsePositiveCount": unsafe_false_positive,
            "authorityViolationCount": len(authority_violations),
            "authorityViolations": authority_violations,
        },
        "resultContract": {
            "duplicateRequestIds": duplicate_ids,
            "unexpectedRequestIds": unexpected_ids,
            "missingRequestIds": sorted(set(expected) - set(results)),
            "requestIssues": {key: value for key, value in request_issues.items() if value},
        },
        "baselineGateCoverage": gate_coverage,
        "mcpGateCoverage": {
            "A": {"comparable": 0, "substitutionAuthorized": False},
            "B": {"comparable": 0, "partialFieldChecksOnly": True, "substitutionAuthorized": False},
            "C": {"comparable": 0, "provided": False, "substitutionAuthorized": False},
            "D": {"comparable": gate_d["mcpComparable"], "substitutionAuthorized": False},
            "E": {"comparable": gate_e["mcpComparable"], "substitutionAuthorized": False},
            "F": {"comparable": 0, "substitutionAuthorized": False},
        },
        "mcpFinalAuthority": False,
        "gateBypassAuthorized": False,
        "formalRunAuthorized": False,
        "formalRunBlockers": formal_blockers,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Offline acceptance analysis for the sealed 91-call MCP validation task")
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--task", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = build_report(
            read_json(args.plan),
            read_json(args.task),
            read_json(args.baseline),
            read_json(args.results),
            plan_sha256=file_sha256(args.plan),
        )
    except AnalysisError as error:
        print(json.dumps({"schemaVersion": REPORT_SCHEMA, "error": str(error)}, ensure_ascii=False, indent=2))
        return 2
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "shadowPairedAcceptance": report["shadowPairedAcceptance"],
                "checks": report["checks"],
                "toolMetrics": report["toolMetrics"],
                "zeroFalsePositive": report["zeroFalsePositive"],
                "formalRunAuthorized": report["formalRunAuthorized"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if report["shadowPairedAcceptance"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
