# Tier 1.2 通过概率排序

## 边界

Tier 1.2 只重新排列已经通过现有硬筛的候选，不新增、删除、放行或淘汰任何 ASIN。

- 硬排除、价格、评分、评论、上架天数、变体、销量硬上限等判断仍由原有预筛执行。
- 自然流量、尺寸、价格趋势和图片仍由原有浏览器采集及验收层判断。
- 排名分数不能作为最终合格证据。
- `probability_rank_candidates` 会校验排序前后的 ASIN 数量和 multiset 完全一致，否则直接报错。

## 版本与开关

- Feature constant：`ENABLE_TIER1_2_PRIORITY_RANKING = True`
- Ranking version：`tier1.2-probability-v2`
- 默认启用新排序。
- 排序版本回退：增加 `--use-ranking-v1`，恢复 v1 的 28-80 天最高年龄分。
- 完整排序回退：增加 `--disable-tier1-2-ranking`，恢复 Tier 1.2 前的 `priority_score` 顺序和输出结构。

## 排名权重

下列分档只影响顺序，不是硬门槛：

| 字段 | 排名分值 |
|---|---|
| 上架天数 | v2：28-90 天 +4；其他已知天数 +2；缺失 +0。v1 回退：28-80 天 +4。 |
| 子体/月销量 | 位于配置的理想区间 +5；其他已知值 +2；缺失 +0 |
| 评论数 | <=30 +4；<=60 +3；其他已知值 +1；缺失 +0 |
| 变体数 | <=5 +4；<=10 +3；其他已知值 +1；缺失 +0 |
| 评分 | >=4.5 +2；其他已知值 +1；缺失 +0 |
| 预筛警告 | 每条 -1 |

评分降序后，同分候选按品牌轮转。品牌轮转后使用评分、评论数、变体数、距离理想销量区间的距离和 ASIN 做确定性排序。

原有 `max-per-source`、`max-per-brand` 和同变体去重仍在队列选择阶段执行，本次没有修改这些规则。

## 审计字段

启用 Tier 1.2 时，每条已接受候选增加：

- `rankingVersion`
- `rankingScore`
- `rankingComponents`
- `rankingPosition`

批次 summary 增加：

- `ranking.enabled`
- `ranking.version`
- `ranking.invariant`
- `ranking.orderedCandidateCount`
- `ranking.scoreHistogram`
- `ranking.selected`

使用 `--use-ranking-v1` 时仍输出排名审计字段并标记 v1；使用 `--disable-tier1-2-ranking` 时不输出这些新增字段，保持旧排序路径。

## 与 Runner 的关系

候选按更高通过概率排在队列前部；Integrated Runner 仍按原规则逐关验证，并在达到 `targetQualified` 后停止。排序不能替代 Runner 或验收层的任何门槛。

## P1 选定队列后的安全重排

`p1-safe-queue-reorder-v1` 在来源上限、品牌上限、同变体去重和 `queue-size` 已经确定最终候选集合后执行，因此不能改变哪些 ASIN 进入队列。

同一 `rankingScore` 内按以下顺序排列：

1. 非未来年份 planner/calendar；
2. `launchAgeDays` 降序；
3. 原 `rankingPosition`，保证同年龄项稳定。

该层默认启用，可用 `--disable-post-selection-reorder` 回退到原队列顺序。每条重排记录增加 `preQueuePosition`、`queuePosition`、`queueReorderVersion` 和 `futureYearPlannerDemoted`。summary 的 `queueReorder` 同时保存前后顺序 SHA-256 以及排序无关的 multiset SHA-256；只有 multiset SHA-256 前后相等才满足纯重排证明。

## 验证证据

- `runs/tier1_2_validation_20260713/validation_summary.json`
- `runs/tier1_2_validation_20260713/validation_report.md`
- `runs/tier1_2_validation_20260713/probability/`
- `runs/tier1_2_validation_20260713/legacy/`
- `runs/p1_safe_queue_reorder_validation_20260728/validation_summary.json`
- `runs/p1_safe_queue_reorder_validation_20260728/validation_report.md`
