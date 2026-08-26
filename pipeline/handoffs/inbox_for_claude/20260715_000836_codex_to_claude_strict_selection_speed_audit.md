---
from: codex
to: claude
priority: p1
requires_action: yes
tags: [performance, collector-0.4.6, runner-0.3.7, tier0, tier2, validation]
---

# Amazon US strict-selection speed audit and optimization review

## 1. Scope

Review the measured performance of run `strict20_live_20260714_084136` and return a versioned optimization proposal.

This handoff authorizes analysis and a patch plan only. Do not edit the Collector, Runner, acceptance code, thresholds, history, or delivered run artifacts in this phase.

Explicit non-scope:

- no A-F threshold, gate order, tolerance, or release-authority changes;
- no inferred or fabricated traffic, dimensions, price, or image evidence;
- no Tier 2.3 preloading, hidden tabs/iframes, next-ASIN prefetch, multi-profile concurrency, parallel product pages, or focus automation;
- no change that can turn a current reject/review/error into a pass.

## 2. Operational result

- Run ID: `strict20_live_20260714_084136`.
- Approved browser pair: Collector `0.4.6`, Runner `0.3.7`.
- Browser results: 371 ASINs, 10 Runner passes, 361 Runner rejects.
- Final replay: target 10, attempts 333, qualified 10, rejected 323, `stoppedReason=target_reached`.
- Strict-history baseline/final: 45 -> 55.
- Acceptance: PASS, including 10 unique ASINs, no final/audit overlap, all current traffic gates, dimensions, allowed price trends, 10 embedded images, and zero formula-error strings.
- Six browser batches were required. The final target changed from 20 to 10 during the run; the tenth cumulative pass occurred at replay attempt 333, but the browser had already processed 38 later rows.

## 3. Measured timeline

| Batch | Rows / passes | Browser wall time | Active total p50 / p90 | Notes |
|---|---:|---:|---:|---|
| `a671b35c` | 79 / 1 | 55.2 min | 15.8 / 34.1 s | 7 abnormal page waits; 25 rows missing Collector version |
| `5fd067fc` | 66 / 1 | 20.7 min | 8.1 / 23.9 s | normal relative baseline |
| `c01f8768` | 64 / 1 | 23.5 min | 7.6 / 35.2 s | normal relative baseline |
| `659ca53f` | 61 / 4 | 26.2 min | 13.4 / 37.3 s | best pass yield |
| `186ea4ec` | 55 / 1 | 25.4 min | 15.4 / 43.4 s | 11 conditional retries |
| `ef64379a` | 46 / 2 | 35.0 min | 15.9 / 43.9 s | one 700 s page stall; max active row 103 s |

Totals:

- six batch wall times: about 186 minutes;
- first row to last row: about 5 h 38 min;
- inter-batch preparation, export, recovery, and idle gaps: about 152 minutes;
- browser throughput during active batches: about 120 ASIN/hour;
- end-to-end observed throughput across the 5 h 38 min span: about 66 ASIN/hour;
- pass yield: 2.70%, or 37.1 browser visits per qualified item.

## 4. Where time was spent

- Detail-page navigation/readiness: 74.83 min.
- SellerSprite traffic chart: 98.17 min.
- Dimensions: about 0.01 min.
- Price chart: 2.54 min.

Detail page plus traffic collection account for about 98.5% of measured stage time. Dimensions and workbook generation are not meaningful bottlenecks.

Only eight `detailPageMs > 30s` rows consumed about 30.98 minutes. The largest waits were 700.07 s, 431.85 s, 317.31 s, and 158.00 s. These values are consistent with browser/control recovery or a throttled/blocked main thread, not ordinary Amazon navigation.

The rejection distribution explains the low yield:

- `traffic_weeks_insufficient`: 214;
- `collection_error`: 43, including 37 x 15 s and 6 x 45 s timeout classes;
- `traffic_error` / no usable data after readiness retry: 30;
- recent-four-week minimum below 70%: 28;
- recent-four-week average below 70%: 5;
- `price_current_missing`: 29;
- ASIN mismatch/redirect: 9;
- disallowed price trend: 3.

There were 30 `tooltip_not_ready` retries. They consumed about 20.5 active minutes and all 30 still ended as `traffic_error`; this run recovered zero passes from retry. That is a high-priority review target, but it is not permission to remove retries globally.

## 5. Why the new skill/version is not proven to be the regression

The skill added an audited state machine and final-qualified target semantics; it did not add browser sleeps.

Code-level comparison:

- Collector `0.4.5 -> 0.4.6` adds guarded explicit-zero parsing and does not expand the tooltip coordinate grid or wait budget.
- Runner `0.3.6 -> 0.3.7` narrows the one-time retry policy to explicit chart/tooltip readiness failures.
- In this run, 22 partial 1-2 week samples were not retried under `0.3.7`; the older policy would have retried them.
- Existing 60-ASIN deterministic pairing showed 60/60 C-gate outcome agreement, zero false positives, and old retries 2 versus new retries 0. That pairing proves gate parity, not live throughput.

The main user-visible regression is therefore explained by scope and environment:

1. the target now means final A-F-qualified products, not queue rows;
2. current pass yield fell to 2.70%, so 333 attempts were needed for 10 final products;
3. every candidate requires serial Amazon navigation and SellerSprite tooltip work before C can reject it;
4. the first and sixth batches contain large browser/control stalls;
5. six separate queues introduced roughly 152 minutes of inter-batch gaps;
6. batch-level `targetQualified` was not reduced to the remaining cumulative target, so 38 rows ran after the tenth overall pass.

Do not claim a `0.3.6` versus `0.3.7` live speed regression without a same-queue, same-session paired timing run.

## 6. Code bottlenecks to review

Collector `scripts/sellersprite_traffic_collector_v0.4.6.user.js`:

- chart wait polling around lines 202-219;
- tooltip DOM reading around lines 222-247;
- `19 x 4` coordinate scan with a fixed 180 ms wait around lines 546-606;
- default chart wait budget around line 735.

The current scan continues through alternate Y coordinates even after the same X coordinate has produced a valid dated tooltip. Measured traffic averages support this as the largest internal cost: first-week short circuit about 7.2 s, second week 13.1 s, third week 18.5 s, and complete four-week reads about 20.9 s.

Runner `scripts/sellersprite_integrated_runner_v0.3.7.user.js`:

- panel polling around lines 555-568;
- full-state persistence/panel rendering around lines 668-680 and full JSON serialization around lines 855-892;
- full-page `location.assign` navigation around lines 952-973;
- price sampling fixed waits around lines 1116-1137;
- serial Collector panel/chart/start/finish waits around lines 1140-1153;
- retry delay around lines 1171-1175;
- fixed per-row/new-page delays around lines 1332-1341.

The 15 s Runner chart wait can fail before the Collector's own 60 s upper bound, while the 45 s completion wait is also shorter than that Collector bound. Please analyze the protocol mismatch; do not merely increase or reduce timeouts.

## 7. Safe first proposal: Tier 0 / class A

Please return a patch design for these low-risk items first:

1. An offline timing analyzer that reports per-stage p50/p90/max, rejection costs, retry yield, navigation stalls, and batch gaps from existing TSVs.
2. More granular telemetry: navigation start, Amazon DOM ready, SellerSprite injection, traffic tab click, chart ready, Collector start/result handshake, state persistence, panel render, and manual pause/recovery.
3. A cumulative remaining-target control so a later batch can stop after the outstanding number of final candidates, plus a clear `stop_after_current_row` action.
4. Operational queue preparation that can occur locally while the current browser batch runs, without background browser preloading.

These changes must remain observation/coordination only and must not alter acceptance.

## 8. Candidate class B experiments

For each item below, propose a separate feature flag, rollback, tests, and paired evidence. Do not implement until approved.

1. For each X position, try a primary Y first and move to the next X once a new dated valid tooltip is confirmed; try alternate Y values only on failure. If fewer than the required weeks are obtained, fall back to the current full `19 x 4` scan.
2. Use the existing `data-ss-run-id` and `data-ss-result-ready` contract for explicit Collector/Runner result handshakes rather than status-text polling.
3. Reconcile the duplicate Runner and Collector readiness budgets through one auditable deadline protocol.
4. Replace fixed 400/500 ms waits with conservative readiness handshakes that retain hard upper bounds.
5. Keep the live panel lightweight and serialize the complete JSON only for export/copy or durable checkpoints.
6. Add an external wall-clock watchdog that distinguishes a paused/throttled page from a genuine 15/45 s Collector failure; do not change final evidence semantics.

Required for every B-class change:

- versioned feature flag and named rollback;
- syntax and focused fixture tests;
- at least 30 real ASINs with old/new paired evidence;
- 100% final gate-outcome agreement;
- zero false positives; any mismatch may only be more conservative;
- timing comparison with p50/p90 and timeout/retry yield;
- one-ASIN live Chrome smoke after deployment;
- rollback to Collector `0.4.6` and Runner `0.3.7`.

## 9. Hard-gate invariants

Preserve without exception:

- current evidence is the only release authority;
- missing, ambiguous, stale, timed-out, redirected, or unreadable data cannot pass;
- C requires `status=ok`, no mismatch, `weeksRead>=3`, and latest/average/minimum natural share all `>=70%`;
- D requires sourced, nonempty dimensions/weight;
- E requires current price in range and `stable` or `rising` trend;
- A/B/F and final replay/acceptance ownership remain unchanged;
- cache/history may skip or lower priority but may never grant a pass.

## 10. Evidence artifacts

- `runs/strict20_live_20260714_084136/run_summary.json`
- `runs/strict20_live_20260714_084136/acceptance_report.md`
- `runs/strict20_live_20260714_084136/timing_log_*.tsv`
- `runs/strict20_live_20260714_084136/gate_log_*.tsv`
- `runs/strict20_live_20260714_084136/integrated_batch_*.json`
- `runs/strict20_live_20260714_084136/candidate_pool*/summary_strict_queue_*.json`
- `runs/tier2_pair_validation_20260713/pair_validation_summary.json`
- `runs/tier2_pair_validation_20260713/pair_validation_report.md`
- `docs/tier2_reader_retry.md`
- `progress.md`

Specific timing evidence:

- batch 1 long waits: `runs/strict20_live_20260714_084136/timing_log_a671b35c.tsv`;
- batch 6 700 s page stall and 103 s active row: `runs/strict20_live_20260714_084136/timing_log_ef64379a.tsv`;
- all 30 retries and their zero recovery result can be joined by ASIN between `timing_log_*.tsv` and `gate_log_*.tsv`.

## 11. Exact response requested from Claude

1. Confirm or challenge the measured root-cause ranking using the raw TSV/JSON evidence.
2. Identify any telemetry arithmetic or timing-ownership flaw before proposing optimization.
3. Return a ranked, versioned patch plan with expected savings and explicit rollback for each item.
4. Specify the exact old/new paired test matrix and live smoke needed for each B-class proposal.
5. Explain whether the tooltip primary-Y/fallback design can preserve every current reading and hard-gate result.
6. Propose how cumulative remaining target should be represented across multiple batches without granting acceptance inside the Runner.
7. Do not edit code until Codex/user separately approves the selected proposal.

Work stopped before Tier 2.3 or any later unauthorized tier.
