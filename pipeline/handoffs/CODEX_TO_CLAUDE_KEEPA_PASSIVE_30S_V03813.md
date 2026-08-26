# Runner 0.3.8.13 Keepa passive-wait handoff

## Scope

Created an independent Class B candidate from Runner 0.3.8.12. `keepa-passive-wait-30s-v1` is enabled by default: after the initial Keepa tab and one-month-range actions, the 30-second readiness loop cannot invoke the retry callback, re-click the tab, re-select the range, or trigger the prior resize/reload sequence.

## Files

- `scripts/sellersprite_integrated_runner_v0.3.8.13_zh_keepa_passive_30s.user.js`
- `tests/test_sellersprite_keepa_passive_wait_v03813.mjs`
- `docs/keepa_passive_30s_20260805.md`
- `progress.md`

## Audit and Safety

Gate logs include `pricePassiveWaitEnabled`, `pricePassiveWaitVersion`, and the existing `priceRetryCount`. For this candidate, price-stage wait fixtures require `priceRetryCount=0` and zero retry-callback calls. Missing canvas or tooltip still fails closed after 30 seconds. The traffic 5-second fail-closed path and all gate functions remain unchanged.

The internal `VERSION` is explicitly 0.3.8.13, while the paired baseline now reports the corrected 0.3.8.12 identity. Result, timing, and gate logs can therefore be attributed to the installed side without relying only on the userscript header.

## Verification

- Syntax and focused passive-wait tests: PASS.
- SellerSprite JavaScript suites: 37/37 PASS.
- Bundled Python regression: 200/200 PASS.
- Canonical strict preflight: PASS with zero rule drift and strict-history count 69.

## Pending Live Evidence

Install only Runner 0.3.8.13 with Collector 0.4.6.4. During a one-ASIN Chrome smoke, confirm there is one initial Keepa activation, no repeated tab/range clicks during the 30-second wait, and exported `priceRetryCount=0`. At least 30 real-ASIN paired outcomes against 0.3.8.12 remain required before formal release.

Rollback: disable 0.3.8.13, enable the unchanged 0.3.8.12 candidate, and refresh Amazon. No state migration is required.
