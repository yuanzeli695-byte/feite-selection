# 亚马逊美国站选品脚本使用指南

更新日期：2026-07-28

适用脚本：SellerSprite Traffic Collector + SellerSprite Integrated Runner

## 1. 先确认版本

| 用途 | Collector | Runner | 状态 |
|---|---:|---:|---|
| 当前正式预检批准组合 | 0.4.6 | 0.3.7 | 正式选品默认使用 |
| P1 增强运行组合 | 0.4.6 | 0.3.8 | 已通过 live smoke，但 canonical preflight 仍登记 0.3.7 |
| 中文/Excel/P1 候选 | 0.4.6.2 | 0.3.8.2 | 增加卖家精灵访问熔断；安装后的 live smoke 待完成 |
| 快速闭环 v1 候选 | 0.4.6.2 | 0.3.10 | 三连瞬态失败熔断、单 Runner 租约、逐行离线计数；30-ASIN 配对和 live smoke 前禁止正式使用 |
| P2 实验组合 | 0.4.7 | 0.3.9 | 验证失败，禁止正式选品 |
| 完整回退组合 | 0.4.5 | 0.3.6 | 仅在 0.4.6/0.3.7 故障时使用 |

开始正式选品时，最稳妥的做法是只启用：

- `SellerSprite Traffic Collector 0.4.6`
- `SellerSprite Integrated Runner 0.3.7`

必须停用其他 Collector、其他 Runner、所有 `P2 ON` 和 `P2 OFF` 脚本。同一页面只能出现一个 Collector 面板和一个 Runner 面板。

Runner 0.3.8 不改变任何 A-F 门槛，增加的只是剩余目标控制、行内停止和细粒度遥测。中文候选 `0.4.6.2/0.3.8.2` 继续继承 P1，并增加存储失败闭环、一键 Excel 和卖家精灵登录/套餐权限熔断；遇到访问受阻时暂停并保留当前行，不写商品拒绝。完成安装后的 smoke 前，不要把它登记成 canonical。任何时候都不得同时启用两组脚本。

快速闭环 `0.4.6.2/0.3.10` 在独立存储命名空间中运行，浏览器通过数不再拥有停止权；逐行 checkpoint 经本机离线 A-F 回放后才更新停止计数。完整操作、发布门槛和回退见 `docs/selection_fast_loop_v1.md`。

## 2. 两个脚本分别负责什么

### Collector 0.4.6

Collector 只负责 C 关自然流量证据：

- 最多读取最近 4 周 SellerSprite tooltip；
- 至少需要 3 个有效周；
- 最新周、近 4 周平均值、近 4 周最低值都必须不低于 70%；
- 任意已读周低于 70% 会立即判定流量不通过；
- 输出当前 ASIN 的周明细、来源、判定和耗时证据。

Collector 通过不等于商品最终合格。它不负责完整的 A、B、D、E、F 关，最终放行仍由离线 replay 和 acceptance checker 决定。

### Integrated Runner

Runner 负责批量调度，并按以下顺序短路采集：

1. ASIN 一致性；
2. C 关自然流量；
3. D 关尺寸和重量；
4. E 关当前价格与价格趋势。

前一关失败后，不再采集后面的昂贵数据。Runner 显示的 `Qualified` 或 browser pass 只是浏览器采集结果，不是最终入选权。

## 3. 运行前准备

1. 使用已经登录且具备“流量洞察”权限的 SellerSprite Chrome；免费会员或套餐过期不能运行严格流量门槛。
2. 打开 `amazon.com` 美国站，并确认配送地址是美国 ZIP。
3. 关闭 Chrome 自动翻译。
4. 确认 SellerSprite 流量图和 Keepa 替代价格图可以加载。
5. ScriptCat 只启用一个 Collector 和一个 Runner。
6. 正式运行前在项目目录执行预检和历史同步：

```powershell
cd C:\Users\13045\Desktop\amazon_products

python "$env:USERPROFILE\.codex\skills\amazon-us-strict-selection\scripts\preflight.py" `
  --project-root "C:\Users\13045\Desktop\amazon_products"

python scripts\strict_history.py --write
```

预检必须返回 `ok: true`。历史中已经严格合格的 ASIN 会在候选准备和 Runner Generate 阶段跳过，不能再次计入目标。

## 4. 准备候选队列和主图

先用 SellerSprite 的严格查询预设导出 `query_*.json`，并生成与导出同时绑定的 `source_manifest.json`。正式来源必须是美国站、24 小时内、非空类目节点、`maxReviews<=100`，清单需记录每个查询 URL 和文件 SHA-256。SellerSprite `5000+`、空类目或旧导出不得进入正式队列。

```powershell
python scripts\prepare_strict_candidate_pool.py `
  --input-dir runs\RUN_ID\source_queries `
  --source-manifest runs\RUN_ID\source_manifest.json `
  --output-dir runs\RUN_ID\candidate_pool `
  --queue-name strict_queue_01 `
  --queue-size 40 `
  --run-date YYYY-MM-DD
```

检查候选池中的：

- `sourceContract.mode` 必须为 `formal`；
- 来源清单时间、美国站、类目节点、查询和哈希均已验证；
- `duplicateConflictCount`，冲突 ASIN 必须留在拒绝审计；
- 历史跳过数量；
- 本地硬筛淘汰原因；
- 必填字段完整性；
- 最终进入 Chrome 的 ASIN 数量和顺序。

随后下载主图：

```powershell
python scripts\download_candidate_images.py `
  runs\RUN_ID\candidate_pool\strict_queue_01.json `
  runs\RUN_ID\source_images `
  --report runs\RUN_ID\image_download_report.json
```

图片下载失败的 ASIN 必须修复或淘汰，不能进入最终工作簿。

`--allow-legacy-source` 只用于紧急回退，它明确没有来源新鲜度、查询范围和哈希保证；不要把它当作正式日常命令。排序默认是 `tier1.2-probability-v2`（28-90 天最高年龄分），`--use-ranking-v1` 只回退排序，不会放宽硬筛。

## 5. Collector 面板怎么用

- `Check Page`：只检查当前 ASIN、SellerSprite 可见性和图表状态，不开始采集。
- `Collect Traffic`：手工采集当前单品的流量证据。
- `Copy Text`：复制人类可读摘要。
- `Copy JSON`：复制当前单品完整 JSON。
- `Copy Gate TSV`：复制当前 C 关日志。
- `Copy Timing TSV`：复制当前耗时日志。

正式批量选品通常不需要逐个点击 `Collect Traffic`，由 Runner 自动调用 Collector。单品按钮主要用于 smoke、故障排查和人工审计。

Collector 状态含义：

- `pass`：只表示 C 关流量通过；
- `sample_low_review`：有效周不足 3 周，不通过；
- `no_data`：没有取得有效 tooltip，不通过；
- `no_chart_loaded`：等待期内图表未出现，不通过；
- `error`：采集异常，不通过。

不得手工补数、修改 JSON、用 `--` 推导比例或把 review 改为 pass。

## 6. Runner 面板怎么填写

- `batchName`：填写唯一批次名，例如 `strict20_20260717_batch01`。
- `operator`：填写实际操作者，例如 `Codex`。
- `targetQualified`：填写整次任务最终需要交付的严格合格数量，不是队列长度。
- `QUEUE input`：一行一个经过历史去重、本地硬筛和图片检查的 ASIN。

例如最终要 20 个合格品，可以放入 40-80 个候补 ASIN，并将 `targetQualified` 填为 `20`。

使用 Runner 0.3.8 时还会看到 `remainingTargetAtStart`：

```text
remainingTargetAtStart = 最终目标 - 当前离线 replay 已合格数量
```

第一批通常与最终目标相同。后续批次必须先离线 replay，再重新计算剩余数量。该字段只控制浏览器停止预算，不能直接授予合格。

## 7. Generate 和 Start

1. 粘贴队列后点击 `Generate`。
2. 核对 `batchName`、queue hash、目标数量和队列数量。
3. 检查 `History auto-skipped`。历史命中只能算 skip，不能计入本批合格数。
4. 确认面板版本唯一后点击 `Start`。
5. 采集期间不要刷新、切换标签、滚动页面或移动鼠标。
6. 遇到 CAPTCHA、SellerSprite 登录失效、重复面板、ASIN 重定向或 parser error 时立即暂停，不要继续强跑。

Runner 0.3.7 只会对明确的图表或 tooltip 未就绪状态最多重试一次。真实低流量、已有 1-2 个有效周但不足 3 周、普通异常和歧义数据不会为了提高通过率而重试。

Runner 0.3.8 的 `Stop after current row` 会让当前 ASIN 完整保存后再停止；它与 `Pause` 不同，不会制造半条结果。

## 8. 完成后必须导出什么

Runner 状态变为 `done` 后，先导出证据，再清理批次：

- `Copy combined JSON`；
- `Copy enrichment JSON`，如面板提供；
- `Copy gate log TSV`；
- `Copy timing log TSV`。

使用 Runner 0.3.8 时额外保存：

- granular JSON；
- granular timing TSV；
- control TSV。

建议文件名：

```text
batch_01_combined.json
batch_01_enrichment.json
batch_01_gate.tsv
batch_01_timing.tsv
batch_01_granular.json
batch_01_granular_timing.tsv
batch_01_control.tsv
```

## 9. 离线回放和最终验收

浏览器完成后不能直接交付 Excel，必须将 batch JSON 和对应 candidates JSON 配对回放：

```powershell
python scripts\replay_existing_batch.py `
  --batch-json runs\RUN_ID\batch_01_combined.json `
  --candidates-json runs\RUN_ID\candidate_pool\strict_queue_01.json `
  --image-dir runs\RUN_ID\source_images `
  --run-id RUN_ID `
  --target 20 `
  --overwrite
```

有多批时，按顺序重复传入相邻的 `--batch-json` 和 `--candidates-json`。合格数不足目标时继续增加新候选和新批次，不得把 reject 或 review 补进 final。

生成并验收工作簿：

```powershell
node scripts\build_replay_workbooks.mjs runs\RUN_ID
python scripts\acceptance_checker.py runs\RUN_ID
```

只有 `acceptance_checker.py` 返回退出码 0，并且预览中图片、标题、价格、百分比和行对齐全部正常，才算交付完成。

## 10. 当前硬门槛摘要

- 禁限售、IP、健康/医疗/化学等风险先于商业指标；
- 当前价格 USD 9.90-50.00；
- 评分至少 4.0；
- 上架不超过 90 天；
- 变体不超过 25；
- 子体月销量超过 1500 硬淘汰；
- 自然流量有效周至少 3 周，最新/平均/最低都不低于 70%；
- 尺寸和重量必须有真实来源；
- 价格趋势只能是 `stable` 或 `rising`；
- 必须有精确 ASIN 的可下载并嵌入主图。

## 11. 我做过的主要改动

### Collector 0.4.6

相对 0.4.5，新增了受保护的明确零值解析：只有“总流量大于 0，且自然流量字面值为 0”时才能推导 `0%`。`--`、缺失、歧义值和 `0/0` 仍保持缺失。这个改动只会更早拒绝，不会制造通过。

同时增加了 Gate/Timing 遥测、runId、来源和读取器版本等审计字段。Collector 本身不拥有最终放行权。

### Runner 0.3.7

相对 0.3.6，将无条件重试收紧为 readiness-only 重试：只对明确的图表或 tooltip 未就绪最多重试一次。低流量、部分有效样本和普通异常不重试，减少无意义等待，并保持零假阳性。

### Runner 0.3.8 P1

没有修改门槛、解析和重试，只增加：

- `remainingTargetAtStart` 累计剩余目标控制；
- `Stop after current row`；
- granular JSON/TSV/control TSV 细粒度遥测；
- 对异步暂停/停止状态的持久化保护。

它已经通过独立 live smoke，但当前项目的 canonical preflight 仍登记 Runner 0.3.7。

### Collector 0.4.7 + Runner 0.3.9 P2

P2 尝试统一 Collector/Runner 的超时截止时间，并加入 heartbeat、hidden/throttled 检测、fresh run ID、quarantine、pending recovery 和 sandbox history。

真实 45 对 ASIN 验证没有达到放行门槛：genuine recovery 为 0，partial-to-full 为 0/32，出现 1 个 false positive，总耗时增加约 19.7%，p90 增加约 14.3 秒。因此 P2 ON 和 P2 OFF 都不得用于正式选品。

## 12. 开跑前快速检查

- [ ] Amazon 美国站和美国配送地址已确认；
- [ ] Chrome 自动翻译已关闭；
- [ ] SellerSprite 已登录且流量/价格图可见；
- [ ] SellerSprite 账号不是免费会员，且“流量洞察”没有显示升级套餐提示；
- [ ] 只启用 Collector 0.4.6；
- [ ] 只启用 Runner 0.3.7，或明确选择已 smoke 的 0.3.8；
- [ ] 所有 0.4.7/0.3.9 P2 ON/OFF 已停用；
- [ ] preflight 返回 `ok: true`；
- [ ] strict history 已同步；
- [ ] 候选已完成硬筛、历史去重和主图下载；
- [ ] `targetQualified` 填的是最终合格目标，而不是队列长度；
- [ ] 已准备保存 combined、gate、timing 和必要的 granular 证据；
- [ ] 最终会运行 replay、workbook build 和 acceptance checker。
