# Runner 0.3.8.12 Keepa 30-second readiness handoff

## Scope

Created a fail-closed browser-timing candidate from Runner 0.3.8.11. The only runtime change is `KEEPA_CHART_READY_TIMEOUT_MS` from 20,000 to 30,000 ms, with protocol id `keepa-chart-ready-30s-v3` and userscript version 0.3.8.12.

Before live paired capture, the stale internal `VERSION = '0.3.8.11'` identifier was corrected to `0.3.8.12`. This changes panel and telemetry identity only; the focused hard-gate parity test remains unchanged.

## Files

- `scripts/sellersprite_integrated_runner_v0.3.8.12_zh_keepa_30s.user.js`
- `tests/test_sellersprite_keepa_wait_v03812.mjs`
- `docs/keepa_30s_readiness_20260805.md`
- `progress.md`

## Safety Contract

The traffic-block 5-second shared deadline and `traffic_block_timeout` reject path remain enabled and unchanged. Missing Keepa canvas or parseable tooltip still fails closed after 30 seconds. Gate functions are byte-for-byte equivalent to the 0.3.8.7 hard-gate baseline, and final acceptance remains owned by offline replay plus acceptance checking.

## Verification

- `node --check`: PASS.
- Focused 25-second late-ready, 30-second no-canvas/no-tooltip, 4-second traffic recovery, 5-second traffic timeout, parent-click, and hard-gate parity fixtures: PASS.
- All SellerSprite JavaScript suites: 36/36 PASS.
- Bundled Python regression: 200/200 PASS.
- Canonical strict preflight: PASS with zero rule drift and strict history count 69.
- Metadata/runtime version identity: PASS; both identifiers are 0.3.8.12.

## Pending Live Evidence

Install only Runner 0.3.8.12 beside Collector 0.4.6.4, refresh Amazon, and verify the panel version. Record a one-ASIN Chrome smoke and at least 30 real-ASIN paired outcomes against 0.3.8.11 before formal release. Do not report offline validation as live deployment evidence.

Rollback is to disable 0.3.8.12, re-enable the unchanged 0.3.8.11 file, and refresh the page. No batch or history migration is required.
