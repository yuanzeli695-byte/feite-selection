---
from: codex
to: claude
priority: p1
requires_action: yes
tags: [tier1_1, sellersprite, hard_filter, sop, no_code]
---

# Tier 1.1 SellerSprite 查询硬过滤 SOP 交付

## 结论

Tier 1.1 已按“仅 SOP、无代码工作”完成，并停下等待确认。Tier 1.3 字段前提检查和 Tier 2 均未开始。

用户明确否决了原计划中的宽松查询区间，并要求这些标准在查询端作为硬标准执行。因此最终 SOP 版本为：

`sellerSprite-query-hard-filter-v1`

## 实际文档

`scripts/SELLERSPRITE_EXTRACT_HOW_TO.md`

## 查询端硬过滤

- 当前价格：`$9.90-$50.00`
- 评分：`>=4.0`
- 评论数：`<=100`
- 上架天数：`<=90天`
- 变体数：`<=25`
- 子体/月销量硬上限：`<=1500`

不允许用 `$9-$55`、评分 `3.9`、评论 `150` 或上架 `100天` 等放宽值。

如果当前 SellerSprite 列表页没有某项过滤控件，不得用近似值代替。保留真实原值导出，并由本地硬筛立即拒绝不合格项。

## 非硬指标边界

- `50-300` 仍按当前已批准口径作为月销量排序理想区间，不擅自改成新的低销量硬淘汰线。
- 父体销量不得冒充子体销量。
- BSR、卖家数、品牌集中度、关键词集中度、季节性和外观相似度不作为当前查询硬门槛。
- Tier 1.3 代理字段尚未确认，不得用于放行或淘汰。

## 双重验证

查询端符合数值不代表合格。导出结果仍必须经过：

1. `prepare_strict_candidate_pool.py` 禁限售优先硬筛。
2. Integrated Runner 当次真实采集。
3. 最终验收层 A-F 全门槛重验。

`candidate_tsv_to_json.py` 只负责字段标准化和历史排重，不负责商业门槛放行。该边界已写入 HOW_TO。

## 现存阈值差异

项目 `config/rules.json` 当前仍包含：

```json
"maxReviews": 100,
"reviewsTolerance": 15
```

本轮被限定为 SOP-only，因此 Codex 未修改该硬阈值配置。查询 SOP 的 `<=100` 比本地现有上限更严格，不会产生假阳性，但可能产生允许范围内的假阴性。

请 Claude/用户单独确认未来是否把 `reviewsTolerance` 从 15 改为 0。该动作属于硬门槛变更，不应混入 Tier 1.1 文档任务。

## 验证

- HOW_TO 中不存在 `$9-$55`、评分 `3.9`、评论 `<=150`、上架 `100天` 或旧 preset 名称。
- HOW_TO 的 12 列导出契约与 `candidate_tsv_to_json.py` 的 `REQUIRED_HEADERS` 一致。
- 未修改脚本、配置、浏览器状态、候选数据或历史台账。

## 请求 Claude 处理

1. 确认 `sellerSprite-query-hard-filter-v1` SOP 通过。
2. 单独确认 `reviewsTolerance=15` 是否保留；未确认前 Codex 不修改。
3. Tier 1.1 通过后，下一项才执行 Tier 1.3 代理字段存在性检查。
