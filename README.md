# Feite Selection

Private source package for the Feite Amazon US product-selection workflow.

This repository contains the local selection console, the strict candidate
pipeline, and the browser userscripts used by the current workflow. It is a
source archive and deployment reference; it does not contain live batches,
browser sessions, exported product data, or credentials.

## Layout

- `console/` - local web console, Browser Bridge source, DangDang UI package,
  frontend assets, tests, and startup scripts.
- `pipeline/scripts/` - candidate normalization, strict filtering, history
  checks, Runner/Collector userscripts, Excel generation, and bridge helpers.
- `pipeline/config/` - non-secret filtering and pipeline configuration.
- `pipeline/docs/` - operational rules, evidence requirements, and rollback
  notes.
- `pipeline/tests/` - pipeline verification tests.

## Current browser pair

The approved local console pairing remains:

- Bridge `2.1.3`
- Collector `0.4.6.4`
- Runner `0.3.8.13`

The active Runner source is the `0.3.8.13` userscript under
`pipeline/scripts/`. The `0.3.8.12` userscript is not the active version and
must not be selected for normal operation.

The userscripts are evidence-collection components. They do not replace the
strict A-F replay and final workbook acceptance checks.

## Local startup

The source package preserves the current Windows layout. The console expects
the canonical pipeline checkout at:

`C:\Users\13045\Desktop\amazon_products`

Start the console from the original working directory with:

```powershell
cd C:\Users\13045\Documents\亚马逊电商选品
.\automation_console\start.ps1
```

The copied `console/` directory is for source distribution. It is not a
replacement deployment directory until its path configuration is deliberately
reviewed.

## Security boundary

This repository is intended to remain private. Do not add collaborators,
publish forks, or paste source files into public issue comments. Runtime data,
Bridge pairing tokens, SellerSprite credentials, browser profiles, local
databases, exports, logs, caches, and run artifacts are intentionally excluded.
See `SECURITY.md` for the handling policy.

## Verification

Run the repository checks from their respective source roots after installing
the local dependencies:

```powershell
python -m pytest pipeline/tests
corepack pnpm --dir console run test:ui
```

The official strict preflight must still be run against the canonical project
root before any real selection batch. A passing source-package check does not
authorize a formal product-selection release.

