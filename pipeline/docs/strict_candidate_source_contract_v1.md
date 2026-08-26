# Strict Candidate Source Contract v1

`prepare_strict_candidate_pool.py` now defaults to a formal, fail-closed source mode. A formal run requires `--source-manifest`. The old unmanifested behavior remains available only through the explicit `--allow-legacy-source` rollback flag.

This contract reduces browser waste. It does not grant product acceptance, change `config/rules.json`, or replace offline replay and final acceptance.

## Manifest Shape

```json
{
  "schemaVersion": "sellerSpriteCandidateSourceManifest/v1",
  "capturedAt": "2026-07-28T10:00:00+08:00",
  "market": "US",
  "preset": {
    "name": "amazon-us-strict-v1"
  },
  "categoryScope": {
    "name": "Home & Kitchen > Storage & Organization",
    "nodeIdPaths": ["123456"]
  },
  "inputs": [
    {
      "path": "query_storage_organizer.json",
      "sha256": "64-lowercase-hex-characters",
      "queryUrl": "https://www.sellersprite.com/v3/product-research?market=US&maxReviews=100&nodeIdPaths=%5B%22123456%22%5D&keywords=storage%20organizer"
    }
  ]
}
```

Requirements:

- `capturedAt` must include a timezone, must be no older than 24 hours, and may be at most five minutes ahead of the local wall clock to tolerate small clock skew.
- `market` must be `US`.
- `preset` (or `preset.name`) and `categoryScope.name` must be nonempty.
- `categoryScope.nodeIdPaths` must be a nonempty list of unique node IDs.
- Every top-level `query_*.json` file must be listed exactly once in `inputs`, and no listed file may be absent.
- Every SHA256 must match the file bytes.
- Every query URL must be HTTPS on SellerSprite, use `market=US`, use `maxReviews<=100`, and contain a nonempty JSON-array `nodeIdPaths` value within the declared category scope.

Each formal source row normally must contain a valid ASIN plus `title`, `categoryPath`, `reviews`, `childSales`, `sourcePage`, `sellerSpriteUrl`, `amazonUrl`, and `image`. `parentSales` is never substituted for missing `childSales`. The Amazon URL must identify the same ASIN, and the row's SellerSprite URL must match the manifest query semantically.

The versioned Excel-import path may explicitly use `--allow-missing-parent-child-sales` (`excel-source-optional-parent-child-sales-v1`) when the user has declared parent/child sales non-gating. Under this opt-in, missing parent/child values remain missing and are never estimated or substituted. Omitting the flag restores the original fail-closed source contract. This source-only override does not grant final acceptance or bypass A, C, D, E, or F evidence.

Create the manifest at export time, not later from an old folder. In PowerShell, use `(Get-Date).ToString('o')` for `capturedAt` and compute each file hash with:

```powershell
(Get-FileHash -Algorithm SHA256 -LiteralPath '.\query_storage_organizer.json').Hash.ToLowerInvariant()
```

Copy the exact SellerSprite result-page URL into both the manifest input and the exported rows. Do not refresh or change filters between copying the URL and saving the corresponding JSON.

## Duplicate Handling

Rows are grouped by ASIN before prefiltering. Missing optional values may be filled by another identical-ASIN row. If two nonempty product facts disagree, the ASIN is excluded with `duplicate_conflict` in `screened_rejected.json`.

`sourcePage` and `sellerSpriteUrl` are provenance, so multiple distinct discoveries are retained as `sourcePages`, `sellerSpriteUrls`, and `sourceEvidence`; they are not treated as contradictory product facts. All source files, row numbers, hashes, and manifest query URLs remain auditable.

## Conservative A-Gate Source Prefilter

`tier1.1-a-source-prefilter-v2` is enabled by default after history/attempt dedupe and before commercial prefiltering. It is a downward-only optimization: it may remove an obvious existing A-gate violation before Chrome, but it cannot create a pass or replace offline replay and acceptance.

The v2 terms are deliberately precise and evidence-backed. They cover the confirmed current-source patterns for Stitch birthday IP risk, solar/flood/socket-fan lighting, light bulbs, box fans, and wood filler. Broad words such as `light`, `solar`, `fan`, `stitch`, or `filler` are not used by themselves.

Every run writes `aSourcePrefilter` to `summary_<queue>.json`, including the version, enabled state, per-rule counts, total rejected count, invariant, and rollback flag. Use `--disable-a-source-prefilter-v2` to restore the previous candidate set and ordering. Any future term expansion requires a concrete rejected-row example plus a negative regression example that must remain allowed.

## Run And Rollback

Formal run:

```powershell
python scripts/prepare_strict_candidate_pool.py `
  --input-dir runs/<run>/source_queries `
  --source-manifest runs/<run>/source_manifest.json `
  --output-dir runs/<run>/candidate_inputs `
  --queue-name batch01 `
  --queue-size 20
```

Source-contract rollback only:

```powershell
python scripts/prepare_strict_candidate_pool.py `
  --input-dir runs/<run>/source_queries `
  --allow-legacy-source `
  --output-dir runs/<run>/candidate_inputs `
  --queue-name batch01 `
  --queue-size 20
```

Ranking v2 is the default reorder-only mode and gives the maximum launch-age score to 28-90 days. Use `--use-ranking-v1` to restore the former 28-80-day scoring window, or `--disable-tier1-2-ranking` to restore the pre-Tier-1.2 ordering. Neither ranking mode can add or remove candidates.

The A-source-prefilter rollback is independent of the ranking rollbacks:

```powershell
python scripts/prepare_strict_candidate_pool.py `
  --input-dir runs/<run>/source_queries `
  --source-manifest runs/<run>/source_manifest.json `
  --output-dir runs/<run>/candidate_inputs `
  --queue-name batch01 `
  --queue-size 20 `
  --disable-a-source-prefilter-v2
```
