import json
import tempfile
import unittest
from pathlib import Path

from scripts.strict_history import collect_strict_history


class StrictHistoryAcceptanceGateTests(unittest.TestCase):
    def test_unaccepted_preview_does_not_seed_history(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            run = root / "runs" / "preview"
            run.mkdir(parents=True)
            (run / "final_candidates_data.json").write_text(
                json.dumps([{"asin": "B0PREV0001"}]), encoding="utf-8"
            )
            self.assertNotIn("B0PREV0001", collect_strict_history(root))

    def test_machine_accepted_delivery_seeds_history(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            run = root / "runs" / "delivery"
            run.mkdir(parents=True)
            (run / "final_candidates_data.json").write_text(
                json.dumps([{"asin": "B0DLVR0001"}]), encoding="utf-8"
            )
            (run / "acceptance_report.md").write_text(
                "# report\n- Delivery complete: yes\n", encoding="utf-8"
            )
            self.assertIn("B0DLVR0001", collect_strict_history(root))


if __name__ == "__main__":
    unittest.main()
