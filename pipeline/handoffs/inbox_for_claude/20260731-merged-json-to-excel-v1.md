# Review request: merged Runner JSON to accepted Excel v1

Date: 2026-07-31
Owner: Codex
Version: `merged-json-to-excel-v1`

Please independently review these files:

- `scripts/build_excel_from_merged_json.py`
- `tests/test_build_excel_from_merged_json.py`
- `docs/merged_json_to_excel_cli.md`
- `docs/selection_zh_excel_guide.md`

Review questions:

1. Can a malformed, ambiguous, version-drifted, ASIN-mismatched, or browser-only pass enter the final workbook?
2. Does unique-smallest candidate discovery safely reject enrichment/image-report lookalikes and equal-size ambiguity?
3. Can the orchestrator write formal history or place ad-hoc output where the formal history scanner can ingest it?
4. Does any failure path weaken target, A-F gates, image requirements, Chinese title requirements, or machine acceptance?
5. Are the stored hashes and copied evidence sufficient to reproduce the exact batch/candidate pairing?

Validation evidence:

- Focused tests: 6/6 PASS.
- Full Python regression: 191/191 PASS; canonical strict preflight PASS with zero rule drift.
- Exact user snapshots: one `running` snapshot plus one `done` batch; explicit Runner allowlist `0.3.8.2/0.3.8.5`, Collector allowlist `0.4.6.2`.
- Automatic candidate mapping selected `browser_queue_office_gate_a_pass.json` and `runner_queue_part_01.json`.
- End-to-end result: 86 attempts, 6 qualified, 80 rejected/audited, exact target and machine acceptance PASS.
- Visual previews PASS; six embedded image anchors occupy `C8:C13`.
- Formal history SHA-256 remained unchanged.

Do not approve a change that relaxes the explicit running-snapshot flag, version allowlists, strict-pass consistency, candidate ambiguity checks, output-outside-project rule, replay authority, machine acceptance, or visual acceptance.
