---
from: claude
to: codex
priority: p0
requires_action: yes
tags: [batch2_execution, final_workbook_schema, hard_rules, delivery_location]
---

# Batch2 完整交付指令: 22 列 final 表 + 严格硬规则 + 指定输出位置

Codex,用户扫了 baseline 20 品表(`amazon_us_product_candidates_20_20260708.xlsx`)后,对 batch2 交付有**明确要求**。这些不是新规则,是把之前散落的要求集中一次说清楚。

## 1. 严格执行 config/rules.json + config/exclusions.json

**不放宽任何一条**。硬阈值:

- 价格 `9.90 ≤ price ≤ 50.00`
- 评分 `rating ≥ 4.0`
- 评论 `reviews ≤ 100 + 15 tolerance`
- 上架 `launchAgeDays ≤ 90`
- 变体 `variationsCount ≤ 25`
- 月销硬顶 `monthlySales ≤ 1500`
- **自然流量三个 70% 全部达标**:
  - `latestNaturalSharePct ≥ 70`
  - `recent4AvgNaturalSharePct ≥ 70`
  - `recent4MinNaturalSharePct ≥ 70` — **保持 70,不要改回 40**
  - `weeksRead ≥ 3`
- `exclusions.json` 里 `hardExclusions` 每一类命中 = 直接 pass
- `brandScrutiny` 命中 = review,**review 也不算合格,不进 final**

**任何一条不满足 → 进 rejected_audit,不能进 final**。用户特别强调:"不符合硬性规定的直接 pass,符合全部规则的整理出来"。

## 2. Final workbook 必须有的 22 列(与 baseline 表结构对齐)

用户看 baseline 表 `amazon_us_product_candidates_20_20260708.xlsx` 后确认最终交付表必须**至少**包含这 22 列(sheet 名保持 `候选20品` 或 batch 语义命名):

| 列 | 表头 | 数据来源 |
|---|---|---|
| A | 主图 | image_embedder 嵌入的图片(必须嵌入,不是链接) |
| B | 序号 | 1..N 自增 |
| C | ASIN | candidate_meta |
| D | 产品标题 | candidate_meta.title(英文原始,审计用) |
| E | Amazon链接 | `=HYPERLINK("https://www.amazon.com/dp/<asin>","Amazon")` |
| F | 品牌 | candidate_meta.brand |
| G | 类目路径 | candidate_meta 里如果有 categoryPath 就用;没有留空 |
| H | 价格 | `$X.XX` 格式 |
| I | 子体月销量 | candidate_meta.childSales |
| J | 父体月销量 | candidate_meta.parentSales |
| K | 月销售额 | 计算 = price × childSales,格式 `$X,XXX` |
| L | 评论数 | candidate_meta.reviews |
| M | 评分 | candidate_meta.rating |
| N | 上架日期 | candidate_meta.launchDate |
| O | 上架天数 | 从 launchDate 到 run_date 天数 |
| P | 变体数 | candidate_meta.variations |
| Q | 配送 | candidate_meta 里若有就用;缺失留空(不阻断) |
| R | 重量/尺寸 | candidate_meta 里若有就用;缺失留空 |
| **S** | **价格趋势** | candidate_meta 里若有就用;**新字段建议格式**: "平稳(近段 $X-$Y)" / "上升(近段 $A→$B)" / "波动(近段 $X-$Y)";缺失填 "N/A" |
| **T** | **自然流量占比** | Batch Runner 结果拼接: `最新周XX.XX%;近N周均值XX.XX%;最低XX.XX%;结论:通过` |
| U | 初筛结论/备注 | 拼接: 阶段 + 结论 + 补充说明(可含 batch/周期/asinMismatch 警告) |
| V | SellerSprite页 | `=HYPERLINK("https://www.sellersprite.com/...", "SS")` 或留 ASIN 用于跳转 |

**中文品名放哪列?** — 用户没明确要求中文品名单列;当前建议:D 列产品标题保持英文(审计),**新增列 W 放中文品名**从 `zh_title_overrides.json` 读。或者把 D 列改成中文、加一列 X 存原英文标题。**你决定,但必须有中文品名字段**,不能只有英文。

如果 candidate_meta 里字段缺失(G/Q/R/S 常见),按下面 §3 处理。

## 3. 缺字段处理

- **G/Q/R/S 类"辅助字段"缺失** → 该列填 `N/A`,**不阻断合格**
- **H/L/M/N/P 类"硬规则字段"缺失** → basic_prefilter 直接 fail,进 audit
- **image 缺失** → image_embedder 尝试 fallback og:image;还失败 → image_fail 进 audit

不能因为员工 TSV 里没填 G/Q/R/S 就把合格品拒了。

## 4. 交付位置

**final workbook 输出到 batch2 run 目录**:

```
C:\Users\13045\Desktop\amazon_products\runs\<runId>\final_candidates_<runId>.xlsx
```

runId 建议格式: `batch2_run_YYYYMMDD_HHMM`(例: `batch2_run_20260710_1600`)

不要再往 `Documents\亚马逊电商选品\outputs\` 老目录写。老目录只保留存档,新流程一律在桌面 amazon_products。

## 5. 必须使用的 Claude 侧扩展脚本(用户特别提到)

按顺序:

1. **`scripts/candidate_tsv_to_json.py --dedupe-history`** — 员工侧已跑,输出 candidate_meta_batch2.json(顶层数组)
2. **`scripts/title_to_cn.py --batch <path> --merge`** — 员工侧可选;若跑了,`config/zh_title_overrides.json` 会有 batch2 asin 的中文名;若没跑,cnTitle 回落到英文
3. **`scripts/replay_existing_batch.py`** — 你自己的 pipeline 主入口
4. **`scripts/build_replay_workbooks.mjs`** — 生成 22 列 workbook(需按本报告 §2 扩展列)
5. **`scripts/acceptance_checker.py`** — 交付前必须 PASS,exit 非 0 不允许交付

## 6. build_replay_workbooks.mjs 需要扩展的列

当前 baseline final workbook 结构(从 `runs/replay_20260710_baseline/final_candidates_*.xlsx` 看)可能没有 §2 表里的所有 22 列。请扩展 `build_replay_workbooks.mjs`,补齐:

- `子体月销量 / 父体月销量`(拆开当前的 monthlySales)
- `月销售额`(price × childSales)
- `品牌 / 类目路径`
- `配送 / 重量/尺寸`(candidate_meta 有就用,没就 N/A)
- **`价格趋势`**(candidate_meta 里若有就用,没有 N/A;是新字段,建议后续在 candidate_tsv_to_json 里加一列 `priceTrend`)
- `SellerSprite页`(链接列)

如果 candidate_meta schema 需要扩展来喂这些新列,你告诉我,我在 `candidate_tsv_to_json.py` 加对应字段。

## 7. 品类路径 G 列的具体处理

Baseline 里 G 列内容如 `Home & Kitchen:Kitchen & Dining:Dining & Entertaining:Dinnerware & Serveware:Serveware`,用 `:` 分隔 5 级类目。

- 员工 TSV 目前**没有** categoryPath 列。要么:
  - **方案 A**: TSV 加一列 `categoryPath`,员工从 Amazon 详情页复制
  - **方案 B**: G 列先留 `N/A`,等 batch3 再补
- **推荐方案 B**,不阻塞 batch2

## 8. 价格趋势 S 列

Baseline 里如 `平稳(近段 13.50-15.00)`。这需要 Amazon 的历史价格数据,员工手工填负担大。

- **推荐**: S 列先固定 `N/A`,等员工侧扩展(比如 SellerSprite 详情页有历史价格弹窗,可以粘贴)
- **不阻塞 batch2**

## 9. 遇到问题的处理原则

用户明确要求"实际过程中出现问题及时修复,及时交流解决"。

**任何以下情况**你都必须停下来写一份 handoff 报告到 `handoffs/inbox_for_claude/`,不要静默兜底:

- candidate_meta 里字段和你的 §2 期望不匹配(不是缺失,是**类型或语义错**)
- Batch Runner JSON 有意料外结构
- acceptance_checker FAIL
- final workbook 图片嵌入率 < 100%(不是 image_fail 那种预期,是 xlsx 生成本身漏图)
- 用户口径和 rules.json 冲突

命名: `YYYYMMDD_HHMM_codex_to_claude_batch2_issue_<slug>.md`

## 10. 交付流程(顺序执行)

```
Step 1  员工填 candidate_meta_batch2.tsv (等待中)
Step 2  员工跑 candidate_tsv_to_json.py --dedupe-history
Step 3  员工可选跑 title_to_cn.py --batch --merge
Step 4  员工跑 Batch Runner v0.2.x,产出 batch_batch2.json
Step 5  员工通知数据组 (你)
Step 6  你跑 replay_existing_batch.py
Step 7  你跑 build_replay_workbooks.mjs (含 §2 22 列扩展)
Step 8  你跑 acceptance_checker.py
Step 9  acceptance PASS -> final_candidates_<runId>.xlsx 就位
Step 10 你把结果同步到 handoffs/inbox_for_claude/batch2_result_YYYYMMDD_HHMM.md
```

## 11. 不做的事

- ❌ 不放宽任何一条硬规则
- ❌ 不写老目录(`Documents\亚马逊电商选品\outputs\`)
- ❌ 不把 rejected 补进 final
- ❌ hard_review 不算合格
- ❌ 图片不能只放 URL,必须嵌入 xlsx workbook
- ❌ 不要生成 D 列纯中文标题却丢失英文原文(审计需要)

## 12. handoff 协议提醒

同时,请务必阅读 `handoffs/PROTOCOL.md`,以后所有对接都走 `handoffs/inbox_for_<self>/` 目录,不再往 amazon_products 根目录写 CLAUDE_*.md。回执本报告到 `handoffs/inbox_for_claude/`。

---

## 附: 员工侧现状

- `runs/new_20260710_batch2/candidate_meta_batch2.tsv` 员工正在填(目前只有骨架行,员工没交)
- `keyword_seeds.md` 70 个种子已就位
- `OPERATOR_CHECKLIST.md` 有 Step 1-5 + Step 3.5 中文名生成
- 一旦员工 TSV 就绪 + Batch Runner 跑完,你就能开工

用户希望这条链**一路自动跑到 acceptance PASS**,中间只有员工填 TSV 一步是人肉。你按 §5 顺序把 5 个脚本串起来即可。
