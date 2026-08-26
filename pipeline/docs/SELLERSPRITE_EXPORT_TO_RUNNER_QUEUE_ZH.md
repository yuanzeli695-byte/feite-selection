# 卖家精灵导出到 Runner ASIN 队列

脚本 `scripts/sellersprite_export_to_runner_queue.py` 将卖家精灵的 `.xlsx`、`.csv` 或 `.tsv` 导出表转换为 Runner 可导入的纯 ASIN 队列。它会映射中文或英文常用列名、拒绝缺失或无法确定的硬字段、同步严格历史去重，并复用 `prepare_strict_candidate_pool.py` 的硬预筛。

这是 Tier 1 候选缩减，不是最终 A-F 选品放行。队列中的 ASIN 仍须经既有 Runner 和完整严格审核；脚本不会修改 Runner、Collector、共享规则或正式历史结果。

## 导出前

在卖家精灵中保留美国站和最近 30 天等当前查询条件，导出当前全部结果，并勾选“导出主图”。导出完成后，复制浏览器地址栏中当前“产品研究”页面的完整 URL，并记录导出时刻。

正式模式要求导出表中可识别这些字段：ASIN、商品名称、品牌、类目、子体销量、价格、评分、评分数、变体数、上架时间和主图链接。卖家精灵当前导出中的 `价格($)` 和 `商品主图` 已被明确支持；当同时存在通用缩略图列 `图片` 时，程序只使用明确的 `商品主图`，不会把缩略图当作主图来源。`月销量`、`父体销量` 可选。表头不能重复映射同一字段；主图必须是 `http` 或 `https` URL，不能仅是嵌入图片。

导出的 ASIN 单元格即使带有亚马逊超链接，程序也使用单元格显示的 ASIN；只有明确主图字段允许使用其超链接目标。

`.xlsx` 输入需要当前 Python 环境具备 `openpyxl`；若命令提示缺失，先执行 `python -m pip install openpyxl`。`.csv` 和 `.tsv` 输入不需要该依赖。

默认要求子体销量。经业务明确授权后，可在命令中加入 `--allow-missing-sales`：父体、子体和月销量都可以保持缺失，程序不会估算或互相替代，且摘要会记录该队列专用覆盖。此覆盖不改变 Runner A-F 最终放行。

## 正式命令

在项目根目录执行。每次使用一个新的 `--output-dir`，避免覆盖原始审计产物。

```powershell
python scripts\sellersprite_export_to_runner_queue.py `
  "C:\Users\13045\Downloads\Product-Storage-US-Last-30-days.xlsx" `
  --output-dir "runs\storage_20260731_01" `
  --queue-name "storage_20260731_01" `
  --queue-size 40 `
  --allow-missing-sales `
  --query-url "粘贴当前卖家精灵产品研究页面的完整 URL" `
  --captured-at "2026-07-31T16:30:00+08:00"
```

成功后导入 Runner 的文件是：

```text
runs\storage_20260731_01\candidate_pool\asin_queue_storage_20260731_01.txt
```

同时保留 `normalized_candidates.json`、`normalization_rejected.json`、`source_manifest.json`、严格候选池的拒绝清单和 `queue_adapter_summary.json`。后者列出本批最终 ASIN 序列，可直接把导出文件交给 Codex 后读取并发回该序列。

## 失败说明

脚本默认失败闭合：表头不匹配、主图不是 URL、数字是区间/估算值、上架日期无法解析、历史重复或硬预筛不通过，都不会进入队列。若剩余 ASIN 不足，命令失败并保留已生成的审计产物；应调整卖家精灵查询后重新导出至新的输出目录。

如果只能恢复一份历史导出且无法提供原始查询 URL 与采集时间，必须显式使用 `--allow-legacy-export`。此模式在摘要中标记为 `legacy_export`，不可作为正式来源证据或最终放行依据：

```powershell
python scripts\sellersprite_export_to_runner_queue.py "C:\path\export.xlsx" `
  --output-dir "runs\legacy_recovery_01" `
  --queue-name "legacy_recovery_01" `
  --allow-legacy-export
```

回退方式是停止使用新脚本并只删除本次新建的 `--output-dir`；它不改写现有 Runner、规则或交付文件。
