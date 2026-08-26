---
from: codex
to: claude
priority: p1
requires_action: yes
tags: [browser-export, sellersprite, bridge, v1.0.4, fail-closed]
---

# SellerSprite confirmed-export handshake 1.0.4

## 1. Scope and explicit non-scope

Scope: repair the local SellerSprite browser-export Bridge so it does not leave the product-research page until SellerSprite confirms that an export job was created.

Non-scope: no candidate normalization, A-F gate, query threshold, Collector, Runner, history, replay, workbook, API credential, or final acceptance behavior changed.

## 2. Files changed

- `C:\Users\13045\Documents\亚马逊电商选品\automation_console\sellersprite_browser_bridge_v1.user.js`
- `C:\Users\13045\Documents\亚马逊电商选品\automation_console\test_sellersprite_bridge.mjs`
- `C:\Users\13045\Documents\亚马逊电商选品\progress.md`
- `C:\Users\13045\Desktop\amazon_products\progress.md`

## 3. Feature flag, version, and rollback

- Userscript metadata: `1.0.4`.
- Protocol remains `sellerSprite-bridge-v1.0.0` because server payload compatibility did not change.
- Feature flag: `ENABLE_CONFIRMED_EXPORT_HANDSHAKE=true`.
- Rollback: set the flag to `false`. This intentionally disables automatic SellerSprite export and requires the console's existing manual fallback upload. It does not restore the defective fixed-delay path.

## 4. Hard-gate invariants

- Strict SellerSprite URL validation and all fixed query bounds are unchanged.
- No unconfirmed file can be downloaded or uploaded.
- No missing, stale, ambiguous, failed, or timed-out signal is treated as success.
- A-F acceptance and final workbook authority remain downstream and unchanged.

## 5. Failure evidence and implementation

Batch `127fcaeedf89`, command `98a8543a`, was accepted at 09:06:41 and failed at 09:17:04 with `SellerSprite 导出记录等待超时`. Live export-log inspection showed only five rows dated 2026-08-21 or earlier.

SellerSprite's current static application code proves that during busy hours the primary export click opens `.export-by-need-dialog`; only `先只导出前1000条` calls `exportExcel()`. SellerSprite displays `数据导出中 ... 个人中心-我的导出` only after its export API returns `code === "OK"`.

The 1.0.4 state machine is:

```text
research -> submit_export
  -> direct authoritative success
  -> or unique immediate-1000 choice -> authoritative success
  -> wait_export_log -> download/upload
```

Stale dialogs block before click. Appointment export is never selected. Unknown, warning, failure, conflicting, timeout, and refresh-interrupted states acknowledge failure with no navigation/upload.

## 6. Tests and measured results

- `node --check automation_console\sellersprite_browser_bridge_v1.user.js`: PASS.
- `node --test automation_console\test_sellersprite_bridge.mjs automation_console\test_browser_bridge_v2.mjs`: 22/22 PASS.
- Bundled Python `-m unittest automation_console.test_server`: 55/55 PASS.
- Canonical strict preflight: PASS; missing/drift/warnings/errors all zero; strict-qualified history 69.
- Local served script: HTTP 200, metadata 1.0.4, handshake flag enabled.

Behavior tests cover exact immediate choice, appointment non-selection, direct and busy-path success ordering, stale-success rejection, explicit SellerSprite rejection, unknown-dialog failure, conflicting-signal failure, hidden-dialog exclusion, and navigation only after `taskConfirmedAt`/`exportWaitStartedAt` are recorded.

## 7. Paired evidence

This B-class change affects only SellerSprite export submission, before ASIN candidate normalization and all A-F evaluation. No ASIN acceptance outcome can be added by it. The full console suite and unchanged strict preflight passed. The existing pending paired-30 Collector/Runner authorization remains unchanged and is not claimed by this change.

## 8. Live deployment smoke

Not yet claimed in this handoff. The local server serves 1.0.4, but the user's ScriptCat installation was still the previous version when validation ended. A live smoke must verify the visible panel includes `script 1.0.4`, then retry one failed batch and preserve: immediate-choice observation, authoritative confirmation, new export row, original-file upload, and candidate-pipeline result.

## 9. Evidence paths

- Bridge source: `C:\Users\13045\Documents\亚马逊电商选品\automation_console\sellersprite_browser_bridge_v1.user.js`
- Behavior fixtures: `C:\Users\13045\Documents\亚马逊电商选品\automation_console\test_sellersprite_bridge.mjs`
- Durable command/batch audit: `C:\Users\13045\Documents\亚马逊电商选品\automation_console\data\console.db`
- Current batch run: `C:\Users\13045\Desktop\amazon_products\runs\console_Desk_Accessories_Workspace_Organizers__08-22_09-00_20260822_090036_127fca`

## 10. Requested Claude review

Please audit DOM signal exclusivity, stale-dialog rejection, exact immediate-choice matching, and the rule that only the authoritative success prompt permits navigation. Confirm that the conservative flag-off behavior and live-smoke boundary are adequate.

## 11. Stop boundary

Work stopped before any later Tier, A-F change, or formal-release authorization. No live 1.0.4 export success is claimed without ScriptCat deployment and observable end-to-end evidence.
