# Tier 2.1 / 2.2 流量读取与条件重试

## 硬约束

本次只修正明确零值解析并减少无效重试，不调整任何 A-F 硬门槛。

- 验收层仍是唯一放行依据。
- `0%` 推导只能产生拒绝，不能产生通过。
- `--`、缺失、歧义和 `0/0` 保持缺失并按未通过处理。
- 重试不能改变门槛，只能重新读取明确未就绪的页面。
- 0.4.5/0.3.6 保留为可执行回退版本。

## 版本与开关

### Collector 0.4.6

- 文件：`scripts/sellersprite_traffic_collector_v0.4.6.user.js`
- 开关：`ENABLE_TIER2_1_ZERO_SHARE_DERIVATION`
- 读取器版本：`tier2.1-zero-share-v1`

仅当以下条件同时满足时，将自然流量占比推导为 `0%`：

1. `totalTraffic` 的当前值被明确解析为大于 `0`；
2. `naturalTraffic` 的当前值是字面数字 `0`；
3. SellerSprite 未提供可解析的自然流量占比。

推导行增加：

- `naturalShareDerived=true`
- `naturalShareSource=derived_explicit_zero_over_positive_total`
- `tier2ReaderVersion=tier2.1-zero-share-v1`

该 `0%` 是有效已读周，计入 `weeksRead`，并立即触发低于 70% 的 C 关拒绝。

以下情况不得推导：

- 自然流量为 `--`；
- 当前值缺失或格式歧义；
- `totalTraffic == 0`，即 `0/0`；
- 只在变化量或百分比中出现数字 `0`。

关闭开关后恢复 0.4.5 的解析输出；完整回退可直接重新启用 0.4.5。

### Integrated Runner 0.3.7

- 文件：`scripts/sellersprite_integrated_runner_v0.3.7.user.js`
- 开关：`ENABLE_TIER2_2_CONDITIONAL_RETRY`
- 重试版本：`tier2.2-conditional-retry-v1`
- 重试上限：仍为 `1`

默认只对下列明确未就绪状态重试：

- `status=no_chart_loaded`：`chart_not_ready`
- `status=no_data` 且没有任何 tooltip detail：`tooltip_not_ready`
- Collector 明确输出 `retryable=true` 的未来兼容信号

以下情况不重试，直接保持未通过：

- 已读到任一低于 70% 的真实流量值；
- 已取得部分有效周，但周数仍不足；
- Collector 普通异常或无法证明是“未加载完”的残缺数据；
- `--`、歧义或其他缺失读数。

Timing TSV 增加 `retryDecision` 和 `retryReason`。关闭开关后恢复 0.3.6 的旧重试条件；完整回退可重新启用 0.3.6。

## Fixture 与自动测试

真实 tooltip fixture：

- `tests/fixtures/sellersprite_tier2_tooltips.json`
- 第 23 周：正总流量 + 明确自然流量 `0` + 占比缺失
- 第 24 周：自然流量 `--`
- 第 25 周：正数自然流量 + 明确占比
- 第 26 周：总流量 `0` + 自然流量 `0`，不得推导

测试：

- `tests/test_sellersprite_traffic_collector_v046.mjs`
- `tests/test_sellersprite_integrated_runner_v037.mjs`

## 真实 ASIN 配对验证

验证脚本：

```powershell
node scripts/validate_tier2_pairing.mjs `
  runs/new_20260710_batch2/batch_batch2.json `
  runs/tier2_pair_validation_20260713 `
  60
```

同一份真实 SellerSprite `rawText` 同时进入 0.4.5 和 0.4.6，随后分别由 Runner 0.3.6 和 0.3.7 执行 C 关判断，避免页面加载和鼠标悬停波动污染对比。

结果：

- 真实 ASIN：60
- C 关结果完全一致：60/60
- 假阳性：0
- 非预期字段差异：0
- 明确零值推导周：10
- 旧重试：2
- 新重试：0

证据：

- `runs/tier2_pair_validation_20260713/pair_validation_summary.json`
- `runs/tier2_pair_validation_20260713/pair_validation_report.md`

## 部署与回退

部署时同一时间只能启用一个 Collector 和一个 Runner：

1. 停用 0.4.5，启用 0.4.6。
2. 停用 0.3.6，启用 0.3.7。
3. 刷新 Amazon 商品页，确认面板版本唯一。
4. 先跑小批 smoke，再开始正式批次。

Tier 2 完整回退：停用 0.4.6/0.3.7，重新启用 0.4.5/0.3.6。历史批次和 `ssIntegratedRunner:v0.3:*` 数据无需删除。
