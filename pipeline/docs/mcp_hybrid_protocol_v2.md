# SellerSprite MCP Hybrid Protocol v2

## Status

- Bridge: 0.3.2
- Policy: 0.3.1
- Assist: 0.3.0
- Runner Adapter: 0.2.0
- Mode: shadow
- Final authority: false
- Original Collector/Runner: unchanged
- Formal run authorization: false until live smoke and sufficient pending-tool validation complete

## Pipeline

```text
MCP discovery (sealed validation task only, pending)
  -> local exclusions/history/hard prefilter
  -> durable prefetch workflow
  -> atomic plan reservation
  -> one-time packet claim
  -> Codex executes the exact declared MCP request
  -> claimed result validation and immutable raw-response archive
  -> 91-request manifest verification and non-authoritative validation summary
  -> Bridge immutable evidence import and field merge
  -> Assist advisory ranking and audit
  -> Adapter draft-queue reorder and audit
  -> Collector/Runner current browser collection
  -> replay/filter A-F
  -> workbook and acceptance checker
```

No MCP field can skip a later stage. Restricted-product exclusions run before business metrics. Gate C remains Collector-owned.

## Tool states

| Tool | State | Formal reservation | Test reservation | Role |
|---|---|---:|---:|---|
| `keepa_info` | validated shadow | yes | yes | field completion and ranking |
| `asin_detail` | pending | no | explicit double key | detail contract validation |
| `asin_sales_trend` | pending | no | explicit double key | price-trend contract validation |
| `traffic_listing_stat` | pending | no | explicit double key | traffic-structure advisory only |
| `product_research` | pending discovery | no | sealed validation task only | discovery-shadow contract validation |
| `competitor_lookup` | blocked | no | no | exact-ASIN contract failed |
| `traffic_extend` | blocked | no | no | cannot provide strict Gate C evidence |

## Quota model

- Official month: 15,000.
- Operational month: 12,000.
- Asia/Shanghai day: 500 hard limit.
- Daily pools: 300 primary, 100 conditional, 100 emergency.
- Default launcher/run budget: 300.
- Reservations count as spent and are not released after failure.
- Conditional and emergency pools require explicit workflow flags; emergency also requires explicit Bridge authorization.
- No automatic retry exists in the workflow, ledger, or recovery path.
- The fixed validation task has `taskBudget=100`, `authorizedCalls=91`, and 9 permanently sealed calls. The 9 calls are not a retry pool.

The shared ledger is `cache/mcp_hybrid_call_ledger.jsonl`. Read-modify-write sections use a cross-process file lock. A plan is one atomic reservation event; partial reservation is forbidden.

### Sealed 91-call validation task

The dedicated task manifest contains exactly one `product_research` request and 30 requests for each of `asin_detail`, `asin_sales_trend`, and `traffic_listing_stat`. It uses a new `mcp-validate-task-*` run ID, a dedicated Bridge instance with `runBudget=100`, and the shared quota ledger.

The complete 91-request plan is reserved in one locked ledger write with `sealRun=true`. Once sealed, the run rejects another plan, a legacy single reservation, any changed version of the plan, and every request ID outside the reserved 91. Each request declares `maxAttempts=1` and `automaticRetry=false`.

`product_research` remains `reservationEnabled=false`. It is accepted only when the policy has `testReservationEnabled=true` and the dedicated Bridge ledger is explicitly created in test mode. This does not authorize formal discovery or A-F decisions.

After a claim, `record-validation-task` requires the exact local claim token and re-reads Bridge `plan_state`. The local task, stored claim receipt, result envelope and Bridge claim must agree on run, plan, request, claim ID, request hash, tool and claim time. The actual UTF-8 JSON provider response is hash-checked and archived as `raw_responses/<requestId>.<sha256>.json`; the task stores only its immutable archive metadata plus the normalized terminal envelope.

`finalize-validation-task` is allowed only after all 91 requests have exactly one terminal result and Bridge contains all 91 unique claims. It rehashes every raw archive and writes `sellerSpriteMcpValidationTaskFinalSummary/v1` with claim, result and raw-response manifest hashes. Any `partial` or `failed` outcome closes the validation ledger plan as `failed`; all 91 must be `succeeded` to close it as `succeeded`. Both outcomes remain shadow-only and non-authoritative.

## Execution protocol

1. `plan` validates a US-only, `prefilterStatus=pass` candidate document and creates exact request packets.
2. `--reserve` is allowed only for validated tools. Pending tools require both `--test-only-allow-pending-tool` and `--reserve-test-only`, plus Bridge test mode.
3. `claim` calls `CallLedger.claim_plan_request`. A packet can receive execution permission only once across processes.
4. The executor calls the exact request stored in the packet. `startedAt` must not precede the Bridge claim time.
5. `record` requires the one-time local claim token. It validates request hash, exact ASIN, tool, timestamps, TTL, normalized fields, missing fields and per-field provenance.
6. `finalize` revalidates every terminal result and its hash, creates a non-authoritative bundle, and closes the reserved plan as succeeded or failed.

For the separate sealed task, use `record-validation-task` and `finalize-validation-task`. These commands never call an MCP provider. They only validate files, re-read the local Bridge ledger, archive raw JSON and close the already-reserved plan.

The sealed validation task is a separate budget-validation path. It does not change the candidate-prefetch workflow schema and does not let `product_research` enter an ASIN-prefetch packet.

Copying a workflow file cannot create a second MCP execution permission because the Bridge claim is global to the shared ledger.

## Validation archive contract

Each terminal validation result uses `sellerSpriteMcpValidationTaskResult/v1` and contains the exact `taskId`, `runId`, `requestId`, `requestHash`, `claimId`, tool name/version, target/actual ASIN binding, terminal status, attempt timestamps, raw-response SHA-256/byte length/capture time, response metadata and a structured non-retryable error for `failed`. Both `usableForFinal` and `finalAuthority` are always `false`.

The final summary contains exactly 91 request outcomes plus `claimManifestSha256`, `resultManifestSha256` and `rawManifestSha256`. It is an audit input for paired validation only. It is not an evidence bundle, cannot be imported as an A-F pass, and cannot reduce Collector/Runner work required by the strict acceptance path.

## Recovery

- `reconcile-reservation`: attaches an exact idempotent reservation only when Bridge reports `phase=reserved`, no terminal event and zero claimed requests.
- `reconcile-claim`: closes an interrupted claim as failed, produces no evidence, and never grants a retry. It accepts either a locally planned packet missing the claim write or a locally claimed packet whose token output was lost, provided local and Bridge claim records match.
- `plan_state`: read-only diagnosis of reservation, claims and terminal state. It never returns execution permission.

## Evidence contract

Every usable field requires:

- exact target and actual ASIN;
- a known tool and immutable evidence ID;
- valid capture and expiry timestamps within the tool TTL;
- non-null value and matching `fieldProvenance.sourceTool`;
- optional `sourceAsin` equal to actual ASIN;
- `usableForFinal=false` and `finalAuthority=false`.

Bridge returns `mergedRanking` with the selected source for every field. Assist independently rejects missing authority flags, invalid/expired windows, unsafe reason codes, missing source paths and missing semantics.

## Browser contract

- Assist requires Bridge 0.3.0 or newer. The sealed 91-call validation task requires Bridge 0.3.2.
- Adapter requires Assist 0.3.0 and supports Runner 0.3.7 or 0.3.8.2 only.
- Auto uses Focus 5 only for queues of five or fewer; queues of ten or more keep original order.
- Balanced requires explicit selection.
- Both ranking and queue application require persisted audit receipts.
- Adapter changes only an ungenerated draft queue and preserves the exact ASIN multiset.
- If application audit fails, Adapter restores the original queue when safe; otherwise Generate remains disabled.

## Loopback API

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/v1/health` | version, mode, policy and budget summary |
| `GET` | `/api/v1/evidence` | exact cached evidence lookup |
| `POST` | `/api/v1/evidence/batch` | 1-40 ASIN cached lookup, zero MCP calls |
| `POST` | `/api/v1/evidence/import` | immutable offline evidence import |
| `GET` | `/api/v1/ledger` | shared quota summary |
| `POST` | `/api/v1/calls/reserve-plan` | atomic plan reservation; `sealRun=true` permanently blocks appended reservations |
| `POST` | `/api/v1/calls/claim` | one-time packet execution claim |
| `POST` | `/api/v1/calls/status` | terminal plan status |
| `GET` | `/api/v1/calls/plan-state` | read-only recovery state |
| `POST` | `/api/v1/audit/events` | append-only ranking/application audit |

All non-health endpoints require the session token. The server binds to `127.0.0.1`; browser origins are restricted to Amazon US.

## Rollback

Stop the dedicated Bridge 0.3.2 validation instance and disable the new task path. The legacy Bridge/runBudget=50 process, frozen original Collector/Runner, old Assist/Adapter, rules, exclusions and strict history remain available and unchanged.
