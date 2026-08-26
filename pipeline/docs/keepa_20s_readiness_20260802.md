# Runner 0.3.8.10 Keepa 20 秒严格就绪候选版

## 实测依据

批次 `8.2_01.` 的 17 行日志中，5 个 ASIN 通过流量和尺寸门槛并进入价格阶段：

- `B0GTQ89M82` 在 519 ms 读取成功，价格 `$23.99`，趋势 `stable`。
- `B0GTTPBVCB`、`B0GTTXJMXK`、`B0GVQ8V9NH`、`B0GWQQZ84W` 均在约 10.0 秒记录 `keepa_chart_not_ready`。

这说明短路顺序正确，但 0.3.8.9 的 10 秒 Keepa 就绪窗口对慢加载页面不足。其余流量不达标、周数不足、无数据或 ASIN 跳转行没有进入价格阶段，属于预期行为。

## 0.3.8.10 改动

- 基于 0.3.8.9，保留 `keepa-parent-click-v1`。
- 将版本化 Keepa 就绪协议更新为 `keepa-chart-ready-20s-v2`。
- 总等待上限从 10,000 ms 延长至 20,000 ms。
- 5 秒的一次受控重试、加载中不重复点击、画布和日期/USD tooltip 双重就绪条件均保持不变。
- 20 秒仍无真实 tooltip 时继续记录 `keepa_chart_not_ready` 或 `keepa_tooltip_not_ready`，严格失败关闭。

## 不变项

自然流量总占比 70%、至少 3 周、尺寸、当前价格范围、价格趋势、历史去重、离线回放、最终 A-F 验收和 Excel 输出均不变。延长等待只能救回慢加载证据，不能把缺失证据判定为合格。

## 安装与回滚

安装：`scripts/sellersprite_integrated_runner_v0.3.8.10_zh_keepa_20s.user.js`

ScriptCat 中关闭 0.3.8.9，只启用 0.3.8.10 Runner，Collector 保持当前版本，刷新 Amazon 商品页。面板标题必须显示“卖家精灵一体化选品 0.3.8.10”。

回滚：关闭 0.3.8.10，重新启用 `scripts/sellersprite_integrated_runner_v0.3.8.9_zh_keepa_click_ready.user.js` 并刷新页面。批次和历史无需迁移。

## 验证状态

- 语法检查和专项夹具通过，包括 15 秒后才出现图表的恢复场景。
- 无图表/无 tooltip 场景仍在 20 秒后失败关闭。
- 硬门槛函数与 0.3.8.7 保持字节级一致。
- 真实浏览器 smoke 和不少于 30 个 ASIN 的新旧配对证据仍待安装后收集。
