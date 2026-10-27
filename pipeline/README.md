# amazon_products — Amazon US 选品长期工作目录

**位置**: `C:\Users\13045\Desktop\amazon_products\`

## 目录约定

- 每张主表:`amazon_products_YYYYMMDD_HHMM.xlsx`
  - 同一天多次跑 → 每次生成新的时分命名
  - Sheet 名保持 `候选20品`,表头在第 3 行,数据从第 4 行起
- 滚动备份:`amazon_products.backup_latest.xlsx`
  - 只保留一份,每次写入前覆盖
  - 万一写崩,把这份 rename 回主表名即可
- 每次爬取的原始 JSON 也丢进本目录,便于溯源:
  - `batch_1_20_YYYYMMDD_HHMM.json`
  - `retry_timeout_YYYYMMDD_HHMM.json`

## 写入器 apply_traffic_batch.py

三种用法:

```bash
# 1. 当天第一次:从旧的候选表新建今天的主表并写流量
python apply_traffic_batch.py batch_1_20.json --new-from source.xlsx

# 2. 补写(自动挑当天最新一份主表)
python apply_traffic_batch.py retry_timeout.json

# 3. 指定要改的主表
python apply_traffic_batch.py partial.json --workbook amazon_products_20260709_1500.xlsx
```

## 硬规则

- 只改 T 列(自然流量占比)和 U 列尾巴(初筛结论/备注),别的列不动
- 目标商品页不可达 → T 写"目标商品页不可达,建议剔除或核对 ASIN"
- 采集超时 → T 写"流量采集超时,需重取"
- ASIN 变体重定向 → U 列追加"采集页面为变体 XXX,需人工核对"
- 阈值:自然流量占比 ≥ 70% 为通过
- 采集窗口:最近 2 个月 / 最多 9 周

## 归档

历史主表可以留在本目录里,通过日期就能追溯。定期把 30 天前的 xlsx + json 手工搬到 `archive/` 子目录。

## 新闭环 pipeline

Claude 框架已落地到本目录:

- `config/rules.json`: 价格、评分、评论、上架天数、变体数、自然流量阈值。
- `config/exclusions.json`: 禁限售/IP/健康化学等硬排词库,以及仅备注的复核词库。
- `scripts/prepare_strict_candidate_pool.py`: 正式运行要求 `--source-manifest`，先验证 24 小时新鲜度、美国站、类目节点、`maxReviews<=100`、文件 SHA-256 和逐行来源字段，再执行历史去重、禁限售优先的逐项硬筛。默认启用 `tier1.1-a-source-prefilter-v2`，仅用已有真实候选证据支持的精确短语，把明确的角色/IP 风险、电器和化学耗材在进入 Chrome 前下行剔除；summary 记录命中数和规则，`--disable-a-source-prefilter-v2` 可恢复旧候选集合。重复 ASIN 会合并互补证据，冲突证据以 `duplicate_conflict` 淘汰。默认 `tier1.2-probability-v2` 先确定候选集合；集合确定后，`p1-safe-queue-reorder-v1` 仅重排最终队列：同分时未来年份 planner/calendar 后置，再按上架天数降序和原排名稳定排序。`--disable-post-selection-reorder` 可立即恢复原队列顺序；上述优化都不能授予 A-F 合格。
- `scripts/strict_history.py`: 扫描所有已交付的 `qualified_pool.json` 与 `final_candidates_data.json`，回填并维护统一排重台账 `history/strict_qualified_asins.json`。
- `scripts/candidate_tsv_to_json.py`: 转换 TSV 时默认强制跳过历史严格合格 ASIN，不再需要额外开启 `--dedupe-history`。
- `scripts/download_candidate_images.py`: 在进入 Batch Runner 前下载并转存候选主图，缺图候选不得进入最终交付。
- `scripts/sellersprite_traffic_collector_v0.4.6.user.js`: ScriptCat 流量采集脚本，只读取最近4周；正总流量且字面自然流量为0时保守推导0%，已读周自然流量低于70%即提前返回失败，并可导出 Tier 0 门槛/耗时日志。0.4.5 保留为 Tier 2 回退基线。
- `scripts/replay_existing_batch.py`: 用已有 SellerSprite batch JSON 回放硬过滤,产出 `state.jsonl`、`qualified_pool.json`、`rejected.jsonl`。
- `scripts/sellersprite_integrated_runner_v0.3.7.user.js`: ScriptCat 短路批处理脚本；只对图表/tooltip 明确未就绪状态重试一次，真低流量和普通残缺样本不重试。历史跳过只记为 `skip`，不计入合格数；可导出 Tier 0 门槛/耗时日志。0.3.6 保留为 Tier 2 回退基线。
- `scripts/sellersprite_traffic_collector_v0.4.6_zh_p1.user.js` + `scripts/sellersprite_integrated_runner_v0.3.8.2_zh_excel.user.js`: 加法式中文/Excel 候选 `0.4.6.2/0.3.8.2`。它继承已 smoke 的 P1 剩余目标、行内停止和细粒度遥测，并增加存储配额失败闭环和卖家精灵登录/套餐权限熔断；仍需安装后的单 ASIN 与真实 Excel smoke，不能替代 canonical `0.4.6.4/0.3.8.13` 预检登记。
- `scripts/sellersprite_integrated_runner_v0.3.8.3_zh_excel_p2_candidate.user.js`: 仅用于验证流量标签暂态恢复的 Class B 候选。它增加 2 秒严格文本就绪宽限和最多一次原行重载，但在 30-ASIN 配对、至少 3 个真实恢复和 live smoke 通过前不得替换 `0.3.8.2`，Excel 桥接版本契约也保持不变。
- `scripts/build_replay_workbooks.mjs`: 从合格池和剔除审计数据生成两张表。
- `scripts/acceptance_checker.py`: 验证 final 表里没有不合格品,且图片已嵌入。
- `docs/qualified_target_pipeline.md`: 定义 targetN 为最终合格数量，并说明多批累计与严格验收流程。
- `docs/tier0_observability.md`: 记录埋点字段、feature flag、真实文件定位、验证证据和回退步骤。
- `docs/tier2_reader_retry.md`: 记录明确零值推导、条件重试、60 个真实 ASIN 配对结果和部署回退步骤。
- `docs/p1_target_control_and_granular_telemetry.md`: 记录 Runner 0.3.8 累计剩余目标、在途停止、细粒度旁路遥测和实机 smoke 证据。
- `docs/p2_collector_deadline_protocol.md`: 记录尚未部署的 0.4.7/0.3.9 Collector 单一截止时间候选、timeout/error 分区配对语义、沙盒 history、恢复复核和回退边界。
- `docs/p2_traffic_tab_recovery_candidate.md`: 记录未部署的 Runner 0.3.8.3 流量标签暂态恢复、人工暂停保护、细粒度计时和真实配对门槛。
- `docs/strict_candidate_source_contract_v1.md`: 记录正式 SellerSprite 来源清单、查询范围、哈希和重复证据契约。
- `docs/selection_zh_excel_guide.md`: 记录中文 P1 候选、存储保护与一键 Excel 操作。
- `docs/merged_json_to_excel_cli.md`: 记录把 Runner 合并 JSON 自动配对候选、受控并发/短期缓存主图并快速生成验收 Excel 的独立入口和回退参数。

当前项目流量阈值按更严格口径执行: `latestNaturalSharePct >= 70`、`recent4AvgNaturalSharePct >= 70`、`recent4MinNaturalSharePct >= 70`、`weeksRead >= 3`。不合格商品只进 audit,不进 final。

当前验收口径要求 `qualifiedCount == targetN`。候选源耗尽或达到最大尝试数不再等同于交付完成；不足目标时必须继续补充候选，或明确以未完成状态结束。

历史严格合格品排重为强制规则：任何出现在 `history/strict_qualified_asins.json`、旧 `qualified_pool.json` 或旧 `final_candidates_data.json` 中的 ASIN，下一次会被标记为 `dedupe_history` 并直接跳过；它不会进入 Chrome Runner 的采集队列、不会计入 `Qualified`，也不会再次写入最终主表。可用以下命令在迁移或人工交付后回填台账：

```powershell
python scripts\strict_history.py --write
```

已完成 baseline:

- `runs/replay_20260710_baseline/final_candidates_replay_20260710_baseline.xlsx`: 5 个全合格品。
- `runs/replay_20260710_baseline/rejected_audit_replay_20260710_baseline.xlsx`: 19 条剔除审计。
- `runs/replay_20260710_baseline/acceptance_report.md`: 全部验收项 PASS。
