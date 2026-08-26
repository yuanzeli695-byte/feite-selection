#!/usr/bin/env python3
"""Convert a SellerSprite export into a strictly prefiltered Runner ASIN queue."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse

try:
    from openpyxl import load_workbook
except ImportError:  # pragma: no cover - exercised by the runtime dependency check
    load_workbook = None

from prepare_strict_candidate_pool import (  # noqa: E402
    SourceContractError,
    parse_aware_datetime,
    validate_query_url,
)


PROGRAM_VERSION = "sellerSpriteExportRunnerQueue/v1.5"
EXPLICIT_QUEUE_EXCLUSION_VERSION = "runner-queue-explicit-exclusion-v1"
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
ASIN_RE = re.compile(r"^[A-Z0-9]{10}$")
QUEUE_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,80}$")
NUMBER_RE = re.compile(r"^-?\d+(?:\.\d+)?$")


class InputError(ValueError):
    """Raised when an exported table cannot support strict source reduction."""


def normalize_header(value: Any) -> str:
    return re.sub(r"[\s_\-:/：()（）\[\]{}$]+", "", str(value or "")).casefold()


HEADER_ALIASES: dict[str, tuple[str, ...]] = {
    "asin": ("asin", "商品asin", "子asin"),
    "title": ("商品名称", "商品标题", "标题", "产品名称", "title", "product title"),
    "brand": ("品牌", "brand"),
    "categoryPath": ("类目", "类目路径", "商品类目", "所属类目", "分类", "category"),
    "monthlySales": ("月销量", "月销售量", "monthly sales"),
    "childSales": ("子体销量", "子asin销量", "子体月销量", "child sales"),
    "parentSales": ("父体销量", "父asin销量", "parent sales"),
    "price": ("价格", "售价", "price"),
    "rating": ("评分", "星级", "rating"),
    "reviews": ("评分数", "评论数", "评论数量", "reviews", "review count"),
    "variations": ("变体数", "变体数量", "variations", "variation count"),
    "launchDate": ("上架时间", "上架日期", "发布日期", "listing date", "launch date"),
    "image": ("商品主图", "主图链接", "主图", "图片链接", "image", "image url"),
}
ALIAS_TO_FIELD = {
    normalize_header(alias): field
    for field, aliases in HEADER_ALIASES.items()
    for alias in aliases
}
REQUIRED_FIELDS = (
    "asin",
    "title",
    "brand",
    "categoryPath",
    "price",
    "rating",
    "reviews",
    "launchDate",
    "variations",
    "image",
)


def text_value(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def resolve_headers(
    headers: Iterable[Any], *, allow_missing_sales: bool = False
) -> dict[str, str]:
    found: dict[str, list[str]] = {}
    for header in headers:
        raw_header = text_value(header)
        field = ALIAS_TO_FIELD.get(normalize_header(raw_header))
        if field:
            found.setdefault(field, []).append(raw_header)

    ambiguous = {field: values for field, values in found.items() if len(values) > 1}
    if ambiguous:
        details = ", ".join(f"{field}={values}" for field, values in ambiguous.items())
        raise InputError(f"ambiguous SellerSprite headers: {details}")

    mapping = {field: values[0] for field, values in found.items()}
    required_fields = REQUIRED_FIELDS if allow_missing_sales else (*REQUIRED_FIELDS, "childSales")
    missing = [field for field in required_fields if field not in mapping]
    if missing:
        known = ", ".join(text_value(header) for header in headers if text_value(header))
        raise InputError(
            "missing required headers: "
            + ", ".join(missing)
            + f". Exported headers were: {known}"
        )
    return mapping


def read_xlsx(path: Path, sheet_name: str | None) -> tuple[list[str], list[tuple[int, dict[str, Any]]]]:
    if load_workbook is None:
        raise InputError(".xlsx input requires openpyxl; install the project runtime dependencies")
    # Normal mode preserves hyperlink targets used by SellerSprite image columns.
    workbook = load_workbook(path, read_only=False, data_only=True)
    try:
        if sheet_name:
            if sheet_name not in workbook.sheetnames:
                raise InputError(f"worksheet not found: {sheet_name}")
            sheet = workbook[sheet_name]
        else:
            sheet = workbook.active

        rows = sheet.iter_rows()
        for row_number, cells in enumerate(rows, start=1):
            headers = [text_value(cell.value) for cell in cells]
            if any(headers):
                break
        else:
            raise InputError("exported workbook has no header row")

        result: list[tuple[int, dict[str, Any]]] = []
        for row_number, cells in enumerate(rows, start=row_number + 1):
            values: dict[str, Any] = {}
            has_value = False
            for index, header in enumerate(headers):
                if not header:
                    continue
                cell = cells[index] if index < len(cells) else None
                value = cell.value if cell is not None else None
                values[header] = value
                hyperlink = getattr(cell, "hyperlink", None) if cell is not None else None
                if hyperlink and hyperlink.target:
                    values[f"{header}__hyperlink"] = hyperlink.target
                has_value = has_value or bool(text_value(value))
            if has_value:
                result.append((row_number, values))
        return headers, result
    finally:
        workbook.close()


def read_delimited(path: Path, delimiter: str) -> tuple[list[str], list[tuple[int, dict[str, Any]]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, delimiter=delimiter)
        if not reader.fieldnames:
            raise InputError("exported file has no header row")
        rows = [
            (line_number, dict(row))
            for line_number, row in enumerate(reader, start=2)
            if any(text_value(value) for value in row.values())
        ]
    return list(reader.fieldnames), rows


def read_export(path: Path, sheet_name: str | None) -> tuple[list[str], list[tuple[int, dict[str, Any]]]]:
    suffix = path.suffix.casefold()
    if suffix == ".xlsx":
        return read_xlsx(path, sheet_name)
    if suffix == ".csv":
        return read_delimited(path, ",")
    if suffix == ".tsv":
        return read_delimited(path, "\t")
    raise InputError("input must be a .xlsx, .csv, or .tsv SellerSprite export")


def parse_number(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        numeric = float(value)
        return numeric if math.isfinite(numeric) else None
    raw = text_value(value).replace(",", "").replace("$", "").replace("￥", "")
    raw = raw.replace(chr(0x00A5), "")
    raw = text_value(value).replace(",", "").replace("$", "").replace(chr(0x00A5), "")
    if not NUMBER_RE.fullmatch(raw):
        return None
    numeric = float(raw)
    return numeric if math.isfinite(numeric) else None


def parse_launch_date(value: Any) -> str | None:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    raw = text_value(value)
    for format_string in ("%Y-%m-%d", "%Y/%m/%d", "%m/%d/%Y", "%Y.%m.%d"):
        try:
            return datetime.strptime(raw, format_string).date().isoformat()
        except ValueError:
            continue
    return None


def valid_http_url(value: Any) -> str | None:
    raw = text_value(value)
    parsed = urlparse(raw)
    if parsed.scheme in {"http", "https"} and parsed.netloc:
        return raw
    return None


def normalize_row(
    row_number: int,
    raw_row: dict[str, Any],
    mapping: dict[str, str],
    source_page: str,
    seller_sprite_url: str | None,
    allow_missing_sales: bool,
) -> tuple[dict[str, Any] | None, list[str]]:
    values = {field: raw_row.get(header) for field, header in mapping.items()}
    errors: list[str] = []

    asin = text_value(values.get("asin")).upper()
    if not ASIN_RE.fullmatch(asin):
        errors.append("invalid_asin")

    strings: dict[str, str] = {}
    for field in ("title", "brand", "categoryPath"):
        value = text_value(values.get(field))
        if not value:
            errors.append(f"missing_{field}")
        else:
            strings[field] = value

    numbers: dict[str, float] = {}
    required_numeric_fields = ["price", "rating", "reviews", "variations"]
    if not allow_missing_sales:
        required_numeric_fields.append("childSales")
    for field in required_numeric_fields:
        numeric = parse_number(values.get(field))
        if numeric is None or numeric < 0:
            errors.append(f"invalid_{field}")
        else:
            numbers[field] = numeric
    for field in ("monthlySales", "parentSales", "childSales"):
        if field not in values:
            continue
        if not text_value(values.get(field)):
            continue
        numeric = parse_number(values.get(field))
        if numeric is None or numeric < 0:
            errors.append(f"invalid_{field}")
        else:
            numbers[field] = numeric

    launch_date = parse_launch_date(values.get("launchDate"))
    if launch_date is None:
        errors.append("invalid_launchDate")
    image_hyperlink = raw_row.get(f"{mapping['image']}__hyperlink")
    image = valid_http_url(image_hyperlink) or valid_http_url(values.get("image"))
    if image is None:
        errors.append("invalid_image")

    if errors:
        return None, sorted(set(errors))

    candidate = {
        "asin": asin,
        **strings,
        **numbers,
        "launchDate": launch_date,
        "image": image,
        "amazonUrl": f"https://www.amazon.com/dp/{asin}?psc=1",
        "sourcePage": source_page,
        "sourceRow": row_number,
    }
    if seller_sprite_url:
        candidate["sellerSpriteUrl"] = seller_sprite_url
    return candidate, []


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def create_formal_manifest(
    output_dir: Path,
    source_query_path: Path,
    query_url: str,
    captured_at: str,
) -> Path:
    try:
        query_contract = validate_query_url(query_url)
        parse_aware_datetime(captured_at, "capturedAt")
    except SourceContractError as exc:
        raise InputError(f"invalid formal SellerSprite source: {exc}") from exc

    manifest_path = output_dir / "source_manifest.json"
    write_json(
        manifest_path,
        {
            "schemaVersion": "sellerSpriteCandidateSourceManifest/v1",
            "capturedAt": captured_at,
            "market": "US",
            "preset": {"name": "sellerSprite_export"},
            "categoryScope": {
                "name": "SellerSprite export query scope",
                "nodeIdPaths": query_contract["nodeIdPaths"],
            },
            "inputs": [
                {
                    "path": source_query_path.name,
                    "sha256": sha256_file(source_query_path),
                    "queryUrl": query_contract["url"],
                }
            ],
        },
    )
    return manifest_path


def validate_args(args: argparse.Namespace) -> None:
    if not args.input.exists() or not args.input.is_file():
        raise InputError(f"input export not found: {args.input}")
    if not QUEUE_NAME_RE.fullmatch(args.queue_name):
        raise InputError("queue name must use letters, digits, hyphens, or underscores only")
    if args.queue_size <= 0:
        raise InputError("queue size must be greater than zero")
    if args.max_per_brand <= 0:
        raise InputError("max per brand must be greater than zero")
    if args.exclude_asins_file and (
        not args.exclude_asins_file.exists() or not args.exclude_asins_file.is_file()
    ):
        raise InputError(f"exclude ASIN file not found: {args.exclude_asins_file}")
    if args.output_dir.exists() and any(args.output_dir.iterdir()):
        raise InputError(f"output directory is not empty: {args.output_dir}. Use a new run directory.")
    if args.allow_legacy_export:
        if args.query_url or args.captured_at:
            raise InputError("--allow-legacy-export cannot be combined with --query-url or --captured-at")
    elif not args.query_url or not args.captured_at:
        raise InputError(
            "formal mode requires --query-url and --captured-at. "
            "Use --allow-legacy-export only for an explicitly labeled recovery queue."
        )


def run_command(command: list[str]) -> None:
    completed = subprocess.run(command, cwd=PROJECT_ROOT, text=True, check=False)
    if completed.returncode:
        raise RuntimeError(f"strict candidate pool failed with exit code {completed.returncode}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Convert a SellerSprite .xlsx/.csv/.tsv export into a Runner ASIN queue."
    )
    parser.add_argument("input", type=Path, help="SellerSprite export (.xlsx, .csv, or .tsv)")
    parser.add_argument("--output-dir", type=Path, required=True, help="new directory for this run")
    parser.add_argument("--queue-name", required=True, help="safe filename prefix for the queue")
    parser.add_argument("--queue-size", type=int, default=40, help="maximum ASINs to queue (default: 40)")
    parser.add_argument("--max-per-brand", type=int, default=2, help="strict queue brand cap (default: 2)")
    parser.add_argument("--sheet", help="worksheet name for .xlsx input")
    parser.add_argument("--source-page", help="human-readable export source label")
    parser.add_argument(
        "--exclude-asins-file",
        type=Path,
        help="text file of previously queued ASINs to exclude from this queue",
    )
    parser.add_argument(
        "--allow-missing-sales",
        action="store_true",
        help=(
            "explicit queue-only override: parent/child/monthly sales may remain missing "
            "without substitution"
        ),
    )
    parser.add_argument("--query-url", help="full active SellerSprite product-research URL")
    parser.add_argument("--captured-at", help="ISO 8601 time when the query URL/export was captured")
    parser.add_argument(
        "--allow-legacy-export",
        action="store_true",
        help="explicit fallback; marks output as non-formal source evidence",
    )
    parser.add_argument("--run-date", default=date.today().isoformat(), help="YYYY-MM-DD, default today")
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT, help="project history root")
    args = parser.parse_args()

    try:
        args.input = args.input.resolve()
        args.output_dir = args.output_dir.resolve()
        args.project_root = args.project_root.resolve()
        if args.exclude_asins_file:
            args.exclude_asins_file = args.exclude_asins_file.resolve()
        validate_args(args)
        headers, exported_rows = read_export(args.input, args.sheet)
        mapping = resolve_headers(headers, allow_missing_sales=args.allow_missing_sales)
        args.output_dir.mkdir(parents=True, exist_ok=True)

        source_page = args.source_page or f"SellerSprite export: {args.input.stem}"
        normalized_rows: list[dict[str, Any]] = []
        rejected_rows: list[dict[str, Any]] = []
        seller_sprite_url = args.query_url if not args.allow_legacy_export else None
        for row_number, raw_row in exported_rows:
            candidate, errors = normalize_row(
                row_number,
                raw_row,
                mapping,
                source_page,
                seller_sprite_url,
                args.allow_missing_sales,
            )
            if candidate is None:
                rejected_rows.append({"sourceRow": row_number, "reasons": errors})
            else:
                normalized_rows.append(candidate)
        if not normalized_rows:
            raise InputError("no rows remained after SellerSprite export normalization")

        normalized_path = args.output_dir / "normalized_candidates.json"
        write_json(normalized_path, normalized_rows)
        source_queries_dir = args.output_dir / "source_queries"
        source_queries_dir.mkdir(parents=True, exist_ok=True)
        source_query_path = source_queries_dir / "query_sellersprite_export.json"
        write_json(source_query_path, normalized_rows)
        rejected_path = args.output_dir / "normalization_rejected.json"
        write_json(rejected_path, rejected_rows)
        write_json(
            args.output_dir / "normalization_report.json",
            {
                "programVersion": PROGRAM_VERSION,
                "input": str(args.input),
                "inputSha256": sha256_file(args.input),
                "headerMapping": mapping,
                "exportedRows": len(exported_rows),
                "normalizedRows": len(normalized_rows),
                "normalizationRejectedRows": len(rejected_rows),
                "sourceMode": "legacy_export" if args.allow_legacy_export else "formal_manifest",
                "allowMissingSales": args.allow_missing_sales,
                "missingSalesFieldCounts": {
                    field: sum(field not in row for row in normalized_rows)
                    for field in ("monthlySales", "childSales", "parentSales")
                },
            },
        )

        source_args: list[str]
        manifest_path: Path | None = None
        if args.allow_legacy_export:
            source_args = ["--allow-legacy-source"]
        else:
            manifest_path = create_formal_manifest(
                args.output_dir, source_query_path, args.query_url, args.captured_at
            )
            source_args = ["--source-manifest", str(manifest_path)]

        run_command(
            [
                sys.executable,
                str(SCRIPT_DIR / "strict_history.py"),
                "--project-root",
                str(args.project_root),
                "--write",
            ]
        )

        pool_dir = args.output_dir / "candidate_pool"
        sales_args = ["--allow-missing-parent-child-sales"] if args.allow_missing_sales else []
        exclusion_args = ["--attempted", str(args.exclude_asins_file)] if args.exclude_asins_file else []
        run_command(
            [
                sys.executable,
                str(SCRIPT_DIR / "prepare_strict_candidate_pool.py"),
                "--input-dir",
                str(source_queries_dir),
                "--output-dir",
                str(pool_dir),
                "--queue-name",
                args.queue_name,
                "--queue-size",
                str(args.queue_size),
                "--max-per-source",
                str(args.queue_size),
                "--max-per-brand",
                str(args.max_per_brand),
                "--run-date",
                args.run_date,
                "--project-root",
                str(args.project_root),
                *sales_args,
                *exclusion_args,
                *source_args,
            ]
        )

        queue_path = pool_dir / f"asin_queue_{args.queue_name}.txt"
        pool_summary_path = pool_dir / f"summary_{args.queue_name}.json"
        pool_summary = json.loads(pool_summary_path.read_text(encoding="utf-8"))
        queue_asins = [line.strip() for line in queue_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        summary_path = args.output_dir / "queue_adapter_summary.json"
        write_json(
            summary_path,
            {
                "programVersion": PROGRAM_VERSION,
                "sourceMode": "legacy_export" if args.allow_legacy_export else "formal_manifest",
                "qualificationScope": "runner_queue_only_no_final_AF_pass",
                "salesPresencePolicy": (
                    "explicit_missing_sales_queue_override/v1"
                    if args.allow_missing_sales
                    else "parent_child_sales_required/v1"
                ),
                "input": str(args.input),
                "normalizedCandidateFile": str(normalized_path),
                "sourceManifest": str(manifest_path) if manifest_path else None,
                "normalizationRejectedFile": str(rejected_path),
                "runnerQueuePath": str(queue_path),
                "runnerQueueCount": len(queue_asins),
                "runnerQueueAsins": queue_asins,
                "explicitQueueExclusion": {
                    "enabled": bool(args.exclude_asins_file),
                    "version": EXPLICIT_QUEUE_EXCLUSION_VERSION if args.exclude_asins_file else None,
                    "input": str(args.exclude_asins_file) if args.exclude_asins_file else None,
                    "inputSha256": sha256_file(args.exclude_asins_file) if args.exclude_asins_file else None,
                    "skippedCount": pool_summary.get("attemptedSkippedCount", 0),
                    "rollback": "omit --exclude-asins-file",
                },
                "strictPoolSummary": str(pool_summary_path),
                "strictPoolCounts": pool_summary.get("counts", {}),
            },
        )
        print(json.dumps({"runnerQueuePath": str(queue_path), "asinCount": len(queue_asins)}, ensure_ascii=False))
        return 0
    except (InputError, RuntimeError, OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
