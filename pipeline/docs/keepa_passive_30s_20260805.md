# Runner 0.3.8.13 Keepa 30 秒被动等待候选版

## 行为

- 进入价格阶段后，只执行一次 Keepa 标签点击和一次“过去 1 个月”选择。
- 随后的 30 秒只观察现有 Keepa DOM、canvas 和 tooltip，不再次点击 Keepa 标签，不重新选择时间范围，也不触发插件刷新回调。
- 图表在第 8 秒或第 25 秒才出现时继续读取；30 秒仍没有真实 canvas 或可解析日期/USD tooltip 时严格失败关闭。
- 版本化开关为 `keepa-passive-wait-30s-v1`，默认开启。

## 审计证据

门槛日志新增：

- `pricePassiveWaitEnabled=true`
- `pricePassiveWaitVersion=keepa-passive-wait-30s-v1`

等待期间 `priceRetryCount` 必须为 `0`。原有 `priceReadyWaitMs` 和 `priceCollectionStatus` 继续记录等待时长及 `ok`、`keepa_chart_not_ready` 或 `keepa_tooltip_not_ready`。

## 不变项

流量洞察 5 秒共享截止时间、`traffic_block_timeout`、Collector、自然流量、周数、尺寸、价格范围和趋势、历史去重、离线回放、最终 A-F 验收与 Excel 输出均不变。被动等待不能把缺失证据判为合格。

## 安装与回退

安装文件：`scripts/sellersprite_integrated_runner_v0.3.8.13_zh_keepa_passive_30s.user.js`

在 ScriptCat 中关闭旧 Runner，只启用 0.3.8.13；Collector 0.4.6.4 保持开启。刷新 Amazon 商品页，确认面板标题为“卖家精灵一体化选品 0.3.8.13”，然后继续原批次，不要重新生成批次。

回退时关闭 0.3.8.13，重新启用 0.3.8.12 并刷新页面。0.3.8.12 保留 30 秒等待，但会在第 5 秒允许一次 Keepa 重试。批次和历史无需迁移。

## 验证状态

- `node --check`：通过。
- 8 秒及 25 秒延迟就绪夹具：通过，重试回调均为 0 次。
- 30 秒无 canvas / 无 tooltip 夹具：通过，重试回调均为 0 次且失败关闭。
- 4 秒流量恢复及 5 秒流量超时：通过。
- 硬门槛函数与 0.3.8.7 基线逐函数一致：通过。
- SellerSprite JavaScript：37/37 通过。
- bundled Python：200/200 通过。
- 严格预检：通过，规则漂移为 0。

真实 Chrome 单 ASIN 烟测和不少于 30 个真实 ASIN 的 0.3.8.12/0.3.8.13 配对证据仍待安装后采集。
