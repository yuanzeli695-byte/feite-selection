# SellerSprite Export to Runner Queue v1 Handoff

## Scope

Added an independent, fail-closed adapter from SellerSprite `.xlsx`, `.csv`, and `.tsv` exports to the existing strict candidate-pool ASIN queue. It does not change Runner, Collector, shared thresholds, or final A-F acceptance.

## Files

- `scripts/sellersprite_export_to_runner_queue.py`: v1.4 header mapping, row normalization, formal query manifest generation, strict-history sync, and invocation of `prepare_strict_candidate_pool.py`.
- `tests/test_sellersprite_export_to_runner_queue.py`: formal source, strict-history reuse, fail-closed header, and explicit legacy-mode coverage.
- `docs/SELLERSPRITE_EXPORT_TO_RUNNER_QUEUE_ZH.md`: operator command and failure/rollback contract.

## Source Contract

Formal mode requires the original full SellerSprite product-research URL and an ISO-8601 capture time. The URL must validate as US, `maxReviews=100`, and a non-empty `nodeIdPaths` scope. The adapter writes a hashed source query and source manifest. `--allow-legacy-export` is explicit and its output is labeled non-formal.

## Verification

Run:

```powershell
python -m unittest tests.test_sellersprite_export_to_runner_queue
python "$env:USERPROFILE\.codex\skills\amazon-us-strict-selection\scripts\preflight.py" --project-root "C:\Users\13045\Desktop\amazon_products"
python tests\test_batch_runner_acceptance.py
```

## Follow-up

The actual 2026-07-31 Home & Kitchen export verified `价格($)`, `商品主图`, generic `图片` as a separate thumbnail column, and ASIN display values with Amazon hyperlinks. The regression uses `商品主图` only and keeps ASIN display values. The user explicitly authorized the v1.4 queue-only `--allow-missing-sales` override: missing parent/child/monthly sales remain missing and do not affect Runner A-F acceptance. Unknown or ambiguous headers intentionally fail closed; add an alias only after inspecting the real exported header and add a regression case for it.
