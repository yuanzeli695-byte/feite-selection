#!/usr/bin/env python3
"""apply_traffic_batch.py — 桌面\amazon_products\ 版

规则:
  - 主表命名: amazon_products_YYYYMMDD_HHMM.xlsx (当前时分)
  - 只保留一份滚动备份: amazon_products.backup_latest.xlsx
  - 原地修改传入的主表
  - 批次元数据(batchName / operator / queueHash)会校验并写进 sheet 备注

用法:
  # 情况 A: 已有当天最新主表,补写流量
  python apply_traffic_batch.py results.json
  # 情况 B: 指定要写入的主表
  python apply_traffic_batch.py results.json --workbook amazon_products_20260709_1500.xlsx
  # 情况 C: 从原始候选表新建今天的主表
  python apply_traffic_batch.py results.json --new-from source.xlsx
  # 情况 D: 强制覆盖 batch 元数据不一致的错误(慎用)
  python apply_traffic_batch.py results.json --force
"""
from __future__ import annotations
import argparse
import json
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

import openpyxl

HERE = Path(__file__).resolve().parent
SHEET = "候选20品"
CAND_TO_ROW = {i: i + 3 for i in range(1, 21)}
BACKUP_LATEST = HERE / "amazon_products.backup_latest.xlsx"
BATCH_META_CELL = "A1"  # 主表 A1 存最近一次写入的 batch 元数据 JSON


def latest_workbook_today() -> Path | None:
    today = datetime.now().strftime("%Y%m%d")
    candidates = sorted(HERE.glob(f"amazon_products_{today}_*.xlsx"))
    return candidates[-1] if candidates else None


def new_workbook_name() -> Path:
    return HERE / f"amazon_products_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"


NOTE_STRIP_PATTERNS = [
    re.compile(r"；?流量占比需重取/复核"),
    re.compile(r"；?周期20\d{2}年?第\d+周\([^)]*\)；自然流量占比(?:未达70%，本轮流量不通过|达标，可保留)"),
    re.compile(r"；?待复核：本次未稳定取到流量来源占比"),
    re.compile(r"；?需重取/需复核：当前未取得可靠自然流量占比"),
    re.compile(r"；?详情页不可达：[^；]*"),
    re.compile(r"；?目标商品页不可达[^；]*"),
    re.compile(r"；?流量采集超时[^；]*"),
    re.compile(r"；?采集页面为变体[^；]*"),
]


def is_page_not_found(r):
    if not r or r.get("status") != "error":
        return False
    n = str(r.get("note") or "").lower()
    return "page_not_found" in n or "target_removed" in n or "removed" in n


def is_timeout(r):
    if not r:
        return False
    if r.get("status") == "timeout":
        return True
    n = str(r.get("note") or "").lower()
    return "timeout" in n and r.get("status") != "ok"


def is_asin_mismatch(r):
    t, a = r.get("targetAsin"), r.get("actualAsin")
    if not t or not a or t == a:
        return False
    if r.get("asinMismatch") is True:
        return True
    n = str(r.get("note") or "").lower()
    return "asin_mismatch" in n or "redirect" in n


def pct(v):
    if v is None:
        return None
    try:
        return f"{float(v):.2f}%"
    except (TypeError, ValueError):
        return None


def valid(r):
    if not r or r.get("status") != "ok":
        return False
    l = r.get("latestNaturalSharePct")
    if not isinstance(l, (int, float)) or l < 0 or l > 100:
        return False
    avg = r.get("recent4AvgNaturalSharePct")
    if isinstance(avg, (int, float)) and (avg < 0 or avg > 100):
        return False
    return True


def build_t(r):
    if is_page_not_found(r):
        return "目标商品页不可达（Page Not Found/已下架），本次未采集到流量数据"
    if is_timeout(r):
        return "流量采集超时：SellerSprite 图表未加载完成，需重取"
    if not valid(r):
        return "需重取/需复核：当前未取得可靠自然流量占比"
    weeks = r.get("weeksRead") or 0
    n = min(int(weeks), 4) if weeks else 4
    parts = [f"最新周{pct(r['latestNaturalSharePct'])}"]
    if r.get("recent4AvgNaturalSharePct") is not None:
        parts.append(f"近{n}周均值{pct(r['recent4AvgNaturalSharePct'])}")
    if r.get("recent4MinNaturalSharePct") is not None:
        parts.append(f"最低{pct(r['recent4MinNaturalSharePct'])}")
    parts.append(f"结论：{'通过' if r.get('pass70') else '不通过'}")
    return "；".join(parts)


def build_suffix(r):
    if is_page_not_found(r):
        return "目标商品页不可达，建议剔除或核对 ASIN"
    if is_timeout(r):
        return "流量采集超时，需重取"
    if not valid(r):
        return "流量占比需重取/复核"
    week = r.get("latestWeek") or ""
    ws_ = f"周期{week}" if week else "周期未标明"
    tail = "自然流量占比达标，可保留" if r.get("pass70") else "自然流量占比未达70%，本轮流量不通过"
    parts = [f"{ws_}；{tail}"]
    if is_asin_mismatch(r):
        parts.append(f"采集页面为变体{r.get('actualAsin')}，已按父体接受，需人工核对")
    return "；".join(parts)


def clean_note(s):
    s = s or ""
    for p in NOTE_STRIP_PATTERNS:
        s = p.sub("", s)
    return re.sub(r"；+", "；", s).strip("；").strip()


def resolve_row(rec, wb_asins):
    row_idx = rec.get("row")
    tgt = rec.get("targetAsin")
    if isinstance(row_idx, int) and row_idx in CAND_TO_ROW:
        sr = CAND_TO_ROW[row_idx]
        if tgt and wb_asins.get(sr) and wb_asins[sr] != tgt:
            print(f"WARN row {sr}: sheet ASIN {wb_asins[sr]} vs target {tgt}")
        return sr
    for r, a in wb_asins.items():
        if a == tgt:
            return r
    return None


KNOWN_SCHEMA_VERSIONS = {
    "sellerSpriteTrafficBatch/v0.2.0",
}


def load_batch(paths):
    """Return (records, meta) — meta = {batchName, operator, queueHash, generatedAt, queue, schemaVersion}."""
    records = []
    meta = {}
    for p in paths:
        data = json.loads(Path(p).read_text(encoding="utf-8-sig"))
        if isinstance(data, dict):
            sv = data.get("schemaVersion")
            if sv and sv not in KNOWN_SCHEMA_VERSIONS:
                print(f"⚠ unknown schemaVersion: {sv} (proceeding, but verify writer compatibility)")
            for k in ("batchName", "operator", "queueHash", "generatedAt", "schemaVersion"):
                if data.get(k) and k not in meta:
                    meta[k] = data[k]
            if "queue" in data and "queue" not in meta:
                meta["queue"] = data["queue"]
            if isinstance(data.get("results"), list):
                records.extend(data["results"])
            elif "row" in data or "targetAsin" in data:
                records.append(data)
        elif isinstance(data, list):
            records.extend(data)
        else:
            print(f"skip {p}: unsupported JSON shape")
    return records, meta


def check_batch_meta(existing: dict, incoming: dict, force: bool) -> bool:
    """Return True if OK to proceed."""
    if not existing or not incoming:
        return True
    for key in ("queueHash", "batchName"):
        e, i = existing.get(key), incoming.get(key)
        if e and i and e != i:
            print(f"⚠ batch meta mismatch: {key} existing={e} incoming={i}")
            if not force:
                print("  refuse to overwrite; pass --force if intended, or open new workbook")
                return False
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("json_files", nargs="+")
    ap.add_argument("--workbook", help="指定主表(相对本目录或绝对路径)")
    ap.add_argument("--new-from", help="从此源 xlsx 新建今天的主表")
    ap.add_argument("--force", action="store_true", help="覆盖批次元数据不一致警告")
    args = ap.parse_args()

    records, incoming_meta = load_batch(args.json_files)
    if not records:
        print("no records to apply")
        return 1

    if args.new_from:
        src = Path(args.new_from)
        if not src.is_absolute():
            src = HERE / src
        target = new_workbook_name()
        shutil.copy2(src, target)
        print(f"created new workbook from {src.name} -> {target.name}")
    elif args.workbook:
        target = Path(args.workbook)
        if not target.is_absolute():
            target = HERE / target
        if not target.exists():
            print(f"ERROR: workbook not found: {target}")
            return 2
    else:
        target = latest_workbook_today()
        if not target:
            print("ERROR: 找不到当天主表,请用 --new-from 或 --workbook 指定")
            return 2

    print(f"target -> {target.name}")

    shutil.copy2(target, BACKUP_LATEST)
    print(f"backup -> {BACKUP_LATEST.name}")

    wb = openpyxl.load_workbook(target)
    ws = wb[SHEET]

    existing_meta = {}
    a1 = ws[BATCH_META_CELL].value
    if isinstance(a1, str) and a1.startswith("{"):
        try:
            existing_meta = json.loads(a1)
        except Exception:
            existing_meta = {}
    if not check_batch_meta(existing_meta, incoming_meta, args.force):
        return 3

    wb_asins = {r: ws.cell(row=r, column=3).value for r in range(4, 24)}
    applied = []
    for rec in records:
        sr = resolve_row(rec, wb_asins)
        if not sr:
            print(f"SKIP unresolved: {rec.get('targetAsin')} row={rec.get('row')}")
            continue
        t_val = build_t(rec)
        cur_u = str(ws.cell(row=sr, column=21).value or "")
        new_u = f"{clean_note(cur_u)}；{build_suffix(rec)}".lstrip("；")
        ws.cell(row=sr, column=20).value = t_val
        ws.cell(row=sr, column=21).value = new_u
        applied.append((sr, wb_asins.get(sr), rec.get("status"), t_val, new_u))

    # 写批次元数据到 A1(不影响原表结构 —— A1 之前用来放大标题,现在会被覆盖)
    if incoming_meta:
        incoming_meta["appliedAt"] = datetime.now().isoformat(timespec="seconds")
        ws[BATCH_META_CELL].value = json.dumps(incoming_meta, ensure_ascii=False)

    wb.save(target)
    print(f"applied {len(applied)} rows")
    for sr, asin, st, t, _u in applied:
        print(f"  row {sr:>2} {str(asin):<12} [{str(st):<7}] T={t[:70]}")
    if incoming_meta:
        print(f"batch meta -> {BATCH_META_CELL}: {incoming_meta}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
