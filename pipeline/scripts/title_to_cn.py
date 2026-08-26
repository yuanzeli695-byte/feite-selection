"""title_to_cn.py — 规则式英文标题 -> 中文品名生成

策略:
    1. lowercase 归一化 title
    2. 抽出 size 规格 (24x36, 8x10, 6 inch 等)
    3. 匹配 contexts (节庆/场景) -> 前置
    4. 匹配 modifiers (材质/颜色/前置词) -> 组合前置
    5. 匹配 categories -> 主品类词(词尾落脚)
    6. 匹配 packaging (X件装) -> 后置括号
    7. brand 保留英文 or 直接嵌入
    8. 拼装,超过 30 字截断,输出

用法:
    # 单条
    python scripts/title_to_cn.py "24x36 Black Flat Profile Wall Photo Frame"
    # 批量: TSV/JSON 输入 -> 生成 overrides map
    python scripts/title_to_cn.py --batch candidate_meta_batch2.json --out zh_title_overrides.json --merge
    # 从 baseline 回归测试
    python scripts/title_to_cn.py --regress
"""
from __future__ import annotations
import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DICT_PATH = ROOT / "config" / "zh_title_dict.json"
MAX_CN_LEN = 30

# 数字x数字 尺寸,如 24x36, 8x10
SIZE_XY_RE = re.compile(r"\b(\d+(?:\.\d+)?)\s*[x×]\s*(\d+(?:\.\d+)?)\s*(inch|in|inches|\")?\b", re.I)
# 单个尺寸如 6 inch, 6"
SIZE_ONE_RE = re.compile(r"\b(\d+(?:\.\d+)?)\s*(inch|in|inches|\")\b", re.I)
# X件装(源标题里的数量)
QTY_RE = re.compile(r"\b(\d+)\s*(?:pack|-pack|pcs|piece|pieces|ct|count)\b", re.I)
# 品牌一般是 title 开头一个词或大写词
BRAND_HEAD_RE = re.compile(r"^([A-Z][A-Za-z0-9]{2,})\b")


class Dict_:
    def __init__(self, path=DICT_PATH):
        d = json.loads(Path(path).read_text(encoding="utf-8"))
        self.categories = d["categories"]
        self.modifiers = d["modifiers"]
        self.contexts = d["contexts"]
        self.packaging = d["packaging"]
        self.brands = set(x.lower() for x in d["keep_english_brands"])
        self.actions = d.get("action_words", {})
        # 按长度倒排匹配(长词优先命中)
        self._cat_keys = sorted(self.categories.keys(), key=len, reverse=True)
        self._mod_keys = sorted(self.modifiers.keys(), key=len, reverse=True)
        self._ctx_keys = sorted(self.contexts.keys(), key=len, reverse=True)
        self._pkg_keys = sorted(self.packaging.keys(), key=len, reverse=True)
        self._act_keys = sorted(self.actions.keys(), key=len, reverse=True)


def _find_all(text, keys):
    """在 text 里找出所有命中的 key 及位置。text 已 lowercase。返回 [(pos, key)]。不重叠。"""
    hits = []
    consumed = [False] * len(text)
    for k in keys:
        i = 0
        while True:
            j = text.find(k, i)
            if j < 0:
                break
            if not any(consumed[j:j + len(k)]):
                # 单词边界粗判: 左右非字母
                left_ok = j == 0 or not text[j - 1].isalpha()
                right_ok = j + len(k) == len(text) or not text[j + len(k)].isalpha()
                if left_ok and right_ok:
                    hits.append((j, k))
                    for x in range(j, j + len(k)):
                        consumed[x] = True
            i = j + 1
    hits.sort()
    return hits


def _detect_brand(title, dict_):
    """从 title 开头找品牌:brands 白名单 or 大写首词。返回(brand_str_original_case, remaining_title)。"""
    stripped = title.strip()
    low = stripped.lower()
    for b in dict_.brands:
        if low.startswith(b + " "):
            return stripped[:len(b)], stripped[len(b):].strip()
    # 未在白名单,试探开头大写词
    m = BRAND_HEAD_RE.match(stripped)
    if m:
        candidate = m.group(1)
        if candidate.lower() in dict_.brands:
            return candidate, stripped[len(candidate):].strip()
    return None, stripped


def _extract_size(low_title):
    """抽 24x36 或 8 inch 类尺寸,返回中文规格串 or ''。"""
    m = SIZE_XY_RE.search(low_title)
    if m:
        a, b, unit = m.group(1), m.group(2), m.group(3)
        unit_cn = "英寸" if unit and unit.lower().startswith("in") or unit == '"' else ""
        return f"{a}x{b}{unit_cn or '英寸'}"
    m = SIZE_ONE_RE.search(low_title)
    if m:
        return f"{m.group(1)}英寸"
    return ""


def _extract_qty(low_title, dict_):
    """抽包装 (5-pack / set of 3 / 2pcs) -> 中文。优先词典命中,退回自动生成 X件装。"""
    hits = _find_all(low_title, dict_._pkg_keys)
    if hits:
        return dict_.packaging[hits[0][1]]
    m = QTY_RE.search(low_title)
    if m:
        n = m.group(1)
        return f"{n}件装"
    return ""


def translate(title, dict_=None):
    """
    Return: dict(cnTitle, confidence, tags, hits)
        confidence: 'high' | 'medium' | 'low' | 'manual'
    """
    if not title or not title.strip():
        return {"cnTitle": None, "confidence": "manual", "tags": ["empty"], "hits": {}}
    dict_ = dict_ or Dict_()

    brand_orig, remaining = _detect_brand(title, dict_)
    low_full = title.lower()
    # 全文扫品牌(不只是开头)
    if not brand_orig:
        for b in dict_.brands:
            idx = low_full.find(b)
            if idx >= 0:
                # 用原文的原始大小写
                brand_orig = title[idx:idx+len(b)]
                # 首字母大写化,匹配 baseline 风格
                brand_orig = brand_orig[:1].upper() + brand_orig[1:]
                break
    low = remaining.lower() if remaining else low_full

    GENERIC_CAT_WORDS = {"套装", "组"}  # 无实体信息量的品类词,只作 fallback

    # 同一语义组(如美国节庆)只保留最前的 1 个,避免"独立日爱国主题阵亡将士纪念日"堆叠
    # 语义组: 组内只留 1 个(以主词为准),防止"独立日爱国主题阵亡将士纪念日"堆叠
    # 但"红白蓝"是色彩组合,不算节庆,不合入
    CTX_SEMANTIC_GROUPS = [
        {"独立日", "爱国主题", "阵亡将士纪念日"},  # 美国节庆
        {"圣诞", "感恩节"},
    ]
    def _dedupe_ctx_by_group(hits):
        seen_group = set()
        kept = []
        for h in hits:
            g_idx = None
            for i, g in enumerate(CTX_SEMANTIC_GROUPS):
                if h in g:
                    g_idx = i
                    break
            if g_idx is None:
                kept.append(h)
                continue
            if g_idx not in seen_group:
                # 组内选一个"主词":独立日/圣诞 优先
                MAIN = {"独立日", "圣诞"}
                # 后续如果有 MAIN 词,替换为它;否则保留第一个
                seen_group.add(g_idx)
                kept.append(h)
            else:
                # 已有同组词,若当前更 canonical 则替换
                MAIN = {"独立日", "圣诞"}
                if h in MAIN and kept[-1] not in MAIN:
                    # 替换最近一次同组词
                    for j in range(len(kept) - 1, -1, -1):
                        if kept[j] in CTX_SEMANTIC_GROUPS[g_idx]:
                            kept[j] = h
                            break
        return kept

    ctx_hits_raw = [dict_.contexts[k] for _, k in _find_all(low, dict_._ctx_keys)]
    ctx_hits = _dedupe_ctx_by_group(ctx_hits_raw)
    mod_hits = [dict_.modifiers[k] for _, k in _find_all(low, dict_._mod_keys)]
    cat_hits_all = [dict_.categories[k] for _, k in _find_all(low, dict_._cat_keys)]
    cat_hits_specific = [c for c in cat_hits_all if c not in GENERIC_CAT_WORDS]
    cat_hits_generic = [c for c in cat_hits_all if c in GENERIC_CAT_WORDS]
    cat_hits = cat_hits_specific if cat_hits_specific else cat_hits_generic

    size_cn = _extract_size(low)
    qty_cn = _extract_qty(low, dict_)

    if not cat_hits:
        return {
            "cnTitle": None,
            "confidence": "manual",
            "tags": ["no_category_hit"],
            "hits": {"contexts": ctx_hits, "modifiers": mod_hits, "size": size_cn, "qty": qty_cn},
        }

    parts = []
    if brand_orig:
        parts.append(brand_orig)
    parts.extend(dict.fromkeys(ctx_hits))  # 保持顺序去重
    if size_cn:
        parts.append(size_cn)
    # 若 context 保留了"红白蓝"(有色彩信息),剥除 modifier 里的单色词以免重复
    kept_ctx_str = "".join(ctx_hits)
    color_words_to_strip = ["红色", "白色", "蓝色"] if "红白蓝" in kept_ctx_str else []
    mod_filtered = [m for m in mod_hits if m not in color_words_to_strip]
    parts.extend(dict.fromkeys(mod_filtered))
    parts.append(cat_hits[-1])  # 主品类词落尾
    cn = "".join(parts)
    if qty_cn:
        cn += f"({qty_cn})"

    confidence = "high"
    if len(cat_hits) > 1:
        confidence = "medium"  # 多品类命中,可能挑错
    if not (brand_orig or ctx_hits or mod_hits or size_cn) and len(cat_hits) == 1:
        confidence = "low"  # 只有单品类词,过于简略

    tags = []
    if len(cn) > MAX_CN_LEN:
        cn = cn[:MAX_CN_LEN]
        tags.append("truncated")

    return {
        "cnTitle": cn,
        "confidence": confidence,
        "tags": tags,
        "hits": {
            "brand": brand_orig,
            "contexts": ctx_hits,
            "modifiers": mod_hits,
            "categories": cat_hits,
            "size": size_cn,
            "qty": qty_cn,
        },
    }


def batch_from_json(in_path, out_path, merge=False):
    data = json.loads(Path(in_path).read_text(encoding="utf-8-sig"))
    if not isinstance(data, list):
        raise SystemExit(f"input must be top-level array (candidate_meta.json), got {type(data).__name__}")
    dict_ = Dict_()
    overrides = {}
    if merge and Path(out_path).exists():
        overrides.update(json.loads(Path(out_path).read_text(encoding="utf-8")))
    stats = {"high": 0, "medium": 0, "low": 0, "manual": 0, "kept_existing": 0}
    manual_list = []
    for item in data:
        asin = item.get("asin")
        if not asin:
            continue
        if merge and asin in overrides:
            stats["kept_existing"] += 1
            continue
        title = item.get("title") or ""
        res = translate(title, dict_)
        if res["cnTitle"]:
            overrides[asin] = res["cnTitle"]
            stats[res["confidence"]] += 1
        else:
            stats["manual"] += 1
            manual_list.append({"asin": asin, "title": title[:80]})
    Path(out_path).write_text(json.dumps(overrides, ensure_ascii=False, indent=2), encoding="utf-8")

    report_path = Path(out_path).with_suffix(".report.txt")
    lines = [
        f"# title_to_cn 批量报告",
        f"输入: {in_path}",
        f"输出: {out_path}",
        f"",
        f"覆盖: {sum(v for k,v in stats.items() if k != 'manual')}/{len(data)}",
        f"  high(高置信度): {stats['high']}",
        f"  medium(多品类命中): {stats['medium']}",
        f"  low(仅品类词): {stats['low']}",
        f"  kept_existing(已有覆盖): {stats['kept_existing']}",
        f"  manual(需人工): {stats['manual']}",
    ]
    if manual_list:
        lines.append("")
        lines.append("## 需人工补的品:")
        for m in manual_list[:20]:
            lines.append(f"  {m['asin']}: {m['title']}")
        if len(manual_list) > 20:
            lines.append(f"  ... 还有 {len(manual_list) - 20} 个")
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print(f"\n[OK] wrote {out_path}")
    print(f"[OK] wrote {report_path}")


BASELINE_REGRESS = [
    ("B0H3P3KG2V", "24x36 Black Flat Profile Wall Photo Frame", "24x36英寸黑色平面墙面相框"),
    ("B0GVDDW8LC", "4th of July Decorations Outdoor - Patriotic Decorations Hanging Banner", "独立日户外挂旗门廊装饰横幅"),
    ("B0GX7MVHV1", "4th of July Balloon Arch Kit, 146pcs Red White and Blue Balloons", "独立日红白蓝气球拱门套装"),
    ("B0GX56PWJH", "4th of July Car Decorations Kit for Parade - Patriotic American Set", "独立日汽车巡游装饰套装"),
    ("B0GSFSJKRF", "Replacement 38754 Filter Compatible with Craftsman Wet Dry Vacuum 2 Pack", "Craftsman干湿吸尘器兼容替换滤芯(2只装)"),
    ("B0GT49SV3M", "Natural Solid Wood 8x10 Picture Frame Set of 2", "天然实木8x10相框2件套"),
]


def regress():
    dict_ = Dict_()
    n_hit = 0
    print(f"{'ASIN':<12} | {'confidence':<10} | {'cn_generated':<30} | {'cn_baseline (人工)':<30} | title_en")
    print("-" * 140)
    for asin, title, expected in BASELINE_REGRESS:
        r = translate(title, dict_)
        cn = r["cnTitle"] or "(NO HIT)"
        conf = r["confidence"]
        print(f"{asin:<12} | {conf:<10} | {cn:<30} | {expected:<30} | {title[:50]}")
        if cn != "(NO HIT)":
            n_hit += 1
    print(f"\n覆盖率: {n_hit}/{len(BASELINE_REGRESS)}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("title", nargs="?", help="单条英文标题(单条模式)")
    ap.add_argument("--batch", help="candidate_meta.json 顶层数组输入")
    ap.add_argument("--out", help="批量输出 zh_title_overrides.json 路径")
    ap.add_argument("--merge", action="store_true", help="批量: 保留 out 里已有的 ASIN,不覆盖")
    ap.add_argument("--regress", action="store_true", help="用 baseline 6 个品跑回归")
    args = ap.parse_args()

    if args.regress:
        regress()
        return
    if args.batch:
        out = args.out or (ROOT / "config" / "zh_title_overrides.json")
        batch_from_json(args.batch, out, merge=args.merge)
        return
    if args.title:
        r = translate(args.title)
        print(json.dumps(r, ensure_ascii=False, indent=2))
        return
    ap.print_help()


if __name__ == "__main__":
    main()
