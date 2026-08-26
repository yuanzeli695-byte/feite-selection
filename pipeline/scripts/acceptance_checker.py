#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import re
import sys
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from filter_engine import launch_age_days, traffic_check  # noqa: E402


ERROR_PATTERNS = ("#REF!", "#DIV/0!", "#VALUE!", "#NAME?", "#N/A")
MAIN_HEADERS = [
    "序号",
    "ASIN",
    "主图",
    "中文品名",
    "商品标题（英文）",
    "品牌",
    "价格（USD）",
    "月销售额（USD）",
    "评分",
    "评论数",
    "子体月销",
    "父体月销",
    "上架日期",
    "上架天数",
    "变体数",
    "配送",
    "重量/尺寸",
    "价格趋势",
    "最新自然流量%",
    "近4周平均自然流量%",
    "近4周最低自然流量%",
    "总自然流量占比%",
    "严格结论",
    "Amazon链接",
]
QUALIFIED_AUDIT_REQUIRED_HEADERS = {
    "读取周数",
    "流量窗口",
    "采集状态",
    "实际ASIN",
    "流量判定",
}
DISPLAY_FORBIDDEN_HEADERS = {
    "类目路径",
    "本地主图路径",
    "来源关键词",
    "SellerSprite页",
    "图片来源URL",
    "批次审计",
    "风险/复核备注",
}
COST_HEADERS = [
    "序号",
    "ASIN",
    "中文品名",
    "当前售价（USD）",
    "美元兑人民币汇率（1 USD = X RMB）",
    "采购价（RMB）",
    "MOQ",
    "国内运费（RMB）",
    "供应商链接",
    "总成本（RMB）",
    "利润（RMB）",
    "毛利率",
    "ROI",
]

_MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def count_xlsx_media(path: Path) -> int:
    if not path.exists():
        return 0
    with zipfile.ZipFile(path) as zf:
        return sum(1 for name in zf.namelist() if name.startswith("xl/media/") and not name.endswith("/"))


def count_xlsx_pictures(path: Path) -> int:
    if not path.exists():
        return 0
    total = 0
    with zipfile.ZipFile(path) as zf:
        for name in zf.namelist():
            if name.startswith("xl/drawings/drawing") and name.endswith(".xml"):
                text = zf.read(name).decode("utf-8", errors="ignore")
                total += len(re.findall(r"<(?:xdr:)?pic[>\s]", text))
    return total


def formula_error_hits(path: Path) -> list[str]:
    hits: list[str] = []
    if not path.exists():
        return hits
    with zipfile.ZipFile(path) as zf:
        for name in zf.namelist():
            if not (name.startswith("xl/worksheets/") or name == "xl/sharedStrings.xml"):
                continue
            text = zf.read(name).decode("utf-8", errors="ignore")
            for pattern in ERROR_PATTERNS:
                if pattern in text:
                    hits.append(f"{name}: {pattern}")
    return hits


def xlsx_searchable_text(path: Path) -> str:
    if not path.exists():
        return ""
    parts: list[str] = []
    with zipfile.ZipFile(path) as zf:
        for name in zf.namelist():
            if name == "xl/sharedStrings.xml" or name.startswith("xl/worksheets/sheet"):
                parts.append(zf.read(name).decode("utf-8", errors="ignore"))
    return "\n".join(parts)


def _column_index(cell_reference: str) -> int:
    match = re.match(r"([A-Z]+)", cell_reference.upper())
    if not match:
        return 0
    result = 0
    for char in match.group(1):
        result = result * 26 + ord(char) - 64
    return result


def _shared_strings(zf: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in zf.namelist():
        return []
    root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
    return ["".join(node.text or "" for node in item.iter(f"{{{_MAIN_NS}}}t")) for item in root]


def xlsx_sheet_rows(path: Path) -> dict[str, dict[int, dict[int, str]]]:
    if not path.exists():
        return {}
    with zipfile.ZipFile(path) as zf:
        workbook_root = ET.fromstring(zf.read("xl/workbook.xml"))
        rels_root = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
        rel_targets = {
            rel.attrib["Id"]: rel.attrib["Target"]
            for rel in rels_root.findall(f"{{{_PKG_REL_NS}}}Relationship")
        }
        shared = _shared_strings(zf)
        output: dict[str, dict[int, dict[int, str]]] = {}
        for sheet in workbook_root.findall(f".//{{{_MAIN_NS}}}sheet"):
            name = sheet.attrib.get("name", "")
            rel_id = sheet.attrib.get(f"{{{_REL_NS}}}id", "")
            target = rel_targets.get(rel_id, "")
            if not target:
                continue
            sheet_path = target.lstrip("/")
            if not sheet_path.startswith("xl/"):
                sheet_path = f"xl/{sheet_path}"
            sheet_root = ET.fromstring(zf.read(sheet_path))
            rows: dict[int, dict[int, str]] = {}
            for cell in sheet_root.findall(f".//{{{_MAIN_NS}}}c"):
                reference = cell.attrib.get("r", "")
                row_match = re.search(r"(\d+)$", reference)
                if not row_match:
                    continue
                row_number = int(row_match.group(1))
                column = _column_index(reference)
                cell_type = cell.attrib.get("t", "")
                value_node = cell.find(f"{{{_MAIN_NS}}}v")
                if cell_type == "inlineStr":
                    value = "".join(node.text or "" for node in cell.iter(f"{{{_MAIN_NS}}}t"))
                elif value_node is None:
                    value = ""
                elif cell_type == "s":
                    index = int(value_node.text or 0)
                    value = shared[index] if index < len(shared) else ""
                else:
                    value = value_node.text or ""
                rows.setdefault(row_number, {})[column] = value
            output[name] = rows
        return output


def row_values(rows: dict[int, dict[int, str]], row_number: int) -> list[str]:
    row = rows.get(row_number, {})
    if not row:
        return []
    last_column = max(row)
    return [row.get(column, "") for column in range(1, last_column + 1)]


def delivery_complete(summary: dict[str, Any], final_rows: list[dict[str, Any]]) -> bool:
    return len(final_rows) == int(summary["targetN"]) and bool(summary.get("completedTarget"))


def check_traffic(candidate: dict[str, Any], rules: dict[str, Any]) -> list[str]:
    traffic = candidate.get("traffic") or {}
    if rules.get("trafficGateMode") == "aggregate_weighted_share":
        result = traffic_check(traffic, rules)
        return [] if result.pass_ else [f"{candidate.get('asin')} {result.rule}: {result.reason}"]
    problems = []
    if traffic.get("status") != "ok":
        problems.append(f"{candidate.get('asin')} traffic status={traffic.get('status')}")
    if traffic.get("asinMismatch") is True:
        problems.append(f"{candidate.get('asin')} asinMismatch=true")
    checks = [
        ("latestNaturalSharePct", "trafficNaturalMinPct"),
        ("recent4AvgNaturalSharePct", "trafficRecent4AvgMinPct"),
        ("recent4MinNaturalSharePct", "trafficRecent4MinMinPct"),
    ]
    for metric, rule_key in checks:
        value = traffic.get(metric)
        threshold = float(rules[rule_key])
        if not isinstance(value, (int, float)) or value < threshold:
            problems.append(f"{candidate.get('asin')} {metric}={value} < {threshold}")
    weeks = int(traffic.get("weeksRead") or 0)
    if weeks < int(rules["trafficWeeksReadMin"]):
        problems.append(f"{candidate.get('asin')} weeksRead={weeks} < {rules['trafficWeeksReadMin']}")
    return problems


def check_launch(candidate: dict[str, Any], rules: dict[str, Any], run_date) -> list[str]:
    product = candidate.get("product") or {}
    age = launch_age_days(product, run_date)
    if age is None:
        return [f"{candidate.get('asin')} launch date missing"]
    if age > int(rules["launchAgeMaxDays"]):
        return [f"{candidate.get('asin')} launch age {age} > {rules['launchAgeMaxDays']}"]
    return []


def check_enrichment(candidate: dict[str, Any], rules: dict[str, Any]) -> list[str]:
    product = candidate.get("product") or {}
    asin = candidate.get("asin")
    problems = []
    if rules.get("dimensionsRequired", False) and not str(product.get("dimensions") or "").strip():
        problems.append(f"{asin} dimensions missing")
    if rules.get("priceTrendRequired", False) and not str(product.get("priceTrend") or "").strip():
        problems.append(f"{asin} price trend missing")
    trend_class = str(product.get("priceTrendClass") or "").strip().lower()
    if rules.get("priceTrendRequired", False) and not trend_class:
        problems.append(f"{asin} price trend class missing")
    allowed = {str(value).strip().lower() for value in rules.get("allowedPriceTrendClasses", ["stable", "rising"])}
    if trend_class and allowed and trend_class not in allowed:
        problems.append(f"{asin} price trend class={trend_class} not allowed")
    return problems


def finite_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def check_current_price(candidate: dict[str, Any], rules: dict[str, Any], price_policy: str) -> list[str]:
    if price_policy != "runner_current_price_v1":
        return []
    product = candidate.get("product") or {}
    asin = candidate.get("asin")
    problems: list[str] = []
    current_price = finite_number(product.get("currentPrice"))
    accepted_price = finite_number(product.get("price"))
    if current_price is None:
        problems.append(f"{asin} Runner currentPrice missing or invalid")
    else:
        minimum = float(rules["priceMinUsd"])
        maximum = float(rules["priceMaxUsd"])
        if current_price < minimum or current_price > maximum:
            problems.append(f"{asin} Runner currentPrice={current_price:g} not in {minimum:g}-{maximum:g}")
    if accepted_price is None:
        problems.append(f"{asin} accepted price missing or invalid")
    elif current_price is not None and not math.isclose(accepted_price, current_price, rel_tol=0, abs_tol=1e-9):
        problems.append(f"{asin} accepted price={accepted_price:g} != Runner currentPrice={current_price:g}")
    if product.get("priceSource") != "runner_current_price_v1":
        problems.append(f"{asin} priceSource={product.get('priceSource')} is not runner_current_price_v1")
    return problems


def check_main_sheet_prices(
    final_rows: list[dict[str, Any]],
    main_rows: dict[int, dict[int, str]],
) -> list[str]:
    workbook_prices = {
        row.get(2, ""): row.get(7, "")
        for row_number, row in main_rows.items()
        if row_number >= 8 and row.get(2, "")
    }
    problems: list[str] = []
    for candidate in final_rows:
        asin = candidate.get("asin")
        expected = finite_number((candidate.get("product") or {}).get("price"))
        actual = finite_number(workbook_prices.get(asin))
        if expected is None or actual is None or not math.isclose(expected, actual, rel_tol=0, abs_tol=1e-9):
            problems.append(f"{asin} workbook price={workbook_prices.get(asin)} expected={expected}")
    return problems


def run(args: argparse.Namespace) -> int:
    run_dir = args.run_dir.resolve()
    rules = read_json(args.rules)
    summary = read_json(run_dir / "run_summary.json")
    final_rows = read_json(run_dir / "final_candidates_data.json")
    rejected_rows = read_json(run_dir / "rejected_audit_data.json")
    build_report = read_json(run_dir / "workbook_build_report.json")
    final_xlsx = Path(build_report["finalXlsx"])
    audit_xlsx = Path(build_report["auditXlsx"])
    run_date = datetime.fromisoformat(str(summary["runDate"])[:10]).date()

    checks: list[tuple[str, bool, str]] = []
    final_asins = {row.get("asin") for row in final_rows}
    rejected_asins = {row.get("asin") for row in rejected_rows}

    checks.append(("final workbook exists", final_xlsx.exists(), str(final_xlsx)))
    checks.append(("audit workbook exists", audit_xlsx.exists(), str(audit_xlsx)))
    checks.append(("qualified pool count matches final data", len(final_rows) == int(summary["qualifiedCount"]), f"{len(final_rows)} vs {summary['qualifiedCount']}"))
    checks.append(("delivery target met exactly", delivery_complete(summary, final_rows), f"qualified={len(final_rows)} target={summary['targetN']} completedTarget={summary.get('completedTarget')} stoppedReason={summary.get('stoppedReason')}"))
    checks.append(("no ASIN overlap between final and rejected", not (final_asins & rejected_asins), ", ".join(sorted(final_asins & rejected_asins))))
    checks.append(("final ASINs are unique", len(final_asins) == len(final_rows), f"unique={len(final_asins)} rows={len(final_rows)}"))

    traffic_problems = []
    launch_problems = []
    enrichment_problems = []
    price_problems = []
    image_problems = []
    price_policy = str(summary.get("priceEvidencePolicy") or "")
    for row in final_rows:
        traffic_problems.extend(check_traffic(row, rules))
        launch_problems.extend(check_launch(row, rules, run_date))
        enrichment_problems.extend(check_enrichment(row, rules))
        price_problems.extend(check_current_price(row, rules, price_policy))
        raw_image_path = str(row.get("imagePath") or "")
        image_path = Path(raw_image_path)
        if not image_path.is_absolute():
            candidates = [run_dir / image_path, run_dir.parent.parent / image_path]
            image_path = next((candidate for candidate in candidates if candidate.exists()), candidates[0])
        if not image_path.exists():
            image_problems.append(f"{row.get('asin')} missing image file {image_path}")
    checks.append(("all final rows pass traffic thresholds", not traffic_problems, "; ".join(traffic_problems)))
    checks.append(("all final rows launch within limit", not launch_problems, "; ".join(launch_problems)))
    checks.append(("all final rows have allowed dimensions and price trends", not enrichment_problems, "; ".join(enrichment_problems)))
    checks.append(("all final rows use valid Runner current prices", not price_problems, "; ".join(price_problems)))
    checks.append(("all final rows have local image files", not image_problems, "; ".join(image_problems)))

    media_count = count_xlsx_media(final_xlsx)
    picture_count = count_xlsx_pictures(final_xlsx)
    checks.append(("xlsx media count equals final rows", media_count == len(final_rows), f"media={media_count} final={len(final_rows)}"))
    checks.append(("xlsx picture shapes equal final rows", picture_count == len(final_rows), f"pictures={picture_count} final={len(final_rows)}"))
    final_xlsx_text = xlsx_searchable_text(final_xlsx)
    missing_final_asins = sorted(asin for asin in final_asins if asin and asin not in final_xlsx_text)
    rejected_asins_in_final = sorted(asin for asin in rejected_asins if asin and asin in final_xlsx_text)
    checks.append(("all final ASINs appear in final workbook", not missing_final_asins, ", ".join(missing_final_asins)))
    checks.append(("no rejected ASIN appears in final workbook", not rejected_asins_in_final, ", ".join(rejected_asins_in_final[:20])))

    workbook_rows = xlsx_sheet_rows(final_xlsx)
    required_sheets = {"最终合格品", "审计数据", "成本利润测算"}
    checks.append(("final workbook has three-layer layout", required_sheets.issubset(workbook_rows), ", ".join(sorted(workbook_rows))))
    main_headers = row_values(workbook_rows.get("最终合格品", {}), 7)
    checks.append(("main sheet headers match approved display fields", main_headers == MAIN_HEADERS, f"actual={main_headers}"))
    audit_header_row = row_values(workbook_rows.get("审计数据", {}), 1)
    forbidden_visible_headers = sorted(DISPLAY_FORBIDDEN_HEADERS.intersection(set(main_headers) | set(audit_header_row)))
    checks.append(("forbidden source/audit fields absent from display sheets", not forbidden_visible_headers, ", ".join(forbidden_visible_headers)))
    workbook_price_problems = check_main_sheet_prices(final_rows, workbook_rows.get("最终合格品", {}))
    checks.append(("main sheet prices match accepted current prices", not workbook_price_problems, "; ".join(workbook_price_problems)))
    qualified_audit_headers = set(audit_header_row)
    missing_audit_headers = sorted(QUALIFIED_AUDIT_REQUIRED_HEADERS - qualified_audit_headers)
    checks.append(("qualified audit sheet retains moved evidence", not missing_audit_headers, ", ".join(missing_audit_headers)))
    cost_headers = row_values(workbook_rows.get("成本利润测算", {}), 4)
    checks.append(("cost sheet headers match approved template", cost_headers == COST_HEADERS, f"actual={cost_headers}"))
    audit_asins = {
        row.get(2, "")
        for row_number, row in workbook_rows.get("审计数据", {}).items()
        if row_number >= 2 and row.get(2, "")
    }
    checks.append(("qualified audit ASINs match final rows", audit_asins == final_asins, f"audit={sorted(audit_asins)} final={sorted(final_asins)}"))
    populated_cost_cells = []
    for row_number, row in workbook_rows.get("成本利润测算", {}).items():
        if row_number < 5:
            continue
        for column in range(1, 14):
            if str(row.get(column, "")).strip():
                populated_cost_cells.append(f"r{row_number}c{column}")
    checks.append(("cost template contains no collected data", not populated_cost_cells, ", ".join(populated_cost_cells[:20])))
    formula_errors = formula_error_hits(final_xlsx) + formula_error_hits(audit_xlsx)
    checks.append(("formula error strings absent", not formula_errors, "; ".join(formula_errors[:10])))

    passed = all(ok for _, ok, _ in checks)
    lines = [
        f"# Pipeline acceptance report: {summary['runId']}",
        "",
        f"- Generated at: {datetime.now().astimezone().isoformat(timespec='seconds')}",
        f"- Final workbook: {final_xlsx}",
        f"- Audit workbook: {audit_xlsx}",
        f"- Target N: {summary['targetN']}",
        f"- Qualified: {len(final_rows)}",
        f"- Rejected/audit rows: {len(rejected_rows)}",
        f"- Attempts: {summary['attempts']} / {summary['maxAttempts']}",
        f"- Delivery complete: {'yes' if delivery_complete(summary, final_rows) else 'no'}",
        f"- Stop reason: {summary.get('stoppedReason')}",
        "",
        "## Checks",
        "",
        "| Check | Result | Detail |",
        "|---|---|---|",
    ]
    for name, ok, detail in checks:
        lines.append(f"| {name} | {'PASS' if ok else 'FAIL'} | {str(detail).replace('|', '/')} |")
    lines.extend(
        [
            "",
            "## Final ASINs",
            "",
            "| ASIN | Title | Latest | Recent4 avg | Recent4 min | Launch age |",
            "|---|---|---:|---:|---:|---:|",
        ]
    )
    for row in final_rows:
        product = row.get("product") or {}
        traffic = row.get("traffic") or {}
        lines.append(
            "| {asin} | {title} | {latest} | {avg} | {minv} | {age} |".format(
                asin=row.get("asin"),
                title=str(row.get("cnTitle") or product.get("title") or "").replace("|", "/"),
                latest=traffic.get("latestNaturalSharePct"),
                avg=traffic.get("recent4AvgNaturalSharePct"),
                minv=traffic.get("recent4MinNaturalSharePct"),
                age=product.get("launchAgeDays"),
            )
        )
    report_path = run_dir / "acceptance_report.md"
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(report_path)
    return 0 if passed else 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate final/audit pipeline outputs.")
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--rules", type=Path, default=ROOT / "config" / "rules.json")
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(run(parse_args()))
