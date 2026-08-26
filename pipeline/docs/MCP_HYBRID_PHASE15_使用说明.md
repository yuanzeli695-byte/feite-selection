# MCP Hybrid Phase 1.5 使用说明

## 推荐日常分配

500 次是硬上限，不是必须用满的目标。默认只开放 300 次 primary：

| 工作 | 建议上限 | 当前状态 |
|---|---:|---|
| 本地排除、历史去重、硬门槛预筛 | 0 | 正式使用 |
| `product_research` 发现候选 | 固定验证任务 1 次 | 仅 TestMode，正式权限仍关闭 |
| `asin_detail` 字段补全 | 仅受控小样本 | pending |
| `asin_sales_trend` 趋势补全 | 仅受控小样本 | pending |
| `keepa_info` 缓存补全 | primary 内按缺口调用 | validated shadow |
| `traffic_listing_stat` 结构建议 | 仅受控小样本 | pending，不能代替 Gate C |
| conditional | 最多 100 | 人工显式开启 |
| emergency | 最多 100 | 单独授权，默认关闭 |

浏览器插件的工作量集中到“正式证据采集”：MCP 先补全和排序，Collector/Runner 再对最终实际访问的候选执行当前页面采集。Collector/Runner 的硬门槛工作不能分给 MCP。

## 固定 91 次密封验证任务

这条路径只用于验证 MCP 与浏览器证据的匹配性，不会代替 A-F，也不会修改原 Collector、Runner 或旧 `runBudget=50` Bridge。调用结构固定为：

- `product_research`：1 次。
- `asin_detail`：30 次。
- `asin_sales_trend`：30 次。
- `traffic_listing_stat`：30 次。
- `taskBudget=100`，实际授权 91 次，剩余 9 次永久密封，不能用于重试或追加候选。

先准备一个只包含本次精确 MCP 参数的 `product_research_request.json`。文件顶层必须是 `{"request": {...}}`，内部 marketplace 必须是 `US`，不能放占位符。

生成任务清单不会预留额度，也不会调用 MCP：

```powershell
python .\scripts\mcp_hybrid_prefetch_orchestrator.py plan-validation-task `
  --sample-plan .\docs\mcp_hybrid_shadow_plan_20260729.json `
  --discovery-request .\runs\mcp-validate-task-20260729-v1\product_research_request.json `
  --task .\runs\mcp-validate-task-20260729-v1\validation_task.json `
  --run-id mcp-validate-task-20260729-v1
```

需要浏览器侧连接时，另启一个未占用端口的测试 Bridge，不要停止或改写旧 50 次实例：

```powershell
python .\scripts\mcp_hybrid_bridge.py `
  --output-root .\runs\mcp-validate-task-20260729-v1\bridge `
  --run-id mcp-validate-task-20260729-v1 `
  --run-budget 100 `
  --port 8768 `
  --test-mode
```

确认任务清单后，再一次性预留全部 91 次。此命令会写共享额度账本，因此只能在真正准备执行时运行：

```powershell
python .\scripts\mcp_hybrid_prefetch_orchestrator.py reserve-validation-task `
  --task .\runs\mcp-validate-task-20260729-v1\validation_task.json `
  --test-mode
```

预留使用一个新的 `mcp-validate-task-*` runId 和 `runBudget=100`。Bridge 会把该 run 密封：第二个 plan、单次 legacy reservation、修改后的原 plan 和第 92 个 requestId 都会拒绝。日/月统计仍写入共享 `cache/mcp_hybrid_call_ledger.jsonl`。

领取某个精确请求：

```powershell
python .\scripts\mcp_hybrid_prefetch_orchestrator.py claim-validation-task `
  --task .\runs\mcp-validate-task-20260729-v1\validation_task.json `
  --request-id REQUEST_ID `
  --executor-id codex-main `
  --test-mode
```

每个 request 只能领取一次，`maxAttempts=1` 且 `automaticRetry=false`。领取成功只代表可执行该 request，不代表产品通过任何硬门槛。

执行精确 MCP 请求后，必须同时保存两份本地文件：

- `REQUEST_ID.raw.json`：MCP provider 返回的原始 UTF-8 JSON，不得整理或删字段。
- `REQUEST_ID.result.json`：`sellerSpriteMcpValidationTaskResult/v1` 结果信封，写入相同 `taskId/runId/requestId/requestHash/claimId`、工具名和版本、目标/实际 ASIN、`succeeded|partial|failed`、时间戳，以及原始文件的 SHA-256 和字节数。`failed` 必须带 `retryable=false`；`usableForFinal` 与 `finalAuthority` 必须都是 `false`。

记录单项终态并归档原始响应：

```powershell
python .\scripts\mcp_hybrid_prefetch_orchestrator.py record-validation-task `
  --task .\runs\mcp-validate-task-20260729-v1\validation_task.json `
  --result .\runs\mcp-validate-task-20260729-v1\incoming\REQUEST_ID.result.json `
  --raw-response .\runs\mcp-validate-task-20260729-v1\incoming\REQUEST_ID.raw.json `
  --claim-token CLAIM_TOKEN `
  --test-mode
```

该命令会重新读取 Bridge 账本，核对 requestId、claimId、requestHash、tool、claim 时间和本地 claimToken 哈希，然后把原始 JSON 固定归档为 `raw_responses/REQUEST_ID.SHA256.json`。完全相同的重复记录是幂等的；不同终态、不同原始响应或第二次尝试会被拒绝。命令本身不会调用 MCP，也不会新增额度。

91 项全部成为终态后生成汇总并封账：

```powershell
python .\scripts\mcp_hybrid_prefetch_orchestrator.py finalize-validation-task `
  --task .\runs\mcp-validate-task-20260729-v1\validation_task.json `
  --summary .\runs\mcp-validate-task-20260729-v1\validation_summary.json `
  --test-mode
```

封账前会再次确认 91 个唯一 Bridge claim、91 个终态、91 个原始归档及三组 manifest hash。存在任意 `partial` 或 `failed` 时，任务状态为 `finalized_with_failures`，Bridge 计划按 `failed` 关闭；只有 91 项全为 `succeeded` 才按 `succeeded` 关闭。汇总仍然 `finalAuthority=false`，不能代替 A-F、Collector、Runner、回放或 Excel 验收。

查看任务状态：

```powershell
python .\scripts\mcp_hybrid_prefetch_orchestrator.py inspect-validation-task `
  --task .\runs\mcp-validate-task-20260729-v1\validation_task.json
```

输出会显示 planned、claimed、succeeded、partial、failed、已记录数、剩余数、原始归档数，以及封账后的 summary 路径和 ledger 状态。

## 创建正式 Keepa 预取工作流

候选 JSON 必须使用 `sellerSpriteMcpPrefilteredCandidates/v1`，每行都包含 `prefilterStatus=pass` 和来源 SHA-256。

```powershell
python .\scripts\mcp_hybrid_prefetch_orchestrator.py plan `
  --input .\runs\RUN_ID\prefiltered_candidates.json `
  --workflow .\runs\RUN_ID\keepa_workflow.json `
  --tool keepa_info `
  --reserve
```

查看 packet：

```powershell
python .\scripts\mcp_hybrid_prefetch_orchestrator.py inspect `
  --workflow .\runs\RUN_ID\keepa_workflow.json
```

领取单个 packet，领取成功后才能调用 MCP：

```powershell
python .\scripts\mcp_hybrid_prefetch_orchestrator.py claim `
  --workflow .\runs\RUN_ID\keepa_workflow.json `
  --packet-id PACKET_ID `
  --executor-id codex-main
```

保存命令返回的 `claimToken`。MCP 调用必须与 packet 中的 `request` 完全一致，禁止重试。

记录结果：

```powershell
python .\scripts\mcp_hybrid_prefetch_orchestrator.py record `
  --workflow .\runs\RUN_ID\keepa_workflow.json `
  --result .\runs\RUN_ID\PACKET_ID.result.json `
  --claim-token CLAIM_TOKEN
```

所有 packet 都终止后，生成证据并关闭账本计划：

```powershell
python .\scripts\mcp_hybrid_prefetch_orchestrator.py finalize `
  --workflow .\runs\RUN_ID\keepa_workflow.json `
  --bundle .\runs\RUN_ID\evidence_bundle.json
```

## Pending 工具受控测试

下面两个开关缺一不可，并且 Bridge 必须以 `-TestMode` 启动：

```powershell
python .\scripts\mcp_hybrid_prefetch_orchestrator.py plan `
  --input .\runs\RUN_ID\one_candidate.json `
  --workflow .\runs\RUN_ID\asin_detail_test.json `
  --tool asin_detail `
  --test-only-allow-pending-tool `
  --reserve-test-only
```

一次失败就是终止结果，不自动重试。测试证据仍不能用于 A-F 最终通过，也不能因为少量样本成功而修改 policy 为正式工具。

## 中断恢复

预留已扣账但 workflow 仍是 planned：

```powershell
python .\scripts\mcp_hybrid_prefetch_orchestrator.py reconcile-reservation `
  --workflow .\runs\RUN_ID\workflow.json
```

Bridge 已 claim，但本地 claim/token 未可靠保存：

```powershell
python .\scripts\mcp_hybrid_prefetch_orchestrator.py reconcile-claim `
  --workflow .\runs\RUN_ID\workflow.json `
  --packet-id PACKET_ID
```

第二个命令会把该 packet 关闭为失败并禁止重试，不会导出 evidence。

## 浏览器阶段

原日常链路仍按原批准版本启用。固定 91 次验证任务必须使用独立的 Bridge 0.3.2 实例、新端口、新 `mcp-validate-task-*` runId 和 `runBudget=100`，不得复用旧 `runBudget=50` 进程。Assist、Adapter、Collector、Runner 及其 A-F 权限不因本次预算封装改变。

当前 `formalRunAuthorized=false`。在完成新组合的一 ASIN 现场 smoke、pending 接口足量配对和零误放验证前，只能使用缓存排序与隔离测试。
