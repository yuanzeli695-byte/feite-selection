from __future__ import annotations

import csv
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from analyze_timing import ContractError, analyze_run  # noqa: E402


TIMING_FIELDS = [
    "startedAt", "finishedAt", "batchName", "queueHash", "asin", "runnerVersion", "collectorVersion",
    "detailPageMs", "detailPageMsReason", "trafficChartMs", "trafficChartMsReason",
    "dimensionsMs", "dimensionsMsReason", "priceChartMs", "priceChartMsReason",
    "retryCount", "retryDecision", "retryReason", "totalMs",
]
GATE_FIELDS = [
    "finishedAt", "batchName", "queueHash", "asin", "outcome", "rejectionRule", "rejectionReason",
]


def timing_row(
    batch: str,
    queue_hash: str,
    asin: str,
    started: str,
    finished: str,
    *,
    detail: str = "1000",
    traffic: str = "1000",
    dimensions: str = "",
    price: str = "",
    retry: str = "0",
    total: str = "1000",
) -> dict[str, str]:
    return {
        "startedAt": started,
        "finishedAt": finished,
        "batchName": batch,
        "queueHash": queue_hash,
        "asin": asin,
        "runnerVersion": "0.3.8",
        "collectorVersion": "0.4.6",
        "detailPageMs": detail,
        "detailPageMsReason": "" if detail else "not_measured",
        "trafficChartMs": traffic,
        "trafficChartMsReason": "" if traffic else "not_run",
        "dimensionsMs": dimensions,
        "dimensionsMsReason": "" if dimensions else "not_run_due_to_prior_gate",
        "priceChartMs": price,
        "priceChartMsReason": "" if price else "not_run_due_to_prior_gate",
        "retryCount": retry,
        "retryDecision": "retry" if retry != "0" else "no_retry",
        "retryReason": "tooltip_not_ready" if retry != "0" else "known_traffic_failure",
        "totalMs": total,
    }


def gate_row(batch: str, queue_hash: str, asin: str, outcome: str, rule: str = "") -> dict[str, str]:
    return {
        "finishedAt": "2026-07-15T00:00:00Z",
        "batchName": batch,
        "queueHash": queue_hash,
        "asin": asin,
        "outcome": outcome,
        "rejectionRule": rule,
        "rejectionReason": rule,
    }


def write_tsv(path: Path, fields: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


class TimingAnalyzerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.run_dir = Path(self.temp.name)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def add_pair(self, suffix: str, timing: list[dict[str, str]], gates: list[dict[str, str]]) -> None:
        write_tsv(self.run_dir / f"timing_log_{suffix}.tsv", TIMING_FIELDS, timing)
        write_tsv(self.run_dir / f"gate_log_{suffix}.tsv", GATE_FIELDS, gates)

    def test_two_batches_report_boundaries_retries_and_rejection_cost(self) -> None:
        self.add_pair(
            "one",
            [
                timing_row("batch-1", "hash-1", "B0AAAA0001", "2026-07-15T00:00:01Z", "2026-07-15T00:00:03Z", detail="1000", traffic="1500", total="2000"),
                timing_row("batch-1", "hash-1", "B0AAAA0002", "2026-07-15T00:00:05Z", "2026-07-15T00:00:06Z", detail="1500", traffic="1000", retry="1", total="1000"),
            ],
            [
                gate_row("batch-1", "hash-1", "B0AAAA0001", "pass"),
                gate_row("batch-1", "hash-1", "B0AAAA0002", "reject", "traffic_error"),
            ],
        )
        self.add_pair(
            "two",
            [timing_row("batch-2", "hash-2", "B0AAAA0003", "2026-07-15T00:00:10Z", "2026-07-15T00:00:11Z")],
            [gate_row("batch-2", "hash-2", "B0AAAA0003", "reject", "traffic_weeks_insufficient")],
        )
        analysis = analyze_run(self.run_dir)
        self.assertEqual(analysis["validation"]["timingRows"], 3)
        self.assertEqual(analysis["outcomes"], {"pass": 1, "reject": 2})
        self.assertEqual(analysis["retries"]["rows"], 1)
        self.assertEqual(analysis["retries"]["finalPasses"], 0)
        self.assertEqual(analysis["retries"]["recoveryYield"], "unknown")
        self.assertEqual(analysis["overall"]["observedInterBatchGapMs"], 4000.0)
        self.assertEqual(analysis["overall"]["inferredInterBatchGapMs"], 3000.0)
        self.assertEqual(
            analysis["overall"]["inferredWallMinusStageMs"],
            analysis["overall"]["unattributedIntraBatchGapMs"]
            + analysis["overall"]["rowClockOverheadMs"]
            - analysis["overall"]["detailOutsideInferredWallMs"],
        )
        self.assertEqual({item["rule"] for item in analysis["rejectionCost"]}, {"traffic_error", "traffic_weeks_insufficient"})

    def test_blank_stage_requires_reason(self) -> None:
        row = timing_row("batch", "hash", "B0AAAA0001", "2026-07-15T00:00:01Z", "2026-07-15T00:00:02Z", traffic="")
        row["trafficChartMsReason"] = ""
        self.add_pair("bad", [row], [gate_row("batch", "hash", "B0AAAA0001", "reject", "traffic_error")])
        with self.assertRaisesRegex(ContractError, "blank trafficChartMs"):
            analyze_run(self.run_dir)

    def test_duplicate_keys_fail_closed(self) -> None:
        row = timing_row("batch", "hash", "B0AAAA0001", "2026-07-15T00:00:01Z", "2026-07-15T00:00:02Z")
        self.add_pair("dup", [row, row.copy()], [gate_row("batch", "hash", "B0AAAA0001", "pass")])
        with self.assertRaisesRegex(ContractError, "duplicate timing key"):
            analyze_run(self.run_dir)

    def test_orphan_keys_fail_closed(self) -> None:
        timing = timing_row("batch", "hash", "B0AAAA0001", "2026-07-15T00:00:01Z", "2026-07-15T00:00:02Z")
        gate = gate_row("batch", "hash", "B0AAAA0002", "pass")
        self.add_pair("orphan", [timing], [gate])
        with self.assertRaisesRegex(ContractError, "orphan rows"):
            analyze_run(self.run_dir)

    def test_mixed_batch_identity_in_one_file_fails_closed(self) -> None:
        self.add_pair(
            "mixed",
            [
                timing_row("batch-1", "hash-1", "B0AAAA0001", "2026-07-15T00:00:01Z", "2026-07-15T00:00:02Z"),
                timing_row("batch-2", "hash-2", "B0AAAA0002", "2026-07-15T00:00:03Z", "2026-07-15T00:00:04Z"),
            ],
            [
                gate_row("batch-1", "hash-1", "B0AAAA0001", "pass"),
                gate_row("batch-2", "hash-2", "B0AAAA0002", "reject", "traffic_error"),
            ],
        )
        with self.assertRaisesRegex(ContractError, "expected one batchName/queueHash pair"):
            analyze_run(self.run_dir)

    def test_overlapping_browser_rows_fail_closed(self) -> None:
        self.add_pair(
            "overlap",
            [
                timing_row("batch", "hash", "B0AAAA0001", "2026-07-15T00:00:01Z", "2026-07-15T00:00:04Z"),
                timing_row("batch", "hash", "B0AAAA0002", "2026-07-15T00:00:03Z", "2026-07-15T00:00:05Z"),
            ],
            [
                gate_row("batch", "hash", "B0AAAA0001", "pass"),
                gate_row("batch", "hash", "B0AAAA0002", "reject", "traffic_error"),
            ],
        )
        with self.assertRaisesRegex(ContractError, "overlapping browser rows"):
            analyze_run(self.run_dir)

    def test_gate_timestamp_and_timezone_fail_closed(self) -> None:
        timing = timing_row("batch", "hash", "B0AAAA0001", "2026-07-15T00:00:01Z", "2026-07-15T00:00:02Z")
        gate = gate_row("batch", "hash", "B0AAAA0001", "pass")
        gate["finishedAt"] = "not-a-time"
        self.add_pair("bad-gate-time", [timing], [gate])
        with self.assertRaisesRegex(ContractError, "invalid gate.finishedAt"):
            analyze_run(self.run_dir)

    def test_naive_timestamps_fail_closed(self) -> None:
        timing = timing_row("batch", "hash", "B0AAAA0001", "2026-07-15T00:00:01", "2026-07-15T00:00:02")
        self.add_pair("naive", [timing], [gate_row("batch", "hash", "B0AAAA0001", "pass")])
        with self.assertRaisesRegex(ContractError, "must include a timezone offset"):
            analyze_run(self.run_dir)

    def test_negative_duration_fails_closed(self) -> None:
        row = timing_row("batch", "hash", "B0AAAA0001", "2026-07-15T00:00:01Z", "2026-07-15T00:00:02Z", detail="-1")
        self.add_pair("negative", [row], [gate_row("batch", "hash", "B0AAAA0001", "pass")])
        with self.assertRaisesRegex(ContractError, "finite non-negative"):
            analyze_run(self.run_dir)

    def test_cli_writes_json_and_markdown(self) -> None:
        self.add_pair(
            "cli",
            [timing_row("batch", "hash", "B0AAAA0001", "2026-07-15T00:00:01Z", "2026-07-15T00:00:02Z")],
            [gate_row("batch", "hash", "B0AAAA0001", "pass")],
        )
        json_out = self.run_dir / "out.json"
        markdown_out = self.run_dir / "out.md"
        completed = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts" / "analyze_timing.py"),
                str(self.run_dir),
                "--json-out",
                str(json_out),
                "--markdown-out",
                str(markdown_out),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(json.loads(json_out.read_text(encoding="utf-8"))["schemaVersion"], "sellerSpriteTimingAnalysis/v1")
        markdown = markdown_out.read_text(encoding="utf-8")
        self.assertIn("SellerSprite timing analysis", markdown)
        self.assertIn("Legacy TSV cannot split the unattributed gap", markdown)


if __name__ == "__main__":
    unittest.main()
