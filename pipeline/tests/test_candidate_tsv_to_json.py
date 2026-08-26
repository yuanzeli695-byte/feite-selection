from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class CandidateTsvToJsonTests(unittest.TestCase):
    def test_history_is_skipped_without_an_opt_in_flag(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp) / "project"
            input_dir = project_root / "incoming"
            prior_run = project_root / "runs" / "prior_delivery"
            input_dir.mkdir(parents=True)
            prior_run.mkdir(parents=True)
            (prior_run / "final_candidates_data.json").write_text(
                json.dumps([{"asin": "B0AAAA0001"}]),
                encoding="utf-8",
            )
            (prior_run / "acceptance_report.md").write_text(
                "# report\n- Delivery complete: yes\n",
                encoding="utf-8",
            )
            tsv = input_dir / "candidate_meta_test.tsv"
            tsv.write_text(
                "\t".join([
                    "asin", "title", "brand", "price", "rating", "reviews", "childSales",
                    "parentSales", "launchDate", "variations", "image", "sourcePage",
                ])
                + "\n"
                + "\t".join([
                    "B0AAAA0001", "Already delivered", "Brand", "19.99", "4.5", "10", "100",
                    "120", "2026-05-01", "1", "https://example.com/old.png", "storage",
                ])
                + "\n"
                + "\t".join([
                    "B0AAAA0002", "Fresh", "Brand", "19.99", "4.5", "10", "100",
                    "120", "2026-05-01", "1", "https://example.com/new.png", "storage",
                ])
                + "\n",
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "candidate_tsv_to_json.py"),
                    str(tsv),
                    "--project-root",
                    str(project_root),
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
            converted = json.loads((input_dir / "candidate_meta_test.json").read_text(encoding="utf-8"))
            sidecar = json.loads((input_dir / "candidate_meta_test.meta.json").read_text(encoding="utf-8"))
            report = (input_dir / "asin_queue_report.txt").read_text(encoding="utf-8")
            self.assertEqual([row["asin"] for row in converted], ["B0AAAA0002"])
            self.assertEqual(sidecar["historySkippedCount"], 1)
            self.assertIn("already strict-qualified in history (auto-skip)", report)


if __name__ == "__main__":
    unittest.main()
