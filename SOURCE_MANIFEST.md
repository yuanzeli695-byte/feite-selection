# Source package manifest

Package name: `feite-selection`

The package was assembled from the local project roots without modifying
either source tree.

## Included

- `console/`: the local selection console source, UI templates and adapters,
  Browser Bridge source, tests, package manifests, and the pinned DangDang UI
  package.
- `pipeline/scripts/`: strict selection tools, bundled read-only preflight and
  direct-import dependencies, and browser userscripts,
  including the active Collector `0.4.6.4` and Runner `0.3.8.13` sources.
- `pipeline/config/`: non-secret rules, policy files, and the protected-script
  SHA-256 manifest.
- `install-client.ps1`, `start-client.ps1`, `stop-client.ps1`, and
  `verify-client.ps1`: portable Windows initialization, service lifecycle, and
  fail-closed verification.
- `automation_console/__init__.py`: a small compatibility import for existing
  console tests and integrations; the implementation remains in `console/`.
- `pipeline/docs/`, `pipeline/handoffs/`, and `pipeline/tests/`: operational
  documentation, implementation handoffs, and verification code.
- Pipeline startup helpers and project guides at `pipeline/` root.

## Intentionally excluded

- `console/data/console.db` and other local databases.
- SellerSprite credentials, Bridge pairing tokens, browser profiles, cookies,
  and environment files.
- `runs/`, `cache/`, runtime history from the owner's machine, logs, Python
  caches, Node dependencies, and
  generated exports or workbooks.
- Product candidate data and other customer/account-specific runtime state.

The exclusions are deliberate. They keep the private repository reviewable and
make a new checkout start with empty customer-specific state instead of
replaying another machine's live session or data. `install-client.ps1` creates
the required empty history and runtime folders locally.
