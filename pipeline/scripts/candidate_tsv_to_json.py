"""candidate_tsv_to_json.py — TSV → candidate_meta JSON (顶层数组, 匹配 codex loader)

用法:
    python scripts/candidate_tsv_to_json.py runs/new_20260710_batch2/candidate_meta_batch2.tsv

输出到 TSV 所在目录:
    - candidate_meta_<batch>.json       顶层数组,codex replay_existing_batch.py 直接读
    - candidate_meta_<batch>.meta.json  sidecar 元数据(batch/count/生成源)
    - asin_queue.txt                     ASIN 一行一个,员工粘 Batch Runner v0.2.x QUEUE
    - asin_queue_report.txt              字段完整度 + 拒收行报告
"""
from __future__ import annotations
import argparse
import csv
import json
import re
import sys
from datetime import date, datetime
from pathlib import Path

from strict_history import load_strict_qualified_asins

ASIN_RE = re.compile(r"^[A-Z0-9]{10}$")
PLACEHOLDER_PREFIX = "B0XXXXXXXX"

REQUIRED_HEADERS = [
    "asin", "title", "brand", "price", "rating", "reviews",
    "childSales", "parentSales", "launchDate", "variations", "image", "sourcePage",
]


def parse_num(v, kind):
    if v is None or v == "":
        return None
    try:
        return int(float(v)) if kind == "int" else float(v)
    except (TypeError, ValueError):
        return None


def parse_date(v):
    if not v:
        return None
    v = str(v).strip()
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(v, fmt).date()
        except (ValueError, TypeError):
            continue
    return None


def normalize_row(raw):
    asin = str(raw.get("asin", "")).strip().upper()
    if not asin or asin.startswith(PLACEHOLDER_PREFIX) or not ASIN_RE.match(asin):
        return None, f"invalid or placeholder asin: {asin!r}"
    d = parse_date(raw.get("launchDate", ""))
    out = {
        "asin": asin,
        "title": (raw.get("title") or "").strip() or None,
        "brand": (raw.get("brand") or "").strip() or None,
        "price": parse_num(raw.get("price"), "float"),
        "rating": parse_num(raw.get("rating"), "float"),
        "reviews": parse_num(raw.get("reviews"), "int"),
        "childSales": parse_num(raw.get("childSales"), "int"),
        "parentSales": parse_num(raw.get("parentSales"), "int"),
        "launchDate": d.isoformat() if d else None,
        "variations": parse_num(raw.get("variations"), "int"),
        "image": (raw.get("image") or "").strip() or None,
        "sourcePage": (raw.get("sourcePage") or "").strip() or None,
        "categoryPath": (raw.get("categoryPath") or "").strip() or None,
        "delivery": (raw.get("delivery") or "").strip() or None,
        "dimensions": (raw.get("dimensions") or "").strip() or None,
        "priceTrend": (raw.get("priceTrend") or "").strip() or None,
        "sellerSpriteUrl": (raw.get("sellerSpriteUrl") or "").strip() or None,
    }
    return out, None


def load_tsv(path):
    rows = []
    with open(path, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f, delimiter="\t")
        headers = reader.fieldnames or []
        missing = [h for h in REQUIRED_HEADERS if h not in headers]
        if missing:
            raise SystemExit(f"TSV 缺少表头: {missing}\n第一行必须是: {REQUIRED_HEADERS}")
        for line_no, r in enumerate(reader, start=2):
            rows.append((line_no, r))
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("tsv")
    ap.add_argument("--batch-name", default=None)
    ap.add_argument("--dedupe-history", action="store_true",
                    help="兼容旧命令；历史严格合格 ASIN 现为默认强制跳过。")
    ap.add_argument("--project-root", default=None,
                    help="项目根目录,默认 = 脚本上级")
    args = ap.parse_args()

    tsv_path = Path(args.tsv).resolve()
    batch_dir = tsv_path.parent
    batch_name = args.batch_name or tsv_path.stem.replace("candidate_meta_", "")

    print(f"loading {tsv_path.name} ...")
    raw_rows = load_tsv(tsv_path)
    print(f"read {len(raw_rows)} data rows (excluding header)")

    history_root = args.project_root or str(Path(__file__).resolve().parent.parent)
    history_qualified = load_strict_qualified_asins(history_root)
    print(f"[dedupe] loaded {len(history_qualified)} historically strict-qualified ASINs")

    accepted = []
    rejected = []
    history_skipped = 0
    seen = set()
    # 历史合格 ASIN 提前塞进 seen,后续新输入命中直接判 duplicate
    for a in history_qualified:
        seen.add(a)
    for line_no, raw in raw_rows:
        rec, err = normalize_row(raw)
        if err:
            rejected.append((line_no, raw.get("asin", ""), err))
            continue
        if rec["asin"] in seen:
            if rec["asin"] in history_qualified:
                why = "already strict-qualified in history (auto-skip)"
                history_skipped += 1
            else:
                why = "duplicate asin in file"
            rejected.append((line_no, rec["asin"], why))
            continue
        seen.add(rec["asin"])
        rec["_batch"] = batch_name
        accepted.append(rec)

    # 顶层数组格式,匹配 codex replay_existing_batch.py 的 loader
    meta_out = batch_dir / f"candidate_meta_{batch_name}.json"
    meta_out.write_text(json.dumps(accepted, ensure_ascii=False, indent=2), encoding="utf-8")

    sidecar_out = batch_dir / f"candidate_meta_{batch_name}.meta.json"
    sidecar_out.write_text(
        json.dumps({
            "batch": batch_name,
            "count": len(accepted),
            "generatedFrom": tsv_path.name,
            "historyStrictQualifiedCount": len(history_qualified),
            "historySkippedCount": history_skipped,
        },
                   ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    queue_out = batch_dir / "asin_queue.txt"
    queue_out.write_text("\n".join(rec["asin"] for rec in accepted) + "\n", encoding="utf-8")

    field_stats = {k: sum(1 for r in accepted if r.get(k) is not None) for k in REQUIRED_HEADERS}
    report_lines = [
        f"# candidate_meta 转换报告 batch={batch_name}",
        f"生成自: {tsv_path.name}",
        "",
        f"- 收 {len(raw_rows)} 行, 接受 {len(accepted)}, 拒绝 {len(rejected)}",
        f"- 历史严格合格库 {len(history_qualified)} 条, 本次直接跳过 {history_skipped} 条",
        f"- 输出主 JSON: {meta_out.name} (顶层数组)",
        f"- 输出 sidecar: {sidecar_out.name}",
        f"- 输出 ASIN 队列: {queue_out.name}",
        "",
        "## 字段完整度 (非 null / 总数):",
    ]
    critical = {"price", "rating", "launchDate", "variations", "image"}
    for k in REQUIRED_HEADERS:
        n = field_stats[k]
        star = " (!)" if n < len(accepted) and k in critical else ""
        report_lines.append(f"  {k:<14}: {n}/{len(accepted)}{star}")
    if rejected:
        report_lines.append("")
        report_lines.append("## 被拒行:")
        for ln, a, err in rejected[:20]:
            report_lines.append(f"  line {ln} asin={a!r}: {err}")
        if len(rejected) > 20:
            report_lines.append(f"  ... 还有 {len(rejected) - 20} 行")
    else:
        report_lines.append("")
        report_lines.append("所有行都接受了 [OK]")

    report_out = batch_dir / "asin_queue_report.txt"
    report_out.write_text("\n".join(report_lines) + "\n", encoding="utf-8")

    print(f"[OK] accepted {len(accepted)}, rejected {len(rejected)}")
    print(f"[OK] wrote {meta_out.name}")
    print(f"[OK] wrote {sidecar_out.name}")
    print(f"[OK] wrote {queue_out.name}")
    print(f"[OK] wrote {report_out.name}")


if __name__ == "__main__":
    main()
