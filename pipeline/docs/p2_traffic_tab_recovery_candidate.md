# P2 traffic-tab recovery candidate

## Status

- Candidate Runner: `sellersprite_integrated_runner_v0.3.8.3_zh_excel_p2_candidate.user.js`
- Collector: unchanged `sellersprite_traffic_collector_v0.4.6_zh_p1.user.js` (`0.4.6.2`)
- Feature flag: `ENABLE_TIER2_TRAFFIC_TAB_RECOVERY`
- Recovery version: `tier2-traffic-tab-recovery-v1`
- Deployment status: not approved and not installed as the production Runner
- Rollback: keep using Runner `0.3.8.2` with Collector `0.4.6.2`

## Confirmed cause

The formal 17-row batch had one false protection pause. The Collector button was observed and the Runner checked for the exact `流量洞察` tab one millisecond later. The tab was not yet rendered, so the existing fail-stop path paused the row for 96,692 ms. Manual refresh and Resume later collected the same ASIN normally.

## Candidate behavior

The candidate preserves exact-text matching and all existing access blockers. It adds:

1. up to 2,000 ms of tab-readiness polling at 100 ms intervals;
2. continuous login and paid-plan blocker checks during the grace period;
3. at most one persisted reload of the same row when only the traffic tab is missing;
4. an exhausted second miss returning to the existing protection pause;
5. recovery marker cleanup when the row is committed;
6. operator Pause ownership preserved if the state changes during the grace period;
7. control events for reload, exhaustion, pause cancellation, and marker cleanup;
8. separate granular fields for wait start, actual click time, grace wait, poll count, and grace recovery.

The recovery marker is persisted before navigation. A storage failure therefore stops navigation and leaves the current row uncommitted. No A-F gate, Collector parser, conditional retry, history rule, result commit, replay, or Excel acceptance function was changed.

The actual click timestamp is recorded only when the exact tab is clicked. Grace recovery is classified by `pollCount > 1`, not by elapsed time, so the wait is not misreported as chart-render latency.

## Automated candidate checks

The isolated fixture executes the asynchronous tab wait against a fake clock and DOM. It covers immediate appearance, 100 ms appearance, 1,900 ms appearance, full grace expiry, a login blocker appearing during grace, and feature-flag OFF behavior. Pure state tests cover one-reload exhaustion, marker retention across blocker transitions, and operator-pause preservation. These checks qualify the file only as a source-level candidate; they do not replace paired real-ASIN evidence.

## Required validation before deployment

- at least 30 real ASINs paired between Runner `0.3.8.2` and `0.3.8.3`;
- exact per-week value and provenance agreement for all non-recovery rows;
- 100% final gate-outcome agreement and zero false positives;
- at least three genuine traffic-tab recoveries;
- raw Collector JSON, manual tooltip review, offline replay, and acceptance for every recovered pass;
- one isolated live smoke after installation;
- Excel bridge version contract remains unchanged until the candidate is approved.

If fewer than three genuine recoveries are observed, the candidate remains experimental even when all automated tests pass.
