# Review request: merged JSON Excel performance v1.1

Date: 2026-07-31
Owner: Codex
Version: `merged-json-to-excel-v1.1.0`

Please independently review:

- `scripts/download_candidate_images.py`
- `scripts/build_replay_workbooks.mjs`
- `scripts/build_excel_from_merged_json.py`
- `tests/test_download_candidate_images.py`
- `tests/test_build_excel_from_merged_json.py`
- `docs/merged_json_to_excel_cli.md`

Review questions:

1. Can a cache hit cross ASINs or URLs, outlive the configured TTL, skip PNG decoding, or grant A-F acceptance?
2. Can bounded image concurrency write one ASIN's bytes into another ASIN's target or bypass a failed download?
3. Does forced Node exit occur only after both workbooks, all previews, and the build report have completed their awaited writes?
4. Does the independent acceptance checker still run after forced exit and fail the orchestrator on any workbook problem?
5. Do the three rollback arguments fully restore sequential no-cache image handling and natural Node exit?

Evidence:

- Focused tests 11/11 PASS; full bundled-runtime Python regression 199/199 PASS; Node syntax PASS.
- 64 real ASINs: old sequential 38.319s, optimized cold 8.279s, warm 0.489s; all 64 image gates agreed. Three Amazon CDN responses changed encoding between requests but remained the same 600x600 product image for the same ASIN/URL; all other 61 were byte-identical.
- Exact six-product cold and warm end-to-end runs completed in 10.473s and 5.676s; both produced the same six final ASINs and passed machine acceptance. All five warm previews passed visual inspection.
- Full rollback run completed with 6/6 accepted.
- Canonical preflight and formal-history hash checks passed; no hard rule, browser script, replay gate, or history entry changed.

Reject any change that lets cached or parallel image handling grant qualification, removes TTL/URL binding/decoding, exits Node before awaited artifacts are written, or skips post-build acceptance.
