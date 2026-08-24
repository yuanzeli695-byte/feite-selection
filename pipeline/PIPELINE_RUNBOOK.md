# Amazon US 选品闭环 pipeline runbook

## 目标

把 SellerSprite 批处理结果变成两张表:

- `final_candidates_*.xlsx`: 只包含全合格商品。
- `rejected_audit_*.xlsx`: 记录剔除商品和原因。

## 固定规则

- 禁限售、IP/角色授权、健康/医疗/补剂/化学属性先于流量和商业指标。
- 价格 `9.90-50.00`,评分 `>=4.0`,上架 `<=90` 天,变体 `<=25`,月销硬顶 `<=1500`。
- 自然流量按严格 70% 执行:最新、近4周均值、近4周最低都要 `>=70%`,且读取周数 `>=3`。
- `重量/尺寸` 必须非空；价格趋势只允许稳定或上升，下降、高波动和无数据全部淘汰。
- final 表必须有嵌入图片;图片缺失时不进 final。

## baseline 回放命令

在 `C:\Users\13045\Desktop\amazon_products` 运行:

```powershell
$env:PYTHONIOENCODING='utf-8'
& 'C:\Users\13045\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' scripts\replay_existing_batch.py --batch-json 'C:\Users\13045\Documents\亚马逊电商选品\outputs\product_selection_20260708\batch_browser_panel_20260710_a54f68db.json' --candidates-json 'C:\Users\13045\Documents\亚马逊电商选品\outputs\product_selection_20260708\seller_refined_candidates.json' --image-dir 'C:\Users\13045\Documents\亚马逊电商选品\outputs\product_selection_20260710\product_images_20260710' --run-id replay_20260710_baseline --process-all --overwrite
& 'C:\Users\13045\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe' scripts\build_replay_workbooks.mjs 'C:\Users\13045\Desktop\amazon_products\runs\replay_20260710_baseline'
& 'C:\Users\13045\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' scripts\acceptance_checker.py 'C:\Users\13045\Desktop\amazon_products\runs\replay_20260710_baseline'
```

## baseline 结果

- 尝试 ASIN: 24
- 合格: 5
- 剔除审计: 19
- 停止原因: 候选源耗尽,未凑够目标 10 个。
- 历史验收曾按“候选源耗尽可结束”的旧口径显示 PASS；按当前严格交付口径，该结果为 5/10，必须显示未完成并返回非零退出码。

## 下一批怎么跑

1. 用户要求的数量是最终严格合格数量，不是 Batch Runner 队列长度。
2. 用 `prepare_strict_candidate_pool.py --source-manifest ...` 从 SellerSprite 搜索结果生成候选 JSON 和 ASIN 队列。来源清单必须是 24 小时内的美国站采集，绑定非空类目节点、`maxReviews<=100`、查询 URL 和每个 `query_*.json` 的 SHA-256；`5000+` 宽泛结果、空类目、过期导出、缺少 `childSales` 或来源字段的行不得进入 Chrome。默认的 `tier1.1-a-source-prefilter-v2` 只按精确证据短语提前剔除明确 A 类硬排除项，summary 必须记录 `aSourcePrefilter`；紧急回退使用 `--disable-a-source-prefilter-v2`。通过硬筛的候选先按 `tier1.2-probability-v2` 确定队列成员，再由 `p1-safe-queue-reorder-v1` 在同分项中后置未来年份 planner/calendar、优先更成熟的上架天数。summary 必须显示前后 multiset SHA-256 相等；`--disable-post-selection-reorder` 只回退最终顺序，`--allow-legacy-source` 是缺少正式来源保证的应急回退，不能当作常规入口。所有源端优化都只能减少浏览器候选，不能授予最终合格。
3. 用 `download_candidate_images.py` 缓存该批全部主图；下载失败的候选不得送入最终工作簿。
4. Canonical 预检仍使用 `scripts/sellersprite_traffic_collector_v0.4.6.user.js` + `scripts/sellersprite_integrated_runner_v0.3.7.user.js`。需要中文、P1 剩余目标、存储保护、卖家精灵访问熔断和一键 Excel 时，安装后经 smoke 才可改用加法式候选 `sellersprite_traffic_collector_v0.4.6_zh_p1.user.js` + `sellersprite_integrated_runner_v0.3.8.2_zh_excel.user.js`；同一页面绝不能同时启用两组。Runner `0.3.8.3` 仍是未部署的 P2 验证候选，不得在 30-ASIN 配对和单 ASIN smoke 前进入正式选品。将 `targetQualified` 设为最终交付数量，后续批次的 `remainingTargetAtStart` 只使用最新离线 replay 的剩余数。浏览器 pass 不能授予最终合格。
5. 每一批用一组重复的 `--batch-json` 和 `--candidates-json` 参数传入，同一 run 可累计多个批次。
6. `--candidates-json` 必须包含价格、评分、评论、上架、变体和图片等硬规则字段。
7. 合格数不足 `--target` 时继续追加新批次；不要把 rejected/review 补入 final。
8. 如果 `acceptance_checker.py` 返回非 0，先读对应 run 目录下的 `acceptance_report.md`，不要交付 final 表。

Integrated Runner 的安装与操作见 `scripts/SELLERSPRITE_INTEGRATED_RUNNER_HOW_TO.md`。其合并 JSON 可直接回放，不需要单独的 `--enrichment-json`。

Tier 2 解析、重试边界和 60-ASIN 配对证据见 `docs/tier2_reader_retry.md`。

Collector 0.4.7 / Runner 0.3.9 截止时间协议目前只是候选，不得用于正式选品。分区验证、30-ASIN flag-off/on 配对、沙盒 history、恢复复核门槛和回退点见 `docs/p2_collector_deadline_protocol.md`。

完整目标语义和多批命令见 `docs/qualified_target_pipeline.md`。
