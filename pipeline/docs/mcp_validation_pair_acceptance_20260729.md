# MCP 91-call paired validation acceptance

This route is offline after the official validation task has been finalized.
Neither the builder nor the analyzer imports the Bridge, reserves quota, writes
the ledger, or invokes MCP.

## Frozen execution contract

- Task: `runs/mcp-validate-task-target2-20260729-v2/validation_task.json`
- Budget: 100 total, exactly 91 authorized, 9 permanently sealed
- Calls: 1 `product_research`, 30 `asin_detail`, 30 `asin_sales_trend`, 30 `traffic_listing_stat`
- Retries: none; one claim and one recorded terminal result per request
- Authority: every MCP artifact remains `finalAuthority=false` and `usableForFinal=false`
- `product_research`: discovery only
- `traffic_listing_stat`: traffic-structure advisory only; never Gate C evidence
- A-F authority: browser Collector/Runner, replay/filter, workbook, and acceptance remain mandatory

## Real data lineage

The paired view is generated, not manually authored:

1. The official finalized task supplies the 91 canonical result envelopes.
2. The official final summary binds request/result/raw manifest hashes.
3. Each raw archive is re-read from
   `runs/mcp-validate-task-target2-20260729-v2/raw_responses/`; its exact path,
   byte length, SHA-256, UTF-8 JSON form, tool, request hash, and ASIN are checked.
4. Tool fields are normalized only from those verified raw archives.
5. `pairedOutcomes.rows[].hybridOutcome` is derived from the exact union of a
   dedicated 30-ASIN browser replay's `final_candidates_data.json` and
   `rejected_audit_data.json`. Their union must equal the frozen sample exactly,
   and `run_summary.json` must report `attempts=30` with matching counts.
6. `liveSmoke` is derived from the smoke JSON and artifact-hash manifest. It
   must bind the current task/run and current Bridge/Assist/Adapter/Collector/
   Runner versions, retain the queue and strict history, persist both audits,
   generate no batch, and add no provider calls.

The builder fails closed if any source is absent or inconsistent. The analyzer
does not accept the older synthetic result schema or a planned/unfinalized task.

## Build the paired view

Run only after the official task has 91 terminal results and has been finalized,
and after a dedicated 30-ASIN replay plus a current task-bound smoke exist:

```powershell
python scripts/build_mcp_validation_pair_view.py `
  --plan docs/mcp_hybrid_shadow_plan_20260729.json `
  --task runs/mcp-validate-task-target2-20260729-v2/validation_task.json `
  --summary runs/mcp-validate-task-target2-20260729-v2/validation_summary.json `
  --baseline runs/mcp_shadow_20260729/browser_baseline.json `
  --hybrid-final <30-replay-dir>/final_candidates_data.json `
  --hybrid-rejected <30-replay-dir>/rejected_audit_data.json `
  --hybrid-run-summary <30-replay-dir>/run_summary.json `
  --smoke <current-smoke-dir>/BROWSER_SMOKE.json `
  --smoke-hashes <current-smoke-dir>/ARTIFACT_HASHES.json `
  --expected-bridge 0.3.2 `
  --expected-assist 0.3.0 `
  --expected-adapter 0.2.0 `
  --expected-collector 0.4.6 `
  --expected-runner 0.3.7 `
  --expected-runner 0.3.8.2 `
  --output runs/mcp-validate-task-target2-20260729-v2/paired_view.json
```

Then run the acceptance analyzer:

```powershell
python scripts/analyze_mcp_validation_task_pair.py `
  --plan docs/mcp_hybrid_shadow_plan_20260729.json `
  --task runs/mcp-validate-task-target2-20260729-v2/validation_task.json `
  --baseline runs/mcp_shadow_20260729/browser_baseline.json `
  --results runs/mcp-validate-task-target2-20260729-v2/paired_view.json `
  --output runs/mcp-validate-task-target2-20260729-v2/paired_acceptance.json
```

## Acceptance decision

`shadowPairedAcceptance=PASS` requires all of the following:

- all 91 official results and raw archives are present and valid;
- tool error rate is 0% for every tool;
- ASIN identity is exact for all 90 ASIN-bound calls;
- required detail-field and Gate D/E advisory comparisons meet the encoded thresholds;
- unsafe false positives are zero;
- `traffic_listing_stat` makes zero Gate C claims;
- `product_research` makes zero A-F or qualification claims;
- the real 30-ASIN replay agrees 30/30 with the frozen browser baseline;
- the current, task-bound one-ASIN smoke passes without queue/history/provider-call mutation.

Even after shadow acceptance passes, `formalRunAuthorized=false` and
`gateBypassAuthorized=false`. The allowed action is advisory ranking/reordering
only; all original hard gates and final acceptance remain unchanged.

## Current state

The v2 task is currently planned with zero reservation and zero calls. The old
one-ASIN smoke has verified hashes, but it uses Bridge 0.3.1 and is not bound to
the v2 task. Existing `strict_auto_20260728_delivery` replay artifacts contain
17 attempts, not the frozen 30. Both are intentionally rejected as final paired
acceptance evidence.

Focused offline validation:

```powershell
python -m unittest tests.test_build_mcp_validation_pair_view tests.test_analyze_mcp_validation_task_pair -v
```
