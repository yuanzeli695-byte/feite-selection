# 严格合格目标选品流程

## 目标语义

`targetN` 表示最终严格合格商品数量，不表示候选队列长度或已采集数量。

只有同时通过禁限售、商业指标、自然流量、重量/尺寸、价格趋势和图片要求的商品，才能进入 `final_candidates_data.json` 和最终工作簿。

自然流量要求：

- `status == ok`
- `asinMismatch != true`
- `weeksRead >= 3`
- `latestNaturalSharePct >= 70`
- `recent4AvgNaturalSharePct >= 70`
- `recent4MinNaturalSharePct >= 70`

## 候选准备

1. 正式运行时，`prepare_strict_candidate_pool.py` 通过 `--source-manifest` 绑定并验证每个 `query_*.json`：采集时间不超过 24 小时、美国站、非空类目节点、`maxReviews<=100`、查询 URL 和文件 SHA-256。旧的无清单输入只允许显式 `--allow-legacy-source` 回退。
2. 程序先聚合同一 ASIN 的互补证据；任何非空产品事实冲突都以 `duplicate_conflict` 淘汰。随后排除历史/已尝试 ASIN，并按禁限售硬排除、价格、子体销量、评论、评分、上架天数、变体数和图片 URL逐项检查；缺少 `childSales` 不得用父体销量替代。
3. 默认使用 `tier1.2-probability-v2` 对已经通过硬筛的候选做纯排序：按上架天数、月销量、评论、变体、评分和预筛警告计算可审计分数，28-90 天获得最高年龄分，同分候选按品牌轮转；随后继续执行原有来源/品牌上限。该分数不能放行或淘汰候选。`--use-ranking-v1` 回退到原 28-80 天评分，`--disable-tier1-2-ranking` 恢复更早的顺序。
4. `download_candidate_images.py` 在流量采集前缓存并转换主图；图片失败记录必须修复或淘汰。

Chrome 中的 Collector 0.4.6 和 Batch Runner 0.2.x 不承担最终过滤。默认快速路径使用 `sellersprite_integrated_runner_v0.3.7.user.js`：它复用 Collector，按 ASIN 一致性、流量、尺寸、价格趋势顺序短路采集，并输出合并批次 JSON。Collector 最多读取最近4周；正总流量且字面自然流量为0时推导0%，该周作为有效已读周并立即触发拒绝。Runner 只对图表或 tooltip 明确未就绪状态重试一次。Tier 0 日志只做观测，不参与放行；0.4.5/0.3.6 和旧版 Batch Runner 保留为回退。

Integrated Runner 的 `targetQualified` 是最终合格目标，不是队列长度。候补队列可大于目标数，但达到目标后必须立即以 `stoppedReason=target_reached` 停止；流量、尺寸或价格趋势失败的 ASIN 不得继续进入后续步骤。

重量/尺寸与价格趋势要求：

- `dimensions` 必须非空。
- `priceTrend` 和 `priceTrendClass` 必须非空。
- `priceTrendClass` 只允许 `stable` 或 `rising`；`declining`、`volatile`、`no_data` 直接淘汰。
- Integrated Runner 0.3.7 的尺寸与价格趋势字段直接写入每条 batch result；旧批次或人工修正仍可通过 `--enrichment-json` 按 ASIN 合并。
- 缺项不得写成 `N/A` 后继续交付。

## 多批累计

`replay_existing_batch.py` 支持重复传入配对参数：

```powershell
python scripts\replay_existing_batch.py `
  --batch-json runs\batch_a\batch.json `
  --candidates-json runs\batch_a\candidates.json `
  --batch-json runs\batch_b\batch.json `
  --candidates-json runs\batch_b\candidates.json `
  --image-dir runs\target_run\source_images `
  --run-id target_run `
  --target 20 `
  --overwrite
```

每个 `--batch-json` 必须与紧邻的 `--candidates-json` 对应。重复 ASIN 只处理第一次。

Integrated Runner 合并 JSON 不需要 `--enrichment-json`。如果同时提供外部 enrichment 文件，外部值优先，便于人工修正。

如果合格数不足目标，继续追加新的 batch/candidates 参数并重跑同一 run。最终数据由所有批次重新回放产生，避免增量覆盖或状态漂移。

## 工作簿

- `final_candidates_<runId>.xlsx` 只读取 `final_candidates_data.json`。
- `rejected_audit_<runId>.xlsx` 保存淘汰、复核和超出目标的审计记录。
- 最终表中 `主图` 位于 `ASIN` 右侧，图片必须嵌入工作簿。
- 用户可见字段使用中文，同时保留英文标题、来源 URL 和批次审计字段。

## 验收

`acceptance_checker.py` 默认要求：

- `qualifiedCount == targetN`
- 最终 ASIN 唯一且不出现在 rejected audit
- 每个最终商品通过全部自然流量要求
- 每个最终商品都有重量/尺寸，且价格趋势为稳定或上升
- 图片文件、XLSX media 和 picture shape 数量均等于最终商品数量
- 最终工作簿包含全部最终 ASIN，不包含 rejected ASIN
- 公式错误扫描为零

达到最大尝试数或候选源耗尽只表示运行结束，不表示交付完成。目标不足时验收退出码为非零，禁止标记为最终交付。
