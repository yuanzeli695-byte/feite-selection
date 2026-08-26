# Claude review request: Chinese 0.4.6/0.3.7 candidates + accepted-only Excel bridge

## Requested review

Please review the additive candidate delivery only. Do not approve broader deployment or change the canonical preflight pair.

## Files

- `scripts/sellersprite_traffic_collector_v0.4.6_zh.user.js`
  - version `0.4.6.1`
  - SHA-256 `AE831513AFFAF1D7A846EBE3A8EC9B60F35A97ADE1D2E858FEB8C98E13D08AF1`
- `scripts/sellersprite_integrated_runner_v0.3.7_zh_excel.user.js`
  - version `0.3.7.1`
  - SHA-256 `AE01043E3FD289BB98E35A0F093C5ED38404189E9EBF7D44A7BA0B7DEE6AFC91`
- `scripts/selection_excel_bridge.py`
  - SHA-256 `BB07C146A9BBDE400584C85AD5F5579A887CA35804109826CB523A846BEC9981`
- `scripts/start_selection_excel_bridge.ps1`
  - SHA-256 `D4D98E41CBFA5C3AEBC1ABA9AA7BEC6F4040AA434ACBA520486AE557C4FECCD3`
- `tests/test_sellersprite_zh_excel_variants.mjs`
- `tests/test_selection_excel_bridge.py`
- `docs/selection_zh_excel_guide.md`
- `runs/zh_excel_0371_smoke_20260717/smoke_report.md`

## Invariants to verify

1. Chinese localization changes display only. JSON statuses, decisions, gate rules, TSV columns, schemas, DOM IDs, and hard-gate functions remain machine-stable.
2. Runner no longer waits on visible `/Collecting/i`; it uses Collector `data-ss-running` plus `data-ss-result-ready`.
3. Excel is enabled only for a `done` batch and only talks to loopback HTTP (`127.0.0.1` or `localhost`) with a token.
   `localhost` is canonicalized to `127.0.0.1` so the bridge response remains same-origin under strict download validation.
4. The browser cannot grant release. The bridge must run replay, workbook build, and acceptance before exposing XLSX.
5. Candidate JSON and batch JSON are immutable evidence snapshots with hashes. Reusing the same batch identity with changed bytes is rejected.
6. Replay receives an attempt-local sandbox project root seeded from production strict history; production history is never updated by the bridge.
7. Target incomplete, acceptance failure, wrong/missing per-row versions, ambiguous candidate mapping, or untrusted download URL cannot expose a workbook.
8. `visualAcceptanceRequired=true` and `productionHistoryUpdated=false` are mandatory response invariants.

## Verification already run

- All 14 `test_sellersprite*.mjs` suites: PASS.
- Python suite: 83 tests PASS.
- Strict-selection preflight: PASS, zero warnings/errors, canonical pair still `0.4.6/0.3.7`, history count 55.
- Isolated browser smoke: Chinese panels and stable Collector handshake PASS; missing chart remained review.

## Known incomplete live evidence

- The candidate pair is not installed/enabled in ScriptCat.
- No real one-ASIN Runner orchestration or real accepted Excel build has run.
- Existing Chrome was observed still running failed P2 ON `0.4.7/0.3.9`; it must be disabled before any formal use.

Named rollback: disable the Chinese candidates and restore canonical Collector `0.4.6` + Runner `0.3.7`. Stop before any canonical/preflight version change.
