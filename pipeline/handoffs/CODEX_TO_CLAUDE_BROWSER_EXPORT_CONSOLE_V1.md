# Codex to Claude: browser-export candidate source v1

Date: 2026-08-05

## Scope

The local console at `C:\Users\13045\Documents\亚马逊电商选品\automation_console` now defaults new category-pool batches to `browser_export`. This is a candidate-source adapter for SellerSprite subaccounts; it does not change A-F acceptance authority.

## Contract

- The console owns a persistent global category pool with case-insensitive dedupe and `available -> assigned -> completed` status tracking.
- A pool-backed batch claims exactly one available category. The server replaces client category text with the claimed row and rejects duplicate claims.
- One current SellerSprite `.xlsx`, `.csv`, or `.tsv` export is required for that batch category.
- Each upload is bound to the full US product-research URL and SHA-256.
- Query parameters must be equal to or narrower than the batch filters; missing or wider parameters fail closed.
- All exports are normalized into `query_*.json`, combined under a current source manifest, then passed to the canonical strict history, candidate-pool, image-download, and analysis-workbook steps.
- Every processing retry uses an isolated attempt directory.
- Runner evidence remains non-final; replay and acceptance remain unchanged.

## Rollback

Select `official_api` when creating a new batch and provide a valid DPAPI-protected Open API key. Existing batches retain their stored `candidateSourceMode`; no canonical rules, history, Collector, or Runner files were changed by this feature.

## Verification

- Console unit tests cover pool import/dedupe, exact-one-category claims, duplicate-claim rejection, completion sync, HTTP import/listing, default source mode, node parsing, URL non-widening, and upload staging.
- Canonical preflight remains the release prerequisite.

## Pool rollback

The pool is an orchestration-only SQLite table. Existing batches do not require migration and remain readable. Rollback the console code to the previous version; `category_pool_items` can remain in SQLite unused, with no effect on A-F processing.
