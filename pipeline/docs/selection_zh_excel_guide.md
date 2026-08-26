# 亚马逊美国站严格选品中文面板与 Excel 使用指南

## 1. 适用范围

本指南适用于以下两个候选用户脚本：

| 用途 | 文件名 | 面板版本 |
| --- | --- | --- |
| 读取卖家精灵自然流量 | `scripts/sellersprite_traffic_collector_v0.4.6_zh_p1.user.js` | `0.4.6.2` |
| 批量选品、离线回放及 Excel 入口 | `scripts/sellersprite_integrated_runner_v0.3.8.2_zh_excel.user.js` | `0.3.8.2` |

这两个脚本基于 Collector `0.4.6` + 已完成 live smoke 的 Runner `0.3.8` P1 逻辑，保留相同 A-F 门槛、Collector 读取顺序、重试边界及离线放行权，并增加中文面板、存储配额保护和受机器验收保护的 Excel 本机桥接。它们不是 P2 候选版，canonical 预检登记仍保持 `0.4.6/0.3.7`。

> 不要在正式选品中启用 Collector `0.4.7` / Runner `0.3.9` 的 `P2 ON` 或 `P2 OFF` 脚本。P2 已在真实配对验证中失败，不得用于正式选品。

## 2. 运行前准备

1. 使用已登录且具备“流量洞察”权限的卖家精灵 Chrome 会话。免费会员或套餐过期时无法完成严格流量门槛。
2. 打开 `amazon.com`，将收货地设为美国邮编，正式运行不得使用非美国地址。
3. 关闭 Chrome 自动翻译。两个脚本面板已是中文，页面翻译可能改写卖家精灵 DOM，导致采集失败。
4. 使用 `prepare_strict_candidate_pool.py --source-manifest ...` 准备正式候选 JSON。来源清单必须是 24 小时内的美国站导出，带非空类目节点、`maxReviews<=100`、查询 URL 和输入文件 SHA-256，格式见 `docs/strict_candidate_source_contract_v1.md`。SellerSprite 显示 `5000+`、类目为空、字段不完整或使用旧导出的结果，不得直接进入 Runner。
5. 准备主图目录；主图目录必须包含最终候选 ASIN 的可用图片。
6. 不要把历史已严格合格的 ASIN 重新加入队列。Runner 会再次自动过滤，但最好在进入 Chrome 前就完成 history 去重。

## 3. ScriptCat 安装与启用

1. 在 ScriptCat 中安装上表两个 `.user.js` 文件。可直接用 ScriptCat 打开本地脚本安装；如未弹出安装页，在 ScriptCat 中新建脚本并粘贴完整文件内容。
2. 禁用其他所有 SellerSprite Collector 和 Runner，包括旧中文版、`0.3.8`、所有 P2 ON/OFF 候选版及 legacy Batch Runner。
3. 只启用：
   - `卖家精灵流量采集器 0.4.6.2 中文 P1 版`，面板版本应显示 `0.4.6.2`；
   - `卖家精灵一体化选品 0.3.8.2 中文 Excel 版`，面板版本应显示 `0.3.8.2`。
4. 刷新一个 Amazon 商品页，确认只有一个左下角 Collector 面板和一个右侧 Runner 面板。

如出现重复面板、版本不符、CAPTCHA、卖家精灵未登录或流量图无法打开，立即停止，不要强制继续。

## 4. Collector 中文面板

Collector 面板位于页面左下角，主要按钮如下：

- `检查当前页面`：显示当前 ASIN、卖家精灵可见性和页面状态，适合开始前排查。
- `采集自然流量`：单页手工采集，主要用于诊断或单 ASIN 复核。
- `复制摘要`：复制中文摘要。
- `复制完整 JSON`：复制完整原始采集结果。
- `复制门槛 TSV` / `复制耗时 TSV`：导出门槛与性能审计记录。

正式批量运行时，Runner 会自动调用 Collector，通常不需要手工点击“采集自然流量”。Collector 显示“正在采集”时，不要移动鼠标、切换标签页、刷新页面或滚动流量图。

## 5. Runner 中文面板

### 5.1 生成批次

1. `批次名称`：使用唯一、可追踪的名称，例如 `strict20-20260717-b01`。
2. `操作人`：填写实际操作人。
3. `最终合格目标数`：填写本次最终要交付的严格合格数，不是队列长度。
4. `离线回放后的剩余目标数`：第一批通常等于最终目标；后续批次必须填“最终目标 - 同一任务最新离线 replay 合格数”。它只是浏览器停止预算，不能授予最终合格。
5. `候选 ASIN 队列`：每行一个 ASIN，队列应明显大于剩余目标数。
6. 点击 `生成批次`，检查队列数、历史自动跳过数和本地 batch 状态。

每个 Runner 批次的完整 queue 必须能被启动 Excel 桥接时指定的某一个候选 JSON 唯一覆盖。如果没有任何候选 JSON 覆盖完整 queue，或有多个 JSON 同时完整覆盖它，桥接会拒绝生成 Excel。

### 5.2 开始与监控

- `开始`：从当前行开始自动采集。
- `暂停`：请求在当前 ASIN 完整保存后停下，不应产生半条结果。
- `继续`：从已保存的进度继续。
- `完成当前行后停止`：让在途 ASIN 完整保存后结束当前批次；适合人工发现环境异常时使用。

运行中关注：状态、当前 ASIN、当前步骤、浏览器通过数、拒绝数、历史跳过数和错误消息。

Runner 显示的“浏览器通过”不是最终合格结论。Runner 主要收集 C/D/E 证据并进行短路，最终 A–F 判定只能由离线回放与 `acceptance_checker.py` 完成。

Runner `0.3.8.2` 不再在每次面板刷新时序列化整批导出 JSON；只有点击复制/Excel 时才生成完整导出。若 localStorage 配额不足，它会先丢弃当前批次非权威的 granular sidecar 后重试一次；仍失败则停止跳页并保留上一条成功状态，必须清理或导出后从同一行继续，不能把未落盘行计入历史或通过数。若检测到卖家精灵未登录、免费会员、套餐过期、Collector 面板缺失、流量洞察标签缺失或流量图未加载，Runner 会在当前 ASIN 写入结果前暂停，保留同一行供恢复后继续，不把基础设施故障误记为商品拒绝。

### 5.3 批次完成后的导出按钮

批次状态变为 `已完成 / done` 后：

- `复制合并 JSON`：复制完整 Runner batch 证据。
- `复制补充数据 JSON`：复制补充数据。
- `复制门槛日志 TSV` / `复制耗时日志 TSV`：保存追溯和耗时证据。
- `一键生成待验收 Excel`：将当前 done 批次发送给本机桥接，见第 7 节。

在合并 JSON/TSV、Excel 结果和人工预览均已保存前，不要点击 `删除已完成批次`。`清理孤立存储` 只删除无法关联到有效批次的记录，不会释放仍有效的旧批次。

## 6. 启动本机 Excel 桥接

先确保以下文件已放入真实项目根目录的 `scripts` 目录：

- `selection_excel_bridge.py`
- `start_selection_excel_bridge.ps1`

桥接还需要同一项目中已有的 `replay_existing_batch.py`、`build_replay_workbooks.mjs`、`acceptance_checker.py`、正式 `history/strict_qualified_asins.json`、Python 和 Node.js。

### 6.1 单个候选 JSON

在 PowerShell 中运行：

```powershell
$Project = 'C:\Users\13045\Desktop\amazon_products'
$RunId = 'strict20_20260717'

& "$Project\scripts\start_selection_excel_bridge.ps1" `
  -RunId $RunId `
  -CandidatesJson "$Project\runs\$RunId\candidate_pool\strict_queue_01.json" `
  -ImageDir "$Project\runs\$RunId\source_images" `
  -Target 20
```

如执行策略禁止本地 PowerShell 脚本，可用：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
  "C:\Users\13045\Desktop\amazon_products\scripts\start_selection_excel_bridge.ps1" `
  -RunId "strict20_20260717" `
  -CandidatesJson "C:\Users\13045\Desktop\amazon_products\runs\strict20_20260717\candidate_pool\strict_queue_01.json" `
  -ImageDir "C:\Users\13045\Desktop\amazon_products\runs\strict20_20260717\source_images" `
  -Target 20
```

### 6.2 多个候选 JSON

同一任务有多个候选文件时，在当前 PowerShell 会话中传入数组：

```powershell
$Project = 'C:\Users\13045\Desktop\amazon_products'
$RunId = 'strict20_20260717'
$CandidateFiles = @(
  "$Project\runs\$RunId\candidate_pool\strict_queue_01.json",
  "$Project\runs\$RunId\candidate_pool\strict_queue_02.json"
)

& "$Project\scripts\start_selection_excel_bridge.ps1" `
  -RunId $RunId `
  -CandidatesJson $CandidateFiles `
  -ImageDir "$Project\runs\$RunId\source_images" `
  -Target 20
```

### 6.3 参数说明

| PowerShell 参数 | 必填 | 说明 |
| --- | --- | --- |
| `-RunId` | 是 | 任务唯一 ID，也用于默认输出目录。 |
| `-CandidatesJson` | 是 | 一个或多个候选 JSON 路径。 |
| `-ImageDir` | 是 | 已下载主图的目录。 |
| `-Target` | 是 | 必须与 Runner 的“最终合格目标数”完全一致。 |
| `-RunDate` | 否 | 默认为当天，格式 `YYYY-MM-DD`。 |
| `-Port` | 否 | 默认 `8765`。修改后 Runner 面板的服务地址也要修改。 |
| `-OutputRoot` | 否 | 默认为 `<project>\runs\<RunId>`。 |
| `-Token` | 否 | 可指定固定令牌；留空时每次启动自动生成安全随机令牌。 |

启动成功后，终端会显示：

- `服务地址`，默认 `http://127.0.0.1:8765`；
- `服务令牌`；
- `runId` 和 `target`。

保持该 PowerShell 窗口运行，将服务地址和令牌填入 Runner 面板。不要将令牌发送给其他人。

## 7. 一键生成 Excel

1. 等当前 Runner 批次状态为 `已完成 / done`。未 done 时 Excel 按钮不可用。
2. 在 `本机 Excel 服务地址` 填入终端显示的地址。只允许 `127.0.0.1` 或 `localhost`，不要填入外网地址。
3. 在 `Excel 服务令牌` 填入终端显示的令牌。
4. 点击 `一键生成待验收 Excel`。
5. 桥接会依次：
   - 对批次 schema、状态、队列、ASIN、Runner/Collector 版本和 target 进行严格校验；
   - 固化保存原始 batch 及候选文件哈希；
   - 将正式 history 复制到本次 attempt 的独立沙箱；
   - 离线回放所有已上传批次；
   - 仅当离线回放严格合格数等于 target 时构建最终与拒绝审计工作簿；
   - 运行 `acceptance_checker.py`；
   - 只在机器验收通过后提供可下载的 XLSX。
6. 机器验收通过后，脚本管理器会弹出保存对话框，下载最终工作簿。

输出证据位于：

```text
<OutputRoot>\excel_bridge\
  bridge_manifest.json
  evidence\
  attempts\attempt_001\
    final_candidates_<RunId>.xlsx
    rejected_audit_<RunId>.xlsx
    workbook_build_report.json
    acceptance_report.md
    bridge_result.json
```

Runner 默认自动下载最终工作簿；拒绝审计工作簿与完整证据保留在 attempt 目录中。

### 目标数不足时

如果离线回放只合格 `N/Target`，桥接会返回 `target_incomplete`，不会生成可下载的最终 Excel。

1. 保留原有批次和桥接窗口。
2. 准备新候选文件和主图，必要时用包含新候选 JSON 的参数重启同一 `RunId` / target 的桥接。
3. 在 Runner 生成新批次并继续采集。
4. 新批次 done 后再点 Excel 按钮。桥接会对已固化的所有批次一起回放。

不得为了凑数降低 target、放宽门槛、将 review/reject 手工改成 pass，或伪造缺失数据。

## 8. 机器验收与人工预览的边界

### 机器验收会检查

- 最终数量与 target 完全一致；
- 最终与拒绝 ASIN 分离，最终 ASIN 唯一；
- 最终行通过流量、上架时间、尺寸、价格及趋势等强制规则；
- 每个最终 ASIN 都有本地主图；
- XLSX 中图片媒体数、图形数与最终行数一致；
- 所有最终 ASIN 均在最终工作簿中，拒绝 ASIN 不在最终工作簿中；
- 最终工作簿包含“最终合格品”“审计数据”“成本利润测算”三层；
- 主表列与已批准展示字段完全一致，移出的采集证据仍存在于审计层；
- 成本利润层除表头和空白模板行外不写入任何采集数据；
- 公式错误扫描为空。

### 三层工作簿结构

1. `最终合格品`：保留日常选品和商品开发需要查看的字段。来源关键词、读取周数、流量窗口、采集状态、实际 ASIN、流量判定、SellerSprite 页、图片来源 URL 和批次审计不再占用主表宽度。
2. `审计数据`：只记录最终合格行，但保留主表移出的完整采集证据、来源和批次追踪字段。拒绝、review 和异常行仍单独写入 `rejected_audit_<runId>.xlsx`。
3. `成本利润测算`：只建立表头和空白模板行。本选品脚本不得向第三层写入 ASIN、品名、售价、采购或利润数据，也不得爬取或计算第三层数据。

月销售额列仅允许显示源数据。源数据未提供真实月销售额时保持空白，不得再用“售价 × 子体月销”进行估算。

### 机器验收不能代替人工预览

机器返回 `accepted=true` 只代表结构和规则验收通过，不代表已完成交付。下载后必须打开工作簿或预览图，人工检查：

- 主图可离线显示，且与对应 ASIN 对齐；
- 中英文文字清晰，长标题不遮挡其他列；
- 行高、列宽、图片尺寸和表头不错位；
- 筛选器、百分比、日期、价格格式可正常使用；
- 主表只含严格合格产品；
- 审计工作簿中的 reject/review/异常保留完整。

机器验收或人工预览任一失败，都不得交付。

## 9. 正式 history 不会自动更新

Excel 桥接只读项目的正式 `history/strict_qualified_asins.json`，并在每次 attempt 内复制一份沙箱用于离线回放。它不会把机器验收通过的 ASIN 自动写回正式 history，`bridge_result.json` 也会明确记录 `productionHistoryUpdated: false`。

Runner 面板中的“本地严格合格历史”是浏览器 localStorage 去重记录，不是最终交付权威，也不等同于项目的正式 history 文件。

只有在以下条件全部满足后，才能由正式交付流程单独同步 history：

1. 离线回放完成；
2. 机器验收通过；
3. 人工预览通过；
4. 最终工作簿已确认交付。

不要从 Runner 的“浏览器通过”数量手工提前写入正式 history。

## 10. 安全限制

- Excel 服务只监听 `127.0.0.1`，Runner 也只接受 `http://127.0.0.1` 或 `http://localhost`。
- 只允许来自 `https://www.amazon.com` 或 `https://amazon.com` 的浏览器请求。
- 上传和下载都要校验服务令牌；下载地址必须是当前本机服务的受验收文件。
- 原始 batch、候选文件哈希、每次 attempt 和验收报告都会保留；不要修改原始证据来让失败变成通过。
- 任何缺失、超时、重定向、ASIN 不一致、含糊值、图片缺失或 parser 错误都应 fail closed，不得手工填值强制通过。
- 不得改动 A–F 硬门槛、价格范围、自然流量占比、上架天数、尺寸/图片要求或 history 去重逻辑。
- 桥接运行时保持终端打开；任务完成后用 `Ctrl+C` 关闭服务。

## 11. 常见失败处理

| 现象 | 处理 |
| --- | --- |
| 没有中文面板 | 确认当前为 `amazon.com` 页面、脚本已启用，然后刷新页面。 |
| 出现两个 Collector 或 Runner | 立即停止，在 ScriptCat 禁用多余版本，刷新后确认每种只有一个面板。 |
| `Collector not found` / 找不到采集器 | 启用 Collector `0.4.6.2`，禁用其他 Collector，刷新 Amazon 页面。 |
| CAPTCHA 或卖家精灵登录失效 | 暂停批次，手工完成验证/登录后再继续；未解决前不得作为 pass。 |
| 面板显示“仅限付费用户”或“升级套餐后即可查看” | 当前账号没有流量洞察权限。续费或切换有权限账号后刷新 Amazon，再从同一行继续；不得绕过流量门槛。 |
| 流量图未加载或 tooltip 不完整 | 保持为 reject/review/采集错误，不要手工伪造周数据。 |
| `无法连接本机 Excel 服务` | 确认 PowerShell 窗口仍在运行，面板地址与 `-Port` 一致，并检查防火墙/本机软件是否阻止 loopback。 |
| `Excel 服务令牌无效` | 重新复制当前桥接终端显示的完整令牌，不要使用上一次启动的随机令牌。 |
| Runner/Collector 版本不一致 | 桥接默认只接受 Runner `0.3.8.2` 和 Collector `0.4.6.2` 证据。切换正确脚本后新建批次，不要改 JSON 伪造版本。 |
| 本地存储/配额失败，Runner 停止跳页 | 先复制仍可导出的 JSON/TSV；点击 `清理孤立存储`。若空间仍不足，只能在证据与 Excel 已保存后选择一个 `done` 批次并点击 `删除已完成批次`。随后从最后成功状态继续，不要手工跳过当前 ASIN 或提前写入严格历史。 |
| `没有候选 JSON 能覆盖该批次完整 queue` | 向桥接增加对应的原始候选 JSON，并确保 queue 中的每个 ASIN 均在同一个文件内。 |
| `多个候选 JSON 同时覆盖该批次` | 使候选文件与 batch 形成唯一对应，不要用多份内容重复的合并 JSON。 |
| `targetQualified 与服务 target 不一致` | 使 Runner 目标和 PowerShell `-Target` 完全相同；不要通过改小 target 规避不足。 |
| `target_incomplete` | 增加新候选和新批次，再回放所有证据；不要放宽硬门槛。 |
| `replay` / `workbook` / `acceptance` 失败 | 保留 attempt 目录，查看终端、`bridge_result.json`、`run_summary.json`、`workbook_build_report.json` 和 `acceptance_report.md`；未通过前不得交付。 |
| Excel 下载成功但人工预览失败 | 不交付、不更新正式 history，修复渲染/数据问题后重新构建并验收。 |

## 12. 回退

如果中文增强版、Excel 按钮或本机桥接出现问题：

1. 停止当前批次，保存已有合并 JSON、enrichment JSON、门槛 TSV 和耗时 TSV。
2. 用 `Ctrl+C` 停止 Excel 桥接服务。
3. 在 ScriptCat 禁用中文增强脚本。
4. 优先回退到本候选的 P1 基线：
   - `scripts/sellersprite_traffic_collector_v0.4.6.user.js`；
   - `scripts/sellersprite_integrated_runner_v0.3.8.user.js`。
5. 如必须回到 canonical 预检组合，再将 Runner 换为 `scripts/sellersprite_integrated_runner_v0.3.7.user.js`。
6. 刷新 Amazon 页面，确认只有一个 Collector 和一个 Runner 面板，版本与所选回退组合一致。
7. 新建一个可追踪批次，按原始流程手工导出 batch JSON/TSV，再使用标准离线 replay、workbook build 和 acceptance 命令。

回退时不需要回退 A–F 规则或正式 history：Excel 桥接从不会自动写入正式 history。

## 13. 已复制合并 JSON 时的快捷入口

如果 Runner 批次已经运行并复制了“合并 JSON”，不必再启动本机 Excel Bridge 服务。使用 `scripts/build_excel_from_merged_json.py` 可直接从一个或多个快照生成 Excel；程序会自动寻找唯一最小的原始候选文件、只下载严格通过品主图、隔离正式 history，并复用同一套 replay、workbook build 和 acceptance。

完整输入契约、命令和失败处理见 `docs/merged_json_to_excel_cli.md`。v1.1 默认使用 4 路主图下载、60 分钟 ASIN + URL 缓存和工作簿完成后安全退出；这些性能策略不并发浏览器采集，也不跳过图片、回放、机器验收或人工预览。该入口仍要求中文标题覆盖，不会自动把结果写入正式 history。
