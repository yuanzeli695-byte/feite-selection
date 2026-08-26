# Runner 0.3.8.8 Keepa 图表就绪协议

## 问题与根因

Runner 0.3.8.7 在点击“Keepa插件替代”后，只等待 `.keepa-module` 外壳可见，再固定等待 700 ms。卖家精灵有时先渲染模块外壳或加载动画，随后才生成 ECharts 画布和价格提示。旧逻辑会在真实价格数据尚未可读时得到空样本，并以 `price_current_missing` 淘汰，造成严格流程中的假阴性。

2026-08-01 的浏览器证据中，当前批次三个已通过流量与尺寸门槛的 ASIN 都在约 1 秒后以 `price_current_missing` 结束，且没有有效当前价格；这与固定 700 ms 等待路径完全吻合。

## 0.3.8.8 行为

- Keepa 阶段使用版本化开关 `keepa-chart-ready-v1`，默认开启。
- 最多等待 10 秒，不再把模块外壳可见当成数据就绪。
- 就绪必须同时满足：存在可见且有实际尺寸的画布，并能从图表提示中解析出至少一个日期和美元价格。
- 5 秒仍未就绪时，仅重新点击一次 Keepa 标签并重选“近1个月”；整行最多一次受控重试。
- 10 秒后仍没有画布时记录 `keepa_chart_not_ready`；有画布但没有有效提示时记录 `keepa_tooltip_not_ready`。
- 两种未就绪状态都进入 `collection_error`，严格失败关闭，不会产生合格结果。
- 门槛日志新增 `priceCollectionStatus`、`priceReadyWaitMs`、`priceRetryCount`，便于区分真实价格不合格和图表未就绪。

## 不变项

- 自然流量、尺寸、价格范围、价格趋势、历史去重及最终离线回放/验收规则不变。
- `evaluateTrafficGate`、`evaluateDimensionsGate`、`evaluatePriceGate` 等硬门槛函数与 0.3.8.7 字节级一致。
- Collector 不变，继续使用当前已验证版本。
- 0.3.8.7 文件未修改，保留为命名回滚版本。

## 安装与回滚

安装文件：

`scripts/sellersprite_integrated_runner_v0.3.8.8_zh_keepa_ready.user.js`

在 ScriptCat 中导入后，只开启一个 Runner。确认面板标题为“卖家精灵一体化选品 0.3.8.8”，Collector 保持当前版本开启，然后刷新 Amazon 商品页再开始批次。

回滚：关闭 0.3.8.8，重新开启 `sellersprite_integrated_runner_v0.3.8.7_zh_no_data_fast_fail.user.js`，刷新 Amazon 页面。无需迁移批次、规则或历史数据。

## 验证

- `node --check`：通过。
- 延迟画布、延迟价格提示、无画布、无提示、单次重试夹具：通过。
- 32/32 个 SellerSprite JavaScript 回归套件：通过。
- 内置工作区 Python 完整回归 200/200：通过。

真实浏览器单 ASIN 冒烟仍需在安装后执行；在该冒烟完成前，0.3.8.8 保持候选状态。
