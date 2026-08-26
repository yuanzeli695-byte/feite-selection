# Runner 0.3.8.11 流量洞察 5 秒快速跳过候选版

## 行为

- 新增版本化开关 `traffic-block-fast-skip-5s-v1`，默认开启。
- 从开始寻找“流量洞察”标签起，到 `.echarts-trends-box` 图表区块可见为止，共用一个 5,000 ms 绝对截止时间。
- 5 秒内区块未就绪时，当前 ASIN 以 `traffic_block_timeout` 严格拒绝，尺寸和价格步骤标记为未运行，然后 Runner 自动进入下一行。
- 明确的登录失效、套餐权限或访问拦截仍暂停整批，等待人工处理；不会被当成普通超时跳过。
- Collector 面板缺失仍暂停整批，因为这通常表示脚本未启用，而不是单个 ASIN 加载慢。

## 安全边界

缺失或迟到的流量证据不能通过。该优化会提高速度，但可能增加慢页面的假阴性；不会产生假阳性。自然流量总占比 70%、至少 3 周、尺寸、价格、Keepa 20 秒严格就绪、历史、回放和最终验收规则均不变。

## 安装与回滚

安装：`scripts/sellersprite_integrated_runner_v0.3.8.11_zh_traffic_5s.user.js`

ScriptCat 中关闭 0.3.8.10，只启用 0.3.8.11 Runner，Collector 保持当前版本，刷新 Amazon 商品页。面板标题应显示“卖家精灵一体化选品 0.3.8.11”。

回滚：关闭 0.3.8.11，启用 `scripts/sellersprite_integrated_runner_v0.3.8.10_zh_keepa_20s.user.js` 并刷新页面。批次、历史和 Excel 桥接无需迁移。

## 验证要求

安装后先做单 ASIN smoke，确认超时行门槛日志为 `traffic_block_timeout`、`skippedSteps=dimensions,price`，面板没有进入暂停，随后自动访问下一 ASIN。正式采用前仍需不少于 30 个真实 ASIN 的新旧配对，以量化节省时间和新增假阴性。
