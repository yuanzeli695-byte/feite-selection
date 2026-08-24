#!/usr/bin/env python3
"""Prepare an audited Runner queue from the official SellerSprite API."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from openpyxl import Workbook
from openpyxl.drawing.image import Image as ExcelImage
from openpyxl.styles import Alignment, Font, PatternFill


API_BASE = "https://api.sellersprite.com"
WEB_RESEARCH = "https://www.sellersprite.com/v3/product-research"
DEFAULT_CREDENTIAL = Path.home() / ".codex" / "secrets" / "sellersprite-open-api.credential.xml"
ASIN_RE = re.compile(r"^[A-Z0-9]{10}$")


class PipelineError(RuntimeError):
    pass


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(path)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_dpapi_secret(path: Path) -> str:
    if not path.is_file():
        raise PipelineError(f"SellerSprite DPAPI 凭据不存在: {path}")
    escaped = str(path).replace("'", "''")
    command = (
        f"$c=Import-Clixml -LiteralPath '{escaped}';"
        "$v=$c.GetNetworkCredential().Password;"
        "[Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($v))"
    )
    result = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", command],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=20,
    )
    if result.returncode != 0 or not result.stdout.strip():
        raise PipelineError("无法读取 SellerSprite DPAPI 凭据")
    try:
        secret = base64.b64decode(result.stdout.strip()).decode("utf-8")
    except (ValueError, UnicodeDecodeError) as exc:
        raise PipelineError("SellerSprite DPAPI 凭据格式无效") from exc
    if not secret:
        raise PipelineError("SellerSprite secret-key 为空")
    return secret


class SellerSpriteClient:
    def __init__(self, secret: str, timeout: int = 45) -> None:
        self.secret = secret
        self.timeout = timeout

    def request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> Any:
        url = API_BASE + path
        body = None
        if payload is not None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=body,
            method=method,
            headers={
                "secret-key": self.secret,
                "Content-Type": "application/json;charset=utf-8",
                "x-request-id": hashlib.sha256(f"{datetime.now().isoformat()}:{url}".encode()).hexdigest()[:32],
                "User-Agent": "AmazonSelectionConsole/2.0",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                result = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:500]
            raise PipelineError(f"SellerSprite API HTTP {exc.code}: {detail}") from exc
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise PipelineError(f"SellerSprite API 请求失败: {exc}") from exc
        if result.get("code") != "OK":
            raise PipelineError(f"SellerSprite API 返回 {result.get('code')}: {result.get('message')}")
        return result.get("data")

    def visits(self) -> Any:
        return self.request("GET", "/v1/visits")

    def product_nodes(self, keyword: str = "", node_id_path: str = "") -> list[dict[str, Any]]:
        query: dict[str, str] = {"marketplace": "US"}
        if keyword:
            query["keyword"] = keyword
        if node_id_path:
            query["nodeIdPath"] = node_id_path
        path = "/v1/product/node?" + urllib.parse.urlencode(query)
        data = self.request("GET", path)
        if not isinstance(data, list):
            raise PipelineError("SellerSprite product/node 返回结构无效")
        return data

    def product_research(self, payload: dict[str, Any]) -> dict[str, Any]:
        data = self.request("POST", "/v1/product/research", payload)
        if not isinstance(data, dict) or not isinstance(data.get("items"), list):
            raise PipelineError("SellerSprite product/research 返回结构无效")
        return data


def normalize_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip()).casefold()


def parse_category_lines(raw: str) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    seen: set[str] = set()
    for line_number, source in enumerate(raw.splitlines(), 1):
        line = source.strip()
        if not line or line.startswith("#"):
            continue
        parts = [part.strip() for part in re.split(r"[|\t]", line, maxsplit=1)]
        label = parts[0]
        node_id_path = parts[1] if len(parts) == 2 else ""
        if not node_id_path and re.fullmatch(r"\d+(?::\d+)*", label):
            node_id_path, label = label, label
        key = f"{normalize_text(label)}|{node_id_path}"
        if key in seen:
            continue
        seen.add(key)
        items.append({"line": str(line_number), "input": line, "label": label, "nodeIdPath": node_id_path})
    if not items:
        raise PipelineError("类目池为空")
    return items


def resolve_category(client: SellerSpriteClient, item: dict[str, str]) -> dict[str, Any]:
    if item["nodeIdPath"]:
        return {
            **item,
            "status": "resolved",
            "nodeIdPath": item["nodeIdPath"],
            "nodeLabelPath": item["label"],
            "nodeLabelPathLocale": item["label"],
            "resolution": "explicit_node_id",
        }
    nodes = client.product_nodes(keyword=item["label"])
    needle = normalize_text(item["label"])
    exact = []
    for node in nodes:
        labels = {
            normalize_text(node.get("nodeLabelPath")),
            normalize_text(node.get("nodeLabelPathLocale")),
            normalize_text(node.get("nodeLabelLocale")),
            normalize_text(str(node.get("nodeLabelPath") or "").split(":")[-1]),
            normalize_text(str(node.get("nodeLabelPathLocale") or "").split(":")[-1]),
        }
        if needle in labels:
            exact.append(node)
    choices = exact if exact else (nodes if len(nodes) == 1 else [])
    if len(choices) != 1:
        return {
            **item,
            "status": "needs_resolution",
            "message": "类目名称无法唯一匹配，请改为 名称 | nodeIdPath",
            "choices": [
                {
                    "nodeIdPath": str(node.get("nodeIdPath") or ""),
                    "nodeLabelPath": str(node.get("nodeLabelPath") or ""),
                    "nodeLabelPathLocale": str(node.get("nodeLabelPathLocale") or ""),
                    "products": node.get("products"),
                }
                for node in nodes[:20]
            ],
        }
    node = choices[0]
    return {
        **item,
        "status": "resolved",
        "nodeIdPath": str(node.get("nodeIdPath") or ""),
        "nodeLabelPath": str(node.get("nodeLabelPath") or item["label"]),
        "nodeLabelPathLocale": str(node.get("nodeLabelPathLocale") or node.get("nodeLabelLocale") or item["label"]),
        "products": node.get("products"),
        "resolution": "exact_label",
    }


def launch_date(value: Any) -> tuple[str, int | None]:
    try:
        timestamp = float(value) / 1000
        launched = datetime.fromtimestamp(timestamp, timezone.utc).date()
        return launched.isoformat(), (datetime.now(timezone.utc).date() - launched).days
    except (TypeError, ValueError, OSError, OverflowError):
        return "", None


def web_query_url(node_path: str, filters: dict[str, Any]) -> str:
    params = {
        "market": "US",
        "page": 1,
        "size": 60,
        "nodeIdPaths": json.dumps([node_path], separators=(",", ":")),
        "minPrice": filters["minPrice"],
        "maxPrice": filters["maxPrice"],
        "minReviews": filters.get("minReviews", 0),
        "maxReviews": filters["maxReviews"],
        "minReviewRating": filters["minRating"],
        "minSales": filters["minChildSales"],
        "maxSales": filters["maxChildSales"],
        "minVariations": filters.get("minVariations", 0),
        "maxVariations": filters["maxVariations"],
        "putawayMonth": filters["availableMonth"],
    }
    return WEB_RESEARCH + "?" + urllib.parse.urlencode(params)


def normalize_product(raw: dict[str, Any], category: dict[str, Any], query_url: str) -> dict[str, Any]:
    asin = str(raw.get("asin") or "").strip().upper()
    launched, age_days = launch_date(raw.get("availableDate"))
    return {
        "asin": asin,
        "title": str(raw.get("title") or "").strip(),
        "brand": str(raw.get("brand") or "").strip(),
        "categoryPath": str(raw.get("nodeLabelPath") or category.get("nodeLabelPath") or "").strip(),
        "categoryPathLocale": str(category.get("nodeLabelPathLocale") or "").strip(),
        "price": raw.get("price"),
        "rating": raw.get("rating"),
        "reviews": raw.get("reviews") if raw.get("reviews") is not None else raw.get("ratings"),
        "childSales": raw.get("amzUnit"),
        "parentSales": raw.get("units"),
        "monthlySales": raw.get("amzUnit"),
        "parentMonthlySales": raw.get("units"),
        "launchDate": launched,
        "launchAgeDays": age_days,
        "variations": raw.get("variations"),
        "image": str(raw.get("imageUrl") or "").strip(),
        "amazonUrl": f"https://www.amazon.com/dp/{asin}" if ASIN_RE.fullmatch(asin) else "",
        "sellerSpriteUrl": query_url,
        "sourcePage": str(category.get("nodeLabelPath") or category.get("label") or ""),
        "sourceApi": f"{API_BASE}/v1/product/research",
        "sourceCategoryInput": category.get("input"),
        "sourceNodeIdPath": category.get("nodeIdPath"),
        "sellerNation": raw.get("sellerNation"),
        "fulfillment": raw.get("fulfillment") or raw.get("sellerType"),
        "rawProduct": raw,
    }


def run_command(argv: list[str], log_path: Path, cwd: Path) -> None:
    result = subprocess.run(argv, cwd=str(cwd), capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=1800)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text((result.stdout or "") + "\n" + (result.stderr or ""), encoding="utf-8")
    if result.returncode != 0:
        raise PipelineError(f"命令失败 ({result.returncode}): {Path(argv[1]).name}; 日志: {log_path}")


def make_analysis_workbook(queue: list[dict[str, Any]], rejected: list[dict[str, Any]], images_dir: Path, output: Path) -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "候选分析"
    headers = ["ASIN", "主图", "类目", "品牌", "英文标题", "价格", "评分", "评论数", "子体月销量", "父体月销量", "上架日期", "变体数", "Amazon", "卖家精灵来源"]
    sheet.append(headers)
    header_fill = PatternFill("solid", fgColor="0B6B63")
    for cell in sheet[1]:
        cell.fill = header_fill
        cell.font = Font(color="FFFFFF", bold=True)
        cell.alignment = Alignment(horizontal="center", vertical="center")
    for row_index, row in enumerate(queue, 2):
        sheet.append([
            row.get("asin"), "", row.get("categoryPathLocale") or row.get("categoryPath"), row.get("brand"), row.get("title"),
            row.get("price"), row.get("rating"), row.get("reviews"), row.get("childSales"), row.get("parentSales"),
            row.get("launchDate"), row.get("variations"), row.get("amazonUrl"), row.get("sellerSpriteUrl"),
        ])
        image_path = images_dir / f"{row.get('asin')}.png"
        if image_path.is_file():
            image = ExcelImage(str(image_path))
            image.width, image.height = 88, 88
            sheet.add_image(image, f"B{row_index}")
        sheet.row_dimensions[row_index].height = 72
        sheet.cell(row_index, 13).hyperlink = row.get("amazonUrl")
        sheet.cell(row_index, 14).hyperlink = row.get("sellerSpriteUrl")
        for cell in sheet[row_index]:
            cell.alignment = Alignment(vertical="center", wrap_text=True)
    widths = {"A": 14, "B": 14, "C": 28, "D": 18, "E": 58, "F": 12, "G": 10, "H": 10, "I": 13, "J": 13, "K": 13, "L": 10, "M": 18, "N": 22}
    for column, width in widths.items():
        sheet.column_dimensions[column].width = width
    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = sheet.dimensions

    audit = workbook.create_sheet("筛除审计")
    audit.append(["ASIN", "标题", "筛除原因", "来源类目"])
    for cell in audit[1]:
        cell.fill = PatternFill("solid", fgColor="9B2C2C")
        cell.font = Font(color="FFFFFF", bold=True)
    for row in rejected:
        reason = row.get("reason") or row.get("reasons") or row.get("decision")
        if isinstance(reason, (list, tuple, set)):
            reason = ", ".join(str(item) for item in reason)
        elif isinstance(reason, dict):
            reason = json.dumps(reason, ensure_ascii=False, sort_keys=True)
        audit.append([row.get("asin"), row.get("title"), reason, row.get("sourcePage")])
    audit.freeze_panes = "A2"
    audit.auto_filter.ref = audit.dimensions
    audit.column_dimensions["A"].width = 14
    audit.column_dimensions["B"].width = 70
    audit.column_dimensions["C"].width = 42
    audit.column_dimensions["D"].width = 30
    output.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(output)


def default_filters(value: dict[str, Any]) -> dict[str, Any]:
    defaults = {
        "minPrice": 9.9,
        "maxPrice": 50,
        "minRating": 4,
        "minReviews": 0,
        "maxReviews": 100,
        "minChildSales": 50,
        "maxChildSales": 300,
        "minVariations": 0,
        "maxVariations": 25,
        "availableMonth": 3,
        "perCategoryLimit": 200,
    }
    merged = {**defaults, **(value or {})}
    if float(merged["minPrice"]) < 9.9 or float(merged["maxPrice"]) > 50 or float(merged["minPrice"]) > float(merged["maxPrice"]):
        raise PipelineError("价格必须保持在 9.90-50.00 的批准范围内")
    if float(merged["minRating"]) < 4:
        raise PipelineError("最低评分不得低于 4.0")
    if int(merged["maxReviews"]) > 100 or int(merged["minReviews"]) > int(merged["maxReviews"]):
        raise PipelineError("最高评论数不得超过 100")
    if int(merged["maxVariations"]) > 25 or int(merged["minVariations"]) > int(merged["maxVariations"]):
        raise PipelineError("最高变体数不得超过 25")
    if not 1 <= int(merged["availableMonth"]) <= 3:
        raise PipelineError("上架月份不得超过 3 个月")
    merged["perCategoryLimit"] = max(1, min(int(merged["perCategoryLimit"]), 2000))
    return merged


def execute(args: argparse.Namespace) -> dict[str, Any]:
    run_dir = args.run_dir.resolve()
    run_dir.mkdir(parents=True, exist_ok=True)
    config = read_json(args.config)
    filters = default_filters(config.get("filters") or {})
    categories = parse_category_lines(str(config.get("categories") or ""))
    secret = load_dpapi_secret(args.credential)
    client = SellerSpriteClient(secret)
    visits = client.visits()
    secret = ""

    source_dir = run_dir / "source_queries"
    raw_dir = run_dir / "sellersprite_api_raw"
    source_dir.mkdir(parents=True, exist_ok=True)
    raw_dir.mkdir(parents=True, exist_ok=True)
    resolved = [resolve_category(client, item) for item in categories]
    unresolved = [item for item in resolved if item["status"] != "resolved"]
    write_json(run_dir / "category_resolution.json", {"items": resolved})
    if unresolved:
        labels = ", ".join(item["input"] for item in unresolved)
        raise PipelineError(f"以下类目无法唯一解析: {labels}")

    manifest_inputs = []
    all_rows: list[dict[str, Any]] = []
    page_size = 100
    for category_index, category in enumerate(resolved, 1):
        category_limit = filters["perCategoryLimit"]
        query_url = web_query_url(category["nodeIdPath"], filters)
        rows: list[dict[str, Any]] = []
        page = 1
        while len(rows) < category_limit:
            request_payload = {
                "marketplace": "US",
                "nodeIdPaths": [category["nodeIdPath"]],
                "nodeIdPathEqual": False,
                "minPrice": filters["minPrice"],
                "maxPrice": filters["maxPrice"],
                "minRating": filters["minRating"],
                "minRatings": filters["minReviews"],
                "maxRatings": filters["maxReviews"],
                "minAmzUnit": filters["minChildSales"],
                "maxAmzUnit": filters["maxChildSales"],
                "minVariations": filters["minVariations"],
                "maxVariations": filters["maxVariations"],
                "availableMonth": filters["availableMonth"],
                "page": page,
                "size": min(page_size, category_limit - len(rows)),
                "order": {"field": "amz_unit", "desc": True},
            }
            response = client.product_research(request_payload)
            write_json(raw_dir / f"category_{category_index:03d}_page_{page:03d}.json", {"request": request_payload, "response": response})
            items = response.get("items") or []
            rows.extend(normalize_product(item, category, query_url) for item in items)
            if not items or len(items) < request_payload["size"] or len(rows) >= int(response.get("total") or len(rows)):
                break
            page += 1
        rows = [row for row in rows if ASIN_RE.fullmatch(row["asin"])]
        filename = f"query_{category_index:03d}_{hashlib.sha256(category['input'].encode()).hexdigest()[:10]}.json"
        query_path = source_dir / filename
        write_json(query_path, rows[:category_limit])
        all_rows.extend(rows[:category_limit])
        manifest_inputs.append({"path": filename, "sha256": sha256_file(query_path), "queryUrl": query_url})
        category["candidateCount"] = min(len(rows), category_limit)

    manifest = {
        "schemaVersion": "sellerSpriteCandidateSourceManifest/v1",
        "capturedAt": datetime.now(timezone.utc).isoformat(),
        "market": "US",
        "preset": {"name": "sellerSprite-query-hard-filter-v1", "source": "official_api"},
        "categoryScope": {
            "name": "Console category pool",
            "nodeIdPaths": [item["nodeIdPath"] for item in resolved],
        },
        "inputs": manifest_inputs,
    }
    manifest_path = run_dir / "source_manifest.json"
    write_json(manifest_path, manifest)

    pool_dir = run_dir / "candidate_pool"
    queue_name = re.sub(r"[^A-Za-z0-9_-]+", "_", args.queue_name).strip("_")[:80] or "console_queue"
    prefilter_log = run_dir / "logs" / "strict_prefilter.log"
    run_command([
        sys.executable,
        str(args.project_root / "scripts" / "prepare_strict_candidate_pool.py"),
        "--input-dir", str(source_dir),
        "--source-manifest", str(manifest_path),
        "--project-root", str(args.project_root),
        "--output-dir", str(pool_dir),
        "--queue-name", queue_name,
        "--queue-size", str(args.queue_size),
        "--run-date", args.run_date,
    ], prefilter_log, args.project_root)
    queue_json = pool_dir / f"{queue_name}.json"
    queue_txt = pool_dir / f"asin_queue_{queue_name}.txt"
    summary_path = pool_dir / f"summary_{queue_name}.json"
    rejected_path = pool_dir / "screened_rejected.json"
    queue = read_json(queue_json)
    rejected = read_json(rejected_path)
    if not queue:
        raise PipelineError("严格预筛后没有可进入 Runner 的候选 ASIN")

    images_dir = run_dir / "source_images"
    image_report = run_dir / "image_download_report.json"
    image_log = run_dir / "logs" / "image_download.log"
    run_command([
        sys.executable,
        str(args.project_root / "scripts" / "download_candidate_images.py"),
        str(queue_json), str(images_dir), "--report", str(image_report), "--workers", "4",
    ], image_log, args.project_root)

    analysis_path = run_dir / f"candidate_analysis_{queue_name}.xlsx"
    make_analysis_workbook(queue, rejected, images_dir, analysis_path)
    title_overrides = {}
    for row in queue:
        category_cn = str(row.get("categoryPathLocale") or row.get("categoryPath") or "商品").split(":")[-1]
        brand = str(row.get("brand") or "").strip()
        title_overrides[row["asin"]] = f"{brand} {category_cn} {row['asin']}".strip()
    title_path = run_dir / "zh_title_overrides_auto.json"
    write_json(title_path, title_overrides)
    result = {
        "schemaVersion": "sellerSpriteConsoleCandidatePipeline/v1",
        "qualificationScope": "runner_queue_only_no_final_AF_pass",
        "runDir": str(run_dir),
        "sourceRowCount": len(all_rows),
        "resolvedCategories": resolved,
        "queueCount": len(queue),
        "queuePath": str(queue_txt),
        "queueJsonPath": str(queue_json),
        "analysisWorkbookPath": str(analysis_path),
        "imagesDir": str(images_dir),
        "imageReportPath": str(image_report),
        "titleOverridesPath": str(title_path),
        "summaryPath": str(summary_path),
        "rejectedPath": str(rejected_path),
        "sourceManifestPath": str(manifest_path),
        "credentialSource": "windows_dpapi",
        "apiVisits": visits,
    }
    write_json(run_dir / "candidate_pipeline_result.json", result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare a strict Runner queue through the official SellerSprite API")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--credential", type=Path, default=DEFAULT_CREDENTIAL)
    parser.add_argument("--queue-name", required=True)
    parser.add_argument("--queue-size", type=int, required=True)
    parser.add_argument("--run-date", required=True)
    args = parser.parse_args()
    try:
        result = execute(args)
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1
    print(json.dumps({"ok": True, "queueCount": result["queueCount"], "analysisWorkbookPath": result["analysisWorkbookPath"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
