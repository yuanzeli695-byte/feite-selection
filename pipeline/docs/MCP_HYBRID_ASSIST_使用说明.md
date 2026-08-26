# SellerSprite MCP Hybrid Assist 0.3.0 使用说明

## 定位

Assist 0.3.0 只读取本地 Bridge 的已缓存证据，对候选 ASIN 做建议排序。它不能创建合格结论，不能替代 Gate C，也不写 Runner 结果、严格历史或最终 Excel。

- MCP/Bridge：批量预取、缓存、逐字段来源与时效校验、调用计账。
- Assist：读取 `mergedRanking`，在允许的模式下生成 `reorder_only` 顺序，并先写审计事件。
- Adapter：把已审计顺序应用到 Runner 的未生成草稿队列。
- Collector/Runner：继续采集当前页面的正式浏览器证据。
- 回放、过滤、Excel、acceptance checker：继续拥有 A-F 最终权威。

任何缺失、超期、ASIN 不一致、来源不完整或测试态 MCP 数据都只能触发浏览器回退，不能触发通过。

## 启动 Bridge

正式缓存读取使用默认 300 次 primary 预算；启动 Bridge 本身不会产生 MCP 调用。

```powershell
cd C:\Users\13045\Desktop\amazon_products
powershell -ExecutionPolicy Bypass -File .\scripts\start_mcp_hybrid_bridge.ps1 `
  -RunId phase15-browser-cache `
  -RunBudget 300 `
  -OutputRoot .\runs\mcp_hybrid_phase15_candidate\bridge
```

只有受控验证 pending 工具时才加 `-TestMode`。测试模式不等于正式授权，所有结果仍为 `finalAuthority=false`。

## 浏览器安装组合

启用：

- `scripts/sellersprite_mcp_hybrid_assist_v0.3.0.user.js`
- `scripts/sellersprite_mcp_hybrid_runner_adapter_v0.2.0.user.js`
- 一组批准的 Collector/Runner

关闭旧版 Assist 0.2.0/0.2.1 和 Adapter 0.1.0，避免页面出现多个控制面板。旧文件保留作回退，不删除。

兼容 Runner：

- Integrated Runner 0.3.7
- 中文 Excel Runner 0.3.8.2

## 使用顺序

1. 启动 Bridge，保留终端窗口，复制 Session token。
2. 打开 Amazon US 商品页，确认右下角出现 `MCP Hybrid Assist 0.3.0`。
3. 勾选 Assist 的 `Enable`，点击 `Connect`，输入 Session token。
4. 在 Runner 中保持“未生成批次”的草稿状态，粘贴候选 ASIN。
5. 勾选 Adapter 0.2.0 的启用开关，选择模式，点击 `Rank draft queue`。
6. Adapter 等待两次 Bridge 审计确认：排序审计和队列应用审计。
7. 成功后再按原 Runner 流程生成批次、逐个访问和采集。
8. 完成回放、硬门槛过滤、中文 Excel 和 acceptance checker。

仅测试重排时 Runner 必须打开，Collector 可以关闭。正式严格选品时 Collector 和 Runner 都必须打开，而且各只启用一个批准版本。MCP 只减少优先顺序上的网页浪费，不能减少最终候选对 Collector/Runner 的必要正式采集。

## 排序模式

- `Auto`：目标数不超过 5 时使用 Focus 5；目标数达到 10 或以上时保持原顺序。
- `Baseline`：始终保持原顺序，只做缓存和审计验证。
- `Focus 5`：只允许目标数不超过 5；更大队列自动退回原顺序。
- `Balanced`：必须人工明确选择，不能由 Auto 隐式启用。

30-ASIN 历史回顾中 Balanced 对“尽快找到 5 个”有收益，但对“找到 10 个”出现回退，因此大目标默认不重排。

## 调用预算

- 月官方上限：15,000。
- 月运行上限：12,000。
- 上海时区日硬上限：500。
- primary：300；conditional：100；emergency：100。
- conditional 和 emergency 必须显式启用；emergency 还需单独授权。
- 每个 packet 必须先整计划原子预留，再从 Bridge 领取一次执行权；第二次领取返回 409。
- 预留即计费，失败不释放，不自动重试。

当前正式可预留工具只有 `keepa_info`。`asin_detail`、`asin_sales_trend`、`traffic_listing_stat` 仍为 pending，只能使用双测试开关；`product_research` 需要独立 discovery planner，当前 candidate-prefetch 命令会拒绝它。

## 失败与恢复

- 审计失败且队列可回滚：恢复原队列并恢复 Generate 按钮。
- 审计失败且队列已被其它事件改变：不覆盖新内容，Generate 保持禁用。
- Bridge 预留成功但本地落盘中断：运行 orchestrator 的 `reconcile-reservation`，只允许恢复“reserved 且零 claim”的精确计划。
- Bridge 已 claim 但本地未落盘：运行 `reconcile-claim`，该 packet 会记为失败并禁止重试，不导出证据。
- `plan-state` 只用于诊断和恢复，不能重新发放执行权。

## 禁止项

- 不得用 MCP 代替 Gate C 周自然流量证据。
- 不得把 MCP 字段直接写成 A-F 通过。
- 不得启用 Tier 2.3 预加载或并行浏览器 Runner。
- 不得改变 restricted-product 排除、A-F 阈值、顺序或容差。
- pending 工具的小样本测试不能自动升级为正式工具。

## 回退

1. 关闭 Assist 0.3.0 和 Adapter 0.2.0。
2. 停止 Bridge 0.3.0。
3. 需要旧方案时，仅启用旧 Assist 0.2.1 + Adapter 0.1.0，或单独启用 Assist 0.2.0。
4. 原 Collector、Runner、规则、排除表和严格历史无需恢复，因为本方案不修改它们。
