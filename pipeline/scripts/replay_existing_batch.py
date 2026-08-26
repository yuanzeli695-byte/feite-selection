#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from filter_engine import (  # noqa: E402
    basic_prefilter,
    commercial_recheck,
    enrichment_check,
    exclusion_check,
    launch_age_days,
    traffic_check,
)
from qualified_pool_manager import QualifiedPool  # noqa: E402
from state_store import StateStore, now_iso  # noqa: E402
from strict_history import load_strict_qualified_asins, sync_strict_history_registry  # noqa: E402


INLINE_ENRICHMENT_KEYS = (
    "dimensions",
    "itemDimensions",
    "itemWeight",
    "packageDimensions",
    "packageWeight",
    "dimensionsSource",
    "currentPrice",
    "priceTrend",
    "priceTrendClass",
    "priceTrendWindow",
    "priceTrendSource",
)


def read_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def write_json(path: str | Path, data: Any) -> None:
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def compact_traffic(record: dict[str, Any]) -> dict[str, Any]:
    keys = [
        "row",
        "targetAsin",
        "actualAsin",
        "status",
        "decision",
        "latestWeek",
        "latestNaturalSharePct",
        "recent4AvgNaturalSharePct",
        "recent4MinNaturalSharePct",
        "aggregateNaturalTraffic",
        "aggregateTotalTraffic",
        "aggregateNaturalSharePct",
        "aggregateWeeksRead",
        "trafficDetails",
        "weeksRead",
        "trafficWindow",
        "pass70",
        "asinMismatch",
        "mismatchReason",
        "note",
        "collectedAt",
    ]
    return {key: record.get(key) for key in keys if key in record}


def inline_enrichment(record: dict[str, Any]) -> dict[str, Any]:
    nested = record.get("enrichment") if isinstance(record.get("enrichment"), dict) else {}
    result: dict[str, Any] = {}
    for key in INLINE_ENRICHMENT_KEYS:
        value = record.get(key)
        if value in (None, ""):
            value = nested.get(key)
        if value not in (None, ""):
            result[key] = value
    return result


def merge_product_evidence(
    source_product: dict[str, Any],
    record: dict[str, Any],
    external_enrichment: dict[str, Any] | None,
    *,
    runner_current_price_v1: bool = False,
) -> dict[str, Any]:
    """Merge evidence while keeping Runner currentPrice authoritative when enabled."""
    merged = dict(source_product)
    runner_evidence = inline_enrichment(record)
    merged.update(runner_evidence)
    merged.update(external_enrichment or {})
    if runner_current_price_v1:
        # External enrichment may correct dimensions/trend evidence, but it may
        # neither replace nor synthesize the Runner's current price.
        merged["currentPrice"] = runner_evidence.get("currentPrice")
    return merged


def compact_product(
    product: dict[str, Any],
    run_date,
    *,
    runner_current_price_v1: bool = False,
) -> dict[str, Any]:
    age = launch_age_days(product, run_date)
    source_price = product.get("price")
    current_price = product.get("currentPrice")
    price = current_price if runner_current_price_v1 else source_price
    return {
        "asin": product.get("asin"),
        "title": product.get("title") or product.get("pageTitle") or "",
        "brand": product.get("brand") or "",
        "categoryPath": product.get("categoryPath") or product.get("category") or "",
        "price": price,
        "sourcePrice": source_price,
        "currentPrice": current_price,
        "priceSource": "runner_current_price_v1" if runner_current_price_v1 else "candidate_source_price_v1",
        "rating": product.get("rating"),
        "reviews": product.get("reviews"),
        "monthlySales": product.get("childSales") or product.get("monthlySales"),
        "parentMonthlySales": product.get("parentSales") or product.get("parentMonthlySales"),
        "launchDate": product.get("launchDate"),
        "launchAgeDays": age,
        "variationsCount": product.get("variations") or product.get("variationsCount"),
        "imageUrl": product.get("image") or product.get("imageUrl") or "",
        "sourcePage": product.get("sourcePage"),
        "delivery": product.get("delivery") or "",
        "dimensions": product.get("dimensions") or product.get("weightDimensions") or "",
        "itemDimensions": product.get("itemDimensions") or "",
        "itemWeight": product.get("itemWeight") or "",
        "packageDimensions": product.get("packageDimensions") or "",
        "packageWeight": product.get("packageWeight") or "",
        "priceTrend": product.get("priceTrend") or "",
        "priceTrendClass": product.get("priceTrendClass") or "",
        "priceTrendWindow": product.get("priceTrendWindow") or "",
        "priceTrendSource": product.get("priceTrendSource") or "",
        "dimensionsSource": product.get("dimensionsSource") or "",
        "sellerSpriteUrl": product.get("sellerSpriteUrl") or "",
        "rawProduct": product.get("rawProduct") or "",
    }


def append_jsonl(path: Path, record: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def reject(rejected_path: Path, product: dict[str, Any], traffic: dict[str, Any], stage: str, rule: str, detail: str, warnings: list[str], tags: list[str]) -> None:
    append_jsonl(
        rejected_path,
        {
            "asin": product.get("asin"),
            "stage": stage,
            "rejectRule": rule,
            "rejectDetail": detail,
            "warnings": warnings,
            "tags": tags,
            "traffic": traffic,
            "product": product,
            "at": now_iso(),
        },
    )


def copy_image_for_candidate(asin: str, source_dir: Path | None, run_dir: Path) -> str:
    if not source_dir:
        return ""
    for suffix in (".png", ".jpg", ".jpeg", ".webp"):
        source = source_dir / f"{asin}{suffix}"
        if source.exists():
            target_dir = run_dir / "images"
            target_dir.mkdir(parents=True, exist_ok=True)
            target = target_dir / f"{asin}.png" if suffix != ".png" else target_dir / source.name
            shutil.copy2(source, target)
            return str(target)
    return ""


def load_title_overrides(path: Path | None) -> dict[str, str]:
    if not path or not path.exists():
        return {}
    return read_json(path)


def load_enrichment(path: Path | None) -> dict[str, dict[str, Any]]:
    if not path or not path.exists():
        return {}
    data = read_json(path)
    if isinstance(data, list):
        return {str(item.get("asin")): item for item in data if isinstance(item, dict) and item.get("asin")}
    if isinstance(data, dict):
        return {str(asin): item for asin, item in data.items() if isinstance(item, dict)}
    raise ValueError(f"enrichment_json must be an array or object: {path}")


def load_sources(batch_paths: list[Path], candidate_paths: list[Path]) -> list[dict[str, Any]]:
    if len(batch_paths) != len(candidate_paths):
        raise ValueError("--batch-json and --candidates-json must be provided in matching pairs")

    sources: list[dict[str, Any]] = []
    for batch_path, candidate_path in zip(batch_paths, candidate_paths):
        batch = read_json(batch_path)
        candidates = read_json(candidate_path)
        if not isinstance(candidates, list):
            raise ValueError(f"candidates_json must be a top-level array, got {type(candidates).__name__}: {candidate_path}")
        if any(not isinstance(item, dict) for item in candidates):
            raise ValueError(f"candidates_json must contain only JSON objects: {candidate_path}")
        sources.append(
            {
                "batchPath": batch_path,
                "candidatePath": candidate_path,
                "batch": batch,
                "candidateByAsin": {item.get("asin"): item for item in candidates if item.get("asin")},
            }
        )
    return sources


def run(args: argparse.Namespace) -> int:
    rules = read_json(args.rules)
    exclusions = read_json(args.exclusions)
    pipeline = read_json(args.pipeline)
    title_overrides = load_title_overrides(args.title_overrides)
    enrichment_by_asin = load_enrichment(args.enrichment_json)
    sources = load_sources(args.batch_json, args.candidates_json)

    run_date = datetime.fromisoformat(str(args.run_date or rules.get("runDate"))[:10]).date()
    run_id = args.run_id or f"replay_{run_date.strftime('%Y%m%d')}_baseline"
    run_dir = Path(args.run_dir) if args.run_dir else ROOT / "runs" / run_id
    if run_dir.exists() and not args.overwrite:
        print(f"ERROR: run dir already exists: {run_dir}; pass --overwrite to replace generated files")
        return 2
    run_dir.mkdir(parents=True, exist_ok=True)

    for name in (
        "state.jsonl",
        "rejected.jsonl",
        "qualified_pool.json",
        "final_candidates_data.json",
        "rejected_audit_data.json",
        "run_summary.json",
    ):
        path = run_dir / name
        if path.exists():
            path.unlink()

    target_n = int(args.target or pipeline["targetN"])
    max_attempts = int(args.max_attempts or pipeline["maxAttemptTotal"])
    state = StateStore(run_dir / "state.jsonl")
    rejected_path = run_dir / "rejected.jsonl"
    pool = QualifiedPool(run_dir / "qualified_pool.json", run_id=run_id, target=target_n)
    strict_history_asins = load_strict_qualified_asins(args.project_root, exclude_run_dir=run_dir)
    manual_reject_asins = {
        str(value).strip().upper()
        for value in (args.manual_reject_asin or [])
        if str(value).strip()
    }
    raw_candidates: list[dict[str, Any]] = []
    attempted_asins: set[str] = set()
    history_skipped = 0
    attempts = 0
    stopped_reason = "source_exhausted"
    stop = False

    for source in sources:
        batch = source["batch"]
        candidate_by_asin = source["candidateByAsin"]
        for record in batch.get("results", []):
            if pool.count() >= target_n and not args.process_all:
                stopped_reason = "target_reached"
                stop = True
                break
            if attempts >= max_attempts:
                stopped_reason = "max_attempts"
                stop = True
                break

            asin = record.get("targetAsin")
            if not asin or asin in attempted_asins:
                continue
            attempted_asins.add(asin)

            if asin in strict_history_asins:
                source_product = dict(candidate_by_asin.get(asin, {}))
                source_product["asin"] = asin
                source_product.setdefault("title", record.get("pageTitle") or "")
                source_product = merge_product_evidence(
                    source_product,
                    record,
                    enrichment_by_asin.get(asin),
                    runner_current_price_v1=args.runner_current_price_v1,
                )
                source_product["asin"] = asin
                product = compact_product(
                    source_product,
                    run_date,
                    runner_current_price_v1=args.runner_current_price_v1,
                )
                traffic = compact_traffic(record)
                state.mark(asin, "history_skip", reason="already strict-qualified in history (auto-skip)")
                reject(
                    rejected_path,
                    product,
                    traffic,
                    "dedupe_history",
                    "already_strict_qualified",
                    "already strict-qualified in history (auto-skip)",
                    [],
                    [],
                )
                history_skipped += 1
                continue
            attempts += 1

            source_product = dict(candidate_by_asin.get(asin, {}))
            source_product["asin"] = asin
            source_product.setdefault("title", record.get("pageTitle") or "")
            source_product = merge_product_evidence(
                source_product,
                record,
                enrichment_by_asin.get(asin),
                runner_current_price_v1=args.runner_current_price_v1,
            )
            source_product["asin"] = asin
            product = compact_product(
                source_product,
                run_date,
                runner_current_price_v1=args.runner_current_price_v1,
            )
            traffic = compact_traffic(record)
            warnings: list[str] = []
            tags: list[str] = []
            raw_candidates.append({"product": product, "traffic": traffic})

            state.mark(asin, "candidate_taken")
            if asin.upper() in manual_reject_asins:
                reason = "run-scoped manual Gate A rejection: obvious brand/IP risk"
                state.mark(asin, "excl_fail", prev_state="candidate_taken", reason=reason)
                reject(
                    rejected_path,
                    product,
                    traffic,
                    "exclusion",
                    "manual_gate_a_brand_ip_risk",
                    reason,
                    warnings,
                    tags,
                )
                continue
            excl = exclusion_check(product, exclusions)
            warnings.extend(excl.warnings)
            tags.extend(excl.tags)
            if not excl.pass_:
                state.mark(asin, "excl_fail", prev_state="candidate_taken", reason=excl.reason)
                reject(rejected_path, product, traffic, excl.stage, excl.rule, excl.reason, warnings, tags)
                continue
            state.mark(asin, "excl_pass", prev_state="candidate_taken", warningCount=len(warnings))

            pre = basic_prefilter(product, rules, run_date)
            if not pre.pass_:
                state.mark(asin, "prefilter_fail", prev_state="excl_pass", reason=pre.reason)
                reject(rejected_path, product, traffic, pre.stage, pre.rule, pre.reason, warnings, tags)
                continue
            state.mark(asin, "prefilter_pass", prev_state="excl_pass")

            if traffic.get("status") == "ok":
                state.mark(asin, "traffic_ok", prev_state="prefilter_pass")
            else:
                status = traffic.get("status") or "missing"
                reason = traffic.get("note") or f"traffic status {status}"
                state.mark(asin, "traffic_error", prev_state="prefilter_pass", reason=reason)
                reject(rejected_path, product, traffic, "traffic", f"traffic_{status}", str(reason), warnings, tags)
                continue

            traffic_result = traffic_check(traffic, rules)
            if not traffic_result.pass_:
                state_name = "hard_review" if traffic_result.decision == "review" else "hard_fail"
                state.mark(asin, state_name, prev_state="traffic_ok", reason=traffic_result.reason)
                reject(rejected_path, product, traffic, traffic_result.stage, traffic_result.rule, traffic_result.reason, warnings, tags)
                continue

            commercial = commercial_recheck(product, rules, run_date)
            if not commercial.pass_:
                state.mark(asin, "hard_fail", prev_state="traffic_ok", reason=commercial.reason)
                reject(rejected_path, product, traffic, commercial.stage, commercial.rule, commercial.reason, warnings, tags)
                continue

            enrichment = enrichment_check(product, rules)
            if not enrichment.pass_:
                state.mark(asin, "hard_fail", prev_state="traffic_ok", reason=enrichment.reason)
                reject(rejected_path, product, traffic, enrichment.stage, enrichment.rule, enrichment.reason, warnings, tags)
                continue

            state.mark(asin, "hard_pass", prev_state="traffic_ok", warningCount=len(warnings))
            image_path = copy_image_for_candidate(asin, args.image_dir, run_dir)
            if rules.get("imageEmbedRequired", True) and not image_path:
                state.mark(asin, "image_fail", prev_state="hard_pass", reason="qualified product has no local image")
                reject(rejected_path, product, traffic, "image", "image_missing", "qualified product has no local image", warnings, tags)
                continue

            state.mark(asin, "image_ok", prev_state="hard_pass")
            final_candidate = {
                "asin": asin,
                "cnTitle": title_overrides.get(asin) or product.get("title") or asin,
                "product": product,
                "traffic": traffic,
                "warnings": warnings,
                "tags": tags,
                "imagePath": image_path,
                "amazonUrl": f"https://www.amazon.com/dp/{asin}?th=1",
                "source": {
                    "batchName": batch.get("batchName"),
                    "operator": batch.get("operator"),
                    "queueHash": batch.get("queueHash"),
                    "row": record.get("row"),
                },
            }
            if pool.count() < target_n:
                pool.add(final_candidate)
                state.mark(asin, "QUALIFIED", prev_state="image_ok")
            else:
                state.mark(asin, "qualified_overflow", prev_state="image_ok")
                reject(
                    rejected_path,
                    product,
                    traffic,
                    "selection",
                    "qualified_overflow",
                    "all hard rules passed, but targetN was already filled",
                    warnings,
                    tags,
                )

        if stop:
            break

    if pool.count() >= target_n and stopped_reason == "source_exhausted" and not args.process_all:
        stopped_reason = "target_reached"

    rejected_rows = []
    if rejected_path.exists():
        rejected_rows = [json.loads(line) for line in rejected_path.read_text(encoding="utf-8").splitlines() if line.strip()]

    write_json(run_dir / "candidates_raw.json", raw_candidates)
    write_json(run_dir / "final_candidates_data.json", pool.data["candidates"])
    write_json(run_dir / "rejected_audit_data.json", rejected_rows)
    history_registry = sync_strict_history_registry(args.project_root)
    summary = {
        "runId": run_id,
        "runDir": str(run_dir),
        "batchJson": str(args.batch_json[0]),
        "candidatesJson": str(args.candidates_json[0]),
        "batchJsons": [str(path) for path in args.batch_json],
        "candidatesJsons": [str(path) for path in args.candidates_json],
        "enrichmentJson": str(args.enrichment_json) if args.enrichment_json else None,
        "priceEvidencePolicy": (
            "runner_current_price_v1" if args.runner_current_price_v1 else "candidate_source_price_v1"
        ),
        "targetN": target_n,
        "attempts": attempts,
        "qualifiedCount": pool.count(),
        "rejectedCount": len(rejected_rows),
        "historyStrictQualifiedCount": len(strict_history_asins),
        "historySkippedCount": history_skipped,
        "historyRegistryCount": history_registry["count"],
        "maxAttempts": max_attempts,
        "completedTarget": pool.count() == target_n,
        "remainingTarget": max(target_n - pool.count(), 0),
        "sourceExhausted": stopped_reason == "source_exhausted",
        "stoppedReason": stopped_reason,
        "runDate": run_date.isoformat(),
        "createdAt": now_iso(),
    }
    write_json(run_dir / "run_summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Replay an existing SellerSprite batch through the hard-filter pipeline.")
    parser.add_argument("--batch-json", required=True, type=Path, action="append", help="Repeat for each Batch Runner JSON.")
    parser.add_argument("--candidates-json", required=True, type=Path, action="append", help="Repeat in the same order as --batch-json.")
    parser.add_argument("--image-dir", type=Path)
    parser.add_argument("--enrichment-json", type=Path, help="Dimensions and price-trend enrichment keyed by ASIN.")
    parser.add_argument("--run-id")
    parser.add_argument("--run-dir", type=Path)
    parser.add_argument("--run-date")
    parser.add_argument("--target", type=int)
    parser.add_argument("--max-attempts", type=int)
    parser.add_argument("--process-all", action="store_true", help="Keep auditing records after targetN is reached.")
    parser.add_argument(
        "--runner-current-price-v1",
        action="store_true",
        help=(
            "Use only the Runner's currentPrice for Gate B/E and workbook price. "
            "Missing Runner currentPrice fails closed; omit this flag to restore the prior candidate-source price path."
        ),
    )
    parser.add_argument(
        "--manual-reject-asin",
        action="append",
        default=[],
        help="Repeat for a run-scoped Gate A brand/IP rejection without changing global exclusions.",
    )
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--project-root", type=Path, default=ROOT)
    parser.add_argument("--rules", type=Path, default=ROOT / "config" / "rules.json")
    parser.add_argument("--exclusions", type=Path, default=ROOT / "config" / "exclusions.json")
    parser.add_argument("--pipeline", type=Path, default=ROOT / "config" / "pipeline.json")
    parser.add_argument("--title-overrides", type=Path, default=ROOT / "config" / "zh_title_overrides.json")
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(run(parse_args()))
