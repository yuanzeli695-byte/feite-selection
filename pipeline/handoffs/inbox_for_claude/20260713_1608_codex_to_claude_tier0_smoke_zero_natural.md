---
from: codex
to: claude
priority: p1
requires_action: yes
tags: [tier0, smoke, collector_0_4_5, zero_natural, parser_gap]
---

# Collector 0.4.5 真实 Smoke 补充报告

## 结论

Collector 0.4.5 已在用户当前 Amazon/SellerSprite 页面完成两次真实采集。Tier 0 门槛日志和耗时日志正常生成，两次均严格记录为 `reject`，未出现假阳性。

同时发现一个继承自现有读取器的解析缺口：SellerSprite 在“自然流量为 0”时可能不显示自然占比行，Collector 将自然占比记为 `null`，而不是从正数总流量和自然流量 0 推导为 0%。

## 实测结果

- ASIN：`B0GQM829MB`
- 页面检查：`SellerSprite visible=YES`、`Traffic chart visible=YES`
- 第一次：`sample_low_review`、`weeksRead=1`、`C=reject`、总耗时 `8330 ms`
- 唯一允许重试：`sample_low_review`、`weeksRead=1`、`C=reject`、总耗时 `11714 ms`
- Runner 未启动，旧批次未修改。

第二次 tooltip 读取到四周：

- 第26周：总流量 2905.18，自然流量 0，SP 占比 100%，自然占比文本缺失。
- 第25周：总流量 1429.39，自然流量 0，SP 占比 100%，自然占比文本缺失。
- 第24周：总流量 4637.09，自然流量显示 `--`，SP 占比 100%，自然占比文本缺失。
- 第23周：自然流量 62.13，自然占比明确显示 100%。

因此只有第23周被计入有效自然占比样本，最终 `weeksRead=1`。

## 风险判断

- 当前行为是安全失败：可能漏掉本可评估的品，但不会把不合格品放进主表。
- 该 ASIN 的最新自然流量为 0 时，本应更早命中 C 关低流量淘汰；当前实现以样本不足方式淘汰，降低速度和日志精度，但不改变拒绝结论。
- 按硬约束，本次只记录问题，不在 Tier 0 中修改解析逻辑。

## 请求 Claude 处理

1. 确认该问题应归入 Tier 2.1 读取器解析/就绪改造，而不是 Tier 0。
2. 确认修复语义只能在 `totalTraffic > 0` 且明确解析到 `naturalTraffic == 0` 时推导自然占比为 0；`--`、缺失或歧义值继续判缺失，不得推导。
3. 修复前增加真实 tooltip fixture，并按 B 类要求完成新旧路径配对验证；任何不一致只能更保守，不能产生假阳性。

## 证据

- `runs/tier0_smoke_20260713/collector_045_smoke_summary.json`
- `runs/tier0_smoke_20260713/collector_045_smoke_report.md`
