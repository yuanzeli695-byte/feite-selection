# MCP Hybrid Runner Adapter 0.2.0 / 0.2.1

Adapter 0.2.0 是独立、默认关闭的 Runner 草稿队列适配器。它只接受 Assist 0.3.0 已经由 Bridge 0.3.0 审计确认的 `reorder_only` 结果。

Adapter 0.2.1 仅增加快速闭环 Runner `0.3.10` 的兼容白名单；排序、多重集合、审计和最终权限边界与 0.2.0 不变。

## 安装组合

新组合：

- `scripts/sellersprite_mcp_hybrid_assist_v0.3.0.user.js`
- `scripts/sellersprite_mcp_hybrid_runner_adapter_v0.2.0.user.js`
- Collector 0.4.6 + Runner 0.3.7，或已知兼容的中文 Excel Runner 0.3.8.2

快速闭环候选组合改用 `scripts/sellersprite_mcp_hybrid_runner_adapter_v0.2.1.user.js`，只配合 Runner `0.3.10`；正式验证完成前不得替换 0.2.0。

旧 Assist 0.2.0/0.2.1 和 Adapter 0.1.0 保留作回退，但不能和新组合同时启用。

## Adapter 会做什么

- 只读取一个 Runner 面板中的草稿队列。
- 校验 Runner、Assist、Bridge 版本和稳定 DOM 契约。
- 校验 `requestId`、原队列、模式、ASIN 格式、数量和重复次数。
- 在大目标 Auto 模式下保持原顺序；Balanced 必须人工选择。
- 在写队列前要求排序审计已持久化。
- 写队列后锁住 Runner Generate，等待应用审计持久化，再解锁。

## Adapter 不会做什么

- 不创建或启动批次。
- 不修改 Runner 本地批次、结果、进度或严格历史。
- 不读取或写入 A-F 通过状态。
- 不替代 Collector，不预加载页面，不并发运行 Runner。
- 不把 MCP 缺失字段解释为通过。

## 操作

1. 启动 Bridge 0.3.0 并连接 Assist 0.3.0。
2. 在 Runner 中保持空的“本地批次”选择，即尚未生成批次。
3. 把候选 ASIN 放入 Runner 队列。
4. 启用 Adapter，选择 `Auto`、`Baseline`、`Focus 5` 或显式 `Balanced`。
5. 点击 `Rank draft queue`。
6. 看到 `Applied and audited N ASINs; no batch was generated.` 后，确认队列成员未变。
7. 再点击 Runner 自己的 Generate，按原流程采集。

正式严格运行时 Runner 和 Collector 都要打开；仅做零调用的队列兼容测试时，Collector 可以关闭。

## 失败安全

下面任一情况都会拒绝应用：

- Runner 面板不是恰好一个，版本不在白名单，或 DOM 结构变化。
- Runner 已经选择/生成批次，队列只读，或等待期间被用户修改。
- Assist 不是 0.3.0、Bridge 低于 0.3.0、Assist 未连接或事件超时。
- 响应不是 `finalAuthority=false` 和 `allowedAction=reorder_only`。
- ASIN 数量、顺序基线或多重集合不一致。
- 排序审计或应用审计没有返回匹配的 `requestId/auditId/persisted=true` 回执。

如果应用审计失败：

- 队列仍等于 Adapter 写入值时，恢复原队列并恢复 Generate。
- 队列已被其它操作改变时，不覆盖新内容，Generate 保持禁用，要求人工检查。

## 兼容性验证

- 30 个真实 ASIN 的 Auto 大目标配对保持原顺序。
- 排名前后数量、成员和重复次数完全相同。
- Assist/Adapter 旧版文件哈希保持不变。
- 新脚本通过字段时效、审计、超时、回滚、按钮锁定和 draft-only 测试。
- 所有结果仍为 `finalAuthority=false`，正式运行授权不由 Adapter 决定。

## 回退

关闭 Adapter 0.2.0 和 Assist 0.3.0，停止 Bridge 0.3.0，即回到原 Runner 流程。需要旧的候选方案时，再单独启用 Assist 0.2.1 + Adapter 0.1.0；不要混用版本。
