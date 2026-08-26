# Runner 0.3.8.9 Keepa 父标签触发候选版

## 触发原因

0.3.8.8 的浏览器证据显示，自动流程在 Keepa 阶段经常等待约 10 秒并记录 `keepa_chart_not_ready`，而人工点击“Keepa插件替代”后加载明显更快。当前页面的“Keepa插件替代”文字位于 `span.tab-name`，实际点击监听器在外层 `.list` 容器；0.3.8.8 直接对文字节点调用 `.click()`，并且 5 秒重试不区分模块是否已经处于加载中。

## 0.3.8.9 改动

- 新增版本化开关 `keepa-parent-click-v1`，只影响 Keepa 标签触发路径。
- 点击前最多等待 8 秒，确认可见标签存在。
- 优先点击承载标签监听器的 `.list` 父容器；找不到父容器时才回退到标签节点。
- 5 秒就绪重试时，如果 Keepa 模块已有“加载中/loading”状态，不再再次点击，不重置进行中的请求；非加载状态仍只允许一次原有受控重试。
- 继续使用 0.3.8.8 的画布+日期/USD tooltip 就绪协议和 10 秒总等待上限。

## 不变项

- 自然流量总占比 70%、周数、尺寸、价格范围、价格趋势、历史去重、回放和最终 A-F 验收均不变。
- 未获得真实价格 tooltip 时仍然 `collection_error` 严格失败关闭，不会放行。
- Collector、Excel 输出、批次目标控制和硬门槛函数不变。

## 安装与回滚

安装文件：

`scripts/sellersprite_integrated_runner_v0.3.8.9_zh_keepa_click_ready.user.js`

ScriptCat 中只启用 0.3.8.9 Runner，Collector 保持当前已验证版本，刷新 Amazon 商品页后做单 ASIN 冒烟。确认面板标题显示“卖家精灵一体化选品 0.3.8.9”。

回滚：关闭 0.3.8.9，重新启用 `scripts/sellersprite_integrated_runner_v0.3.8.8_zh_keepa_ready.user.js` 并刷新页面；若需回到更早版本，再按记录回退到 0.3.8.7。无需修改批次历史或硬性规则。

## 验证状态

- `node --check` 和 0.3.8.9 专项父标签夹具：通过。
- 硬门槛函数与 0.3.8.7 保持字节级一致：通过。
- 30-ASIN OFF/ON 配对、真实浏览器单 ASIN smoke 和吞吐收益尚待安装后验证；在验证完成前保持候选状态。
