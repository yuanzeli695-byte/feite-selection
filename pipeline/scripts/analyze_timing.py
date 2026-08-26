"""Analyze SellerSprite Runner timing and gate TSV exports.

This tool is observation-only. It never evaluates or changes product eligibility.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "sellerSpriteTimingAnalysis/v1"
KEY_FIELDS = ("batchName", "queueHash", "asin")
STAGE_FIELDS = (
    ("detailPageMs", "detailPageMsReason"),
    ("trafficChartMs", "trafficChartMsReason"),
    ("dimensionsMs", "dimensionsMsReason"),
    ("priceChartMs", "priceChartMsReason"),
)
TIMING_REQUIRED = {
    "startedAt",
    "finishedAt",
    *KEY_FIELDS,
    "runnerVersion",
    "collectorVersion",
    *(field for pair in STAGE_FIELDS for field in pair),
    "retryCount",
    "retryDecision",
    "retryReason",
    "totalMs",
}
GATE_REQUIRED = {
    "finishedAt",
    *KEY_FIELDS,
    "outcome",
    "rejectionRule",
    "rejectionReason",
}


class ContractError(ValueError):
    """Raised when exported evidence is incomplete or internally inconsistent."""


def _key(row: dict[str, str]) -> tuple[str, str, str]:
    return tuple((row.get(field) or "").strip() for field in KEY_FIELDS)  # type: ignore[return-value]


def _read_tsv(path: Path, required: set[str]) -> list[dict[str, str]]:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle, delimiter="\t")
            fields = set(reader.fieldnames or [])
            missing = sorted(required - fields)
            if missing:
                raise ContractError(f"{path}: missing columns: {', '.join(missing)}")
            rows = [dict(row) for row in reader]
    except OSError as error:
        raise ContractError(f"cannot read {path}: {error}") from error
    if not rows:
        raise ContractError(f"{path}: no data rows")
    return rows


def _number(value: str | None, field: str, key: tuple[str, str, str], *, integer: bool = False) -> float | int | None:
    text = (value or "").strip()
    if not text:
        return None
    try:
        number = int(text) if integer else float(text)
    except ValueError as error:
        raise ContractError(f"{key}: {field} is not numeric: {text!r}") from error
    if number < 0 or (not integer and not math.isfinite(float(number))):
        raise ContractError(f"{key}: {field} must be a finite non-negative number")
    return number


def _timestamp(value: str | None, field: str, key: tuple[str, str, str]) -> datetime | None:
    text = (value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as error:
        raise ContractError(f"{key}: invalid {field}: {text!r}") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ContractError(f"{key}: {field} must include a timezone offset")
    return parsed


def _percentile(values: list[float], quantile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * quantile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def _stats(values: list[float], total_count: int) -> dict[str, Any]:
    return {
        "count": len(values),
        "missing": total_count - len(values),
        "sumMs": round(sum(values), 3),
        "p50Ms": _round_or_none(_percentile(values, 0.5)),
        "p90Ms": _round_or_none(_percentile(values, 0.9)),
        "maxMs": _round_or_none(max(values) if values else None),
    }


def _round_or_none(value: float | None, digits: int = 3) -> float | None:
    return None if value is None else round(value, digits)


def _pair_files(run_dir: Path) -> list[tuple[Path, Path]]:
    timing_files = sorted(run_dir.glob("timing_log_*.tsv"))
    gate_files = sorted(run_dir.glob("gate_log_*.tsv"))
    if not timing_files:
        raise ContractError(f"{run_dir}: no timing_log_*.tsv files")
    timing_by_suffix = {path.stem.removeprefix("timing_log_"): path for path in timing_files}
    gate_by_suffix = {path.stem.removeprefix("gate_log_"): path for path in gate_files}
    if set(timing_by_suffix) != set(gate_by_suffix):
        missing_gate = sorted(set(timing_by_suffix) - set(gate_by_suffix))
        missing_timing = sorted(set(gate_by_suffix) - set(timing_by_suffix))
        raise ContractError(
            f"timing/gate file mismatch; missing gate={missing_gate}, missing timing={missing_timing}"
        )
    return [(timing_by_suffix[suffix], gate_by_suffix[suffix]) for suffix in sorted(timing_by_suffix)]


def _validated_rows(timing_path: Path, gate_path: Path) -> list[dict[str, Any]]:
    timing_rows = _read_tsv(timing_path, TIMING_REQUIRED)
    gate_rows = _read_tsv(gate_path, GATE_REQUIRED)
    timing_map: dict[tuple[str, str, str], dict[str, str]] = {}
    gate_map: dict[tuple[str, str, str], dict[str, str]] = {}
    for label, rows, target in (("timing", timing_rows, timing_map), ("gate", gate_rows, gate_map)):
        for row in rows:
            key = _key(row)
            if not all(key):
                raise ContractError(f"{label} row has an incomplete composite key: {key}")
            if key in target:
                raise ContractError(f"duplicate {label} key: {key}")
            target[key] = row
    if set(timing_map) != set(gate_map):
        orphan_timing = sorted(set(timing_map) - set(gate_map))
        orphan_gate = sorted(set(gate_map) - set(timing_map))
        raise ContractError(f"orphan rows; timing={orphan_timing[:5]}, gate={orphan_gate[:5]}")
    batch_identities = {(key[0], key[1]) for key in timing_map}
    if len(batch_identities) != 1:
        raise ContractError(
            f"{timing_path.name}/{gate_path.name}: expected one batchName/queueHash pair, got {sorted(batch_identities)}"
        )

    validated: list[dict[str, Any]] = []
    for key, timing in timing_map.items():
        gate = gate_map[key]
        outcome = (gate.get("outcome") or "").strip()
        if outcome not in {"pass", "reject", "skip"}:
            raise ContractError(f"{key}: unsupported gate outcome {outcome!r}")
        gate_finished = _timestamp(gate.get("finishedAt"), "gate.finishedAt", key)
        if gate_finished is None and outcome != "skip":
            raise ContractError(f"{key}: only skip rows may omit gate.finishedAt")
        started = _timestamp(timing.get("startedAt"), "startedAt", key)
        finished = _timestamp(timing.get("finishedAt"), "finishedAt", key)
        if (started is None) != (finished is None):
            raise ContractError(f"{key}: startedAt and finishedAt must both be present or both be blank")
        if started and finished and finished < started:
            raise ContractError(f"{key}: finishedAt precedes startedAt")
        if started is None and outcome != "skip":
            raise ContractError(f"{key}: only skip rows may omit browser timestamps")

        stages: dict[str, float | None] = {}
        for value_field, reason_field in STAGE_FIELDS:
            value = _number(timing.get(value_field), value_field, key)
            reason = (timing.get(reason_field) or "").strip()
            if value is None and not reason:
                raise ContractError(f"{key}: blank {value_field} requires {reason_field}")
            stages[value_field] = float(value) if value is not None else None
        total = _number(timing.get("totalMs"), "totalMs", key)
        if total is None:
            raise ContractError(f"{key}: totalMs is required")
        retry_count = _number(timing.get("retryCount"), "retryCount", key, integer=True)
        if retry_count is None:
            raise ContractError(f"{key}: retryCount is required")
        if outcome == "skip" and (float(total) != 0 or int(retry_count) != 0):
            raise ContractError(f"{key}: skip rows must have zero totalMs and retryCount")

        validated.append(
            {
                "key": key,
                "timing": timing,
                "gate": gate,
                "outcome": outcome,
                "started": started,
                "finished": finished,
                "gateFinished": gate_finished,
                "stages": stages,
                "totalMs": float(total),
                "retryCount": int(retry_count),
                "sourceTiming": str(timing_path),
                "sourceGate": str(gate_path),
            }
        )
    return validated


def _batch_summary(rows: list[dict[str, Any]], suffix: str) -> dict[str, Any]:
    browser_rows = sorted((row for row in rows if row["started"] is not None), key=lambda row: row["started"])
    if not browser_rows:
        raise ContractError(f"batch {suffix}: no browser-visited rows")
    first = browser_rows[0]
    last = browser_rows[-1]
    observed_wall = (last["finished"] - first["started"]).total_seconds() * 1000
    initial_detail = first["stages"]["detailPageMs"] or 0.0
    inferred_wall = observed_wall + initial_detail

    intra_gap = 0.0
    detail_claim = 0.0
    detail_outside_observed = initial_detail
    for previous, current in zip(browser_rows, browser_rows[1:]):
        raw_gap = (current["started"] - previous["finished"]).total_seconds() * 1000
        if raw_gap < 0:
            raise ContractError(
                f"batch {suffix}: overlapping browser rows {previous['key'][2]} and {current['key'][2]}"
            )
        gap = raw_gap
        detail = current["stages"]["detailPageMs"] or 0.0
        claimed = min(gap, detail)
        intra_gap += gap
        detail_claim += claimed
        detail_outside_observed += max(0.0, detail - gap)

    stage_totals = {
        field: sum((row["stages"][field] or 0.0) for row in browser_rows)
        for field, _ in STAGE_FIELDS
    }
    active_total = sum(row["totalMs"] for row in browser_rows)
    row_clock = sum((row["finished"] - row["started"]).total_seconds() * 1000 for row in browser_rows)
    inner_stage = stage_totals["trafficChartMs"] + stage_totals["dimensionsMs"] + stage_totals["priceChartMs"]
    stage_sum = stage_totals["detailPageMs"] + inner_stage
    row_active_overhead = active_total - inner_stage
    row_clock_overhead = row_clock - inner_stage
    unattributed_gap = intra_gap - detail_claim
    detail_outside_inferred = max(0.0, detail_outside_observed - initial_detail)

    return {
        "suffix": suffix,
        "batchName": first["key"][0],
        "queueHash": first["key"][1],
        "rows": len(rows),
        "browserRows": len(browser_rows),
        "firstStartedAt": first["started"].isoformat(),
        "lastFinishedAt": last["finished"].isoformat(),
        "observedStartAt": first["started"].isoformat(),
        "inferredNavigationStartAt": (first["started"] - timedelta(milliseconds=initial_detail)).isoformat(),
        "initialDetailMs": round(initial_detail, 3),
        "observedWallMs": round(observed_wall, 3),
        "inferredWallIncludingInitialNavigationMs": round(inferred_wall, 3),
        "activeTotalMs": round(active_total, 3),
        "rowClockMs": round(row_clock, 3),
        "intraBatchGapMs": round(intra_gap, 3),
        "stageSumMs": round(stage_sum, 3),
        "observedWallMinusStageMs": round(observed_wall - stage_sum, 3),
        "inferredWallMinusStageMs": round(inferred_wall - stage_sum, 3),
        "attribution": {
            "detailClaimInsideGapsMs": round(detail_claim, 3),
            "detailOutsideObservedWallMs": round(detail_outside_observed, 3),
            "detailOutsideInferredWallMs": round(detail_outside_inferred, 3),
            "rowActiveOverheadMs": round(row_active_overhead, 3),
            "rowClockOverheadMs": round(row_clock_overhead, 3),
            "unattributedGapMs": round(unattributed_gap, 3),
            "timingClockDriftMs": round(row_clock - active_total, 3),
            "overlapTransitions": 0,
        },
    }


def analyze_run(run_dir: str | Path) -> dict[str, Any]:
    run_path = Path(run_dir).resolve()
    if not run_path.is_dir():
        raise ContractError(f"run directory does not exist: {run_path}")

    all_rows: list[dict[str, Any]] = []
    batches: list[dict[str, Any]] = []
    source_files: list[dict[str, str]] = []
    for timing_path, gate_path in _pair_files(run_path):
        suffix = timing_path.stem.removeprefix("timing_log_")
        rows = _validated_rows(timing_path, gate_path)
        all_rows.extend(rows)
        batches.append(_batch_summary(rows, suffix))
        source_files.append({"timing": str(timing_path), "gate": str(gate_path)})

    batch_keys = [(batch["batchName"], batch["queueHash"]) for batch in batches]
    if len(batch_keys) != len(set(batch_keys)):
        raise ContractError("duplicate batchName/queueHash pairs across TSV files")
    batches.sort(key=lambda batch: batch["observedStartAt"])

    stage_values = {
        field: [row["stages"][field] for row in all_rows if row["stages"][field] is not None]
        for field, _ in STAGE_FIELDS
    }
    total_values = [row["totalMs"] for row in all_rows]
    stages = {field: _stats(values, len(all_rows)) for field, values in stage_values.items()}
    stages["totalMs"] = _stats(total_values, len(all_rows))

    outcomes = defaultdict(int)
    rejection_values: dict[str, list[float]] = defaultdict(list)
    retry_rows: list[dict[str, Any]] = []
    for row in all_rows:
        outcomes[row["outcome"]] += 1
        if row["outcome"] == "reject":
            rule = (row["gate"].get("rejectionRule") or "unclassified_reject").strip() or "unclassified_reject"
            rejection_values[rule].append(row["totalMs"])
        if row["retryCount"] > 0:
            retry_rows.append(row)

    rejection_cost = []
    reject_total = sum(sum(values) for values in rejection_values.values())
    for rule, values in sorted(rejection_values.items(), key=lambda item: (-len(item[1]), item[0])):
        rejection_cost.append(
            {
                "rule": rule,
                **_stats(values, len(values)),
                "shareOfRejectActivePct": round(100 * sum(values) / reject_total, 4) if reject_total else 0.0,
            }
        )

    observed_inter_batch_gap = 0.0
    inferred_inter_batch_gap = 0.0
    for previous, current in zip(batches, batches[1:]):
        previous_end = datetime.fromisoformat(previous["lastFinishedAt"])
        observed_start = datetime.fromisoformat(current["observedStartAt"])
        inferred_start = datetime.fromisoformat(current["inferredNavigationStartAt"])
        observed_inter_batch_gap += max(0.0, (observed_start - previous_end).total_seconds() * 1000)
        inferred_inter_batch_gap += max(0.0, (inferred_start - previous_end).total_seconds() * 1000)

    first_observed = datetime.fromisoformat(batches[0]["observedStartAt"])
    first_inferred = datetime.fromisoformat(batches[0]["inferredNavigationStartAt"])
    last_finished = datetime.fromisoformat(batches[-1]["lastFinishedAt"])
    observed_batch_wall = sum(batch["observedWallMs"] for batch in batches)
    inferred_batch_wall = sum(batch["inferredWallIncludingInitialNavigationMs"] for batch in batches)
    stage_sum = sum(batch["stageSumMs"] for batch in batches)
    unattributed_gap = sum(batch["attribution"]["unattributedGapMs"] for batch in batches)
    row_active_overhead = sum(batch["attribution"]["rowActiveOverheadMs"] for batch in batches)
    row_clock_overhead = sum(batch["attribution"]["rowClockOverheadMs"] for batch in batches)
    timing_clock_drift = sum(batch["attribution"]["timingClockDriftMs"] for batch in batches)
    detail_outside_observed = sum(batch["attribution"]["detailOutsideObservedWallMs"] for batch in batches)
    detail_outside_inferred = sum(batch["attribution"]["detailOutsideInferredWallMs"] for batch in batches)
    observed_residual = observed_batch_wall - stage_sum
    inferred_residual = inferred_batch_wall - stage_sum

    return {
        "schemaVersion": SCHEMA_VERSION,
        "runDir": str(run_path),
        "generatedAt": datetime.now().astimezone().isoformat(timespec="seconds"),
        "validation": {
            "timingRows": len(all_rows),
            "gateRows": len(all_rows),
            "uniqueCompositeKeys": len({_row["key"] for _row in all_rows}),
            "orphanRows": 0,
            "batchPairs": len(batches),
        },
        "outcomes": dict(sorted(outcomes.items())),
        "stages": stages,
        "batches": batches,
        "overall": {
            "observedBatchWallMs": round(observed_batch_wall, 3),
            "inferredBatchWallIncludingInitialNavigationMs": round(inferred_batch_wall, 3),
            "activeTotalMs": round(sum(total_values), 3),
            "stageSumMs": round(stage_sum, 3),
            "observedWallMinusStageMs": round(observed_residual, 3),
            "inferredWallMinusStageMs": round(inferred_residual, 3),
            "observedInterBatchGapMs": round(observed_inter_batch_gap, 3),
            "inferredInterBatchGapMs": round(inferred_inter_batch_gap, 3),
            "observedEndToEndMs": round((last_finished - first_observed).total_seconds() * 1000, 3),
            "inferredEndToEndIncludingInitialNavigationMs": round(
                (last_finished - first_inferred).total_seconds() * 1000, 3
            ),
            "unattributedIntraBatchGapMs": round(unattributed_gap, 3),
            "rowActiveOverheadMs": round(row_active_overhead, 3),
            "rowClockOverheadMs": round(row_clock_overhead, 3),
            "timingClockDriftMs": round(timing_clock_drift, 3),
            "detailOutsideObservedWallMs": round(detail_outside_observed, 3),
            "detailOutsideInferredWallMs": round(detail_outside_inferred, 3),
            "residualAttribution": {
                "observed": {
                    "residualMs": round(observed_residual, 3),
                    "unattributedIntraBatchGapMs": round(unattributed_gap, 3),
                    "rowClockOverheadMs": round(row_clock_overhead, 3),
                    "detailOutsideWallBoundaryMs": round(detail_outside_observed, 3),
                    "equation": "residual = unattributed gap + row-clock overhead - detail outside observed wall",
                },
                "inferred": {
                    "residualMs": round(inferred_residual, 3),
                    "unattributedIntraBatchGapMs": round(unattributed_gap, 3),
                    "rowClockOverheadMs": round(row_clock_overhead, 3),
                    "detailOutsideWallBoundaryMs": round(detail_outside_inferred, 3),
                    "equation": "residual = unattributed gap + row-clock overhead - detail outside inferred wall",
                },
                "legacyEvidenceLimit": (
                    "Legacy TSV cannot split the unattributed gap into panel rendering, JSON serialization, "
                    "storage writes, or fixed delays; Runner 0.3.8 granular telemetry measures those separately."
                ),
            },
        },
        "rejectionCost": rejection_cost,
        "retries": {
            "rows": len(retry_rows),
            "attempts": sum(row["retryCount"] for row in retry_rows),
            "finalPasses": sum(1 for row in retry_rows if row["outcome"] == "pass"),
            "finalPassRatePct": round(
                100 * sum(1 for row in retry_rows if row["outcome"] == "pass") / len(retry_rows), 4
            ) if retry_rows else 0.0,
            "recoveryYield": "unknown",
            "recoveryYieldReason": "TSV contains final row outcome but not the first-attempt outcome",
        },
        "sourceFiles": source_files,
    }


def render_markdown(analysis: dict[str, Any]) -> str:
    overall = analysis["overall"]
    outcomes = analysis["outcomes"]
    lines = [
        "# SellerSprite timing analysis",
        "",
        f"- Run: `{analysis['runDir']}`",
        f"- Timing/gate rows: {analysis['validation']['timingRows']} / {analysis['validation']['gateRows']}",
        f"- Outcomes: pass={outcomes.get('pass', 0)}, reject={outcomes.get('reject', 0)}, skip={outcomes.get('skip', 0)}",
        f"- Observed batch wall: {overall['observedBatchWallMs'] / 60000:.2f} min",
        f"- Inferred wall including each batch's initial navigation: {overall['inferredBatchWallIncludingInitialNavigationMs'] / 60000:.2f} min",
        f"- Stage sum: {overall['stageSumMs'] / 60000:.2f} min",
        f"- Observed wall minus stage residual: {overall['observedWallMinusStageMs'] / 60000:.3f} min",
        f"- Inferred wall minus stage residual: {overall['inferredWallMinusStageMs'] / 60000:.3f} min",
        f"- Unattributed intra-batch gap: {overall['unattributedIntraBatchGapMs'] / 60000:.2f} min",
        f"- Observed inter-batch gap: {overall['observedInterBatchGapMs'] / 60000:.2f} min",
        "",
        "The two wall-time values intentionally use different boundaries. The inferred value adds the first row's",
        "`detailPageMs` to each batch; it must not be mixed with the observed first-start to last-finish span.",
        "",
        "## Residual attribution",
        "",
        (
            f"- Observed: {overall['observedWallMinusStageMs']:.0f} ms = "
            f"{overall['unattributedIntraBatchGapMs']:.0f} ms unattributed gap + "
            f"{overall['rowClockOverheadMs']:.0f} ms row-clock overhead - "
            f"{overall['detailOutsideObservedWallMs']:.0f} ms detail outside the observed boundary."
        ),
        (
            f"- Inferred: {overall['inferredWallMinusStageMs']:.0f} ms = "
            f"{overall['unattributedIntraBatchGapMs']:.0f} ms unattributed gap + "
            f"{overall['rowClockOverheadMs']:.0f} ms row-clock overhead - "
            f"{overall['detailOutsideInferredWallMs']:.0f} ms detail outside the inferred boundary."
        ),
        f"- Timing clock drift (`rowClockMs - totalMs`): {overall['timingClockDriftMs']:.0f} ms.",
        "",
        analysis["overall"]["residualAttribution"]["legacyEvidenceLimit"],
        "",
        "## Stage statistics",
        "",
        "| Stage | Count | Missing | Sum min | P50 ms | P90 ms | Max ms |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for field, stats in analysis["stages"].items():
        lines.append(
            f"| {field} | {stats['count']} | {stats['missing']} | {stats['sumMs'] / 60000:.2f} | "
            f"{stats['p50Ms'] or 0:.1f} | {stats['p90Ms'] or 0:.1f} | {stats['maxMs'] or 0:.1f} |"
        )
    lines.extend(
        [
            "",
            "## Retry result",
            "",
            f"- Retried rows: {analysis['retries']['rows']}",
            f"- Retry attempts: {analysis['retries']['attempts']}",
            f"- Final passes after a retried row: {analysis['retries']['finalPasses']}",
            "- Recovery yield: unknown because first-attempt outcomes are not present in the TSV contract.",
            "",
            "## Rejection active-time cost",
            "",
            "| Rule | Rows | Sum min | P50 ms | P90 ms |",
            "|---|---:|---:|---:|---:|",
        ]
    )
    for item in analysis["rejectionCost"]:
        lines.append(
            f"| {item['rule']} | {item['count']} | {item['sumMs'] / 60000:.2f} | "
            f"{item['p50Ms'] or 0:.1f} | {item['p90Ms'] or 0:.1f} |"
        )
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Analyze SellerSprite timing and gate TSV evidence.")
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--format", choices=("json", "markdown", "both"), default="both")
    parser.add_argument("--json-out", type=Path)
    parser.add_argument("--markdown-out", type=Path)
    args = parser.parse_args(argv)
    try:
        analysis = analyze_run(args.run_dir)
        run_dir = args.run_dir.resolve()
        if args.format in {"json", "both"}:
            json_out = (args.json_out or (run_dir / "timing_analysis.json")).resolve()
            json_out.parent.mkdir(parents=True, exist_ok=True)
            json_out.write_text(json.dumps(analysis, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            print(json_out)
        if args.format in {"markdown", "both"}:
            markdown_out = (args.markdown_out or (run_dir / "timing_analysis.md")).resolve()
            markdown_out.parent.mkdir(parents=True, exist_ok=True)
            markdown_out.write_text(render_markdown(analysis), encoding="utf-8")
            print(markdown_out)
        return 0
    except ContractError as error:
        print(f"[ERROR] {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
