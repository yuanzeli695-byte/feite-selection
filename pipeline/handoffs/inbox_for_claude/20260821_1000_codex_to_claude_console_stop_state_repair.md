---
from: codex
to: claude
priority: p1
requires_action: yes
tags: [console, state-machine, stop, category-parser, queue-draft, sse, validation]
---

# Review request: console stop-state and category-node repair

Date: 2026-08-21
Owner: Codex
Status: deployed to the local console; strict release authority unchanged

## 1. Scope and explicit non-scope

Scope is limited to the local orchestration console at `C:\Users\13045\Documents\亚马逊电商选品\automation_console`:

- preserve terminal batch status when stale/later Browser Bridge heartbeats or events arrive;
- make Stop idempotent and deliver `stop_after_current` to an active Runner;
- exclude terminal Bridge sessions from the active lease;
- hide Stop for terminal batches and describe the stop-after-current behavior;
- parse one numeric SellerSprite `nodeIdPaths` value from direct or Markdown category links and reject malformed inputs.
- preserve each batch's unsubmitted ASIN textarea draft across normal console render, overview refresh, and SSE-triggered refresh; clear it only after successful queue approval;
- track SSE `lastEventId` per batch and reconnect with `?after=<id>` to avoid replaying already handled events during same-page-session reconnects.

Non-scope: no A-F threshold, gate order, Collector reader, Runner reader/timing, replay, acceptance, workbook builder, strict history, or browser userscript behavior changed. Runner output remains evidence only and cannot grant release acceptance.

## 2. Files changed

- `C:\Users\13045\Documents\亚马逊电商选品\automation_console\server.py`
- `C:\Users\13045\Documents\亚马逊电商选品\automation_console\static\app.js`
- `C:\Users\13045\Documents\亚马逊电商选品\automation_console\test_server.py`
- `C:\Users\13045\Documents\亚马逊电商选品\progress.md`
- This handoff file.

No canonical strict-selection source file under `C:\Users\13045\Desktop\amazon_products\scripts`, `config`, or `tests` was changed.

## 3. Feature flags, versions, and rollback

- No browser userscript or protocol version changed. The console continues to report Bridge `2.1.3`, Collector `0.4.6.4`, and Runner `0.3.8.13` as the technical candidate pair; `formalRunAuthorized` remains false.
- Canonical preflight still validates the approved baseline Collector `0.4.6` / Runner `0.3.7` and their rollback files.
- No new runtime feature flag was introduced for this local control-plane correctness repair. Please decide whether governance requires a named console flag/version before treating the change package as complete.
- Rollback is code-level: restore the prior `server.py`, `static/app.js`, and `test_server.py`, then restart the local console. The additive state fields, SQLite records, and already-written run artifacts require no migration and should remain for audit.

## 4. Hard-gate invariants preserved

- Candidate query bounds remain price `$9.90-50.00`, rating `>=4`, reviews `<=100`, child sales `50-300`, variations `<=25`, and availability `<=3 months`.
- Stop and terminal-state handling can reduce work or prevent stale mutation; neither path can pass an ASIN.
- URL parsing only narrows a category input to one numeric node and fails closed otherwise.
- Queue drafts are client-side review state only. They do not write an approved queue, create a Runner batch, or bypass the explicit `approve-candidates` server call.
- SSE cursoring changes event delivery bookkeeping only; terminal-state guards and server-side acceptance ownership remain unchanged.
- The replacement Office queue is explicitly labeled `runner_queue_only_no_final_AF_pass`.
- Final acceptance still requires current evidence, offline replay, workbook separation, and `acceptance_checker.py` success.

## 5. Test commands and measured results

Run from `C:\Users\13045\Documents\亚马逊电商选品`:

```powershell
& 'C:\Users\13045\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m unittest automation_console.test_server
& 'C:\Users\13045\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m py_compile automation_console\server.py automation_console\test_server.py
node --test automation_console\test_browser_bridge_v2.mjs automation_console\test_sellersprite_bridge.mjs
node --check automation_console\static\app.js
node --check automation_console\browser_bridge_v2.user.js
python "$env:USERPROFILE\.codex\skills\amazon-us-strict-selection\scripts\preflight.py" --project-root "C:\Users\13045\Desktop\amazon_products"
```

Measured results (final stabilized code):

- Python console suite: 54/54 PASS.
- Python compile checks: PASS.
- Node Browser Bridge/SellerSprite suites: 12/12 PASS.
- JavaScript syntax checks: PASS.
- Canonical preflight: PASS; no missing files, approved-rule drift, warnings, or errors; strict-qualified history count 69.
- The system `python` lacks `openpyxl` and cannot import the full console suite; the bundled runtime used by the running console is the verified Python environment.
- Post-change `node --check automation_console\static\app.js`: PASS.

Focused fixtures are inspectable in `C:\Users\13045\Documents\亚马逊电商选品\automation_console\test_server.py`: direct/Markdown node extraction; concurrent cancel/heartbeat and SellerSprite callbacks; cancellation after SellerSprite file storage; stopping reload preservation; delivered-command lease, new-ID stop retry, and retry-exhaustion lease retention; stale heartbeat lease retention; stopped JSON audit-only handling, including cancel during normalization; terminal queue-approval rejection; and completed-batch status restoration.

## 6. Paired evidence

Not applicable to this orchestration/parser repair: no Class B reader, retry, cache, browser timing, or Class C parallelism behavior changed. Deterministic fixtures prove terminal state preservation and fail-closed parsing.

The separate Runner `0.3.8.12` / `0.3.8.13` paired-30 requirement is still incomplete and is not claimed by this change.

## 7. Live deployment smoke

- Restarted the local console at `http://127.0.0.1:8788` and verified the overview API reports preflight healthy.
- Durable repair verified: Home batch `a644d195e085` reports `completed`; malformed Office batch `bcee6bd25422` reports `cancelled`.
- Live SellerSprite candidate flow verified with replacement Office batch `6ffe76239e31`, node `1064954`: 60 source rows, 0 normalization rejects, 35 prepared Runner ASINs, image cache ready, and candidate analysis workbook generated.
- The replacement batch intentionally remains `needs_attention` pending human queue review; Runner was not started.
- On batch `6ffe76239e31`, clicking Load ASIN Queue displayed all 35 ASINs. Clicking the workbench Refresh action then re-rendered current state without clearing the unsubmitted textarea. After the final server restart and a hard browser reload, the same 35 unique, well-formed ASINs were loaded again from the proposal. Confirm Runner Queue was never clicked.
- The follow-up API check still reports `overallStatus=needs_attention`, candidate status `needs_attention`, `queueCount=35`, no Runner batch name, and no approved queue path.
- Terminal UI state was inspected and Stop is hidden for the completed batch.
- No browser userscript was deployed in this change. A live stop while Runner is actively processing an ASIN was not exercised and is not claimed.
- Stop is now two-phase. Any existing connected Bridge is signalled even when its heartbeat is stale; heartbeats cannot consume commands; control delivery has a lease; and unacknowledged or failed stops are resent with new command IDs. Automatic retry exhaustion and heartbeat loss do not release the stop intent or single-Bridge lease. The UI exposes an explicit `重试停止` command while the batch remains `stopping`.
- Bridge registration/reload, acknowledgements, queue approval, and merged-JSON intake recheck state ownership under the store lock. Terminal or stopping batches cannot be revived by a late callback or stale approval request.
- Canonical browser merged JSON is rejected unless it explicitly has `status=done`; an early authenticated upload cannot advance the batch to `excel_ready`.
- Cancellation after a SellerSprite file is stored but before its command acknowledgement cannot set the cancelled batch's bridge state to `uploaded` or launch candidate processing.

## 8. Residual risks and audit nuances

- Active-Runner stop delivery, response-loss recovery, new-command-ID resend, explicit retry, reload behavior, and terminal non-revival are covered by deterministic tests but still lack a live one-ASIN smoke.
- The original malformed category-pool row remains linked to cancelled batch `bcee6bd25422` for audit history; the replacement row is numeric and separate.
- Queue review can delete candidates before approval but cannot add an unevaluated ASIN or grant A-F acceptance.
- `queueDrafts` and `streamAfterByBatch` are in-memory page-session state. They survive console refresh/render and SSE reconnects, but a hard browser reload or tab close resets them; no cross-session persistence is claimed.
- After a hard browser reload the SSE cursor begins from zero, so historical event replay is still possible at the transport layer. The terminal-state guard prevents that replay from reviving a terminal batch.
- No console feature flag/version identifier was added; Claude should decide whether that governance gap blocks approval of this narrow control-plane repair.
- Formal browser-pair authorization remains false because the separate paired-30 evidence is absent.

## 9. Evidence artifact paths

Replacement run root:

`C:\Users\13045\Desktop\amazon_products\runs\console_Office_Products__08-21_09-50_20260821_095054_6ffe76`

Raw inspectable evidence:

- `browser_export_attempts\20260821T015234Z_440729\source_manifest.json`
- `browser_export_attempts\20260821T015234Z_440729\image_download_report.json`
- `browser_export_attempts\20260821T015234Z_440729\candidate_pool\summary_Office_Products__08-21_09-50___6ffe76239e31.json`
- `browser_export_attempts\20260821T015234Z_440729\candidate_pool\screened_rejected.json`
- `browser_export_attempts\20260821T015234Z_440729\candidate_pool\asin_queue_Office_Products__08-21_09-50___6ffe76239e31.txt`
- `browser_export_attempts\20260821T015234Z_440729\candidate_analysis_Office_Products__08-21_09-50___6ffe76239e31.xlsx`
- `console_sellersprite_browser_exports_stdout.log`
- `console_sellersprite_browser_exports_stderr.log`

The original malformed run remains at:

`C:\Users\13045\Desktop\amazon_products\runs\console_Office_Products__08-21_09-22_20260821_092232_bcee6b`

## 10. Exact review and approval requested

1. Confirm the terminal-state guard, stop command delivery, connected-lease rule, and terminal-event ignore path cannot create a false positive or bypass final acceptance.
2. Confirm direct/Markdown SellerSprite link parsing fails closed and cannot silently select multiple or non-numeric nodes.
3. Decide whether this control-plane repair may be classified outside Class B/C, or whether a named console feature flag/version and additional comparison package are required.
4. Decide whether an isolated live active-Runner stop smoke is required before approving the operational fix.
5. Confirm the page-session-only queue-draft and SSE-cursor scope is acceptable, or request durable session persistence as a separately reviewed change.

## 11. Stop boundary

Work stopped at the manual candidate queue-review gate. No Runner dispatch, offline acceptance, final workbook delivery, later Tier, Tier 2.3 preloading, or other unauthorized optimization was started.
