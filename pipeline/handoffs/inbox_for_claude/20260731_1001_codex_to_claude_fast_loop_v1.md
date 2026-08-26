# Review request: strict-selection fast-loop v1

Date: 2026-07-31
Owner: Codex
Status: candidate only; not formally deployed

Please independently review the following candidate without changing or weakening A-F:

- `scripts/sellersprite_integrated_runner_v0.3.10_fast_loop.user.js`
- `scripts/selection_fast_loop_bridge.py`
- `scripts/start_selection_fast_loop_bridge.ps1`
- `scripts/sellersprite_mcp_hybrid_runner_adapter_v0.2.1.user.js`
- `tests/test_sellersprite_fast_loop_v0310.mjs`
- `tests/test_selection_fast_loop_bridge.py`
- `tests/test_sellersprite_mcp_hybrid_runner_adapter_v021.mjs`
- `docs/selection_fast_loop_v1.md`
- `runs/fast_loop_v1_validation/VALIDATION_REPORT.md`

Review questions:

1. Can any browser-pass state stop the run or enter formal history without offline replay and acceptance?
2. Can checkpoint mutation, queue reordering, a repeated attempted ASIN, stale auth, or a version mismatch be accepted?
3. Does the cross-tab lease have a path that permits two active Runner `0.3.10` tabs?
4. Can the MCP adapter do anything beyond reordering an ungenerated draft queue?
5. Are the 30-real-ASIN paired test and isolated live smoke sufficient before approving the candidate, or is another Class B check required?

Offline evidence already passed: A-F function parity, focused circuit/lease/checkpoint tests, 181 Python tests, 28 Node suites, 28 userscript syntax checks, and 9/9 frozen baseline hashes. The real-data replay handled 124 attempts and recovered the known 10 qualified rows in about 559.2 ms. No MCP provider call and no formal history write occurred.

Do not mark this candidate as production-ready without reviewing the stored paired/live evidence; that evidence is not yet present.
