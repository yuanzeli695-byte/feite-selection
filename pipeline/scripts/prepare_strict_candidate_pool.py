#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from collections import Counter, defaultdict, deque
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, parse_qs, urlencode, urlparse, urlunparse

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from filter_engine import (  # noqa: E402
    basic_prefilter,
    exclusion_check,
    get_number,
    keyword_hit,
    launch_age_days,
    text_blob,
)
from strict_history import load_strict_qualified_asins  # noqa: E402


EXTRA_SAFETY_TERMS = (
    "medicine",
    "first aid",
    "pill case",
    "drug storage",
    "gun",
    "rifle",
    "firearm",
    "ammo",
    "ammunition",
    "winnie",
    "pooh",
    "for yeti",
    "blackstone",
    "walker basket",
    "foot bath",
)

ENABLE_TIER1_2_PRIORITY_RANKING = True
PRIORITY_RANKING_VERSION_V1 = "tier1.2-probability-v1"
PRIORITY_RANKING_VERSION_V2 = "tier1.2-probability-v2"
PRIORITY_RANKING_VERSION = PRIORITY_RANKING_VERSION_V2
ENABLE_A_SOURCE_PREFILTER_V2 = True
A_SOURCE_PREFILTER_VERSION = "tier1.1-a-source-prefilter-v2"
OPTIONAL_PARENT_CHILD_SALES_VERSION = "excel-source-optional-parent-child-sales-v1"
EXPLICIT_ATTEMPTED_EXCLUSION_VERSION = "runner-queue-explicit-exclusion-v1"
A_SOURCE_HARD_EXCLUSION_TERMS = {
    "ip_character_risk": (
        "stitch happy birthday",
    ),
    "electric_electronic": (
        "solar light",
        "solar lights",
        "solar garden light",
        "solar garden lights",
        "solar spot light",
        "solar spot lights",
        "flood light",
        "flood lights",
        "socket fan light",
        "light bulb",
        "light bulbs",
        "box fan",
    ),
    "chemical_consumable": (
        "wood filler",
    ),
}
ENABLE_POST_SELECTION_QUEUE_REORDER = True
POST_SELECTION_QUEUE_REORDER_VERSION = "p1-safe-queue-reorder-v1"
FUTURE_YEAR_RE = re.compile(r"\b(?:19|20)\d{2}\b")
FUTURE_PLANNING_TERMS = ("planner", "calendar")

SOURCE_MANIFEST_SCHEMA_VERSION = "sellerSpriteCandidateSourceManifest/v1"
SOURCE_MANIFEST_MAX_AGE = timedelta(hours=24)
SOURCE_MANIFEST_FUTURE_SKEW = timedelta(minutes=5)
FORMAL_REQUIRED_STRING_FIELDS = (
    "title",
    "categoryPath",
    "sourcePage",
    "sellerSpriteUrl",
    "amazonUrl",
    "image",
)
FORMAL_REQUIRED_NUMBER_FIELDS = ("reviews", "childSales")
PROVENANCE_FIELDS = {"sourcePage", "sellerSpriteUrl", "sourceRow"}
CATEGORY_HARD_EXCLUSION_TERMS = ("electronics", "clothing")
ASIN_RE = re.compile(r"^[A-Z0-9]{10}$")


class SourceContractError(ValueError):
    pass


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def read_asins(path: Path | None) -> set[str]:
    if not path or not path.exists():
        return set()
    return {line.strip().upper() for line in path.read_text(encoding="utf-8-sig").splitlines() if line.strip()}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def parse_aware_datetime(value: Any, field_name: str) -> datetime:
    text = str(value or "").strip()
    if not text:
        raise SourceContractError(f"manifest {field_name} is required")
    try:
        parsed = datetime.fromisoformat(text[:-1] + "+00:00" if text.endswith("Z") else text)
    except ValueError as exc:
        raise SourceContractError(f"manifest {field_name} is not valid ISO-8601: {text!r}") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise SourceContractError(f"manifest {field_name} must include a timezone offset")
    return parsed.astimezone(timezone.utc)


def normalize_node_ids(value: Any, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise SourceContractError(f"{field_name} must be a nonempty JSON array")
    normalized_items: list[str] = []
    for item in value:
        if isinstance(item, bool) or not isinstance(item, (str, int)):
            raise SourceContractError(f"{field_name} must contain only string or integer node IDs")
        text = str(item).strip()
        if not text:
            raise SourceContractError(f"{field_name} must contain only nonempty node IDs")
        normalized_items.append(text)
    normalized = tuple(normalized_items)
    if not normalized:
        raise SourceContractError(f"{field_name} must contain only nonempty node IDs")
    if len(set(normalized)) != len(normalized):
        raise SourceContractError(f"{field_name} contains duplicate node IDs")
    return normalized


def canonical_query_url(value: str) -> str:
    parsed = urlparse(str(value or "").strip())
    pairs = sorted(parse_qsl(parsed.query, keep_blank_values=True))
    return urlunparse(
        (
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            parsed.path,
            "",
            urlencode(pairs, doseq=True),
            "",
        )
    )


def validate_query_url(value: Any, *, allowed_node_ids: set[str] | None = None) -> dict[str, Any]:
    url = str(value or "").strip()
    parsed = urlparse(url)
    hostname = (parsed.hostname or "").lower()
    if parsed.scheme.lower() != "https" or not (hostname == "sellersprite.com" or hostname.endswith(".sellersprite.com")):
        raise SourceContractError("queryUrl must be an HTTPS SellerSprite URL")
    params = parse_qs(parsed.query, keep_blank_values=True)

    raw_market_values = params.get("market", [])
    market_values = {value.strip().upper() for value in raw_market_values if value.strip()}
    if len(raw_market_values) != 1 or market_values != {"US"}:
        raise SourceContractError("queryUrl market must be exactly US")

    max_review_values = params.get("maxReviews", [])
    if len(max_review_values) != 1:
        raise SourceContractError("queryUrl must contain exactly one maxReviews value")
    try:
        max_reviews = float(max_review_values[0])
    except ValueError as exc:
        raise SourceContractError("queryUrl maxReviews must be numeric") from exc
    if not math.isfinite(max_reviews) or max_reviews < 0 or max_reviews > 100:
        raise SourceContractError(f"queryUrl maxReviews must be <= 100, got {max_reviews:g}")

    node_values = params.get("nodeIdPaths", [])
    if len(node_values) != 1:
        raise SourceContractError("queryUrl must contain exactly one nodeIdPaths value")
    try:
        node_ids = normalize_node_ids(json.loads(node_values[0]), "queryUrl nodeIdPaths")
    except json.JSONDecodeError as exc:
        raise SourceContractError("queryUrl nodeIdPaths must be a JSON array") from exc
    if allowed_node_ids is not None and not set(node_ids).issubset(allowed_node_ids):
        raise SourceContractError("queryUrl nodeIdPaths fall outside the manifest categoryScope")

    return {
        "url": url,
        "canonicalUrl": canonical_query_url(url),
        "market": "US",
        "maxReviews": max_reviews,
        "nodeIdPaths": list(node_ids),
    }


def validate_source_manifest(
    manifest_path: Path,
    input_dir: Path,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    manifest_path = manifest_path.resolve()
    input_dir = input_dir.resolve()
    manifest = read_json(manifest_path)
    if not isinstance(manifest, dict):
        raise SourceContractError("source manifest must be a JSON object")
    if manifest.get("schemaVersion") != SOURCE_MANIFEST_SCHEMA_VERSION:
        raise SourceContractError(
            f"manifest schemaVersion must be {SOURCE_MANIFEST_SCHEMA_VERSION!r}"
        )

    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    captured_at = parse_aware_datetime(manifest.get("capturedAt"), "capturedAt")
    age = current - captured_at
    if age < -SOURCE_MANIFEST_FUTURE_SKEW:
        raise SourceContractError("manifest capturedAt is more than 5 minutes in the future")
    if age > SOURCE_MANIFEST_MAX_AGE:
        raise SourceContractError("manifest capturedAt is older than 24 hours")

    if str(manifest.get("market") or "").strip().upper() != "US":
        raise SourceContractError("manifest market must be US")
    preset = manifest.get("preset")
    preset_name = preset.get("name") if isinstance(preset, dict) else preset
    if not str(preset_name or "").strip():
        raise SourceContractError("manifest preset (or preset.name) is required")

    category_scope = manifest.get("categoryScope")
    if not isinstance(category_scope, dict) or not str(category_scope.get("name") or "").strip():
        raise SourceContractError("manifest categoryScope.name is required")
    category_node_ids = normalize_node_ids(
        category_scope.get("nodeIdPaths"),
        "manifest categoryScope.nodeIdPaths",
    )
    allowed_node_ids = set(category_node_ids)

    inputs = manifest.get("inputs")
    if not isinstance(inputs, list) or not inputs:
        raise SourceContractError("manifest inputs must be a nonempty array")

    actual_paths = sorted(path.resolve() for path in input_dir.glob("query_*.json"))
    if not actual_paths:
        raise SourceContractError("input directory has no query_*.json files")
    actual_by_name = {path.name: path for path in actual_paths}
    if len(actual_by_name) != len(actual_paths):
        raise SourceContractError("input query filenames must be unique")

    input_contracts: dict[str, dict[str, Any]] = {}
    for index, entry in enumerate(inputs):
        if not isinstance(entry, dict):
            raise SourceContractError(f"manifest inputs[{index}] must be an object")
        relative_name = str(entry.get("path") or "").strip()
        relative_path = Path(relative_name)
        if (
            not relative_name
            or relative_path.is_absolute()
            or len(relative_path.parts) != 1
            or relative_path.name != relative_name
            or not relative_name.startswith("query_")
            or relative_path.suffix.lower() != ".json"
        ):
            raise SourceContractError(f"manifest inputs[{index}].path must name one query_*.json file")
        if relative_name in input_contracts:
            raise SourceContractError(f"manifest contains duplicate input path: {relative_name}")
        source_path = actual_by_name.get(relative_name)
        if source_path is None:
            raise SourceContractError(f"manifest input file does not exist: {relative_name}")

        expected_hash = str(entry.get("sha256") or "").strip().lower()
        if not re.fullmatch(r"[0-9a-f]{64}", expected_hash):
            raise SourceContractError(f"manifest input {relative_name} has an invalid sha256")
        actual_hash = sha256_file(source_path)
        if actual_hash != expected_hash:
            raise SourceContractError(f"SHA256 mismatch for {relative_name}")

        query_contract = validate_query_url(
            entry.get("queryUrl"),
            allowed_node_ids=allowed_node_ids,
        )
        input_contracts[relative_name] = {
            "path": source_path,
            "sha256": actual_hash,
            "queryUrl": query_contract["url"],
            "canonicalQueryUrl": query_contract["canonicalUrl"],
            "query": query_contract,
        }

    unlisted = sorted(set(actual_by_name) - set(input_contracts))
    extra = sorted(set(input_contracts) - set(actual_by_name))
    if unlisted or extra:
        details = []
        if unlisted:
            details.append(f"unlisted files: {', '.join(unlisted)}")
        if extra:
            details.append(f"missing files: {', '.join(extra)}")
        raise SourceContractError("manifest/input file set mismatch: " + "; ".join(details))

    return {
        "schemaVersion": SOURCE_MANIFEST_SCHEMA_VERSION,
        "manifestPath": str(manifest_path),
        "capturedAt": captured_at.isoformat(),
        "market": "US",
        "preset": preset,
        "categoryScope": {
            "name": str(category_scope["name"]).strip(),
            "nodeIdPaths": list(category_node_ids),
        },
        "inputs": input_contracts,
    }


def nonempty(value: Any) -> bool:
    return value is not None and (not isinstance(value, str) or bool(value.strip()))


def validate_formal_row(
    item: dict[str, Any],
    source_contract: dict[str, Any],
    *,
    allow_missing_parent_child_sales: bool = False,
) -> list[str]:
    errors = [field for field in FORMAL_REQUIRED_STRING_FIELDS if not nonempty(item.get(field))]
    required_number_fields = (
        tuple(field for field in FORMAL_REQUIRED_NUMBER_FIELDS if field != "childSales")
        if allow_missing_parent_child_sales
        else FORMAL_REQUIRED_NUMBER_FIELDS
    )
    for field in required_number_fields:
        value = item.get(field)
        if value is None or value == "" or isinstance(value, bool):
            errors.append(field)
            continue
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            errors.append(field)
            continue
        if not math.isfinite(numeric) or numeric < 0:
            errors.append(field)

    asin = str(item.get("asin") or "").strip().upper()
    if not ASIN_RE.fullmatch(asin):
        errors.append("asin")

    if nonempty(item.get("sellerSpriteUrl")):
        try:
            row_query = validate_query_url(item["sellerSpriteUrl"])
            if row_query["canonicalUrl"] != source_contract["canonicalQueryUrl"]:
                errors.append("sellerSpriteUrl_manifest_mismatch")
        except SourceContractError:
            errors.append("sellerSpriteUrl_query_contract")

    if nonempty(item.get("amazonUrl")):
        parsed = urlparse(str(item["amazonUrl"]).strip())
        host = (parsed.hostname or "").lower()
        amazon_asin = re.search(r"/(?:dp|gp/product)/([A-Z0-9]{10})(?:[/?]|$)", parsed.path, re.I)
        if parsed.scheme.lower() not in {"http", "https"} or not (host == "amazon.com" or host.endswith(".amazon.com")):
            errors.append("amazonUrl_domain")
        elif not amazon_asin or amazon_asin.group(1).upper() != asin:
            errors.append("amazonUrl_asin_mismatch")

    if nonempty(item.get("image")):
        image_url = urlparse(str(item["image"]).strip())
        if image_url.scheme.lower() not in {"http", "https"} or not image_url.netloc:
            errors.append("image_url")
    return sorted(set(errors))


def values_conflict(left: Any, right: Any) -> bool:
    if isinstance(left, bool) or isinstance(right, bool):
        return left != right
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return float(left) != float(right)
    if isinstance(left, str) and isinstance(right, str):
        return left.strip() != right.strip()
    return left != right


def aggregate_duplicate_rows(
    rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row.get("asin") or "").upper()].append(row)

    merged_rows: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []
    duplicate_asin_count = 0
    for asin, group in grouped.items():
        if len(group) > 1:
            duplicate_asin_count += 1
        merged: dict[str, Any] = {}
        evidence: list[dict[str, Any]] = []
        conflicting_fields: set[str] = set()
        provenance_values: dict[str, list[Any]] = defaultdict(list)
        for row in group:
            evidence.extend(row.get("_sourceEvidence") or [])
            for key, value in row.items():
                if key == "_sourceEvidence":
                    continue
                if key in PROVENANCE_FIELDS:
                    if nonempty(value) and value not in provenance_values[key]:
                        provenance_values[key].append(value)
                    if key not in merged and nonempty(value):
                        merged[key] = value
                    continue
                if not nonempty(value):
                    continue
                if key not in merged or not nonempty(merged[key]):
                    merged[key] = value
                elif values_conflict(merged[key], value):
                    conflicting_fields.add(key)

        unique_evidence: list[dict[str, Any]] = []
        seen_evidence: set[str] = set()
        for entry in evidence:
            marker = json.dumps(entry, sort_keys=True, ensure_ascii=True)
            if marker not in seen_evidence:
                seen_evidence.add(marker)
                unique_evidence.append(entry)
        merged["sourceEvidence"] = unique_evidence
        if len(provenance_values["sourcePage"]) > 1:
            merged["sourcePages"] = provenance_values["sourcePage"]
        if len(provenance_values["sellerSpriteUrl"]) > 1:
            merged["sellerSpriteUrls"] = provenance_values["sellerSpriteUrl"]

        if conflicting_fields:
            conflicts.append(
                {
                    "asin": asin,
                    "stage": "source_contract",
                    "reason": "duplicate_conflict: " + ", ".join(sorted(conflicting_fields)),
                    "conflictingFields": sorted(conflicting_fields),
                    "sourceEvidence": unique_evidence,
                }
            )
        else:
            merged_rows.append(merged)
    return merged_rows, conflicts, duplicate_asin_count


def category_exclusion_hit(item: dict[str, Any]) -> str | None:
    category_path = str(item.get("categoryPath") or "").lower()
    return next(
        (
            term
            for term in CATEGORY_HARD_EXCLUSION_TERMS
            if re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", category_path)
        ),
        None,
    )


def a_source_hard_exclusion_hit(item: dict[str, Any]) -> dict[str, str] | None:
    blob = text_blob(item)
    for rule, terms in A_SOURCE_HARD_EXCLUSION_TERMS.items():
        for term in terms:
            if keyword_hit(blob, term):
                return {"rule": rule, "term": term}
    return None


def variant_key(item: dict[str, Any]) -> str:
    title = str(item.get("title") or "").lower()
    title = re.sub(r"\([^)]*\)", " ", title)
    title = re.sub(r"\b(black|white|pink|blue|green|red|gray|grey|brown|beige|clear|ivory)\b", " ", title)
    title = re.sub(r"[^a-z0-9]+", " ", title)
    return f"{str(item.get('brand') or '').lower()}|{' '.join(title.split())[:140]}"


def priority_score(item: dict[str, Any], run_date: date, warning_count: int) -> int:
    age = launch_age_days(item, run_date) or 0
    child = item.get("childSales")
    parent = item.get("parentSales")
    reviews = item.get("reviews")
    variations = item.get("variations")
    rating = item.get("rating")
    score = 0
    score += 4 if 28 <= age <= 80 else 2
    score += 4 if isinstance(child, (int, float)) and 50 <= child <= 300 else 0
    score += 3 if isinstance(parent, (int, float)) and 50 <= parent <= 400 else 1 if isinstance(parent, (int, float)) and parent <= 800 else 0
    score += 3 if isinstance(reviews, (int, float)) and reviews <= 30 else 2 if isinstance(reviews, (int, float)) and reviews <= 60 else 1
    score += 3 if isinstance(variations, (int, float)) and variations <= 5 else 2 if isinstance(variations, (int, float)) and variations <= 10 else 1
    score += 2 if isinstance(rating, (int, float)) and rating >= 4.5 else 0
    score += 1 if str(item.get("delivery") or "").upper() == "FBA" else 0
    score -= warning_count
    return score


def probability_score_components(
    item: dict[str, Any],
    run_date: date,
    warning_count: int,
    rules: dict[str, Any],
    ranking_version: str = PRIORITY_RANKING_VERSION,
) -> dict[str, int]:
    age = launch_age_days(item, run_date)
    monthly_sales = get_number(item, "monthlySales", "childSales")
    reviews = get_number(item, "reviews")
    variations = get_number(item, "variationsCount", "variations")
    rating = get_number(item, "rating")
    ideal_min = float(rules["monthlySalesIdealMin"])
    ideal_max = float(rules["monthlySalesIdealMax"])

    max_age_score_day = 80 if ranking_version == PRIORITY_RANKING_VERSION_V1 else 90
    age_score = 0 if age is None else 4 if 28 <= age <= max_age_score_day else 2
    sales_score = 0 if monthly_sales is None else 5 if ideal_min <= monthly_sales <= ideal_max else 2
    reviews_score = 0
    if reviews is not None:
        reviews_score = 4 if reviews <= 30 else 3 if reviews <= 60 else 1
    variations_score = 0
    if variations is not None:
        variations_score = 4 if variations <= 5 else 3 if variations <= 10 else 1
    rating_score = 0 if rating is None else 2 if rating >= 4.5 else 1

    return {
        "launchAge": age_score,
        "monthlySales": sales_score,
        "reviews": reviews_score,
        "variations": variations_score,
        "rating": rating_score,
        "warningPenalty": -max(0, int(warning_count)),
    }


def probability_tie_key(item: dict[str, Any], rules: dict[str, Any]) -> tuple[Any, ...]:
    rating = get_number(item, "rating")
    reviews = get_number(item, "reviews")
    variations = get_number(item, "variationsCount", "variations")
    monthly_sales = get_number(item, "monthlySales", "childSales")
    ideal_min = float(rules["monthlySalesIdealMin"])
    ideal_max = float(rules["monthlySalesIdealMax"])
    if monthly_sales is None:
        sales_distance = float("inf")
    elif monthly_sales < ideal_min:
        sales_distance = ideal_min - monthly_sales
    elif monthly_sales > ideal_max:
        sales_distance = monthly_sales - ideal_max
    else:
        sales_distance = 0.0
    return (
        -(rating if rating is not None else -1.0),
        reviews if reviews is not None else float("inf"),
        variations if variations is not None else float("inf"),
        sales_distance,
        str(item.get("asin") or ""),
    )


def ranking_brand_bucket(item: dict[str, Any]) -> str:
    brand = str(item.get("brand") or "").strip().lower()
    return brand or f"unknown:{item.get('asin') or ''}"


def probability_rank_candidates(
    candidates: list[dict[str, Any]],
    rules: dict[str, Any],
    run_date: date,
    ranking_version: str = PRIORITY_RANKING_VERSION,
) -> list[dict[str, Any]]:
    if ranking_version not in {PRIORITY_RANKING_VERSION_V1, PRIORITY_RANKING_VERSION_V2}:
        raise ValueError(f"unsupported ranking version: {ranking_version}")
    original_asins = [str(row.get("asin") or "") for row in candidates]
    by_score: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in candidates:
        components = probability_score_components(
            row,
            run_date,
            len(row.get("preselectionWarnings") or []),
            rules,
            ranking_version,
        )
        row["rankingVersion"] = ranking_version
        row["rankingScore"] = sum(components.values())
        row["rankingComponents"] = components
        by_score[int(row["rankingScore"])].append(row)

    ordered: list[dict[str, Any]] = []
    for score in sorted(by_score, reverse=True):
        brand_queues: dict[str, deque[dict[str, Any]]] = defaultdict(deque)
        for row in sorted(by_score[score], key=lambda item: probability_tie_key(item, rules)):
            brand_queues[ranking_brand_bucket(row)].append(row)
        brand_order = sorted(
            brand_queues,
            key=lambda brand: (probability_tie_key(brand_queues[brand][0], rules), brand),
        )
        while any(brand_queues[brand] for brand in brand_order):
            for brand in brand_order:
                if brand_queues[brand]:
                    ordered.append(brand_queues[brand].popleft())

    ordered_asins = [str(row.get("asin") or "") for row in ordered]
    if len(ordered_asins) != len(original_asins) or Counter(ordered_asins) != Counter(
        original_asins
    ):
        raise RuntimeError("Tier 1.2 ranking must reorder candidates without adding or removing ASINs")
    for position, row in enumerate(ordered, start=1):
        row["rankingPosition"] = position
    return ordered


def is_future_year_planner(item: dict[str, Any], run_date: date) -> bool:
    title = str(item.get("title") or "").lower()
    if not any(term in title for term in FUTURE_PLANNING_TERMS):
        return False
    return any(int(match.group(0)) > run_date.year for match in FUTURE_YEAR_RE.finditer(title))


def asin_queue_sha256(rows: list[dict[str, Any]]) -> str:
    payload = "\n".join(str(row.get("asin") or "") for row in rows) + "\n"
    return hashlib.sha256(payload.encode("ascii")).hexdigest()


def asin_multiset_sha256(rows: list[dict[str, Any]]) -> str:
    payload = "\n".join(sorted(str(row.get("asin") or "") for row in rows)) + "\n"
    return hashlib.sha256(payload.encode("ascii")).hexdigest()


def post_selection_queue_reorder(
    selected: list[dict[str, Any]],
    run_date: date,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    original_asins = [str(row.get("asin") or "") for row in selected]
    before_order_sha256 = asin_queue_sha256(selected)
    before_multiset_sha256 = asin_multiset_sha256(selected)
    for position, row in enumerate(selected, start=1):
        row["preQueuePosition"] = position

    def queue_key(row: dict[str, Any]) -> tuple[Any, ...]:
        score = int(row.get("rankingScore") or 0)
        age = get_number(row, "launchAgeDays")
        original_position = int(row.get("rankingPosition") or row["preQueuePosition"])
        return (
            -score,
            is_future_year_planner(row, run_date),
            -(age if age is not None else -1.0),
            original_position,
        )

    reordered = sorted(selected, key=queue_key)
    reordered_asins = [str(row.get("asin") or "") for row in reordered]
    if len(reordered_asins) != len(original_asins) or Counter(reordered_asins) != Counter(
        original_asins
    ):
        raise RuntimeError("P1 queue reorder must preserve the exact selected ASIN multiset")

    for position, row in enumerate(reordered, start=1):
        row["queuePosition"] = position
        row["queueReorderVersion"] = POST_SELECTION_QUEUE_REORDER_VERSION
        row["futureYearPlannerDemoted"] = is_future_year_planner(row, run_date)

    return reordered, {
        "enabled": True,
        "version": POST_SELECTION_QUEUE_REORDER_VERSION,
        "invariant": "post_selection_reorder_only",
        "selectedCount": len(reordered),
        "beforeOrderSha256": before_order_sha256,
        "afterOrderSha256": asin_queue_sha256(reordered),
        "beforeMultisetSha256": before_multiset_sha256,
        "afterMultisetSha256": asin_multiset_sha256(reordered),
        "asinMultisetPreserved": True,
        "orderChanged": original_asins != reordered_asins,
        "futureYearPlannerDemotedCount": sum(
            1 for row in reordered if row["futureYearPlannerDemoted"]
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a strict, deduplicated SellerSprite candidate queue.")
    parser.add_argument("--input-dir", required=True, type=Path)
    parser.add_argument(
        "--source-manifest",
        type=Path,
        help=f"Required for formal mode; schema {SOURCE_MANIFEST_SCHEMA_VERSION}.",
    )
    parser.add_argument(
        "--allow-legacy-source",
        action="store_true",
        help="Explicit rollback: accept unmanifested legacy query files without formal source guarantees.",
    )
    parser.add_argument("--history", type=Path, help="额外历史 ASIN 文本；严格合格历史台账始终自动读取。")
    parser.add_argument("--attempted", type=Path)
    parser.add_argument("--project-root", type=Path, default=ROOT)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--queue-name", required=True)
    parser.add_argument("--queue-size", type=int, default=20)
    parser.add_argument("--run-date", default=date.today().isoformat())
    parser.add_argument("--min-traffic-age-days", type=int, default=24)
    parser.add_argument("--source-contains", action="append", default=[], help="Only select candidates whose source query contains this text.")
    parser.add_argument("--exclude-tag", action="append", default=[], help="Skip candidates carrying this preselection review tag.")
    parser.add_argument("--max-per-source", type=int, default=4)
    parser.add_argument("--max-per-brand", type=int, default=2)
    parser.add_argument(
        "--disable-tier1-2-ranking",
        action="store_true",
        help="Use the pre-Tier-1.2 priority_score ordering as an immediate rollback.",
    )
    parser.add_argument(
        "--ranking-version",
        choices=(PRIORITY_RANKING_VERSION_V2, PRIORITY_RANKING_VERSION_V1),
        default=PRIORITY_RANKING_VERSION_V2,
        help="Tier 1.2 reorder-only ranking version; v2 scores launch age 28-90 days at maximum.",
    )
    parser.add_argument(
        "--use-ranking-v1",
        "--use-tier1-2-ranking-v1",
        action="store_true",
        help="Explicit rollback to tier1.2-probability-v1 (28-80 day maximum age score).",
    )
    parser.add_argument(
        "--disable-post-selection-reorder",
        action="store_true",
        help="Rollback: keep the selected queue in its existing Tier 1.2 order.",
    )
    parser.add_argument(
        "--disable-a-source-prefilter-v2",
        action="store_true",
        help=f"Rollback: disable the conservative {A_SOURCE_PREFILTER_VERSION} source-only A-gate filter.",
    )
    parser.add_argument(
        "--allow-missing-parent-child-sales",
        action="store_true",
        help=(
            f"Versioned Excel-source override ({OPTIONAL_PARENT_CHILD_SALES_VERSION}): "
            "parent/child sales may remain missing; values are never estimated or substituted."
        ),
    )
    args = parser.parse_args()

    if bool(args.source_manifest) == bool(args.allow_legacy_source):
        parser.error("choose exactly one source mode: --source-manifest for formal runs or --allow-legacy-source for rollback")

    rules = read_json(ROOT / "config" / "rules.json")
    exclusions = read_json(ROOT / "config" / "exclusions.json")
    run_date = date.fromisoformat(args.run_date)
    strict_history_asins = load_strict_qualified_asins(args.project_root)
    manual_history_asins = read_asins(args.history)
    attempted_asins = read_asins(args.attempted)
    historical_asins = strict_history_asins | manual_history_asins
    excluded_asins = historical_asins | attempted_asins
    args.output_dir.mkdir(parents=True, exist_ok=True)

    manifest_contract: dict[str, Any] | None = None
    if args.source_manifest:
        try:
            manifest_contract = validate_source_manifest(args.source_manifest, args.input_dir)
        except (OSError, json.JSONDecodeError, SourceContractError) as exc:
            parser.error(f"source manifest validation failed: {exc}")

    raw_source_rows: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    raw_source_row_count = 0
    for path in sorted(args.input_dir.glob("query_*.json")):
        rows = read_json(path)
        if not isinstance(rows, list):
            parser.error(f"source file must contain a top-level JSON array: {path.name}")
        source_contract = manifest_contract["inputs"].get(path.name) if manifest_contract else None
        for row_index, item in enumerate(rows, start=1):
            raw_source_row_count += 1
            if not isinstance(item, dict):
                rejected.append(
                    {
                        "asin": "",
                        "stage": "source_contract",
                        "reason": f"invalid row object: {path.name} row {row_index}",
                    }
                )
                continue
            item = dict(item)
            asin = str(item.get("asin") or "").upper()
            item["asin"] = asin
            source_evidence = {
                "inputFile": path.name,
                "row": row_index,
                "sourcePage": item.get("sourcePage"),
                "sellerSpriteUrl": item.get("sellerSpriteUrl"),
            }
            if source_contract:
                source_evidence.update(
                    {
                        "inputSha256": source_contract["sha256"],
                        "manifestQueryUrl": source_contract["queryUrl"],
                    }
                )
                missing_or_invalid = validate_formal_row(
                    item,
                    source_contract,
                    allow_missing_parent_child_sales=args.allow_missing_parent_child_sales,
                )
                if missing_or_invalid:
                    rejected.append(
                        {
                            "asin": asin,
                            "stage": "source_contract",
                            "reason": "formal_row_invalid: " + ", ".join(missing_or_invalid),
                            "fields": missing_or_invalid,
                            "sourceEvidence": [source_evidence],
                        }
                    )
                    continue
            elif not ASIN_RE.fullmatch(asin):
                rejected.append(
                    {
                        "asin": asin,
                        "stage": "source_contract",
                        "reason": "invalid ASIN",
                        "sourceEvidence": [source_evidence],
                    }
                )
                continue
            item["_sourceEvidence"] = [source_evidence]
            raw_source_rows.append(item)

    source_rows, duplicate_conflicts, duplicate_asin_count = aggregate_duplicate_rows(raw_source_rows)
    rejected.extend(duplicate_conflicts)

    accepted: list[dict[str, Any]] = []
    history_skipped = 0
    attempted_skipped = 0
    a_source_prefilter_enabled = (
        ENABLE_A_SOURCE_PREFILTER_V2
        and not args.disable_a_source_prefilter_v2
    )
    a_source_prefilter_rule_counts: Counter[str] = Counter()
    for item in source_rows:
        asin = str(item.get("asin") or "").upper()
        if asin in excluded_asins:
            if asin in historical_asins:
                history_skipped += 1
                rejected.append({
                    "asin": asin,
                    "stage": "dedupe_history",
                    "reason": "already strict-qualified in history (auto-skip)",
                })
            else:
                attempted_skipped += 1
                rejected.append({"asin": asin, "stage": "dedupe_attempted", "reason": "already attempted"})
            continue
        category_hit = category_exclusion_hit(item)
        if category_hit:
            rejected.append(
                {
                    "asin": asin,
                    "stage": "exclusion",
                    "reason": f"hard category exclusion: {category_hit}",
                }
            )
            continue
        a_source_hit = a_source_hard_exclusion_hit(item) if a_source_prefilter_enabled else None
        if a_source_hit:
            rule = a_source_hit["rule"]
            term = a_source_hit["term"]
            a_source_prefilter_rule_counts[rule] += 1
            rejected.append(
                {
                    "asin": asin,
                    "stage": "exclusion",
                    "reason": (
                        f"source hard exclusion {A_SOURCE_PREFILTER_VERSION}: "
                        f"{rule}: {term}"
                    ),
                    "sourcePrefilterVersion": A_SOURCE_PREFILTER_VERSION,
                    "sourcePrefilterRule": rule,
                    "sourcePrefilterTerm": term,
                }
            )
            continue
        title_blob = f"{item.get('title') or ''} {item.get('categoryPath') or ''}".lower()
        safety_hit = next((term for term in EXTRA_SAFETY_TERMS if term in title_blob), None)
        if safety_hit:
            rejected.append({"asin": asin, "stage": "safety", "reason": f"extra safety term: {safety_hit}"})
            continue
        excl = exclusion_check(item, exclusions)
        if not excl.pass_:
            rejected.append({"asin": asin, "stage": excl.stage, "reason": excl.reason})
            continue
        excluded_tags = sorted(set(excl.tags) & set(args.exclude_tag))
        if excluded_tags:
            rejected.append({"asin": asin, "stage": "review_preference", "reason": f"excluded review tag(s): {', '.join(excluded_tags)}"})
            continue
        if not item.get("image"):
            rejected.append({"asin": asin, "stage": "data", "reason": "missing image URL"})
            continue
        age = launch_age_days(item, run_date)
        if age is not None and age < args.min_traffic_age_days:
            rejected.append({"asin": asin, "stage": "traffic_readiness", "reason": f"launch age {age} < {args.min_traffic_age_days} days"})
            continue
        pre = basic_prefilter(item, rules, run_date)
        if not pre.pass_:
            rejected.append({"asin": asin, "stage": pre.stage, "reason": pre.reason})
            continue
        enriched = dict(item)
        enriched["asin"] = asin
        enriched["preselectionWarnings"] = excl.warnings
        enriched["preselectionTags"] = excl.tags
        enriched["preselectionScore"] = priority_score(item, run_date, len(excl.warnings))
        enriched["launchAgeDays"] = age
        accepted.append(enriched)

    ranking_version = PRIORITY_RANKING_VERSION_V1 if args.use_ranking_v1 else args.ranking_version
    ranking_enabled = ENABLE_TIER1_2_PRIORITY_RANKING and not args.disable_tier1_2_ranking
    if ranking_enabled:
        accepted = probability_rank_candidates(accepted, rules, run_date, ranking_version)
    else:
        accepted.sort(
            key=lambda row: (
                -int(row["preselectionScore"]),
                int(row.get("reviews") or 999999),
                int(row.get("variations") or 999999),
                row["asin"],
            )
        )

    selected: list[dict[str, Any]] = []
    source_counts: Counter[str] = Counter()
    brand_counts: Counter[str] = Counter()
    used_variants: set[str] = set()
    for item in accepted:
        source = str(item.get("sourcePage") or "unknown")
        brand = str(item.get("brand") or "unknown").lower()
        key = variant_key(item)
        if args.source_contains and not any(term.lower() in source.lower() for term in args.source_contains):
            continue
        if source_counts[source] >= args.max_per_source or brand_counts[brand] >= args.max_per_brand or key in used_variants:
            continue
        selected.append(item)
        source_counts[source] += 1
        brand_counts[brand] += 1
        used_variants.add(key)
        if len(selected) >= args.queue_size:
            break

    if len(selected) < args.queue_size:
        raise SystemExit(f"only {len(selected)} candidates available for requested queue size {args.queue_size}")

    queue_reorder_summary: dict[str, Any] | None = None
    queue_reorder_enabled = (
        ENABLE_POST_SELECTION_QUEUE_REORDER
        and ranking_enabled
        and not args.disable_post_selection_reorder
    )
    if queue_reorder_enabled:
        selected, queue_reorder_summary = post_selection_queue_reorder(selected, run_date)

    prefix = args.output_dir / args.queue_name
    (prefix.with_suffix(".json")).write_text(json.dumps(selected, ensure_ascii=False, indent=2), encoding="utf-8")
    (args.output_dir / f"asin_queue_{args.queue_name}.txt").write_text("\n".join(row["asin"] for row in selected) + "\n", encoding="ascii")
    (args.output_dir / "screened_candidates_all.json").write_text(json.dumps(accepted, ensure_ascii=False, indent=2), encoding="utf-8")
    (args.output_dir / "screened_rejected.json").write_text(json.dumps(rejected, ensure_ascii=False, indent=2), encoding="utf-8")
    summary = {
        "sourceRows": len(source_rows),
        "rawSourceRows": raw_source_row_count,
        "duplicateAsinCount": duplicate_asin_count,
        "duplicateConflictCount": len(duplicate_conflicts),
        "screenedAccepted": len(accepted),
        "screenedRejected": len(rejected),
        "selected": len(selected),
        "queueName": args.queue_name,
        "historyStrictQualifiedCount": len(strict_history_asins),
        "historySkippedCount": history_skipped,
        "attemptedSkippedCount": attempted_skipped,
        "attemptedExclusion": {
            "enabled": bool(args.attempted),
            "version": EXPLICIT_ATTEMPTED_EXCLUSION_VERSION if args.attempted else None,
            "input": str(args.attempted) if args.attempted else None,
            "inputSha256": sha256_file(args.attempted) if args.attempted else None,
            "skippedCount": attempted_skipped,
            "invariant": "downward_only_explicit_queue_dedupe",
            "rollback": "omit --attempted",
        },
        "aSourcePrefilter": {
            "enabled": a_source_prefilter_enabled,
            "version": A_SOURCE_PREFILTER_VERSION,
            "invariant": "downward_only_existing_A_gate",
            "rejectedCount": sum(a_source_prefilter_rule_counts.values()),
            "ruleCounts": dict(a_source_prefilter_rule_counts),
            "rollbackFlag": "--disable-a-source-prefilter-v2",
        },
        "sourceCounts": dict(source_counts),
        "selectedAsins": [row["asin"] for row in selected],
        "sourceContract": (
            {
                "mode": "formal",
                "schemaVersion": manifest_contract["schemaVersion"],
                "manifestPath": manifest_contract["manifestPath"],
                "capturedAt": manifest_contract["capturedAt"],
                "market": manifest_contract["market"],
                "preset": manifest_contract["preset"],
                "categoryScope": manifest_contract["categoryScope"],
                "verifiedInputCount": len(manifest_contract["inputs"]),
                "optionalParentChildSales": {
                    "enabled": args.allow_missing_parent_child_sales,
                    "version": (
                        OPTIONAL_PARENT_CHILD_SALES_VERSION
                        if args.allow_missing_parent_child_sales
                        else None
                    ),
                    "invariant": "missing_values_remain_missing_no_substitution",
                    "rollback": "omit --allow-missing-parent-child-sales",
                },
            }
            if manifest_contract
            else {
                "mode": "legacy_opt_in",
                "warning": "formal freshness, query-scope, and file-hash guarantees were not applied",
            }
        ),
    }
    if ranking_enabled:
        summary["ranking"] = {
            "enabled": True,
            "version": ranking_version,
            "invariant": "reorder_only",
            "orderedCandidateCount": len(accepted),
            "scoreHistogram": dict(Counter(str(row["rankingScore"]) for row in accepted)),
            "selected": [
                {
                    "asin": row["asin"],
                    "position": row["rankingPosition"],
                    "rankingPosition": row["rankingPosition"],
                    "queuePosition": row.get("queuePosition"),
                    "score": row["rankingScore"],
                }
                for row in selected
            ],
        }
    if queue_reorder_summary is not None:
        summary["queueReorder"] = queue_reorder_summary
    (args.output_dir / f"summary_{args.queue_name}.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
