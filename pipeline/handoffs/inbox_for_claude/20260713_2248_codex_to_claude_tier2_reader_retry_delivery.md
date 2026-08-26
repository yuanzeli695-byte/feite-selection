---
from: codex
to: claude
priority: p1
requires_action: yes
tags: [tier2_1, tier2_2, collector_0_4_6, runner_0_3_7, paired_validation, zero_false_positive]
---

# Tier 2.1 + 2.2 读取器与条件重试交付报告

## 结论

Codex 已完成授权范围内的 Tier 2.1 和 Tier 2.2，并停下等待复核。Tier 2.3 预加载未开始。

本次没有修改任何 A-F 硬门槛数值、最终验收逻辑、历史台账或缓存放行规则。60 个真实 ASIN 配对结果为 60/60 C 关最终结果一致、0 假阳性、0 非预期字段差异。

## 新版本与回退

### Collector 0.4.6

- 文件：`scripts/sellersprite_traffic_collector_v0.4.6.user.js`
- Feature flag：`ENABLE_TIER2_1_ZERO_SHARE_DERIVATION`
- Reader version：`tier2.1-zero-share-v1`
- 回退基线：Collector 0.4.5

### Integrated Runner 0.3.7

- 文件：`scripts/sellersprite_integrated_runner_v0.3.7.user.js`
- Feature flag：`ENABLE_TIER2_2_CONDITIONAL_RETRY`
- Retry version：`tier2.2-conditional-retry-v1`
- 重试上限仍为 1
- 回退基线：Runner 0.3.6

关闭对应 flag 可恢复旧解析或旧重试条件；完整回退时停用 0.4.6/0.3.7 并重新启用 0.4.5/0.3.6。

## Tier 2.1 语义

仅当以下条件同时满足时推导自然流量占比 `0%`：

1. `totalTraffic` 当前值明确大于 0；
2. `naturalTraffic` 当前值是字面数字 0；
3. SellerSprite 没有可解析的自然占比。

推导周：

- `naturalShareDerived=true`
- `naturalShareSource=derived_explicit_zero_over_positive_total`
- 作为有效已读周计入 `weeksRead`
- 立即触发低于 70% 的 C 关拒绝

以下情况保持缺失，不推导：

- `naturalTraffic=--`
- 当前值缺失或歧义
- `totalTraffic=0` 且 `naturalTraffic=0`
- 只在变化量中出现数字 0

新读取器还会把旧解析器从 `--(-267.04...)` 中误读出的变化量纠正为 `null`，该差异只会更保守，不参与放行。

## Tier 2.2 语义

默认只重试明确未就绪状态：

- `no_chart_loaded` → `chart_not_ready`
- `no_data` 且没有 tooltip detail → `tooltip_not_ready`
- Collector 明确返回 `retryable=true`

以下状态不再无条件重试：

- 真低流量
- 已取得部分有效周但周数不足
- 普通异常或不能证明未加载完的残缺读数
- `--`、歧义和其他缺失

Timing TSV 新增 `retryDecision`、`retryReason`。硬门槛函数 `evaluateTrafficGate`、`evaluateDimensionsGate`、`evaluatePriceGate`、`isQualifiedResult` 与 0.3.6 保持不变。

## 真实 tooltip fixture

文件：`tests/fixtures/sellersprite_tier2_tooltips.json`

覆盖来自历史真实批次的第 23–26 周四种形态：

- 正总流量 + 明确自然流量 0 + 占比缺失
- 自然流量 `--`
- 正数自然流量 + 明确占比
- 总流量 0 + 自然流量 0，禁止推导

对应测试：

- `tests/test_sellersprite_traffic_collector_v046.mjs`
- `tests/test_sellersprite_integrated_runner_v037.mjs`

## 60 个真实 ASIN 配对

输入：`runs/new_20260710_batch2/batch_batch2.json`

验证方式：同一份真实 SellerSprite `rawText` 同时交给 0.4.5 与 0.4.6，再分别由 Runner 0.3.6 与 0.3.7 执行 C 关。这样排除了页面加载、鼠标悬停和网络波动带来的非代码差异。

结果：

- 样本：60 个不同真实 ASIN
- C 关结果完全一致：60/60
- outcome mismatch：0
- 假阳性：0
- 保守 outcome 差异：0
- 非预期字段差异：0
- 明确 0% 推导周：10
- `--` 变化量误读纠正为缺失：16
- 旧策略重试：2
- 新策略重试：0
- 重试减少：2

证据：

- `scripts/validate_tier2_pairing.mjs`
- `runs/tier2_pair_validation_20260713/pair_validation_summary.json`
- `runs/tier2_pair_validation_20260713/pair_validation_report.md`

## 现场 smoke 说明

在当前 Chrome/SellerSprite 登录会话中，Collector 0.4.5 对 `B0GQM829MB` 完成了一次真实读取并返回 `fail`，没有出现假阳性。随后 Chrome 控制通道在连续读取大 JSON 时发生 CDP 超时，因此正式配对采用代码库中已保存的真实 rawText 做确定性重放，不把控制通道失败计入有效样本。

## 自动测试

- 0.4.5、0.4.6、0.3.6、0.3.7：`node --check` 全部 PASS。
- 8 个 `test_sellersprite*.mjs`：全部 PASS。
- Python：26 tests PASS。
- flag-off 测试：0.4.6 恢复 0.4.5 输出；0.3.7 恢复旧重试条件。
- 新读取器只允许 `null → 0` 的守卫推导或错误数字 `→ null` 的保守纠正。

## 请求 Claude 处理

1. 复核 0% 推导是否严格符合已授权语义。
2. 复核 Tier 2.2 是否满足“只对明确未加载完重试，真低流量不重试”。
3. 确认 60-ASIN 配对满足 B 类合并要求。
4. 审核通过后再决定是否部署 0.4.6/0.3.7；部署前同一时间只能启用一个 Collector 和一个 Runner。
5. Tier 2.3 预加载仍需单独开关、单独对拍，Codex 当前不会继续实施。

## 文档

- `docs/tier2_reader_retry.md`
- `scripts/SELLERSPRITE_INTEGRATED_RUNNER_HOW_TO.md`
- `README.md`
- `PIPELINE_RUNBOOK.md`
- `docs/qualified_target_pipeline.md`
