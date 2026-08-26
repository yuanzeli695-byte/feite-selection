# SellerSprite Integrated Runner 0.3.7

## 作用

`sellersprite_integrated_runner_v0.3.7.user.js` 在同一次 Amazon 商品页访问中完成：

- 调用 `SellerSprite Traffic Collector 0.4.6` 采集最近 4 周自然流量；已读周出现低于 70% 时立即返回淘汰结果。只有正总流量与字面自然流量 `0` 同时成立时才推导 `0%`。
- 读取 SellerSprite/Amazon 的商品尺寸和重量。
- 扫描 SellerSprite `Keepa插件替代` 近1个月价格点并判定 `stable`、`rising`、`declining`、`volatile` 或 `no_data`。
- 输出 `sellerSpriteIntegratedBatch/v0.3.0` 合并 JSON，回放时无需再传 `--enrichment-json`。
- 按“ASIN一致性 → 流量 → 尺寸 → 价格趋势”短路执行；任一关失败立即保存淘汰原因，不再读取后续昂贵数据。
- 达到 `targetQualified` 后自动停止，队列剩余 ASIN 保留为候补而不继续访问。
- 已严格合格的 ASIN 会在 `Generate` 时直接跳过：不打开商品页、不采集流量、不计入本批 `Qualified`，也不会进入最终主表。新版首次启用时会预置已有交付历史，之后每个新严格合格 ASIN 会自动写入浏览器本地历史。
- Tier 0 开启时可导出门槛日志和耗时日志；日志只观测，不参与放行判定。

旧版 Batch Runner 0.2.x 的 localStorage 和历史批次不会被修改。新版使用独立的 `ss-v3-*` URL 参数和 `ssIntegratedRunner:v0.3:*` 存储键。

## 安装

1. 保持 SellerSprite Chrome 扩展已登录。
2. 在 ScriptCat 导入并启用：

   `C:\Users\13045\Desktop\amazon_products\scripts\sellersprite_traffic_collector_v0.4.6.user.js`

   面板标题应显示 `SellerSprite Traffic Collector 0.4.6`。0.4.5 和其他 Collector 必须停用，避免两个 Collector 同时写入同一面板。
3. 打开 ScriptCat，选择导入本地用户脚本或新建脚本。
4. 停用旧的 `SellerSprite Integrated Runner 0.3.3/0.3.4/0.3.5/0.3.6`，避免两个 Runner 同时生成面板或重复导航。
5. 导入：

   `C:\Users\13045\Desktop\amazon_products\scripts\sellersprite_integrated_runner_v0.3.7.user.js`

6. 保存并启用 `SellerSprite Integrated Runner 0.3.7`；面板标题应显示版本 `0.3.7`。
7. 旧版 Batch Runner 可以继续启用，但运行新版时不要同时点击旧版 `Start`。

Codex 无法自动操作 `chrome-extension://` 的 ScriptCat 管理页，因此安装确认需要在 Chrome 中手动完成一次。

## 使用

1. 打开任意 Amazon.com 商品详情页。
2. 右上角出现 `SellerSprite Integrated Runner 0.3.7` 面板。
3. 填写 `batchName`、`operator` 和 `targetQualified`。`targetQualified` 是要交付的严格合格品数量，通常填 `20`。
4. 在 `QUEUE input` 中每行粘贴一个已通过本地硬筛的候补 ASIN。队列可以大于目标数，脚本达到目标后会自动停止。
5. 点击 `Generate`。面板会显示 `History auto-skipped`；该数必须不计入 `Qualified`。确认队列剩余的是未交付 ASIN 后点击 `Start`。
6. 每个 ASIN 先验证流量；流量失败不读取尺寸和价格，尺寸失败不读取价格。面板会显示累计合格数、淘汰数和停止原因。
7. 运行期间保持 Chrome、Amazon 页、SellerSprite 和 Collector 开启，不切换标签、不移动鼠标。
8. 状态变为 `done` 后点击 `Copy combined JSON`，保存为批次 JSON。JSON 中会保留 `historySkippedAsins`，用于审计本次直接跳过的历史品。
9. 点击 `Copy gate log TSV` 和 `Copy timing log TSV` 可分别导出整批门槛日志和耗时日志。历史命中只显示为 `skip`，不得视为本批通过。
10. 将该 JSON 与对应候选 metadata JSON 配对传给 `replay_existing_batch.py`。

示例：

```powershell
python scripts\replay_existing_batch.py `
  --batch-json runs\target_run\integrated_batch.json `
  --candidates-json runs\target_run\candidates.json `
  --image-dir runs\target_run\source_images `
  --run-id target_run `
  --target 20 `
  --overwrite
```

合并批次已经包含尺寸与价格趋势，不需要 `--enrichment-json`。如需人工修正，仍可额外传入 `--enrichment-json`，其值会覆盖批次内字段。

## 失败处理

- `Collector not found`：确认 0.4.6 已启用、其他 Collector 已停用，并刷新 Amazon 页面。
- `weeksRead < 3`：普通部分样本不再无条件重试，直接保持未通过；只有图表或 tooltip 明确未就绪时才重试一次。
- `priceTrendClass = no_data`：SellerSprite Keepa 图未加载或有效价格点不足，最终 pipeline 会淘汰。
- `declining` 或 `volatile`：属于硬淘汰，不进入最终工作簿。
- CAPTCHA、SellerSprite 登录失效或 Amazon 拦截：暂停批次，人工处理后点击 `Resume`。

## Tier 0 回退

- 将两个新脚本内的 `ENABLE_TIER0_TELEMETRY` 改为 `false`，即可关闭日志附加字段和 TSV 按钮。
- 完整回退时停用 0.4.5/0.3.6，重新启用保留的 0.4.4/0.3.5。
- 详细字段与验证证据见 `docs/tier0_observability.md`。

## Tier 2 开关与回退

- Collector 0.4.6：`ENABLE_TIER2_1_ZERO_SHARE_DERIVATION`。
- Runner 0.3.7：`ENABLE_TIER2_2_CONDITIONAL_RETRY`。
- 关闭对应开关可恢复旧解析或旧重试条件。
- 完整回退时停用 0.4.6/0.3.7，重新启用 0.4.5/0.3.6；无需删除旧批次或 localStorage。
- 真实 60-ASIN 对拍和详细语义见 `docs/tier2_reader_retry.md`。

## 预计速度

- Collector 最多读取最近 4 周；最新值或已读周最低值低于 70% 时会在流量阶段提前结束。
- 流量不通过的 ASIN 在流量阶段即停止，不再支付尺寸和价格趋势采集时间。
- 只有通过流量和尺寸的 ASIN 才会进入价格趋势采集，因此总耗时取决于流量通过率和目标合格数，而不是固定跑完整条候补队列。
