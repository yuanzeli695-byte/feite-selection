from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from audit_strict_history_snapshot import HistoryAuditError, compare_histories  # noqa: E402


def history(updated_at: str = "2026-07-15T00:00:00Z") -> dict[str, object]:
    return {
        "schemaVersion": "strictQualifiedHistory/v1",
        "updatedAt": updated_at,
        "asins": {
            "B0AAAAAAAA": {"qualifiedAt": "preloaded", "source": "fixture"},
            "B0BBBBBBBB": {"qualifiedAt": "preloaded", "source": "fixture"},
        },
    }


class HistorySnapshotAuditTests(unittest.TestCase):
    def test_whitespace_and_object_order_do_not_change_canonical_identity(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = root / "first.json"
            second = root / "second.json"
            first.write_text(json.dumps(history(), indent=2), encoding="utf-8")
            second.write_text(json.dumps(history(), separators=(",", ":")), encoding="utf-8")
            result = compare_histories([first, second])
            self.assertTrue(result["allEqual"])
            self.assertEqual(result["snapshots"][0]["canonicalSha256"], result["snapshots"][1]["canonicalSha256"])
            self.assertEqual(result["snapshots"][0]["asinCount"], 2)

    def test_metadata_difference_is_not_hidden(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = root / "first.json"
            second = root / "second.json"
            first.write_text(json.dumps(history()), encoding="utf-8")
            second.write_text(json.dumps(history("2026-07-15T01:00:00Z")), encoding="utf-8")
            self.assertFalse(compare_histories([first, second])["allEqual"])

    def test_invalid_schema_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.json"
            path.write_text(json.dumps({"schemaVersion": "wrong", "asins": {}}), encoding="utf-8")
            with self.assertRaisesRegex(HistoryAuditError, "expected schemaVersion"):
                compare_histories([path])


if __name__ == "__main__":
    unittest.main()
