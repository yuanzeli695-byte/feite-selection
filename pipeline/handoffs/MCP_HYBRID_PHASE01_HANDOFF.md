# MCP Hybrid Phase 0-1 Handoff

## Result

Phase 0-1 is complete as an offline Shadow data plane. The original Runner,
Collector, Excel Bridge, rules, exclusions, and strict history were not modified.

## New Files

- `config/mcp_hybrid_policy.json`
- `docs/mcp_hybrid_protocol_v1.md`
- `docs/mcp_hybrid_original_baseline_20260728.json`
- `scripts/mcp_hybrid_bridge.py`
- `scripts/start_mcp_hybrid_bridge.ps1`
- `scripts/sellersprite_mcp_hybrid_shadow_v0.1.0.user.js`
- `tests/fixtures_mcp_hybrid_valid_bundle.json`
- `tests/test_mcp_hybrid_bridge.py`
- `tests/test_sellersprite_mcp_hybrid_shadow.mjs`

## Guarantees

- Bridge binds only to `127.0.0.1` and uses a header token for protected APIs.
- No outbound MCP client exists in version 0.1.0.
- Imported evidence is `shadow` and `finalAuthority: false`.
- Stale, mismatched, malformed, and hash-conflicted evidence fails closed.
- Monthly call accounting is shared across runs through
  `cache/mcp_hybrid_call_ledger.jsonl`.
- The companion userscript does not read or write the existing Runner's
  persistent state and never changes A-F decisions.

## Verification

```powershell
python -m unittest discover -s tests -p 'test_*.py' -v
$tests = Get-ChildItem tests -Filter 'test_sellersprite*.mjs' | Sort-Object Name
foreach ($test in $tests) { node $test.FullName }
node --check scripts/sellersprite_mcp_hybrid_shadow_v0.1.0.user.js
python "$env:USERPROFILE\.codex\skills\amazon-us-strict-selection\scripts\preflight.py" --project-root "C:\Users\13045\Desktop\amazon_products"
```

Observed results: 100 Python tests passed, 19 SellerSprite Node suites passed,
new Shadow core passed, and preflight passed. No real MCP calls were made.

## Next Approved Step

Use a 30-ASIN queue in Shadow mode. Keep the original Runner and Collector as
the only browser decision path. Import only an offline MCP bundle or a future
prefetch captured by an explicitly approved adapter. Declare an 8-11 call
budget, compare the complete accepted/rejected multiset, and stop on any
false-positive or Gate C mismatch.

Do not implement direct MCP credentials, Enforced mode, traffic-gate
replacement, background preloading, or concurrency in this phase.

## Rollback

Stop the process started by `scripts/start_mcp_hybrid_bridge.ps1` and disable
the Shadow companion userscript. The original plugin pair and formal history
remain usable without migration.
