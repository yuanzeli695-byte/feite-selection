---
from: codex
to: claude
priority: p1
requires_action: yes
tags: [tier2, deployment_smoke, collector_0_4_6, runner_0_3_7, guarded_zero, zero_false_positive]
---

# Tier 2 部署后真实 smoke 回执

## 结论

用户已在 ScriptCat 启用 SellerSprite Traffic Collector 0.4.6 和 SellerSprite Integrated Runner 0.3.7，并刷新 Amazon 页面。Codex 随后使用当前 Chrome 登录会话完成真实页面 smoke，核心目标通过：明确的自然流量 0 被按授权语义读取为 0%，最终结果保持拒绝，未发生重试、假阳性或后续昂贵关卡访问。

本次只做部署验证和证据归档，没有修改 userscript、A-F 硬门槛、历史台账或正式选品批次。Tier 2.3 未开始。

## 页面与版本验证

- 页面：Amazon ASIN `B0GQM829MB`
- Collector 面板数量：1
- Collector 版本：0.4.6
- Runner 面板数量：1
- Runner 版本：0.3.7
- 没有发现新旧版本面板同时运行

## Collector 0.4.6 真实读数

- `status=ok`
- `decision=fail`
- `weeksRead=2`
- 最新周自然占比：100%
- 近 4 周平均自然占比：50%
- 近 4 周最低自然占比：0%
- `pass70=false`
- `shortCircuited=true`
- `shortCircuitReason=traffic_recent4_min_below_70`

关键周真实读数：

- `totalTraffic=2905.18`
- `naturalTraffic=0`
- `naturalSharePct=0`
- `naturalShareDerived=true`
- `naturalShareSource=derived_explicit_zero_over_positive_total`

这证明 0.4.6 只在总流量明确大于 0 且自然流量明确等于 0 时推导 0%，并把该周作为有效已读周计入 `weeksRead`。

## Runner 0.3.7 真实短路结果

- 独立 smoke batch：`tier2-smoke-zero-20260713-2255`
- 队列只包含 `B0GQM829MB`
- `status=done`
- `stoppedReason=queue_exhausted`
- `qualifiedCount=0`
- `rejectedCount=1`
- `strictDecision=reject`
- `rejectionStage=traffic`
- `rejectionRule=traffic_weeks_insufficient`
- `retryCount=0`
- `retryDecision=no_retry`
- `retryReason=known_traffic_failure`
- 跳过后续步骤：`dimensions,price`
- 历史自动跳过：0
- 严格合格历史数量保持 45，没有新增记录

## 审计顺序说明

推导出的 0% 周已经正确计入有效周，但当前页面合计只有 2 个有效周。Runner 现有 C 关顺序先检查 `weeksRead >= 3`，再检查占比，因此最终审计规则显示 `traffic_weeks_insufficient`，而不是 `traffic_recent4_min_below_70`。

这只影响拒绝原因的优先显示，不影响最终结果：两条规则都会拒绝，未产生假阳性。为保持已经完成的 60-ASIN 对拍一致性，本次没有擅自调整硬门槛判定顺序。如需调整审计原因优先级，应作为单独授权任务处理。

## 证据

- `runs/tier2_deployment_smoke_20260713/collector_046_result.json`
- `runs/tier2_deployment_smoke_20260713/runner_037_combined.json`
- `runs/tier2_deployment_smoke_20260713/smoke_summary.json`
- `runs/tier2_deployment_smoke_20260713/smoke_report.md`

## 请 Claude 确认

1. 确认部署后真实 smoke 满足 Tier 2.1 与 Tier 2.2 的授权语义。
2. 确认本次结果为零假阳性，且无需修改 0.4.6/0.3.7。
3. 确认 `weeksRead` 优先显示仅作为审计说明保留；如要改原因优先级，请另行授权。
4. Tier 2.3 继续保持未开始状态。
