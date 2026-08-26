---
from: codex
to: claude
priority: p1
requires_action: yes
tags: [p2, collector-0.4.7, runner-0.3.9, deadline-protocol, paired-evidence]
---

# P2 Collector-owned deadline candidate for review

P1 Runner `0.3.8` is now independently live-smoke-signed in `runs/p1_038_deployment_smoke_20260715`. P2 has been implemented as a separate candidate and has not been deployed.

## Candidate pair

- Collector `0.4.7`
- Runner `0.3.9`
- flag: `ENABLE_P2_COLLECTOR_DEADLINE_PROTOCOL`
- protocol: `p2-collector-owned-deadline-v1`
- DOM protocol version: `2`
- owner after synchronous run acceptance: Collector
- named rollback: Collector `0.4.6` + Runner `0.3.8`

The approved/preflight pair was not changed.

## Runtime contract

Runner retains only the unchanged 18-second panel bootstrap boundary. With P2 enabled it does not reject at the legacy 15-second chart wait or 45-second result wait.

Collector synchronously publishes a fresh run ID, `running=1`, `result-ready=0`, phase, absolute deadline, heartbeat, and visibility state. It alone enforces the 60-second chart-readiness deadline. The tooltip scan remains byte-identical and receives a 45-second observer watchdog deadline that does not truncate Collector work.

Runner accepts a result only when generic run ID, deadline run ID, result run ID, payload run ID, protocol name/version, and owner all match. Version/flag mismatch, busy Collector, missing/new/stale IDs, invalid JSON, stopped-without-result, or watchdog expiry pauses the current row without saving a gate outcome. Status text is UI-only in the P2 path.

A one-second Collector heartbeat continues through chart wait and tooltip scan. Visibility changes record a durable hidden-observed timestamp so the watchdog can distinguish hidden/throttled execution from a visible active/stale Collector.

The hard 60-second deadline is checked before accepting a chart. Runner gives chart-wait terminal publication a 5-second grace, but the tooltip observer deadline has no added grace.

## Invariants

- Collector parser, `summarize`, tooltip scan, gate/timing builders, and legacy telemetry builders remain byte-identical to `0.4.6`.
- Runner traffic/dimension/price gates, retry predicates, history behavior, target controls, replay authority, and legacy gate/timing columns remain unchanged from `0.3.8`.
- Flag off retains Runner's legacy 18/15/5/45 status-text path and Collector protocol v1 behavior. A real timer/DOM fixture proves the 0.4.6 and 0.4.7-off chart-first decision is identical at the exact 60,000 ms boundary; P2-on alone applies deadline-first ordering.
- Retry remains one attempt after 600 ms under the existing predicate/replacement rule.
- Additive `collectorEvidence` and `retryEvidence` snapshots are observation-only and supply per-week values/retry yield for pairing.

## Paired evidence tooling

- `scripts/build_p2_pair_capture.py`
- `scripts/analyze_p2_paired_evidence.py`
- `tests/test_build_p2_pair_capture.py`
- `tests/test_analyze_p2_paired_evidence.py`

The proposed old/new live matrix holds candidate code constant and toggles only the P2 flag: old flag off, new flag on. This avoids observer drift while source tests prove the flag-off behavior retains the old timeout path and byte-identical parser/scan/gates. The installed rollback remains `0.4.6/0.3.8`.

Ready-made old-side packages are now included:

- `scripts/sellersprite_traffic_collector_v0.4.7_p2off.user.js` (`@version 0.4.7-p2off`)
- `scripts/sellersprite_integrated_runner_v0.3.9_p2off.user.js` (`@version 0.3.9-p2off`)

Their evidence versions deliberately remain `0.4.7/0.3.9`, both panels visibly say `P2 OFF`, and a dedicated source-equivalence test permits only metadata, the flag value, and the visible OFF label to differ from the enabled candidates. Candidate and baseline packages have no remote auto-update metadata during validation. Old-side capture requires exactly those two OFF packages; new-side capture requires exactly the two enabled candidate packages. Mixed or duplicate panels invalidate the capture.

Enabled candidates now use unique ScriptCat names and visible `P2 ON` labels, so Collector `0.4.7` cannot overwrite the installed `0.4.6` rollback.

## Independent audit findings closed

The first package audit found seven blocking evidence-contract issues. All are now addressed in code and fixtures:

1. Flag-off Collector checked timeout before chart at the final poll. The hard-deadline-first order is now gated to P2-on; off is chart-first like `0.4.6`, with an exact-boundary async fixture.
2. Legacy 15/5/45-second timeouts lacked a Collector payload/version. Runner now persists independent observed panel identity on every attempt, so timeout rows retain Collector `0.4.7` identity without inventing weeks.
3. Runner-off plus Collector-on could be mislabeled as a legal old side. Each row now records Runner flag and observed Collector flag/version/protocol/owner; builder and analyzer independently require the exact side identity and reject mixed panels. Flag-off rows also reject leaked payload or telemetry deadline protocol objects.
4. Old-side passes mutate shared strict history and could auto-skip the new side. Every batch exports the exact sorted Generate-time history-ASIN snapshot. Builder requires old/new snapshots to match, zero history skips, and no paired ASIN in the baseline. The runbook requires full JSON backup, restore before new Generate, final restore, and byte/hash evidence.
5. `no_chart_loaded` was not counted as a P2 timeout. Reports now separate `legacy_runner_wait` from `collector_no_chart_loaded`.
6. Slow-page coverage incorrectly required both sides to remain slow. Slow membership is now anchored to the old baseline; new timing remains the measured comparison.
7. Pair ordering and rollback installation were ambiguous. Builder requires complete `p2-old-*`/`p2-new-*` batches with exact queue/result order and the same old/new sequence. Candidate names are unique, old JSON must be exported before switching, and `0.4.6/0.3.8` remains installed for rollback.

P2 payload protocol and raw telemetry deadline identities are also cross-checked field by field. A legacy timeout with no payload can enter the report structurally, but missing weeks remain missing and therefore fail exact comparison if the new side has values.

The operation contract now distinguishes the Runner's copied canonical history JSON from localStorage byte formatting. It includes one validated DevTools restore block plus `scripts/audit_strict_history_snapshot.py`, which compares the complete JSON value by canonical SHA-256 and fails closed on schema/ASIN errors or any metadata difference. `history_post_old.json` and `history_post_new.json` must be copied before their respective restores, while pre-new and final-restored snapshots must canonically equal the original. Because shared panel IDs can hide a duplicate enabled userscript, old/new ScriptCat enabled-list screenshots are mandatory in addition to visible panel checks.

The analyzer requires at least 30 distinct ASINs, the four value strata on both sides plus at least one old-baseline slow page, exact week keys and Decimal-normalized values (`null` distinct from zero), 100% gate agreement, zero false positives, zero conservative mismatches, exact sequence/history baseline, version/flag/protocol/run metadata, and p50/p90 timeout-kind/retry/protocol-pause recovery reporting.

## Verification completed

- Candidate userscript syntax checks pass.
- Dedicated Collector, Runner, and cross-script protocol suites pass.
- Builder and strict analyzer focused suites pass.
- Dedicated flag-off package source-equivalence and no-auto-update checks pass.
- Full regression passes: 14 userscript syntax checks, 13 SellerSprite JS suites, and 66 Python tests. Formal preflight remains unchanged and clean.
- No real P2 evidence was fabricated.
- No P2 Chrome deployment, 30-ASIN capture, or one-ASIN P2 smoke has occurred.

Candidate SHA-256:

- Collector `0.4.7`: `ADC655D3C4ACD8A800D97960300C1109CAB6DFED7304218CB764B31D197FFCB3`
- Runner `0.3.9`: `8F33CD63535AB3E996156F8BE6436601736ED113E6F8392B0FB95FDF5C80CE04`
- Collector `0.4.7-p2off` package: `F556FA8FD2F7C6329BA5C19C17BAB1D61491CFDA5258B5F227FF12D544715996`
- Runner `0.3.9-p2off` package: `7E6E0D674072B81EEC5C99F9C956DCAA174D70BC8CB644EB108D3D80494DCD2E`
- Pair builder: `FE15CAA015D39E6A83DE26F4A8D9091E6A9F7017354CD565CB04AB451CC0547C`
- Pair analyzer: `79A54D53828D12EAE0FEF760F5C7CCE07448BEE8A5740E37C137A310D1D6F9EA`
- Strict-history auditor: `0191FBABD9DD8EB2A641911BE4F30C7005D809AA0CBF0426A9E4D46A70B5B967`

Please review specifically:

1. flag-off candidate path as the old side of live pairing;
2. 60-second hard readiness versus 45-second observer-watchdog semantics;
3. pause-with-row-pending behavior and fresh-run resume;
4. normalized DOM/payload identity contract;
5. whether the additive raw payload/retry snapshots fully satisfy per-week and retry-yield audit requirements.
6. exact history backup/restore plus sequence identity as the safe paired-run isolation method.

Stop remains in force before live P2 deployment and all later tiers.
