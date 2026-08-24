# Source package manifest

Package name: `feite-selection`

The package was assembled from the local project roots without modifying
either source tree.

## Included

- `console/`: the local selection console source, UI templates and adapters,
  Browser Bridge source, tests, package manifests, and the pinned DangDang UI
  package.
- `pipeline/scripts/`: strict selection tools and browser userscripts,
  including the active Collector `0.4.6.4` and Runner `0.3.8.13` sources.
- `pipeline/config/`: non-secret rules and policy files.
- `pipeline/docs/`, `pipeline/handoffs/`, and `pipeline/tests/`: operational
  documentation, implementation handoffs, and verification code.
- Pipeline startup helpers and project guides at `pipeline/` root.

## Intentionally excluded

- `console/data/console.db` and other local databases.
- SellerSprite credentials, Bridge pairing tokens, browser profiles, cookies,
  and environment files.
- `runs/`, `cache/`, `history/`, logs, Python caches, Node dependencies, and
  generated exports or workbooks.
- Product candidate data and other customer/account-specific runtime state.

The exclusions are deliberate. They keep the private repository a reviewable
source package and prevent a checkout from replaying another machine's live
session or data.

