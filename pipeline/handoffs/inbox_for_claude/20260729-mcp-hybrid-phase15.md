# MCP Hybrid Phase 1.5 Handoff

## 目标和边界

新架构把 MCP 用于本地硬预筛后的 durable prefetch、缓存和候选重排，把网页插件保留给正式证据采集。原 Collector/Runner、规则、排除表和严格历史均未修改，A-F 最终权威不变。

正式严格运行必须同时打开一个批准版本的 Collector 和一个批准版本的 Runner。MCP/Assist/Adapter 只减少优先顺序不佳造成的网页浪费，不能替代 Gate C、D/E、回放、Excel 或 acceptance checker。

## 新文件

- `scripts/mcp_hybrid_bridge.py` - Bridge 0.3.1，原子额度、单次 claim、字段合并和审计；审计 ID 使用独立安全规则兼容 Assist/Adapter 的冒号分隔请求 ID。
- `scripts/mcp_hybrid_prefetch_orchestrator.py` - durable packet 工作流、恢复和关账。
- `scripts/sellersprite_mcp_hybrid_assist_v0.3.0.user.js` - 非权威排序与 ranking audit。
- `scripts/sellersprite_mcp_hybrid_runner_adapter_v0.2.0.user.js` - draft-only 队列应用与 application audit。
- `config/mcp_hybrid_policy.json` - 300/100/100 日池、12,000 月运营上限和工具状态。
- `docs/mcp_hybrid_protocol_v2.md` - 完整协议。
- `docs/MCP_HYBRID_PHASE15_使用说明.md` - 操作、恢复和预算说明。

旧 Assist `0.2.0/0.2.1`、旧 Adapter `0.1.0`、Bridge `0.2.0` 备份和原 Collector/Runner 都保留作回滚，不得与新组合混用。

## 核心协议

1. candidate 文档必须是 US、`prefilterStatus=pass`、带来源 SHA-256。
2. 整批计划先原子预留，再逐 packet 单次 claim；预留即计费，失败不释放，不自动重试。
3. 结果必须 exact ASIN、请求哈希一致、时间不早于 claim、TTL 合规、缺失字段完整列举、每个非 null 字段有 provenance。
4. Bridge 只输出 `mergedRanking.finalAuthority=false`。
5. Assist/Adapter 需要两次持久化审计回执，且只允许 `reorder_only`。
6. Adapter 只处理未生成批次的草稿队列，保持 ASIN 多重集合完全一致。

## 工具状态

- `keepa_info`: validated shadow，可正式预留但仍非最终权威。
- `asin_detail`、`asin_sales_trend`、`traffic_listing_stat`: pending，只能双开关受控测试。
- `product_research`: candidate-prefetch 和 policy 双层阻断，等待独立 discovery planner。
- `competitor_lookup`、`traffic_extend`: blocked。

## 受控测试证据

对 `B0GTQFW672` 各调用一次，共 3 次、零重试，账本从 33 到 36，低于任务硬上限 50。

- `asin_detail`: partial，返回基础字段和未解析 dimensions；reviews、重量、包装尺寸等缺失。
- `asin_sales_trend`: succeeded，3 个价格点按现有 Runner 算法分类为 rising。
- `traffic_listing_stat`: succeeded，659 free / 17 paid；只作流量结构建议，不能替代 Gate C。

三个 workflow 和 bundle 位于 `runs/mcp_hybrid_phase15_candidate/controlled_tests/`，均已 finalized，所有 evidence 仍为 `finalAuthority=false`。

## 验证

- Bridge + Orchestrator 39/39。
- Assist、Adapter、30-ASIN 配对 PASS。
- 全量 Python、SellerSprite Node、userscript syntax PASS。
- 严格预检 PASS，严格历史 57。
- 冻结原文件 9/9 哈希一致。
- 真实浏览器一 ASIN 配对冒烟 PASS：`B0GTQFW672` 排序前后队列不变、批次选择器为空、未生成批次、两条审计持久化、严格历史仍为 57、MCP provider 调用仍为 36。

浏览器组合测试已通过，但 `formalRunAuthorized=false`。不得基于单样本把 pending 工具升级为正式来源，也不得让 MCP 替代 Gate C 或 A-F。

## 回滚

关闭 Adapter 0.2.0 和 Assist 0.3.0，停止 Bridge 0.3.1。必要时单独启用旧 Assist/Adapter 组合；不需要恢复 Collector、Runner、规则、排除表或历史文件。
