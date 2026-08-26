# MCP Hybrid Runner Adapter 0.1.0 Handoff

## Scope

新增独立的 Runner 队列重排适配器，与 Assist `0.2.1` 配套；原 Collector/Runner 和 Assist `0.2.0` 均为回退基线，不能改写。

## Files

- `scripts/sellersprite_mcp_hybrid_assist_v0.2.1.user.js`
- `scripts/sellersprite_mcp_hybrid_runner_adapter_v0.1.0.user.js`
- `tests/test_sellersprite_mcp_hybrid_assist_v021.mjs`
- `tests/test_sellersprite_mcp_hybrid_runner_adapter.mjs`
- `docs/MCP_HYBRID_RUNNER_ADAPTER_使用说明.md`

## Contract

Assist `0.2.1` adds `requestId` and `eventProtocol=runner-adapter/v1` to `ss-mcp-hybrid:queue-ranked` and `ss-mcp-hybrid:rank-error`. Adapter only accepts the matching request, exact original array, equal-length valid ASIN array, unchanged multiset, `finalAuthority=false`, and `allowedAction=reorder_only`.

The adapter acts only while the Runner picker is blank and the queue is editable. It dispatches `ss-mcp-hybrid:rank-request`, then writes the returned order to `#ss-v3-queue` and emits an audit event. It does not generate/start batches or touch batch storage, results, gates, or strict history.

## Verification

```powershell
node --check scripts/sellersprite_mcp_hybrid_assist_v0.2.1.user.js
node --check scripts/sellersprite_mcp_hybrid_runner_adapter_v0.1.0.user.js
node tests/test_sellersprite_mcp_hybrid_assist_v021.mjs
node tests/test_sellersprite_mcp_hybrid_runner_adapter.mjs
node tests/test_sellersprite_mcp_hybrid_runner_adapter_paired30.mjs
```

All commands pass in the candidate workspace. The adapter handshake was replayed against the existing 30-real-ASIN frozen evidence with exact binding, unchanged multiset, and the prior zero-false-positive result. A one-ASIN live smoke is still pending; do not call this candidate production-approved.

## MCP Budget

No new provider call is made by either userscript. Bridge reads its local evidence cache; the task ledger remains 33 calls against the user ceiling of 50.

## Rollback

Disable Adapter and Assist `0.2.1`. The original Runner/Collector and Assist `0.2.0` remain available without file restoration.
