---
from: codex
to: claude
priority: p1
requires_action: yes
tags: [skill, strict_selection, architecture, fail_closed, preflight, zero_false_positive]
---

# Amazon US 严格选品技能架构回执

## 结论

Codex 已把当前亚马逊美国站严格选品、SellerSprite 浏览器采集、A-F 验收、中文工作簿交付、版本治理和 Codex-Claude 对接流程整理为可自动触发的个人技能：

- 技能名：`amazon-us-strict-selection`
- 安装路径：`C:\Users\13045\.codex\skills\amazon-us-strict-selection`
- 状态：技能格式验证通过，真实项目只读预检通过，两个前向测试通过

本次没有修改项目业务脚本、配置、硬门槛、历史台账或 Chrome userscript。Tier 2.3 仍未授权。

## 架构

技能采用控制面架构，不复制项目业务实现：

1. `SKILL.md`：不可变运行契约、任务路由、强制预检、十阶段状态机、组件职责和停止条件。
2. `references/hard-gates.md`：A-F 门槛、失败关闭、0% 推导边界和数据诚实规则。
3. `references/runbook.md`：候选、历史排重、图片、Chrome、批次回放、出表和验收命令契约。
4. `references/browser-userscripts.md`：登录态、美国配送地址、单 Collector/Runner、版本、导出、部署 smoke 和失败处理。
5. `references/workbook-delivery.md`：主表/审计隔离、中文字段、ASIN 右侧主图、图片嵌入和机器/视觉验收。
6. `references/engineering-governance.md`：A/B/C 变更分级、Tier 顺序、feature flag、对拍、缓存只向下和回退。
7. `references/handoffs.md`：Codex-Claude 回执结构和证据要求。
8. `scripts/preflight.py`：只读校验显式项目路径、核心文件、JSON、硬门槛快照、ASIN mismatch 策略、当前/回退 userscript 版本、Tier 2 feature flag 和严格合格历史。

业务逻辑继续以项目内 `filter_engine.py`、`replay_existing_batch.py`、`build_replay_workbooks.mjs` 和 `acceptance_checker.py` 为权威实现，避免技能和项目产生两套判定逻辑。

## 真实预检结果

对 `C:\Users\13045\Desktop\amazon_products` 执行：

```powershell
python C:\Users\13045\.codex\skills\amazon-us-strict-selection\scripts\preflight.py `
  --project-root C:\Users\13045\Desktop\amazon_products
```

结果：

- `ok=true`
- 核心文件缺失：0
- 硬门槛漂移：0
- Collector：0.4.6，通过
- Runner：0.3.7，通过
- Collector 回退：0.4.5，通过
- Runner 回退：0.3.6，通过
- Collector/Runner 授权 feature flag：均为 true
- 历史严格合格 ASIN：45
- warnings：0
- errors：0

另用 `runs/strict12_integrated_20260711_1930_summary` 验证完成 run bundle，核心交付文件全部存在。

## 前向测试

测试 1：用户要求正式筛 20 品，但 Amazon 配送地址为 Hong Kong。

- 技能正确停止正式采集。
- 要求先改为授权的美国配送地址，默认 ZIP 10010。
- 正确定位 Desktop 项目而不是把聊天工作目录当成业务根目录。
- 正确要求预检、历史排重、A-F 重放、图片和最终验收证据。

测试 2：用户要求直接实现 Tier 2.3，并允许缓存直接判合格。

- 技能拒绝执行。
- 明确缓存只能跳过或降优先级，不能放行。
- 明确 Tier 2.3 需要单独开关、至少 30 个真实 ASIN 对拍、零假阳性和 live smoke 后再授权。

## 验证

- `quick_validate.py`：PASS
- `python -m py_compile scripts/preflight.py`：PASS
- 真实项目 preflight：PASS
- 完整 run bundle preflight：PASS
- 错误显式项目路径：正确以退出码 2 拒绝，没有静默回退
- TODO/占位符扫描：0
- 技能正文：97 行
- 前向测试：2/2 满足失败关闭和授权边界

## 请 Claude 处理

1. 复核该控制面/业务面分离是否符合现有协作协议。
2. 后续接手选品、脚本改造或交付验收时，优先引用此技能和项目实际文件，不再从旧聊天重建规则。
3. 确认 Tier 2.3、Tier 3、Tier 4 仍需各自独立授权，技能本身不构成授权。
