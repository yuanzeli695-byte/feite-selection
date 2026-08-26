# 合并 JSON 一键生成严格选品 Excel

`scripts/build_excel_from_merged_json.py` 用于把一个或多个 Runner“复制合并 JSON”快照直接转换为机器验收后的中文 Excel。它是独立编排入口，不替换 Collector、Runner、A-F 离线回放、工作簿渲染器或验收器。

版本标识：`merged-json-to-excel-v1.1.0`。

## 适用方式

以后可以直接把 Runner 面板复制出的合并 JSON 发给 Codex。Codex 只需为严格通过的 ASIN 准备一份中文标题映射，再运行一个命令；程序会自动完成：

1. 校验 batch schema、状态、queue/results 唯一性、严格通过状态及 ASIN 一致性。
2. 校验显式允许的 Runner/Collector 版本；版本漂移不会自动放行。
3. 在 `runs/` 中扫描正式候选 JSON，忽略 enrichment、图片报告等相似 JSON，并选择能覆盖完整 queue 的唯一最小候选集。
4. 固化原始 batch、候选文件、中文标题和 SHA-256 证据。
5. 只下载合并 JSON 中严格通过 ASIN 的主图；默认最多 4 路并发，并使用 60 分钟的 ASIN + 图片 URL 缓存。
6. 在正式 history 的隔离副本上调用现有 `replay_existing_batch.py`。
7. 调用现有 `build_replay_workbooks.mjs` 和 `acceptance_checker.py`。
8. 生成最终工作簿、剔除审计工作簿、预览图、验收报告和 `automation_result.json`。

## 输入要求

- 一个或多个 `sellerSpriteIntegratedBatch/v0.3.0` JSON 文件。
- 默认只接受 `status=done`。仍在运行但已经复制固化的快照必须显式增加 `--allow-running-snapshot`。
- 所有实际出现的 Runner 和 Collector 版本必须分别用 `--allow-runner-version`、`--allow-collector-version` 明确列出。
- 每个 `qualified=true + strictDecision=pass` 行都必须同时具备 `status=ok`、`decision=pass`、目标/实际 ASIN 一致和 Collector 版本。
- 中文标题 JSON 必须是 `{ "ASIN": "中文品名" }` 对象，并覆盖全部严格通过 ASIN。
- 输出目录必须位于项目根目录之外，且运行前不存在。

`running` 快照只代表本次复制内容被当作不可变证据使用；它不会把未完成 queue 当成已采集，也不会为未出现的结果补数据。

## 命令

```powershell
python scripts\build_excel_from_merged_json.py `
  --batch-json "C:\path\batch-1.json" `
  --batch-json "C:\path\batch-2.json" `
  --output-dir "C:\path\outside-project\excel-run" `
  --title-overrides "C:\path\zh_title_overrides.json" `
  --allow-runner-version 0.3.8.2 `
  --allow-runner-version 0.3.8.5 `
  --allow-collector-version 0.4.6.2 `
  --allow-running-snapshot `
  --run-id merged_json_excel_20260731 `
  --run-date 2026-07-31
```

正常的 `done` 批次不要加 `--allow-running-snapshot`。如果候选文件不在默认 `runs/` 下，可重复增加 `--candidate-search-root`。只有在 Codex 运行环境无法自动发现打包 Node 时才需要传 `--node-exe` 和 `--node-modules`。

## v1.1 性能策略

- `bounded_parallel_image_cache_v1`：图片下载默认 `--image-workers 4`，上限固定为 8。它只并发访问当前候选行已记录的 Amazon 主图 URL，不并发 Chrome、SellerSprite、Collector 或 Runner。
- 持久缓存默认位于 `%USERPROFILE%\.cache\amazon-products\candidate-images-v1`。缓存键同时包含 ASIN 和完整图片 URL，命中时仍会重新解码 PNG；超过 `--image-cache-ttl-minutes 60` 后必须重新联网下载。
- `force_exit_after_awaited_build_v1`：最终 XLSX、预览图和 `workbook_build_report.json` 全部 `await` 完成后结束 Node 进程，随后仍照常运行独立 `acceptance_checker.py`。
- 两项策略及参数会写入 `evidence_manifest.json` 和 `automation_result.json`，不会改变 A-F 结果、target、图片必需规则、回放或验收。

2026-07-31 真实验证中，同一 64 个图片 URL 的旧串行下载为 38.32 秒，4 路冷缓存为 8.28 秒，热缓存为 0.49 秒；64/64 图片门槛结论一致。相同 6 品完整 Excel 流程由原平均 18.93 秒降至冷缓存 10.47 秒、热缓存 5.68 秒，三次结果均为 6/6 严格合格并通过机器验收。

## 成功与失败

成功时退出码为 `0`，并且 `automation_result.json` 中：

- `accepted=true`
- `machineAcceptancePassed=true`
- `visualAcceptanceRequired=true`
- `productionHistoryUpdated=false`

离线回放不足目标时退出码为 `3`，保留证据和回放目录，但不构建可交付工作簿。输入、版本、候选配对、图片、渲染或验收失败时退出码为 `2`。任何失败都不得通过降低 target、放宽门槛或修改原始 JSON 解决。

机器验收后仍必须检查全部预览图、主图与 ASIN 对齐、中文标题、行列尺寸及工作簿三层结构，再将该次结果记为人工预览通过。

## history 与回退

程序只把 `history/strict_qualified_asins.json` 复制到输出目录中的 `sandbox_project/history/`。运行前后会比较正式 history 的 SHA-256；程序不会自动更新正式 history。

只回退 v1.1 性能策略时，在原命令末尾增加：

```powershell
  --image-workers 1 `
  --disable-image-cache-v1 `
  --disable-workbook-force-exit-v1
```

该回退已用同一 6 品批次验证，仍为 6/6 严格合格并通过机器验收。完整回退无需改 Collector、Runner、规则或 history；停止使用独立入口，继续按 `docs/selection_zh_excel_guide.md` 的 Excel Bridge 或标准 replay/build/acceptance 命令操作即可。
