# P2 Collector-Owned Deadline Protocol

## Status

Collector `0.4.7` and Runner `0.3.9` remain validation candidates only. Claude's corrected-design review and the two pre-capture confirmations (value metrics and backward-clock quarantine) are complete. They are not deployed, no 30-ASIN paired capture has run, and no P2 live smoke has run. The currently installed rollback remains Collector `0.4.6` plus Runner `0.3.8`. Tier 2.3 and all later tiers remain out of scope.

Feature flags:

- `ENABLE_P2_COLLECTOR_DEADLINE_PROTOCOL` selects the P2 deadline path.
- `ENABLE_P2_PAIR_SANDBOX_HISTORY` keeps paired validation off the production strict-history ledger.

## Deadline ownership

Protocol: `p2-collector-owned-deadline-v1`, DOM version `2`, owner `collector`.

1. Runner retains the 18-second Collector-panel bootstrap limit.
2. Runner verifies Collector version, flag, protocol name/version, owner, and idle state.
3. The Collect click must synchronously advance to a new run ID with `running=1`, `result-ready=0`, and absolute deadline metadata.
4. Collector owns the existing 60-second chart-readiness budget. The budget is unchanged; P2 only prevents Runner from abandoning the read at 15/45 seconds.
5. Collector evaluates the absolute `Date.now()` wall clock before every chart acceptance, including the first check after a suspended or throttled main thread.
6. A chart first observed at exactly `60,000ms`, at `60,001ms`, or after a long wall-clock jump is rejected by P2-on. The 5-second Runner grace is publication-only: it may wait for an already-decided terminal result, never extend chart reading.
7. The 45-second tooltip deadline is an observer watchdog. Expiry pauses the current row; it never produces a gate outcome.
8. Status text is UI-only while P2 is enabled.

Collector also keeps `lastObservedAtMs` as a wall-clock high-water mark. If `Date.now()` moves backward, Collector publishes `clockAnomalyKind=wall_clock_backward`; Runner checks both explicit anomaly fields and inferred regressions against accepted, phase-start, heartbeat, and last-observed timestamps. Either path quarantines any payload and pauses before acceptance. Panel and payload accepted/last-observed timestamps must match exactly. Builder and analyzer reject anomalous or non-monotonic protocol evidence.

Collector publishes run, phase, hard-deadline, heartbeat, chart-ready, result-ready, overrun, visibility, and first-hidden timestamps in both DOM attributes and the final payload. Runner accepts a payload only when panel run ID, deadline run ID, result run ID, payload run ID, protocol identity, and owner all match.

## Hidden and pause semantics

Current document visibility and Collector-published visibility are checked separately and before `result-ready` acceptance. If either is not `visible`, or `hiddenObservedAtMs` is present, Runner quarantines any observed payload and pauses. A hidden or throttled result can never be accepted later merely because JSON exists.

An unfinished paused row is exported as `pendingRecovery.state=pending-recovery`. It is neither pass nor reject and prevents the batch from becoming `done`. `Start` cannot bypass it; the operator must use `Resume`.

For protocol pauses, Runner preserves:

- pause reason and stale run IDs;
- quarantined attempt and payload evidence;
- the fresh payload, protocol, and successful-attempt run IDs after Resume.

Recovery is valid only when all three fresh IDs are equal, non-empty, and absent from the stale-ID set. Otherwise the row remains fail-closed. Offline replay and acceptance remain the only release authority.

## Additive evidence

Both P2-on and P2-off packages run the same observation code. Their source may differ only in ScriptCat metadata, the P2 flag, and the visible ON/OFF label.

Every completed row preserves:

- final `collectorEvidence`, including every observed week's total traffic, natural traffic, natural share, raw tooltip text, derivation flag, source, and reader version;
- `retryEvidence.firstAttemptEvidence` for the first payload or error;
- `retryEvidence.secondAttemptEvidence` when retry occurs;
- reported and independently recomputable retry recovery yield;
- full protocol recovery evidence.

No missing week or value is synthesized.

## Sandbox strict history

Paired candidates never write `ssIntegratedRunner:v0.3:strict-qualified-history`.

- Production key: `ssIntegratedRunner:v0.3:strict-qualified-history` (read-only).
- Old-side sandbox: `ssIntegratedRunner:v0.3:p2-paired-sandbox-history:off`.
- New-side sandbox: `ssIntegratedRunner:v0.3:p2-paired-sandbox-history:on`.

Each Generate performs an exact clone of the current production ledger into the active side's sandbox. History filtering and any browser-pass recording use only that sandbox. The combined JSON records `p2PairHistoryIsolation/v1`, production write protection, side/key identity, the production snapshot, and the sandbox seed snapshot. The builder requires all snapshots to match exactly and requires zero history skips.

The production ledger must still be audited defensively:

1. Before switching scripts, use `Copy production history JSON` and save it outside the project working path, for example `C:\Users\13045\Documents\amazon_p2_history_audit\<run>\production_before.json`.
2. After both sides finish, copy production history again to `production_after.json` in the same external audit folder.
3. Require the canonical auditor to report `allEqual: true`. Any difference aborts capture review. Do not continue by editing history in DevTools.

```powershell
python scripts\audit_strict_history_snapshot.py `
  "C:\Users\13045\Documents\amazon_p2_history_audit\<run>\production_before.json" `
  "C:\Users\13045\Documents\amazon_p2_history_audit\<run>\production_after.json"
```

## Flag-only paired packages

Old side:

- `scripts/sellersprite_traffic_collector_v0.4.7_p2off.user.js`
- `scripts/sellersprite_integrated_runner_v0.3.9_p2off.user.js`

New side:

- `scripts/sellersprite_traffic_collector_v0.4.7.user.js`
- `scripts/sellersprite_integrated_runner_v0.3.9.user.js`

At every switch, disable all other Collector/Runner versions, reload, verify exactly one panel of each expected version and ON/OFF label, and preserve a ScriptCat enabled-list screenshot. Duplicate panels, mixed versions, an incomplete batch, a non-matching sequence, a pending recovery row, or any history skip invalidates the capture.

## Paired validation semantics

Use at least 30 distinct ASINs. The deliberate sample must include:

- at least 5 old-side timeout/error rows;
- at least 3 genuine P2 recoveries;
- explicit-zero weeks;
- `--` weeks;
- missing-ratio weeks;
- partial 1-2 week reads;
- at least one slow old-side page.

Rows are partitioned by old-side evidence:

### Old-side non-timeout rows

Require 100% agreement for:

- `weekSort` and week label;
- total traffic, natural traffic, and natural share as exact normalized decimals;
- derivation/source/reader provenance;
- final browser gate outcome.

Any mismatch fails reader validation.

### Old-side timeout/error rows

P2-on may legitimately recover a real reading and may change reject/error to pass. This mismatch is expected behavior, not a conservative-mismatch failure. Every recovered row is listed separately with raw per-week tooltip evidence.

A genuine recovery requires:

- P2-on status `ok` and `weeksRead >= 3`;
- non-empty raw tooltip text for every observed week;
- explicit SellerSprite ratios or the existing guarded zero derivation only;
- valid traffic ranges and no fabricated weeks;
- visible, non-hidden protocol evidence;
- chart readiness at or before the fixed 60-second hard deadline.

Every genuine recovery requires manual tooltip review and Builder-verified evidence artifacts. A recovered pass additionally requires full gate completion, offline replay `pass`, and acceptance `pass`. Without that review, analysis may report `readerValidationPassed=true`, but `releaseValidationComplete=false` and final `passed=false`.

Zero false positives remains absolute: no released pass may rest on missing, ambiguous, stale, timed-out, hidden, throttled, or unreadable evidence.

### Old-side partial-to-full recovery rows

An old-side `traffic_weeks_insufficient` row with `weeksRead` 1-2 may enter the same recovery-review path when P2-on reaches `weeksRead >= 3`. This reclassification happens in the analyzer before manual review and is allowed only when:

- every week present on the old side is also present on the new side;
- every overlapping week is exact across normalized traffic values, derivation/source/reader provenance, raw tooltip text, and marker evidence;
- at least one additional week is present on the new side;
- every added week independently has non-empty raw tooltip evidence, valid provenance, valid traffic ranges, and either an explicit SellerSprite ratio or the existing guarded-zero derivation.

Any overlapping-week difference or dropped old week is a hard reader-validation failure. A genuine partial-to-full recovery remains unreleased until the same manual tooltip review applies; a recovered pass also requires offline replay `pass` and acceptance `pass`. The reclassification does not alter any A-F gate and cannot itself grant acceptance.

## Recovery review file

Provide a UTF-8 JSON file for all recovered rows:

```json
{
  "schemaVersion": "sellerSpriteP2RecoveryReview/v2",
  "rows": [
    {
      "asin": "B0XXXXXXXX",
      "pairId": "p2-001-B0XXXXXXXX",
      "reviewBinding": {
        "schemaVersion": "sellerSpriteP2ReviewBinding/v1",
        "pairId": "p2-001-B0XXXXXXXX",
        "asin": "B0XXXXXXXX",
        "evidenceSha256": "<64 lowercase hex characters from the initial analyzer output>"
      },
      "manualTooltipVerified": true,
      "offlineReplayOutcome": "pass",
      "acceptanceOutcome": "pass",
      "evidenceArtifacts": [
        {
          "path": "evidence/B0XXXXXXXX.json",
          "bytes": 1234,
          "sha256": "<64 lowercase hex characters>"
        }
      ],
      "verifiedBy": "operator",
      "verifiedAt": "2026-07-15T00:00:00Z"
    }
  ]
}
```

For a genuine recovered reject, replay and acceptance may be `not_required`; manual tooltip verification and verified evidence artifacts remain required. The Builder resolves relative artifact paths from the review JSON directory, checks file existence, byte count, and SHA-256, stamps `artifactsVerifiedByBuilder=true`, and binds the complete review/artifact manifest into `reviewAttestationSha256`. The final analyzer reopens and rehashes every artifact, recomputes both the evidence binding and review attestation, and fails if any file is missing or changed. A stale ASIN review, changed pair evidence, or changed artifact fails closed.

## Build and analyze

```powershell
python scripts\build_p2_pair_capture.py `
  --old runs\p2_pair_live\old_batch_01.json `
  --new runs\p2_pair_live\new_batch_01.json `
  --out runs\p2_pair_live\pair_capture_unreviewed.json

# First analysis intentionally exits 1 while release review is pending. Use each
# recovery row's reviewBinding in the manual review JSON.
python scripts\analyze_p2_paired_evidence.py `
  runs\p2_pair_live\pair_capture_unreviewed.json `
  --representative-run-dir runs\strict20_live_20260714_084136 `
  --format both

python scripts\build_p2_pair_capture.py `
  --old runs\p2_pair_live\old_batch_01.json `
  --new runs\p2_pair_live\new_batch_01.json `
  --recovery-review runs\p2_pair_live\recovery_review.json `
  --out runs\p2_pair_live\pair_capture_reviewed.json

python scripts\analyze_p2_paired_evidence.py `
  runs\p2_pair_live\pair_capture_reviewed.json `
  --representative-run-dir runs\strict20_live_20260714_084136 `
  --format both
```

The formal analyzer CLI requires a manifest-complete raw representative run directory and exits `0` only when reader validation passes, all recovered rows have complete required review, false positives are zero, and the headline ROI is available. `run_summary.json` must identify the complete batch set; its derived gate filenames must exactly match the directory's `gate_log_*.tsv` set, and its `maxAttempts`/qualified totals must match the re-derived gate rows. The final analyzer rehashes the run summary and every gate file. Empty, partial, mixed, synthetic, or mistyped baselines are contract errors. It exits `1` for valid but failing or release-pending evidence and `2` for an invalid capture contract.

The report also includes:

- old `traffic_weeks_insufficient` rows with `weeksRead` 1-2, raw P2-on conversions to at least 3 weeks, exact-overlap/evidence-verified recoveries, release-validated qualified recoveries, and first-attempt versus retry-assisted counts;
- old `collection_error` rows and their raw and evidence-verified recovery counts;
- true pairwise `new - old` p50/p90 timing deltas for total, chart, and Collector time, with missing-pair counts;
- independently verified retry yield as recovered/retried and its side-to-side delta when both sides have a measured value.

The headline ROI is projected browser visits per qualified item. The analyzer independently re-derives the representative run from raw `gate_log_*.tsv` files, computes separate sample rates for partial-to-full and `collection_error`, and applies only release-validated qualified rates to the corresponding representative rejection buckets. For the last real run, the re-derived baseline is 371 visits, 10 qualified, and 361 rejected (`37.1` visits per qualified), including 214 `traffic_weeks_insufficient` rows with 1-2 weeks and 43 `collection_error` rows.

The deliberately stratified 30-ASIN sample's raw overall yield is never extrapolated as representative. Projected visits per qualified remains unavailable until reader validation passes and all recovery review/replay/acceptance requirements are complete. Evidence-recovery rates, qualified-recovery rates, pairwise p50/p90 timing, and retry yield remain separately visible.

OFF and ON are sequential captures, so SellerSprite data drift can contribute to a recovered week. Exact overlapping evidence reduces that attribution risk. A recovery that clears all evidence, manual review, replay, and acceptance guardrails is still a genuine qualifier regardless of cause; only the amount of value credited specifically to P2 may be slightly overstated. This is an attribution caveat, not a false-positive relaxation.

## Stop point

The corrected design and pre-capture confirmations are approved. The only authorized next actions are the documented P2-OFF/P2-ON 30-ASIN capture, external history equality audit, paired analysis, and, only if paired evidence passes, one isolated one-ASIN P2 smoke. Report before any merge or formal-run enablement. Rollback remains Collector `0.4.6` plus Runner `0.3.8`. Stop before Tier 2.3.
