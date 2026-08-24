# 给 Claude 的对接说明：Codex 已落地 Amazon US 选品闭环 pipeline

Claude 你好。你之前给的 `自动化选品闭环框架 v1.0` 已由 Codex 落地成可运行的 baseline。现在请按下面接口继续对接,不要再回到“跑固定 N 个后混合展示”的旧流程。

## 1. 当前落地位置

长期目录:

```text
C:\Users\13045\Desktop\amazon_products
```

核心文件:

```text
config\rules.json
config\exclusions.json
config\pipeline.json
scripts\replay_existing_batch.py
scripts\build_replay_workbooks.mjs
scripts\acceptance_checker.py
scripts\filter_engine.py
scripts\state_store.py
scripts\cache_store.py
scripts\qualified_pool_manager.py
PIPELINE_RUNBOOK.md
```

baseline run:

```text
runs\replay_20260710_baseline
```

baseline 输出:

```text
runs\replay_20260710_baseline\final_candidates_replay_20260710_baseline.xlsx
runs\replay_20260710_baseline\rejected_audit_replay_20260710_baseline.xlsx
runs\replay_20260710_baseline\acceptance_report.md
```

## 2. Codex 已实现的闭环

当前流程已经从旧的“混合验收表”改成:

```text
SellerSprite batch JSON
  -> 候选元数据 JSON
  -> 便宜字段预筛
  -> 禁限售/IP/健康化学硬排
  -> SellerSprite 流量硬过滤
  -> 图片检查
  -> qualified_pool.json
  -> final_candidates.xlsx + rejected_audit.xlsx
  -> acceptance_report.md
```

最终主表只从 `qualified_pool.json` 生成。任何 `prefilter_fail`、`excl_fail`、`traffic_error`、`hard_fail`、`hard_review`、`image_fail` 都只能进入 audit,不能进入 final。

## 3. 当前硬规则

不要把这些规则放宽,除非用户明确修改。

- 价格: `9.90 <= price <= 50.00`
- 评分: `rating >= 4.0`
- 评论: `reviews <= 100 + 15 tolerance`
- 上架: `launchAgeDays <= 90`
- 变体: `variationsCount <= 25`
- 月销硬顶: `monthlySales <= 1500`
- 自然流量严格 70%:
  - `latestNaturalSharePct >= 70`
  - `recent4AvgNaturalSharePct >= 70`
  - `recent4MinNaturalSharePct >= 70`
  - `weeksRead >= 3`
- 禁限售/IP/健康/化学/电池/穿戴等硬排优先于所有商业指标。
- 图片必须嵌入 Excel workbook;图片缺失不进 final。

说明: 你文档里曾建议 `recent4MinNaturalSharePct >= 40` 作为地板,但 Codex 按用户需求改成了严格 `>=70`。这点不要改回 40,否则会把 `B0GK11L4JF` 这类近4周最低不足 70 的品误放进 final。

## 4. baseline 验收结果

输入:

```text
C:\Users\13045\Documents\亚马逊电商选品\outputs\product_selection_20260708\batch_browser_panel_20260710_a54f68db.json
C:\Users\13045\Documents\亚马逊电商选品\outputs\product_selection_20260708\seller_refined_candidates.json
```

结果:

- 尝试 ASIN: 24
- 合格: 5
- 剔除审计: 19
- 停止原因: 候选源耗尽,未凑够目标 10 个
- 验收: PASS

合格 ASIN:

```text
B0GX7MVHV1
B0GSFSJKRF
B0GX56PWJH
B0H3P3KG2V
B0GVDDW8LC
```

验收通过项:

- final workbook exists
- audit workbook exists
- qualified pool count matches final data
- target met / attempts exhausted / source exhausted
- final 和 rejected 无 ASIN 重叠
- final 每行流量阈值通过
- final 每行上架天数通过
- final 每行图片文件存在
- xlsx media count >= final rows
- xlsx picture shapes >= final rows
- formula error strings absent

## 5. Claude 后续需要提供什么

下一批要继续补货时,请只负责给 Codex 准备两个输入。

### 5.1 SellerSprite batch JSON

必须保持 v0.2.x Batch Runner 输出结构,至少包含:

```json
{
  "schemaVersion": "sellerSpriteTrafficBatch/v0.2.0",
  "batchName": "Li-next-batch",
  "operator": "Li",
  "queueHash": "...",
  "results": [
    {
      "row": 1,
      "targetAsin": "B0XXXXXXXX",
      "actualAsin": "B0XXXXXXXX",
      "status": "ok",
      "latestWeek": "2026第27周(06/28~07/04)",
      "latestNaturalSharePct": 100,
      "recent4AvgNaturalSharePct": 97.52,
      "recent4MinNaturalSharePct": 94.62,
      "weeksRead": 8,
      "trafficWindow": "recent 2 months / max 9 weeks",
      "pass70": true,
      "asinMismatch": false,
      "note": "ok",
      "collectedAt": "2026-07-10T09:20:00+08:00"
    }
  ]
}
```

### 5.2 候选元数据 JSON

每个 ASIN 至少要有:

```json
{
  "asin": "B0XXXXXXXX",
  "title": "Original English title",
  "brand": "Brand",
  "price": 19.99,
  "rating": 4.8,
  "reviews": 12,
  "childSales": 300,
  "parentSales": 500,
  "launchDate": "2026-06-01",
  "variations": 1,
  "image": "https://m.media-amazon.com/images/I/....jpg",
  "sourcePage": 12
}
```

如果字段缺失,尤其是 `price`、`rating`、`launchDate`、`variations`、`image`,Codex 会按 fail 或 image_fail 处理,不会强行进 final。

## 6. Codex 当前运行命令

在 `C:\Users\13045\Desktop\amazon_products` 下运行:

```powershell
$env:PYTHONIOENCODING='utf-8'

& 'C:\Users\13045\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' scripts\replay_existing_batch.py --batch-json '<新的batch_json路径>' --candidates-json '<新的候选元数据json路径>' --image-dir '<已有图片缓存目录,可选>' --run-id '<新的run_id>' --process-all

& 'C:\Users\13045\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe' scripts\build_replay_workbooks.mjs 'C:\Users\13045\Desktop\amazon_products\runs\<新的run_id>'

& 'C:\Users\13045\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' scripts\acceptance_checker.py 'C:\Users\13045\Desktop\amazon_products\runs\<新的run_id>'
```

只有 `acceptance_checker.py` exit code 为 0 时,final 表才可以交付。

## 7. 对接边界

请 Claude 不要做这些事:

- 不要把 `rejected_audit.xlsx` 里的商品补进 `final_candidates.xlsx`。
- 不要把 `hard_review` 当成合格。
- 不要为了凑够 10 个而放宽 `recent4MinNaturalSharePct >= 70`。
- 不要只凭最新周自然流量通过就判定合格。
- 不要把图片 URL 当成图片嵌入通过。
- 不要重写 `build_replay_workbooks.mjs` 的 Excel 生成方式,除非要扩展列。

可以做这些事:

- 帮忙准备更大的 ASIN 候选池,建议 50-100 个。
- 帮忙补齐候选元数据 JSON。
- 帮忙检查 `rejected_audit.xlsx` 里高频剔除原因,提议扩充 `config\exclusions.json`。
- 帮忙把人工复核类目拆成更细的 `reviewFlags`,但不能变成自动通过。

## 8. 下一步建议

下一轮不要继续讨论框架,直接给 Codex 新的 batch JSON 和候选元数据 JSON。Codex 会继续跑:

```text
补候选 -> 过滤 -> qualified_pool 累计 -> final/audit 输出 -> acceptance PASS 后交付
```

如果目标是 10 个最终合格品,而 baseline 已有 5 个,下一批应至少再准备 50 个 ASIN。不要用 5 个剔除品补 final。
