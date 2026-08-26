from __future__ import annotations

import csv
import json
import subprocess
import sys
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from openpyxl import Workbook


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_ROOT / "scripts" / "sellersprite_export_to_runner_queue.py"
HEADERS = [
    "ASIN",
    "商品名称",
    "品牌",
    "类目",
    "月销量",
    "子体销量",
    "父体销量",
    "价格",
    "评分",
    "评分数",
    "变体数",
    "上架时间",
    "主图链接",
]
REAL_EXPORT_HEADERS = [
    "图片",
    "ASIN",
    "商品标题",
    "品牌",
    "类目路径",
    "月销量",
    "子体销量",
    "父ASIN",
    "价格($)",
    "评分",
    "评分数",
    "变体数",
    "上架时间",
    "商品主图",
]


def row(asin: str, title: str = "Desk Drawer Organizer") -> list[object]:
    return [
        asin,
        title,
        "Acme",
        "Home & Kitchen > Storage & Organization",
        800,
        800,
        1000,
        19.99,
        4.5,
        42,
        3,
        date.today() - timedelta(days=45),
        f"https://images.example.com/{asin}.jpg",
    ]


def real_export_row(asin: str, title: str = "Desk Drawer Organizer") -> list[object]:
    return [
        "thumbnail-not-used",
        asin,
        title,
        "Acme",
        "Home & Kitchen > Storage & Organization",
        800,
        800,
        "B0PARENT00",
        19.99,
        4.5,
        42,
        3,
        date.today() - timedelta(days=45),
        f"https://images.example.com/{asin}.jpg",
    ]


class SellerSpriteExportQueueTests(unittest.TestCase):
    def run_script(self, *arguments: object) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPT), *map(str, arguments)],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_formal_xlsx_builds_auditable_runner_queue_and_reuses_history(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            export = root / "seller_sprite.xlsx"
            workbook = Workbook()
            sheet = workbook.active
            sheet.append(REAL_EXPORT_HEADERS)
            sheet.append(real_export_row("B0AAAA0001"))
            sheet.append(real_export_row("B0AAAA0002"))
            sheet.append(real_export_row("B0AAAA0003", "Solar Garden Lights"))
            for row_number in range(2, 5):
                asin = sheet.cell(row_number, 2).value
                sheet.cell(row_number, 2).hyperlink = f"https://www.amazon.com/dp/{asin}"
                sheet.cell(row_number, 14).hyperlink = sheet.cell(row_number, 14).value
            workbook.save(export)
            workbook.close()

            project_root = root / "project"
            delivery = project_root / "runs" / "prior_delivery"
            delivery.mkdir(parents=True)
            (delivery / "final_candidates_data.json").write_text(
                json.dumps([{"asin": "B0AAAA0001"}]), encoding="utf-8"
            )
            (delivery / "acceptance_report.md").write_text(
                "- Delivery complete: yes\n", encoding="utf-8"
            )
            output = root / "out"
            completed = self.run_script(
                export,
                "--output-dir",
                output,
                "--queue-name",
                "storage_01",
                "--queue-size",
                "1",
                "--query-url",
                "https://www.sellersprite.com/v3/product-research?market=US&maxReviews=100&nodeIdPaths=%5B%22123456%22%5D",
                "--captured-at",
                datetime.now(timezone.utc).isoformat(),
                "--run-date",
                date.today().isoformat(),
                "--project-root",
                project_root,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)

            queue_path = output / "candidate_pool" / "asin_queue_storage_01.txt"
            self.assertEqual(queue_path.read_text(encoding="utf-8").splitlines(), ["B0AAAA0002"])
            summary = json.loads((output / "queue_adapter_summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["sourceMode"], "formal_manifest")
            self.assertEqual(summary["runnerQueueAsins"], ["B0AAAA0002"])
            self.assertTrue((output / "source_manifest.json").is_file())
            rejected = json.loads(
                (output / "candidate_pool" / "screened_rejected.json").read_text(encoding="utf-8")
            )
            rejected_asins = {item["asin"] for item in rejected}
            self.assertIn("B0AAAA0001", rejected_asins)
            self.assertIn("B0AAAA0003", rejected_asins)

    def test_missing_required_header_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            export = root / "missing_image.csv"
            with export.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow(HEADERS[:-1])
                writer.writerow(row("B0AAAA0001")[:-1])
            completed = self.run_script(
                export,
                "--output-dir",
                root / "out",
                "--queue-name",
                "missing_header",
                "--allow-legacy-export",
            )
            self.assertEqual(completed.returncode, 2)
            self.assertIn("missing required headers", completed.stderr)

    def test_explicit_legacy_mode_is_labeled(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            export = root / "legacy.csv"
            with export.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow(HEADERS)
                writer.writerow(row("B0AAAA0002"))
            output = root / "out"
            completed = self.run_script(
                export,
                "--output-dir",
                output,
                "--queue-name",
                "legacy_01",
                "--queue-size",
                "1",
                "--allow-legacy-export",
                "--project-root",
                root / "project",
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            summary = json.loads((output / "queue_adapter_summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["sourceMode"], "legacy_export")
            self.assertIsNone(summary["sourceManifest"])

    def test_explicit_missing_sales_override_preserves_missing_values(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            export = root / "missing_sales.csv"
            missing_sales = row("B0AAAA0002")
            missing_sales[4] = ""
            missing_sales[5] = ""
            missing_sales[6] = ""
            with export.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow(HEADERS)
                writer.writerow(missing_sales)
            output = root / "out"
            completed = self.run_script(
                export,
                "--output-dir",
                output,
                "--queue-name",
                "missing_sales_01",
                "--queue-size",
                "1",
                "--allow-legacy-export",
                "--allow-missing-sales",
                "--project-root",
                root / "project",
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            selected = json.loads(
                (output / "candidate_pool" / "missing_sales_01.json").read_text(encoding="utf-8")
            )
            self.assertNotIn("monthlySales", selected[0])
            self.assertNotIn("childSales", selected[0])
            self.assertNotIn("parentSales", selected[0])
            summary = json.loads((output / "queue_adapter_summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["salesPresencePolicy"], "explicit_missing_sales_queue_override/v1")

    def test_exclude_asins_file_builds_disjoint_follow_up_queue(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            export = root / "export.csv"
            with export.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow(HEADERS)
                writer.writerow(row("B0AAAA0001"))
                writer.writerow(row("B0AAAA0002"))
            first_queue = root / "first_queue.txt"
            first_queue.write_text("B0AAAA0001\n", encoding="utf-8")
            output = root / "out"

            completed = self.run_script(
                export,
                "--output-dir",
                output,
                "--queue-name",
                "follow_up_01",
                "--queue-size",
                "1",
                "--allow-legacy-export",
                "--exclude-asins-file",
                first_queue,
                "--project-root",
                root / "project",
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            queue_path = output / "candidate_pool" / "asin_queue_follow_up_01.txt"
            self.assertEqual(queue_path.read_text(encoding="utf-8").splitlines(), ["B0AAAA0002"])
            summary = json.loads((output / "queue_adapter_summary.json").read_text(encoding="utf-8"))
            self.assertTrue(summary["explicitQueueExclusion"]["enabled"])
            self.assertEqual(summary["explicitQueueExclusion"]["skippedCount"], 1)


if __name__ == "__main__":
    unittest.main()
