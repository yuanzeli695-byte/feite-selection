# Tier 0 观测埋点

## 范围与硬约束

本次只增加观测能力，不调整、替代或提前放行任何 A-F 硬门槛。

- 验收层仍是唯一放行依据。
- 缓存和历史命中只允许记为 `skip`，不得记为 `pass`。
- `status != ok`、周数不足、图表未加载、超时和异常都记录为 `reject`。
- 未采集的读数保持空值，并附带 `*Reason`，不得估算。
- A、B、F 不由 Collector/Runner 完整评估，日志明确写为 `not_evaluated_*`，不得冒充通过。

## 实际文件与版本

Tier 0 新版本：

- `scripts/sellersprite_traffic_collector_v0.4.5.user.js`
- `scripts/sellersprite_integrated_runner_v0.3.6.user.js`

可执行回退基线：

- `scripts/sellersprite_traffic_collector_v0.4.4.user.js`
- `scripts/sellersprite_integrated_runner_v0.3.5.user.js`

目标代码库中原先引用的 `scripts/sellersprite_traffic_collector_v0.4.3.user.js` 已不存在。Collector 的真实现行源文件位于：

`C:\Users\13045\Documents\github仓库建设\scripts\sellersprite-traffic-collector.user.js`

该文件版本为 0.4.4；复制到本代码库后的 SHA-256 与源文件一致：

`6DC00A5A734805811C60BE127E1C2BC25665B012ABA6988C432FBEB6533971C2`

报告中未写全的文件定位结果：

- “出表脚本”实际是 `scripts/build_replay_workbooks.mjs`。
- 代码库内不存在单一“上游查询模板”文件。`scripts/prepare_strict_candidate_pool.py` 的实际输入契约是 `--input-dir` 下的 `query_*.json`；现有样例位于 `runs/strict20_integrated_20260711_1930/source_queries/` 和 `runs/strict20_20260711_0215/candidate_inputs/`。Tier 1 开始前需基于该真实契约确定要前推到哪个查询生成端。

## Feature flag

两个新脚本都包含：

```javascript
var ENABLE_TIER0_TELEMETRY = true;
```

设置为 `false` 后不向结果附加 `telemetry`、不向批次导出增加日志表，也不显示 TSV 日志按钮。完整回退可直接停用 0.4.5/0.3.6 并重新启用 0.4.4/0.3.5。

## 日志输出

Collector 0.4.5：

- `Copy Gate TSV`：导出当前 ASIN 的 C 关结果与真实读数。
- `Copy Timing TSV`：导出图表等待、tooltip 扫描和总耗时。
- JSON 的 `telemetry.gate`、`telemetry.timing` 保存同一份结构化数据。

Runner 0.3.6：

- `Copy gate log TSV`：导出整批 `pass/reject/skip`、短路关卡和 C/D/E 读数。
- `Copy timing log TSV`：导出详情页、流量图、尺寸、价格图和重试次数。
- Combined JSON 的 `telemetry.gateRows`、`telemetry.timingRows` 保存两张表。
- 历史严格合格 ASIN 只记录为 `skip`，各关为 `not_run_history_skip`，不计入本批合格数。

## 验证

Tier 0 是纯观测改动，不属于要求 30 条真实 ASIN 对拍的 B/C 类读取器、缓存或并行改造。本次使用旧版和新版核心函数的同输入对照：

- Collector 0.4.4 与 0.4.5 的流量短路函数逐字一致，最近 4 周与至少 3 周常量一致。
- Runner 0.3.5 与 0.3.6 的流量、尺寸、价格和最终合格判定函数逐字一致。
- 覆盖 70% 边界、周数不足、读数缺失、价格上下界、趋势不允许、历史跳过和 flag 关闭场景。
- `node tests/test_sellersprite_traffic_collector_v045.mjs`
- `node tests/test_sellersprite_integrated_runner_v036.mjs`

Tier 2、Tier 3、Tier 4 的 B/C 类改动仍必须先完成同批至少 30 条 ASIN 的新旧路径对拍，判定 100% 一致后才能合并。

## 回退

1. 在 ScriptCat 停用 Collector 0.4.5 和 Runner 0.3.6。
2. 重新启用 Collector 0.4.4 和 Runner 0.3.5。
3. 或在新脚本中将 `ENABLE_TIER0_TELEMETRY` 改为 `false` 后重新保存。
4. 同一时间只启用一个 Collector 和一个 Integrated Runner，避免重复面板和重复导航。
