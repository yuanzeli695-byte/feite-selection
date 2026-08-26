---
from: codex
to: claude
priority: p1
requires_action: yes
tags: [tier1, mcp, userscript, paired-validation]
---

# Scope and non-scope

Review the new loopback MCP queue-ranking companion and its 30-ASIN evidence. Scope is reorder-only advisory behavior. Non-scope is Gate C/D/E substitution, browser preloading, formal selection enablement, and any threshold change.

# Files changed

- `scripts/mcp_hybrid_bridge.py`: Bridge 0.2.0 batch evidence lookup.
- `scripts/sellersprite_mcp_hybrid_assist_v0.2.0.user.js`: new independent queue-ranking userscript.
- `scripts/build_mcp_keepa_completion_plan.py`: fixed 25-call completion plan.
- `scripts/analyze_mcp_keepa_full_pair.py`: Runner-compatible trend and ranking analysis.
- `scripts/build_mcp_hybrid_assist_bundle.py`: combined immutable 30-ASIN bundle.
- matching Python/Node tests, protocol docs, reports, and evidence artifacts.

# Feature flag and rollback

- Candidate flag: `ENABLE_MCP_HYBRID_ASSIST_V0_2`.
- Candidate plugin/Bridge: 0.2.0.
- Rollback: disable the candidate userscript and stop port 8766. Original Collector/Runner files are unchanged.

# Hard-gate invariants

- MCP evidence has `finalAuthority=false`.
- Queue multiset is preserved exactly.
- Plugin actions are limited to reorder-only advice.
- Gate C remains Collector-owned.
- D/E values remain non-authoritative because field agreement is incomplete.
- Strict history and formal result contracts are never written.

# Tests and measured evidence

- Thirty exact Keepa ASINs: 30/30.
- Total MCP calls: 33, zero retries, task ceiling 50.
- Price match 11/14 comparable; rating 23/30; reviews 16/30; dimensions 8/16; trend 9/17; variations unavailable.
- First-ten pass count changed retrospectively from 1 to 5.
- Time to five passes improved 30.90%; time to ten passes regressed 3.67%.
- Bridge HTTP batch smoke: HTTP 200, 30 rows, final authority false.
- Targeted Python and Node tests pass; full regression and canonical preflight are required before installation.

# Paired evidence

- `runs/mcp_shadow_20260729/browser_baseline.json`
- `runs/mcp_shadow_20260729_keepa_complete/full_pair_analysis.json`
- `runs/mcp_hybrid_assist_v0.2_paired30/evidence_bundle.json`
- `runs/mcp_hybrid_assist_v0.2_paired30/VALIDATION_REPORT.md`
- `runs/mcp_hybrid_assist_v0.2_paired30/RELEASE_DECISION.json`

# Live deployment smoke

The authorized one-ASIN isolated smoke is complete. The user-provided Chrome screenshot shows Hybrid Assist 0.2.0 enabled, connected, ranking `B0GTQFW672`, preserving the one-ASIN queue, and displaying `Ranked 1; evidence does not pass gates`. Local checks at the same acceptance point report Bridge ledger 33, outbound MCP disabled, strict history count 57, preflight OK, and zero original-file hash mismatches. Formal Runner use remains blocked.

# Residual risks

- No MCP Gate C source exists.
- Field freshness and semantics differ from browser evidence.
- Ranking helps the five-pass milestone in this sample but not the ten-pass milestone.
- Browser installation may require a manual ScriptCat confirmation click.
- Browser smoke evidence was supplied by the user because the Chrome control surface could not reliably inspect the extension prompt after connection.

# Review questions

1. Confirm the userscript has no path to mutate Runner, Collector, strict history, or A-F results.
2. Confirm batch lookup remains loopback-only, token-protected, immutable, and non-authoritative.
3. Confirm the measured evidence supports only an isolated smoke and not formal enablement.

Work stopped before any browser preloading, gate substitution, concurrency tier, or formal-run enablement.
