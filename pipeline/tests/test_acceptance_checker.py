from __future__ import annotations

import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from acceptance_checker import (  # noqa: E402
    COST_HEADERS,
    MAIN_HEADERS,
    QUALIFIED_AUDIT_REQUIRED_HEADERS,
    check_enrichment,
    check_current_price,
    check_main_sheet_prices,
    check_traffic,
    delivery_complete,
    row_values,
    xlsx_sheet_rows,
)


RULES = json.loads((ROOT / "config" / "rules.json").read_text(encoding="utf-8"))


def final_row(product_overrides=None, **traffic_overrides):
    traffic = {
        "status": "ok",
        "asinMismatch": False,
        "latestNaturalSharePct": 80.0,
        "recent4AvgNaturalSharePct": 79.0,
        "recent4MinNaturalSharePct": 72.0,
        "weeksRead": 4,
    }
    traffic.update(traffic_overrides)
    product = {
        "dimensions": "商品尺寸 10 x 8 inches",
        "priceTrend": "近30天价格稳定",
        "priceTrendClass": "stable",
    }
    product.update(product_overrides or {})
    return {"asin": "B0AAAA0001", "traffic": traffic, "product": product}


class AcceptanceCheckerTests(unittest.TestCase):
    def test_partial_result_is_not_delivery_complete(self):
        summary = {"targetN": 20, "completedTarget": False}
        self.assertFalse(delivery_complete(summary, [final_row()] * 3))

    def test_exact_target_is_delivery_complete(self):
        summary = {"targetN": 2, "completedTarget": True}
        self.assertTrue(delivery_complete(summary, [final_row(), final_row()]))

    def test_timeout_never_passes_traffic_acceptance(self):
        problems = check_traffic(final_row(status="timeout"), RULES)
        self.assertTrue(any("traffic status=timeout" in item for item in problems))

    def test_asin_mismatch_never_passes_traffic_acceptance(self):
        problems = check_traffic(final_row(asinMismatch=True), RULES)
        self.assertTrue(any("asinMismatch=true" in item for item in problems))

    def test_missing_dimensions_fail_enrichment_acceptance(self):
        problems = check_enrichment(final_row(product_overrides={"dimensions": ""}), RULES)
        self.assertTrue(any("dimensions missing" in item for item in problems))

    def test_declining_price_fails_enrichment_acceptance(self):
        problems = check_enrichment(final_row(product_overrides={"priceTrendClass": "declining"}), RULES)
        self.assertTrue(any("not allowed" in item for item in problems))

    def test_runner_current_price_acceptance_enforces_source_value_and_bounds(self):
        passing = final_row(
            product_overrides={
                "price": 11.99,
                "currentPrice": 11.99,
                "priceSource": "runner_current_price_v1",
            }
        )
        self.assertEqual(check_current_price(passing, RULES, "runner_current_price_v1"), [])
        for boundary in (9.90, 50.00):
            row = final_row(
                product_overrides={
                    "price": boundary,
                    "currentPrice": boundary,
                    "priceSource": "runner_current_price_v1",
                }
            )
            self.assertEqual(check_current_price(row, RULES, "runner_current_price_v1"), [])

        cases = [
            {"price": 9.89, "currentPrice": 9.89, "priceSource": "runner_current_price_v1"},
            {"price": 50.01, "currentPrice": 50.01, "priceSource": "runner_current_price_v1"},
            {"price": 11.99, "currentPrice": None, "priceSource": "runner_current_price_v1"},
            {"price": 11.99, "currentPrice": "not-a-number", "priceSource": "runner_current_price_v1"},
            {"price": 9.99, "currentPrice": 11.99, "priceSource": "runner_current_price_v1"},
            {"price": 11.99, "currentPrice": 11.99, "priceSource": "candidate_source_price_v1"},
        ]
        for product in cases:
            with self.subTest(product=product):
                self.assertTrue(
                    check_current_price(
                        final_row(product_overrides=product),
                        RULES,
                        "runner_current_price_v1",
                    )
                )

    def test_main_sheet_price_must_match_final_candidate_price(self):
        row = final_row(product_overrides={"price": 11.99})
        rows = {8: {2: "B0AAAA0001", 7: "11.99"}}
        self.assertEqual(check_main_sheet_prices([row], rows), [])
        rows[8][7] = "9.99"
        self.assertTrue(check_main_sheet_prices([row], rows))

    def test_three_layer_workbook_rows_are_read_without_excel(self):
        main_ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
        rel_ns = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
        package_rel_ns = "http://schemas.openxmlformats.org/package/2006/relationships"

        def column_name(index: int) -> str:
            name = ""
            while index:
                index, remainder = divmod(index - 1, 26)
                name = chr(65 + remainder) + name
            return name

        def row_xml(row_number: int, values: list[str]) -> str:
            cells = []
            for index, value in enumerate(values, 1):
                escaped = value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                cells.append(f'<c r="{column_name(index)}{row_number}" t="inlineStr"><is><t>{escaped}</t></is></c>')
            return f'<row r="{row_number}">{"".join(cells)}</row>'

        workbook_xml = (
            f'<workbook xmlns="{main_ns}" xmlns:r="{rel_ns}"><sheets>'
            '<sheet name="最终合格品" sheetId="1" r:id="rId1"/>'
            '<sheet name="审计数据" sheetId="2" r:id="rId2"/>'
            '<sheet name="成本利润测算" sheetId="3" r:id="rId3"/>'
            "</sheets></workbook>"
        )
        rels_xml = (
            f'<Relationships xmlns="{package_rel_ns}">'
            '<Relationship Id="rId1" Target="worksheets/sheet1.xml"/>'
            '<Relationship Id="rId2" Target="worksheets/sheet2.xml"/>'
            '<Relationship Id="rId3" Target="worksheets/sheet3.xml"/>'
            "</Relationships>"
        )
        main_sheet = f'<worksheet xmlns="{main_ns}"><sheetData>{row_xml(7, MAIN_HEADERS)}</sheetData></worksheet>'
        audit_sheet = f'<worksheet xmlns="{main_ns}"><sheetData>{row_xml(1, sorted(QUALIFIED_AUDIT_REQUIRED_HEADERS))}</sheetData></worksheet>'
        cost_sheet = f'<worksheet xmlns="{main_ns}"><sheetData>{row_xml(4, COST_HEADERS)}</sheetData></worksheet>'

        with tempfile.TemporaryDirectory() as temp_dir:
            xlsx_path = Path(temp_dir) / "layout.xlsx"
            with zipfile.ZipFile(xlsx_path, "w") as zf:
                zf.writestr("xl/workbook.xml", workbook_xml)
                zf.writestr("xl/_rels/workbook.xml.rels", rels_xml)
                zf.writestr("xl/worksheets/sheet1.xml", main_sheet)
                zf.writestr("xl/worksheets/sheet2.xml", audit_sheet)
                zf.writestr("xl/worksheets/sheet3.xml", cost_sheet)
            rows = xlsx_sheet_rows(xlsx_path)

        self.assertEqual(row_values(rows["最终合格品"], 7), MAIN_HEADERS)
        self.assertEqual(set(row_values(rows["审计数据"], 1)), QUALIFIED_AUDIT_REQUIRED_HEADERS)
        self.assertEqual(row_values(rows["成本利润测算"], 4), COST_HEADERS)


if __name__ == "__main__":
    unittest.main()
