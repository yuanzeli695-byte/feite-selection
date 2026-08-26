---
from: claude
to: codex
priority: p0
requires_action: yes
tags: [qualified_target, traffic_gate, workbook_contract, pipeline_orchestration, batch3_correction]
---

# 最终合格数量语义与自然流量 70% 硬门槛执行指令

Codex，用户已复核 Batch3 工作簿。表格视觉和主图位置可以保留，但当前交付把“尝试采集的 20 个候选”误当成了“选出的 20 个商品”。本指令立即覆盖任何把候选数、尝试数或 Batch Runner 队列长度当成交付数量的旧口径。

## 0. 必须先理解的执行结论

1. 用户说“选 20 个品”，`20` 指 **最终严格合格品数量**，不是候选数量，也不是 Batch Runner 跑过的数量。
2. 自然流量是选品硬门槛，不只是表格展示字段。
3. 任何自然流量指标低于 70%、数据缺失、超时、样本不足、ASIN 跳转待复核的商品，都不得进入最终交付主表。
4. 如果首批 20 个候选只合格 3 个，就必须继续寻找和运行新候选，直到合格池达到 20 个，或者真实候选源耗尽并向用户明确报告。
5. 本次问题不需要修改 Chrome 中的 Collector 0.4.2 或 Batch Runner 0.2.x。修复点在 Codex 的选品编排、合格池累积、工作簿数据源和验收门禁。

## 1. Batch3 问题与真实根因

当前文件：

`C:\Users\13045\Desktop\amazon_products\runs\new_20260711_batch3_20\batch3_20_products_with_main_images.xlsx`

当前 Batch3 结果：

- 尝试候选：20
- 严格合格：3
- 需要复核：5
- 淘汰：12
- 采集正常：19
- 超时：1

Pipeline 的分类数据本身已经正确：

- `final_candidates_data.json`：3 个严格合格品
- `qualified_pool.json`：3 个严格合格品
- `rejected_audit_data.json`：17 个淘汰或复核品

错误发生在临时工作簿生成层：

`C:\Users\13045\AppData\Local\Temp\batch3_workbook\build_batch3_workbook.mjs`

该临时脚本用 `allRows = candidates.map(...)` 构建 `20品结果`，把 20 个候选全部写进了主表，再用“严格结论”列区分。这违反最终交付语义。

不要误改以下已经正确的标准逻辑：

- `scripts/filter_engine.py` 已对三个自然流量指标执行 70% 硬门槛。
- `scripts/replay_existing_batch.py` 已把不合格项写入 rejected audit，把合格项写入 qualified pool。
- `scripts/build_replay_workbooks.mjs` 已声明“本表只写入 state=QUALIFIED 的商品”，并从 `final_candidates_data.json` 构建最终表。

正式流程禁止继续使用 `AppData\Local\Temp` 下的临时 builder 作为生产交付逻辑。若要保留 Batch3 的视觉样式，应把样式迁入仓库内的标准 builder，但数据源必须仍是 `final_candidates_data.json`。

## 2. `targetN` 的唯一语义

从本指令开始：

```text
targetN = 用户要求的最终严格合格商品数量
attempts = 为得到 targetN 而实际检查过的候选数量
queueLength = 某一次 Batch Runner 运行的候选数量
qualifiedCount = 已进入合格池的数量
completedTarget = qualifiedCount == targetN
```

严禁再使用以下错误等式：

```text
targetN == queueLength
目标20品 == 跑完20个候选
工作簿有20行 == 已完成20品选品
```

假设用户要求 20 个最终品，第一轮跑 20 个只合格 3 个，正确状态必须是：

```text
目标：20
已合格：3
仍缺：17
尝试：20
状态：未完成，继续寻找候选
```

## 3. 自然流量硬门槛

候选只有同时满足以下条件，流量阶段才算通过：

```text
traffic.status == "ok"
traffic.asinMismatch != true
traffic.weeksRead >= 3
traffic.latestNaturalSharePct >= 70
traffic.recent4AvgNaturalSharePct >= 70
traffic.recent4MinNaturalSharePct >= 70
```

同时还必须通过 `config/rules.json` 和 `config/exclusions.json` 的其他全部硬规则，才能进入最终合格池。

以下情况一律不得进入最终表：

| 情况 | 处理 |
|---|---|
| 任一自然流量指标 `< 70%` | 淘汰，写入 audit |
| 自然流量指标缺失 | 淘汰，写入 audit |
| `weeksRead < 3` | 需要复核，但不进 final |
| `status=timeout/error/no_data` | 淘汰或复核，但不进 final |
| `asinMismatch=true` | 需要复核，但不进 final |
| 其他硬规则失败 | 淘汰，写入 audit |
| `decision=review` | 只进 audit，绝不算合格 |

“自然流量低于 70% 不要统计在表格中”的正式含义是：不得出现在面向用户的最终合格商品工作簿中。为审计保留的信息应写入单独的 audit 工作簿，不得混入主表。

## 4. 自动选品循环

Codex 需要把流程实现为“合格池驱动”，而不是“固定候选数驱动”：

```text
读取 targetN
  -> 搜索一批新候选
  -> 历史 ASIN 和本轮 ASIN 去重
  -> 基础商业指标与禁限售预筛
  -> 把仍可能合格的候选送入 Chrome Batch Runner
  -> 保存原始 batch JSON
  -> replay_existing_batch.py 执行统一硬规则
  -> 只把严格合格项加入 qualified pool
  -> qualifiedCount < targetN：继续搜索下一批
  -> qualifiedCount == targetN：生成最终工作簿
  -> acceptance_checker.py 全部通过后才允许交付
```

实现要求：

1. 新增或完善仓库内的 orchestration 入口，例如 `scripts/run_until_target.py`。名称可以调整，但职责必须清楚。
2. 每轮新队列不得包含历史已合格 ASIN、本 run 已尝试 ASIN或当前合格池 ASIN。
3. 合格池必须可跨多个 Batch Runner JSON 累积，不能每跑一批就覆盖前一批结果。
4. 达到目标后立即停止继续补货；合格池多于目标时，按明确且稳定的排序规则截取 targetN，并把排序依据写入 run summary。
5. 如果候选源耗尽或达到合理的最大尝试数，状态应是 `partial/not_completed`，不得伪装成已完成。
6. 未达到 targetN 时，除非用户明确同意部分交付，否则 acceptance 必须失败，禁止交付最终表。

## 5. Chrome 脚本职责边界

本次不要修改：

- SellerSprite Traffic Collector `0.4.2`
- SellerSprite Batch Runner `0.2.x`

原因：Chrome 脚本应继续负责原始流量采集和 batch JSON 输出，过滤决策应由仓库中的统一规则引擎完成。这样才能保留完整 audit 数据，并避免 Chrome 脚本与 `config/rules.json` 发生阈值漂移。

只有出现以下证据时，才另开任务修改 Chrome 脚本：

- 无法稳定输出三个自然流量字段；
- `weeksRead` 或时间窗口无法辨认；
- Batch JSON 字段语义与当前 schema 不一致；
- Collector/Runner 自身漏数据或覆盖数据。

如确需修改，先向 `handoffs/inbox_for_claude/` 写问题报告，列明实际 JSON 样例和缺失字段，不得直接在用户 Chrome 中静默升级。

## 6. 工作簿交付契约

### 6.1 最终工作簿

输出：

`runs/<runId>/final_candidates_<runId>.xlsx`

要求：

- 主工作表命名为 `最终合格品`。
- 数据源只能是 `final_candidates_data.json` 或等价的 `state=QUALIFIED` 集合。
- 每一行必须通过所有硬规则，不能包含 `需复核` 或 `淘汰`。
- 保留 Batch3 用户认可的中文表格风格。
- `ASIN` 右侧紧邻 `主图` 列，主图必须嵌入 Excel，不能只放 URL。
- 保留中文品名、英文原始标题、Amazon 链接、价格、销量、评论、评分、上架信息、变体、三个自然流量指标、周数、流量窗口和审计来源。
- 最终表行数必须等于 targetN，除非用户书面同意部分交付。

### 6.2 剔除审计工作簿

输出：

`runs/<runId>/rejected_audit_<runId>.xlsx`

要求：

- 单独文件，不与最终主表混装。
- 保存淘汰和复核商品、失败阶段、规则 ID、具体阈值、实际值、流量窗口和原始 ASIN。
- audit 的存在不能被当作“这些商品也属于选品结果”。

## 7. 验收门禁必须收紧

当前 `scripts/acceptance_checker.py` 把以下任一情况视为可结束：

```text
qualified == target
或 attempts >= maxAttempts
或 sourceExhausted == true
```

这只能说明“运行结束”，不能说明“交付目标完成”。必须拆成两个状态：

```text
runFinished = 达到目标、达到最大尝试数或候选源耗尽
deliveryComplete = qualifiedCount == targetN
```

默认 acceptance 必须要求 `deliveryComplete == true`。如需部分交付，必须使用显式参数（例如 `--allow-partial`）并在 acceptance report 中记录用户授权；不能默认放行。

最终交付至少通过以下检查：

1. `qualifiedCount == targetN`。
2. 最终工作簿数据行数等于 `qualifiedCount`。
3. 最终工作簿 ASIN 集合与 `final_candidates_data.json` 完全一致。
4. 最终 ASIN 与 rejected ASIN 无交集。
5. 每行 `latestNaturalSharePct >= 70`。
6. 每行 `recent4AvgNaturalSharePct >= 70`。
7. 每行 `recent4MinNaturalSharePct >= 70`。
8. 每行 `weeksRead >= 3`。
9. 最终数据行中不存在“需复核”“淘汰”“timeout”“no_data”。
10. 嵌入图片数等于最终商品行数，且图片位于 ASIN 右侧列。
11. `xl/media`、图片 shape、公式错误和预览检查全部通过。
12. 生成 Markdown acceptance report，明确写出目标数、合格数、尝试数和是否完成目标。

任何一项失败，命令退出码必须非 0，禁止把工作簿标记为最终交付。

## 8. Batch3 立即整改

先保留当前文件作为“20 个尝试项的审计快照”，不要覆盖或删除：

`batch3_20_products_with_main_images.xlsx`

然后执行：

1. 使用 `final_candidates_data.json` 重新生成只含 3 个严格合格品的 partial 工作簿。
2. 3 个严格合格 ASIN 应为：
   - `B0GTYFBN9F`
   - `B0GWCPW954`
   - `B0GX12QFSV`
3. 17 个淘汰/复核项写入独立 audit 工作簿。
4. partial 文件名和表内摘要必须明确写“目标 20，当前合格 3，未完成”，不得称为“20 品最终结果”。
5. 修复自动循环后继续补充新候选，排除 Batch3 已尝试的 20 个 ASIN和历史 ASIN，直到合格池达到 20。
6. 达到 20 后再生成真正的 `final_candidates_<runId>.xlsx` 并交付。

## 9. 禁止事项

- 不得把 `candidates_raw.json`、Batch Runner 全部结果或 `allRows` 直接写入最终主表。
- 不得为了凑数量把 `review` 或 `rejected` 商品补入 final。
- 不得降低三个 70% 阈值或减少 `weeksRead >= 3` 要求。
- 不得把“跑了 20 个候选”描述成“完成 20 个选品”。
- 不得继续依赖 Temp 目录下的临时 workbook builder。
- 不得仅通过改工作表名称掩盖数据源错误。
- 不得在没有证据的情况下修改用户 Chrome、ScriptCat、Collector 或 Batch Runner。

## 10. Codex 完成后必须回执

处理完成后，在 `handoffs/inbox_for_claude/` 写回执，至少包含：

- 修改过的仓库文件及其职责；
- 是否修改 Chrome 脚本，预期答案应为“否”；
- Batch3 corrected partial workbook 路径；
- rejected audit workbook 路径；
- 自动补足到 targetN 的实现方式；
- 最终 qualified / attempted / rejected 数量；
- acceptance 命令和 PASS/FAIL 结果；
- 尚未解决的阻断项。

回执命名建议：

`YYYYMMDD_HHMM_codex_to_claude_reply_to_qualified_target_traffic_gate.md`

处理本报告后，按 `handoffs/PROTOCOL.md` 将本文件归档到 `handoffs/archive/2026-07/`。

## 11. 优先级

这是 P0 交付语义修复。在完成这项修复前，不要再向用户交付新的“20 品结果表”，因为当前流程可能继续把尝试项误报为最终合格品。
