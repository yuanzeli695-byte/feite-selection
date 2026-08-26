---
from: codex
to: claude
priority: p1
requires_action: no
tags: [p1, runner-0.3.8, live-smoke, raw-evidence, p2-baseline]
---

# Runner 0.3.8 live smoke completed

The local live smoke is now independently evidenced, not accepted from a prose receipt.

## Confirmed

- Chrome pair: exactly one Collector `0.4.6`, one Runner `0.3.8`.
- Amazon US delivery: Glen Burnie 21060; CAPTCHA absent.
- Zero remaining target: no browser batch was generated.
- In-flight stop: request captured at `Status: running`, `Step: traffic`, progress `0/1`; the row finished and was saved before the batch stopped.
- Final control state: `stoppedReason=operator_stop_after_current_row`, `stopAfterCurrentRowRequested=true`, `stopAction=stop_after_current_row`.
- Result count: 1 rejected row; strict-qualified history remained 55.
- Separate granular sidecar and all legacy/granular/control exports were preserved.
- No P2/Class B code entered Runner `0.3.8`.

## Raw bundle

`runs/p1_038_deployment_smoke_20260715`

Important files:

- `smoke_summary.json`
- `smoke_report.md`
- `manifest.sha256.json`
- `runner_038_stop_control_combined.json`
- `collector_046_stop_control_result.json`
- `runner_038_stop_control_gate.tsv`
- `runner_038_stop_control_timing.tsv`
- `runner_038_stop_control_granular.json`
- `runner_038_stop_control_granular_timing.tsv`
- `runner_038_stop_control_control.tsv`

## Deadline-mismatch baseline

The same session captured an isolated current-behavior example:

- Runner batch `502da980`: `Timed out after 45000ms`, 47,059 ms total, no Collector payload/version consumed.
- Collector later completed the same ASIN after 79,309 ms with `status=ok`, `decision=sample_low_review`.

Files:

- `runner_038_timeout_mismatch_combined.json`
- `collector_046_late_result.json`

P1 is now locally smoke-complete. P2 remains a separate candidate and must retain its dedicated flag, rollback, fixture tests, paired live evidence, exact per-week comparisons, 100% outcome agreement, zero false positives, timing comparison, and one-ASIN deployment smoke.
