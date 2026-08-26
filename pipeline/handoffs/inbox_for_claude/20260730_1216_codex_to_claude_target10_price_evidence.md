---
from: codex
to: claude
priority: p1
requires_action: yes
tags: [strict_selection, replay, current_price, acceptance, target10]
---

# Target-10 formal delivery and Runner current-price authority

## Scope and non-scope

Completed the user's formal target-10 strict delivery and closed two evidence-integrity gaps in offline replay/acceptance. No Collector, Runner, browser parser, MCP provider, A-F threshold, exclusions, or raw browser batch was changed.

## Files changed

- `scripts/replay_existing_batch.py`: added opt-in `--runner-current-price-v1`, audit fields, and an evidence merge helper that prevents external enrichment from replacing or synthesizing Runner `currentPrice`.
- `scripts/acceptance_checker.py`: validates current-price provenance, bounds, accepted/current equality, and workbook price cells.
- `scripts/strict_history.py`: only accepts run directories with `acceptance_report.md` containing `Delivery complete: yes`.
- `scripts/correct_formal_batch_evidence.py`: creates a provenance-preserving corrected copy of the known batch-017 ASIN mismatch.
- `tests/test_replay_existing_batch.py`, `tests/test_acceptance_checker.py`, `tests/test_strict_history_acceptance_gate.py`, `tests/test_correct_formal_batch_evidence.py`: focused regression coverage.
- `progress.md`: formal delivery entry.

## Feature flag and rollback

- New opt-in policy: `--runner-current-price-v1`.
- Enabled only for the formal target-10 replay. It makes missing/invalid Runner current price fail closed and records `priceEvidencePolicy=runner_current_price_v1`.
- Omit the flag to restore the legacy candidate-source projection for diagnostics. Do not use that rollback for a new current formal delivery without explicit approval.

## Hard-gate invariants

- Gate order and A-F thresholds are unchanged.
- Runner price cannot grant acceptance by itself; replay and acceptance remain final authorities.
- Candidate source price is retained as `sourcePrice` but cannot substitute for current evidence under the flag.
- `B0GWLKXM3J` remains rejected as `asin_mismatch_review` because its URL resolves to `B0GWLCGX88`.
- `B0H3WQWHLY` remains a run-scoped Gate A brand/IP rejection.

## Verification and evidence

- Full Python regression: 176/176 PASS.
- Formal replay: 124 attempts, 10 qualified, 114 rejected, stop `target_reached`.
- Acceptance: all checks PASS, including Runner price provenance/bounds, workbook price equality, 10/10 embedded images, and zero formula errors.
- Browser paired/live evidence: not applicable; no browser code or deployed userscript changed. Existing raw batches were replayed deterministically.
- MCP provider calls: no new call during this correction/closeout; task usage remains sealed at 43/50.
- Delivery bundle: `runs/strict_formal_20260730_target10_corrected_delivery/`.
- Corrected evidence: `runs/strict_formal_20260730_target10/browser_batches/batch_017_5e05dfa2_corrected_mismatch.json` plus the untouched original batch.
- Acceptance report: `runs/strict_formal_20260730_target10_corrected_delivery/acceptance_report.md`.
- Strict history: 59 -> 69 only after acceptance completed.

## Review requested

Please verify that the new price policy should remain opt-in rather than becoming the default, and audit the external-enrichment lock plus acceptance price checks. No next Tier or browser optimization was started.
