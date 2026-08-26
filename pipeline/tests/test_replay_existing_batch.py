from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")


def candidate(asin: str) -> dict:
    return {
        "asin": asin,
        "title": "Simple metal desk organizer",
        "brand": "TestBrand",
        "price": 19.99,
        "rating": 4.5,
        "reviews": 10,
        "childSales": 100,
        "parentSales": 150,
        "launchDate": "2026-06-15",
        "variations": 1,
        "image": "https://example.com/image.png",
        "sourcePage": "desk organizer",
    }


def traffic_result(asin: str, row: int) -> dict:
    return {
        "row": row,
        "targetAsin": asin,
        "actualAsin": asin,
        "status": "ok",
        "latestNaturalSharePct": 90.0,
        "recent4AvgNaturalSharePct": 85.0,
        "recent4MinNaturalSharePct": 75.0,
        "weeksRead": 4,
        "trafficWindow": "recent 4 weeks",
        "asinMismatch": False,
    }


class ReplayExistingBatchTests(unittest.TestCase):
    def test_run_scoped_manual_gate_a_rejection_precedes_normal_checks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            batch_path = root / "batch.json"
            candidate_path = root / "candidates.json"
            run_dir = root / "run"
            asin = "B0AAAA0001"
            write_json(
                batch_path,
                {
                    "batchName": "manual-gate-a-test",
                    "operator": "test",
                    "queueHash": "manual-gate-a-hash",
                    "results": [traffic_result(asin, 1)],
                },
            )
            write_json(candidate_path, [candidate(asin)])

            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "replay_existing_batch.py"),
                    "--batch-json",
                    str(batch_path),
                    "--candidates-json",
                    str(candidate_path),
                    "--run-id",
                    "manual_gate_a_test",
                    "--run-dir",
                    str(run_dir),
                    "--project-root",
                    str(root),
                    "--run-date",
                    "2026-07-15",
                    "--target",
                    "1",
                    "--max-attempts",
                    "10",
                    "--manual-reject-asin",
                    asin.lower(),
                    "--overwrite",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
            final_rows = json.loads((run_dir / "final_candidates_data.json").read_text(encoding="utf-8"))
            audit_rows = json.loads((run_dir / "rejected_audit_data.json").read_text(encoding="utf-8"))
            self.assertEqual(final_rows, [])
            self.assertEqual(audit_rows[0]["stage"], "exclusion")
            self.assertEqual(audit_rows[0]["rejectRule"], "manual_gate_a_brand_ip_risk")
            self.assertIn("manual Gate A", audit_rows[0]["rejectDetail"])

    def test_hard_exclusion_precedes_commercial_prefilter(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            batch_path = root / "batch.json"
            candidate_path = root / "candidates.json"
            run_dir = root / "run"
            asin = "B0AAAA0001"
            excluded_candidate = candidate(asin)
            excluded_candidate["title"] = "Super Mario Decorations"
            excluded_candidate["price"] = 1.0
            write_json(
                batch_path,
                {
                    "batchName": "gate-order-test",
                    "operator": "test",
                    "queueHash": "gate-order-hash",
                    "results": [traffic_result(asin, 1)],
                },
            )
            write_json(candidate_path, [excluded_candidate])

            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "replay_existing_batch.py"),
                    "--batch-json",
                    str(batch_path),
                    "--candidates-json",
                    str(candidate_path),
                    "--run-id",
                    "gate_order_test",
                    "--run-dir",
                    str(run_dir),
                    "--project-root",
                    str(root),
                    "--run-date",
                    "2026-07-15",
                    "--target",
                    "1",
                    "--max-attempts",
                    "10",
                    "--overwrite",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
            audit_rows = json.loads((run_dir / "rejected_audit_data.json").read_text(encoding="utf-8"))
            self.assertEqual(audit_rows[0]["stage"], "exclusion")
            self.assertIn("super mario", audit_rows[0]["rejectDetail"])

    def test_runner_target_control_cannot_grant_offline_acceptance(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            batch_path = root / "batch.json"
            candidate_path = root / "candidates.json"
            run_dir = root / "run"
            asin = "B0AAAA0001"
            failing_candidate = candidate(asin)
            failing_candidate["price"] = 55.0
            result_record = traffic_result(asin, 1)
            result_record.update(
                {
                    "strictDecision": "pass",
                    "qualified": True,
                    "dimensions": "product dimensions 10 x 8 inches",
                    "priceTrend": "stable for 30 days",
                    "priceTrendClass": "stable",
                    "currentPrice": 19.99,
                }
            )
            write_json(
                batch_path,
                {
                    "batchName": "target-control-test",
                    "operator": "test",
                    "queueHash": "target-control-hash",
                    "targetQualified": 10,
                    "requestedFinalTargetAtStart": 10,
                    "remainingTargetAtStart": 1,
                    "browserPassesThisBatch": 1,
                    "targetControlVersion": "p1-cumulative-remaining-v1",
                    "stoppedReason": "target_reached",
                    "results": [result_record],
                },
            )
            write_json(candidate_path, [failing_candidate])

            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "replay_existing_batch.py"),
                    "--batch-json",
                    str(batch_path),
                    "--candidates-json",
                    str(candidate_path),
                    "--run-id",
                    "target_control_test",
                    "--run-dir",
                    str(run_dir),
                    "--project-root",
                    str(root),
                    "--run-date",
                    "2026-07-15",
                    "--target",
                    "1",
                    "--max-attempts",
                    "10",
                    "--overwrite",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
            summary = json.loads((run_dir / "run_summary.json").read_text(encoding="utf-8"))
            final_rows = json.loads((run_dir / "final_candidates_data.json").read_text(encoding="utf-8"))
            self.assertEqual(final_rows, [])
            self.assertEqual(summary["qualifiedCount"], 0)
            self.assertFalse(summary["completedTarget"])

    def test_runner_current_price_v1_is_authoritative_and_audited(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            batch_path = root / "batch.json"
            candidate_path = root / "candidates.json"
            enrichment_path = root / "enrichment.json"
            run_dir = root / "run"
            asin = "B0AAAA0001"
            result_record = traffic_result(asin, 1)
            result_record.update(
                {
                    "dimensions": "product dimensions 10 x 8 inches",
                    "priceTrend": "stable for 30 days",
                    "priceTrendClass": "stable",
                    "currentPrice": 55.0,
                }
            )
            write_json(
                batch_path,
                {
                    "batchName": "runner-current-price-test",
                    "operator": "test",
                    "queueHash": "runner-current-price-hash",
                    "results": [result_record],
                },
            )
            write_json(candidate_path, [candidate(asin)])
            write_json(enrichment_path, [{"asin": asin, "currentPrice": 19.99}])

            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "replay_existing_batch.py"),
                    "--batch-json",
                    str(batch_path),
                    "--candidates-json",
                    str(candidate_path),
                    "--run-id",
                    "runner_current_price_test",
                    "--run-dir",
                    str(run_dir),
                    "--project-root",
                    str(root),
                    "--run-date",
                    "2026-07-15",
                    "--enrichment-json",
                    str(enrichment_path),
                    "--target",
                    "1",
                    "--max-attempts",
                    "10",
                    "--runner-current-price-v1",
                    "--overwrite",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
            summary = json.loads((run_dir / "run_summary.json").read_text(encoding="utf-8"))
            audit_rows = json.loads((run_dir / "rejected_audit_data.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["priceEvidencePolicy"], "runner_current_price_v1")
            self.assertEqual(audit_rows[0]["rejectRule"], "price_out_of_range")
            self.assertEqual(audit_rows[0]["product"]["sourcePrice"], 19.99)
            self.assertEqual(audit_rows[0]["product"]["currentPrice"], 55.0)
            self.assertEqual(audit_rows[0]["product"]["price"], 55.0)
            self.assertEqual(audit_rows[0]["product"]["priceSource"], "runner_current_price_v1")

    def test_runner_current_price_v1_fails_closed_when_current_price_is_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            batch_path = root / "batch.json"
            candidate_path = root / "candidates.json"
            enrichment_path = root / "enrichment.json"
            run_dir = root / "run"
            asin = "B0AAAA0001"
            result_record = traffic_result(asin, 1)
            result_record.update(
                {
                    "dimensions": "product dimensions 10 x 8 inches",
                    "priceTrend": "stable for 30 days",
                    "priceTrendClass": "stable",
                }
            )
            write_json(
                batch_path,
                {
                    "batchName": "runner-current-price-missing-test",
                    "operator": "test",
                    "queueHash": "runner-current-price-missing-hash",
                    "results": [result_record],
                },
            )
            write_json(candidate_path, [candidate(asin)])
            write_json(enrichment_path, [{"asin": asin, "currentPrice": 19.99}])

            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "replay_existing_batch.py"),
                    "--batch-json",
                    str(batch_path),
                    "--candidates-json",
                    str(candidate_path),
                    "--run-id",
                    "runner_current_price_missing_test",
                    "--run-dir",
                    str(run_dir),
                    "--project-root",
                    str(root),
                    "--run-date",
                    "2026-07-15",
                    "--enrichment-json",
                    str(enrichment_path),
                    "--target",
                    "1",
                    "--max-attempts",
                    "10",
                    "--runner-current-price-v1",
                    "--overwrite",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
            audit_rows = json.loads((run_dir / "rejected_audit_data.json").read_text(encoding="utf-8"))
            self.assertEqual(audit_rows[0]["rejectRule"], "missing_fields")
            self.assertIn("price", audit_rows[0]["rejectDetail"])
            self.assertIsNone(audit_rows[0]["product"]["price"])
            self.assertEqual(audit_rows[0]["product"]["sourcePrice"], 19.99)

    def test_runner_current_price_v1_writes_live_price_to_final_candidate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            images = root / "images"
            images.mkdir()
            batch_path = root / "batch.json"
            candidate_path = root / "candidates.json"
            run_dir = root / "run"
            asin = "B0AAAA0001"
            (images / f"{asin}.png").write_bytes(b"not-a-real-png")
            source_candidate = candidate(asin)
            source_candidate["price"] = 9.99
            result_record = traffic_result(asin, 1)
            result_record.update(
                {
                    "dimensions": "product dimensions 10 x 8 inches",
                    "priceTrend": "rising for 30 days",
                    "priceTrendClass": "rising",
                    "currentPrice": 11.99,
                }
            )
            write_json(
                batch_path,
                {
                    "batchName": "runner-current-price-final-test",
                    "operator": "test",
                    "queueHash": "runner-current-price-final-hash",
                    "results": [result_record],
                },
            )
            write_json(candidate_path, [source_candidate])

            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "replay_existing_batch.py"),
                    "--batch-json",
                    str(batch_path),
                    "--candidates-json",
                    str(candidate_path),
                    "--image-dir",
                    str(images),
                    "--run-id",
                    "runner_current_price_final_test",
                    "--run-dir",
                    str(run_dir),
                    "--project-root",
                    str(root),
                    "--run-date",
                    "2026-07-15",
                    "--target",
                    "1",
                    "--max-attempts",
                    "10",
                    "--runner-current-price-v1",
                    "--overwrite",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
            final_rows = json.loads((run_dir / "final_candidates_data.json").read_text(encoding="utf-8"))
            self.assertEqual(len(final_rows), 1)
            self.assertEqual(final_rows[0]["product"]["sourcePrice"], 9.99)
            self.assertEqual(final_rows[0]["product"]["currentPrice"], 11.99)
            self.assertEqual(final_rows[0]["product"]["price"], 11.99)

    def test_historical_strict_asin_is_audited_but_never_reenters_final_pool(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prior_run = root / "runs" / "prior_delivery"
            prior_run.mkdir(parents=True)
            asin = "B0AAAA0001"
            write_json(prior_run / "final_candidates_data.json", [{"asin": asin}])
            (prior_run / "acceptance_report.md").write_text(
                "# report\n- Delivery complete: yes\n",
                encoding="utf-8",
            )
            batch_path = root / "batch.json"
            candidate_path = root / "candidates.json"
            run_dir = root / "runs" / "current_delivery"
            write_json(
                batch_path,
                {
                    "batchName": "history-test",
                    "operator": "test",
                    "queueHash": "history-hash",
                    "results": [traffic_result(asin, 1)],
                },
            )
            write_json(candidate_path, [candidate(asin)])

            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "replay_existing_batch.py"),
                    "--batch-json",
                    str(batch_path),
                    "--candidates-json",
                    str(candidate_path),
                    "--run-id",
                    "history_test",
                    "--run-dir",
                    str(run_dir),
                    "--project-root",
                    str(root),
                    "--run-date",
                    "2026-07-11",
                    "--target",
                    "1",
                    "--max-attempts",
                    "10",
                    "--overwrite",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
            summary = json.loads((run_dir / "run_summary.json").read_text(encoding="utf-8"))
            final_rows = json.loads((run_dir / "final_candidates_data.json").read_text(encoding="utf-8"))
            audit_rows = json.loads((run_dir / "rejected_audit_data.json").read_text(encoding="utf-8"))
            self.assertEqual(final_rows, [])
            self.assertEqual(summary["historySkippedCount"], 1)
            self.assertEqual(audit_rows[0]["stage"], "dedupe_history")
            self.assertEqual(audit_rows[0]["rejectRule"], "already_strict_qualified")

    def test_multiple_batch_candidate_pairs_accumulate_to_exact_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            images = root / "source_images"
            images.mkdir()
            run_dir = root / "run"
            asins = ["B0AAAA0001", "B0AAAA0002"]
            batch_paths = []
            candidate_paths = []
            enrichment_path = root / "enrichment.json"

            for index, asin in enumerate(asins, start=1):
                (images / f"{asin}.png").write_bytes(b"not-a-real-png")
                batch_path = root / f"batch_{index}.json"
                candidate_path = root / f"candidates_{index}.json"
                result_record = traffic_result(asin, index)
                if index == 1:
                    result_record.update(
                        {
                            "dimensions": "商品尺寸 10 x 8 inches",
                            "priceTrend": "近30天价格稳定",
                            "priceTrendClass": "stable",
                            "priceTrendWindow": "past 30 days",
                            "priceTrendSource": "integrated runner",
                        }
                    )
                write_json(
                    batch_path,
                    {
                        "batchName": f"test-{index}",
                        "operator": "test",
                        "queueHash": f"hash-{index}",
                        "results": [result_record],
                    },
                )
                write_json(candidate_path, [candidate(asin)])
                batch_paths.append(batch_path)
                candidate_paths.append(candidate_path)

            write_json(
                enrichment_path,
                [
                    {
                        "asin": asins[1],
                        "dimensions": "商品尺寸 10 x 8 inches",
                        "priceTrend": "近30天价格稳定",
                        "priceTrendClass": "stable",
                        "priceTrendWindow": "past 30 days",
                        "priceTrendSource": "test",
                    }
                ],
            )

            command = [
                sys.executable,
                str(ROOT / "scripts" / "replay_existing_batch.py"),
                "--run-id",
                "multi_batch_test",
                "--run-dir",
                str(run_dir),
                "--project-root",
                str(root),
                "--run-date",
                "2026-07-11",
                "--target",
                "2",
                "--max-attempts",
                "10",
                "--image-dir",
                str(images),
                "--enrichment-json",
                str(enrichment_path),
                "--overwrite",
            ]
            for batch_path, candidate_path in zip(batch_paths, candidate_paths):
                command.extend(["--batch-json", str(batch_path), "--candidates-json", str(candidate_path)])

            result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=False)
            self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
            summary = json.loads((run_dir / "run_summary.json").read_text(encoding="utf-8"))
            final_rows = json.loads((run_dir / "final_candidates_data.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["qualifiedCount"], 2)
            self.assertTrue(summary["completedTarget"])
            self.assertEqual(summary["remainingTarget"], 0)
            self.assertEqual(summary["batchJsons"], [str(path) for path in batch_paths])
            self.assertEqual([row["asin"] for row in final_rows], asins)
            self.assertTrue(all(row["product"]["dimensions"] for row in final_rows))
            self.assertTrue(all(row["product"]["priceTrendClass"] == "stable" for row in final_rows))


if __name__ == "__main__":
    unittest.main()
