# 严格选品快速闭环 v1

更新日期：2026-07-31

状态：候选版。代码和离线测试已完成；30 个真实 ASIN 配对与单 ASIN live smoke 未完成前，不得替换正式 `0.4.6/0.3.7` 组合。

## 目标与边界

快速闭环只减少空跑、批次交接和重复访问，不修改 A-F 门槛：

- 连续 3 个 `tooltip_not_ready`、`chart_not_ready` 或无明细 `traffic_error/no_data` 后自动暂停；
- 一个 Amazon 站点会话同一时刻只允许一个快速 Runner 租约；
- 每保存一行就把单调递增的证据发送到本机桥并执行离线 A-F 回放；
- 浏览器通过数不能停止批次，只有离线回放达到最终目标数才能停止；
- 达到目标后自动生成机器验收工作簿，仍要求人工预览；
- MCP 只可重排未生成的草稿队列，不能提供 Gate C 或最终放行。

缺失、桥接中断、版本不匹配、结果回写、重复已尝试 ASIN 或租约冲突都会暂停/拒绝，不会创建合格结果。

## 候选组合

- Collector：`scripts/sellersprite_traffic_collector_v0.4.6_zh_p1.user.js`，版本 `0.4.6.2`。
- Runner：`scripts/sellersprite_integrated_runner_v0.3.10_fast_loop.user.js`。
- 本机桥：`scripts/selection_fast_loop_bridge.py`。
- 启动器：`scripts/start_selection_fast_loop_bridge.ps1`。
- 可选 MCP Adapter：`scripts/sellersprite_mcp_hybrid_runner_adapter_v0.2.1.user.js`，配合 Assist `0.3.0`，默认关闭。

同一页面不得同时启用其他 Collector、Runner 或 Adapter 版本。

## 启动本机桥

候选 JSON 必须覆盖 Runner 中的完整队列，主图目录必须已经缓存全部候选图片。

```powershell
$Project = 'C:\Users\13045\Desktop\amazon_products'

& "$Project\scripts\start_selection_fast_loop_bridge.ps1" `
  -RunId 'strict-fast-YYYYMMDD-target10' `
  -CandidatesJson "$Project\runs\RUN_ID\candidate_pool\strict_queue_01.json" `
  -ImageDir "$Project\runs\RUN_ID\source_images" `
  -Target 10
```

把终端显示的服务地址和令牌填入 Runner 面板。Runner 点击“开始”时会先发送零行 checkpoint，校验版本、候选映射、历史重复和桥接状态；失败时不会打开第一个 ASIN。

## 运行行为

1. Runner 保存当前行的原始结果。
2. 瞬态失败计数器更新；正常读取、真实低流量、周数不足或 ASIN 跳转不会误触发熔断。
3. Runner 把当前批次 checkpoint 发给 `127.0.0.1`。
4. Bridge 拒绝任何已保存结果变化，只接受 queue 前缀式增长。
5. Bridge 使用 `runner_current_price_v1` 回放所有批次的最新 checkpoint。
6. 返回离线合格数、剩余目标和已尝试数；`finalAuthority` 始终为 `false`。
7. 离线合格数达到目标后 Runner 停止并调用既有 Excel/acceptance 流程。

浏览器面板中的“离线严格合格”仍是机器判定；人工 Gate A/IP 复核和工作簿视觉预览完成后才能交付。

## MCP 协作

Adapter `0.2.1` 只增加 Runner `0.3.10` 的 DOM 白名单，排序协议、审计回执和 `reorder_only` 边界与 `0.2.0` 相同。操作顺序：

1. Runner 保持未生成草稿。
2. 启用 Assist `0.3.0` 和 Adapter `0.2.1`。
3. 只在需要时点击一次 `Rank draft queue`。
4. 审计成功后关闭 Adapter 或保持默认关闭，再由 Runner 生成批次。

快速闭环本身产生 0 次 MCP provider 调用；MCP 额度仍由独立 Bridge ledger 控制。

## 发布门槛

正式启用前必须保存：

- 与 `0.3.8.2` 对同一组至少 30 个真实 ASIN 的配对证据；
- A-F 最终结果 100% 一致，任何差异只能更保守，零误放；
- 三连瞬态失败熔断、桥断开、重复批次和跨标签租约 smoke；
- 一个不污染正式历史的单 ASIN live smoke；
- 原始 JSON、门槛 TSV、耗时 TSV、版本和截图。

## 回退

1. 关闭 Runner `0.3.10` 和 Adapter `0.2.1`。
2. 停止 `selection_fast_loop_bridge.py`。
3. 重新启用正式 Collector `0.4.6` + Runner `0.3.7`；需要中文候选时回到 `0.4.6.2/0.3.8.2`。
4. 不删除新版本的 `runs/<RUN_ID>/excel_bridge`，它是审计证据，不会污染正式 strict history。
