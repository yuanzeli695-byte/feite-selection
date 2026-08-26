# SellerSprite MCP Hybrid Protocol v1

## Status

- Version: `0.2.0`
- Mode: `shadow`
- Outbound MCP calls: disabled
- Final A-F authority: unchanged
- Canonical Collector and Runner: unchanged

This protocol adds an isolated evidence and budgeting plane. It does not replace
the Collector, replay engine, filter engine, workbook builder, or acceptance
checker. MCP evidence may be compared, ranked, cached, and audited. It cannot
grant a pass in version 0.1.0.

## Ownership

| Concern | Owner in v0.1.0 |
|---|---|
| Restricted/compliance decision | Existing local exclusion and review flow |
| Commercial, dimensions, price, image comparison | MCP shadow evidence |
| Weekly natural traffic Gate C | Existing Collector only |
| Browser batch schema and gate codes | Existing Runner contract |
| Final A-F evaluation | `replay_existing_batch.py` and `filter_engine.py` |
| Workbook release | `acceptance_checker.py` plus visual review |

The browser batch contract remains `sellerSpriteIntegratedBatch/v0.3.0`.
MCP data is stored in a sidecar and is never merged into that contract during
Shadow mode.

## Security Boundary

- The Bridge binds only to `127.0.0.1`.
- Browser requests require `X-MCP-Hybrid-Token` except for health checks.
- Allowed browser origins are `https://www.amazon.com` and
  `https://amazon.com`.
- Tokens are generated at startup and are not written to disk.
- The userscript keeps the token in memory only. It does not use persistent
  browser storage for credentials or evidence.
- Version 0.1.0 contains no outbound HTTP client and cannot call SellerSprite
  MCP directly.

## Evidence Bundle

An offline producer may import a bundle using
`sellerSpriteMcpEvidenceBundle/v1`. Every evidence item must use
`sellerSpriteMcpEvidence/v1` and contain:

- exact `runId`, marketplace, target ASIN, and actual ASIN;
- tool name and request/response SHA-256 hashes;
- captured and expiry timestamps;
- normalized fields plus field-level provenance;
- explicit missing fields and fallback requirement;
- `mode: shadow` and `finalAuthority: false`.

ASIN mismatch, stale evidence, missing evidence, hash conflict, unknown tools,
or invalid timestamps remain non-usable. Imported evidence is immutable by
`evidenceId`; a changed payload with the same identifier is rejected.

## Call Ledger

The append-only ledger uses `sellerSpriteMcpCallLedgerEvent/v1`.

- Official monthly limit: 15,000 calls.
- Operational cap: 12,000 calls.
- Default run budget: 100 calls.
- Reservations count as spent and are not automatically released.
- Cache hits and offline imports consume zero calls.
- The Bridge rejects a reservation that would exceed the run budget or
  operational monthly cap.
- The monthly ledger is shared across runs at
  `cache/mcp_hybrid_call_ledger.jsonl`; starting a new run does not reset the
  monthly usage.
- Run only one MCP Hybrid Bridge process at a time during Phase 0-1.

No real reservations are required for Phase 0-1 fixtures and tests.

## Loopback API

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/v1/health` | Mode, policy, evidence count, budget summary |
| GET | `/api/v1/evidence?asin=...&tool=...` | Fresh shadow evidence lookup |
| GET | `/api/v1/ledger` | Current run/month call usage |
| POST | `/api/v1/evidence/import` | Import an offline immutable bundle |
| POST | `/api/v1/evidence/batch` | Read 1-40 cached ASIN evidence rows without an MCP call |
| POST | `/api/v1/calls/reserve` | Atomically reserve future MCP calls |

All responses use `sellerSpriteMcpHybridResponse/v1`.

## Rollout Gates

Before any Enforced mode exists:

1. Preserve the original-file hashes in the frozen baseline manifest.
2. Pass all offline protocol, budget, immutability, stale-data, mismatch, and
   userscript isolation tests.
3. Run a 30-ASIN Shadow comparison with the same queue multiset.
4. Require 100% Gate C agreement and zero false positives.
5. Keep MCP use within the declared per-run budget.
6. Complete a one-ASIN browser smoke.

Disabling the new companion script and stopping port 8766 is the complete
Phase 0-1 rollback. No original state or strict history is migrated.
