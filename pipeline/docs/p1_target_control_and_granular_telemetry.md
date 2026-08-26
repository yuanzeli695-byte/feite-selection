# P1 Target Control And Granular Telemetry

## Scope

Runner `0.3.8` adds two observation/coordination features while keeping the Collector at `0.4.6`:

- an optional externally supplied cumulative remaining target;
- a `Stop after current row` action that lets an in-flight row finish;
- a granular telemetry sidecar for navigation, Collector handshakes, persistence, panel rendering, and control events.

The final release authority remains `replay_existing_batch.py` plus `acceptance_checker.py`. Runner `qualifiedCount`, `browserPassesThisBatch`, `remainingTargetAfterBrowser`, and any sidecar field are not final acceptance evidence.

## Target control

The existing `targetQualified` field remains the requested final target for the run. For a later browser batch, the operator may enter `remainingTargetAtStart`, computed from the latest offline replay of the same run:

```text
remainingTargetAtStart = requested final target - offline replay qualified count
```

When present, Runner uses that snapshot only as a queue-stop budget. It stores:

- `requestedFinalTargetAtStart`;
- `remainingTargetAtStart`;
- `browserPassesThisBatch`;
- `remainingTargetAfterBrowser` (observation only);
- `targetControlVersion`;
- `stopAfterCurrentRowRequested`, `stopAction`, and `stopReason`.

The snapshot is not automatically changed by Runner. Recompute it after offline replay before generating the next batch. A zero remaining target does not generate a browser batch. An invalid or oversized remaining target fails closed.

Use the same frozen run baseline when calculating the snapshot. The current replay/history synchronization behavior is unchanged in P1, so repeatedly replaying a partial run against a history ledger already updated by that unfinished run can self-skip prior rows. This change does not silently alter that history contract.

`Stop after current row` is separate from `Pause`: it does not cancel Collector work or create a partial result. The current row is saved first, then the batch ends with `operator_stop_after_current_row`.
Before every in-flight stage save, Runner merges the latest persisted stop/pause fields so a button click made during an asynchronous Collector or chart wait cannot be overwritten by an older state snapshot.

## Granular sidecar

With `ENABLE_TIER0_GRANULAR_TELEMETRY=true`, Runner stores `sellerSpriteGranularTelemetry/v1` under its local sidecar key and exposes separate copy buttons for granular JSON, granular TSV, and control-event TSV. The legacy `sellerSpriteTelemetry/v1`, gate TSV, timing TSV, and combined JSON structures remain unchanged apart from the additive target-control fields.

Missing or stale sidecars are reported as missing; no zero or inferred timing is inserted. Sidecar writes never call `saveBatch` or alter gate decisions.

Granular writes and cleanup are best-effort: storage quota or permission errors are isolated from Runner state saves, navigation, stop handling, and gate evaluation. Sidecars are tied to the batch creation timestamp, and regenerating the same deterministic queue hash starts a fresh sidecar instead of reusing prior rows or control events.

The sidecar records navigation intent and page timing snapshots, observed Collector button/tab/chart/status events, every Collector attempt including retry attempts, existing Collector internal timing fields, state persistence and panel-render timings, fixed delay observations, and pause/resume/recovery/error events.

The current status-text handshake, 15/45/60 second budgets, tooltip scan order, and retry policy are deliberately unchanged. Those are separate Class B experiments and require paired validation before modification.

## Offline timing analysis

Run the standard-library analyzer against a completed run:

```powershell
python scripts\analyze_timing.py runs\strict20_live_20260714_084136 --format both
```

The analyzer strictly pairs `timing_log_*.tsv` with `gate_log_*.tsv` by `(batchName, queueHash, asin)`. It fails closed on missing columns, duplicate/orphan rows, malformed timestamps, negative durations, or unexplained blank stage values.

It reports both observed wall time (first `startedAt` to last `finishedAt`) and inferred wall time including each batch's first `detailPageMs`. It separately reports stage totals, row-clock overhead, intra-batch unattributed gaps, and inter-batch gaps because `detailPageMs` spans navigation and adjacent-row transitions rather than being a pure isolated stage.

For the 371-row run, the inferred wall-minus-stage residual is exactly `624,505 ms = 615,273 ms unattributed intra-batch gap + 9,232 ms row-clock overhead - 0 ms detail outside the inferred boundary`. The legacy TSV cannot prove whether the 615,273 ms came from panel rendering, JSON serialization, storage writes, fixed delays, or another inter-row activity. Runner `0.3.8` records those candidate components separately so the next live run can attribute them from evidence.

## Deployment smoke

Runner `0.3.8` was enabled with Collector `0.4.6` and independently smoke-tested on 2026-07-15. The raw bundle is in `runs/p1_038_deployment_smoke_20260715`.

The live checks confirmed:

- exactly one Collector `0.4.6` and one Runner `0.3.8` panel on Amazon US;
- `remainingTargetAtStart=0` generated no browser batch;
- a stop request made while a row was in `Status: running / Step: traffic` let that row finish and persist before ending with `operator_stop_after_current_row`;
- the result remained rejected, strict-qualified history stayed at 55, and Runner did not grant acceptance;
- legacy gate/timing exports and the separate granular JSON/timing/control exports were present;
- the granular sidecar matched the batch timestamp/hash boundary and remained outside gate/replay authority.

The same smoke session also preserved a baseline example of the existing deadline mismatch: Runner timed out at 45 seconds while Collector later returned a valid payload. That evidence does not change P1 behavior and is only an input to the separately gated P2 experiment.

## Rollback

Rollback is to Runner `0.3.7` with Collector `0.4.6`. No history or acceptance rollback is required. Before enabling `0.3.8` in a formal Chrome run:

1. verify exactly one Collector `0.4.6` and one Runner `0.3.8` panel;
2. run one isolated ASIN that cannot contaminate a formal target;
3. confirm legacy gate/timing output is unchanged in meaning and granular fields are populated;
4. confirm a forged sidecar cannot affect replay or acceptance;
5. preserve the raw JSON, sidecar exports, and smoke report.

These smoke requirements are now satisfied by `runs/p1_038_deployment_smoke_20260715`. The rollback remains available until the formal approved-version configuration is deliberately updated.

No timeout, tooltip-scan, DOM-attribute-handshake, preloading, hidden-tab, or concurrent-page optimization is included in this P1 change.
