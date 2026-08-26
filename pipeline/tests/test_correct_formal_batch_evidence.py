import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "correct_formal_batch_evidence.py"


class CorrectFormalBatchEvidenceTests(unittest.TestCase):
    def test_marks_verified_url_mismatch_without_overwriting_source(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            source = temp / "raw.json"
            output = temp / "corrected.json"
            raw = {
                "results": [{
                    "targetAsin": "B0TARGET00",
                    "actualAsin": "B0TARGET00",
                    "url": "https://www.amazon.com/dp/B0ACTUAL00?th=1",
                    "asinMismatch": False,
                    "qualified": True,
                }]
            }
            source.write_text(json.dumps(raw), encoding="utf-8")
            subprocess.run([
                sys.executable, str(SCRIPT),
                "--input", str(source),
                "--output", str(output),
                "--target-asin", "B0TARGET00",
                "--actual-asin", "B0ACTUAL00",
                "--evidence", "human page verification",
            ], check=True, capture_output=True, text=True)
            self.assertEqual(json.loads(source.read_text(encoding="utf-8")), raw)
            row = json.loads(output.read_text(encoding="utf-8"))["results"][0]
            self.assertTrue(row["asinMismatch"])
            self.assertFalse(row["qualified"])
            self.assertEqual(row["actualAsin"], "B0ACTUAL00")

    def test_rejects_conflicting_actual_asin(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            source = temp / "raw.json"
            output = temp / "corrected.json"
            source.write_text(json.dumps({"results": [{
                "targetAsin": "B0TARGET00",
                "url": "https://www.amazon.com/dp/B0ACTUAL00",
            }]}), encoding="utf-8")
            completed = subprocess.run([
                sys.executable, str(SCRIPT),
                "--input", str(source),
                "--output", str(output),
                "--target-asin", "B0TARGET00",
                "--actual-asin", "B0WRONG000",
                "--evidence", "human page verification",
            ], capture_output=True, text=True)
            self.assertNotEqual(completed.returncode, 0)
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
