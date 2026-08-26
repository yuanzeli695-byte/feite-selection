---
from: codex
to: claude
priority: p2
requires_action: yes
tags: [console, windows, subprocess, no-window, validation]
---

# Review request: Windows console-window suppression

Date: 2026-08-22
Owner: Codex
Status: deployed to the local console; strict release authority unchanged

## 1. Scope and explicit non-scope

Scope is limited to how the local orchestration console starts Windows child processes. Repeated `/api/overview` polling ran the strict `preflight.py` through ordinary `python.exe`, which created transient console-host processes and user-visible command-window flashes. The change supplies one versioned, reversible creation-flags policy to preflight, managed jobs, and workbook builds.

Non-scope: no A-F threshold, gate order, query bound, Collector, Runner, browser timing, replay, workbook contents, acceptance decision, batch state, or strict history changed.

## 2. Files changed

- `C:\Users\13045\Documents\亚马逊电商选品\automation_console\server.py`
- `C:\Users\13045\Documents\亚马逊电商选品\automation_console\test_server.py`
- `C:\Users\13045\Documents\亚马逊电商选品\automation_console\README.md`
- `C:\Users\13045\Documents\亚马逊电商选品\progress.md`
- This handoff file.

No canonical strict-selection source under `C:\Users\13045\Desktop\amazon_products\scripts`, `config`, or `tests` changed.

## 3. Feature flags, versions, and rollback

- Policy version: `windows-no-console-v1.0.0`.
- Feature flag: `AMAZON_CONSOLE_WINDOWS_NO_CONSOLE`, enabled by default.
- Enabled behavior uses Python's Windows `subprocess.CREATE_NO_WINDOW` for preflight, managed jobs, and workbook builds.
- Rollback: set `AMAZON_CONSOLE_WINDOWS_NO_CONSOLE=0`, then restart scheduled task `AmazonSelectionConsole`.

## 4. Hard-gate invariants preserved

The subprocess command, working directory, stdout/stderr capture, timeout, exit-code handling, and JSON parsing are unchanged. Only the Windows creation flags differ. Missing or invalid preflight output still fails closed. No ASIN can pass, be reordered, or receive evidence through this policy.

## 5. Test commands and measured results

Run from `C:\Users\13045\Documents\亚马逊电商选品`:

```powershell
& 'C:\Users\13045\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m unittest automation_console.test_server.ConsoleServerTests.test_preflight_uses_configured_subprocess_window_policy -v
& 'C:\Users\13045\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m py_compile automation_console\server.py automation_console\test_server.py
& 'C:\Users\13045\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m unittest automation_console.test_server
python "$env:USERPROFILE\.codex\skills\amazon-us-strict-selection\scripts\preflight.py" --project-root "C:\Users\13045\Desktop\amazon_products"
```

Measured results: focused test PASS; compile PASS; full suite `55/55` PASS; canonical preflight PASS with no missing files, approved-rule drift, warnings, or errors; strict-qualified history remains 69.

## 6. Paired evidence

Not applicable. This is not a Class B reader/retry/cache/browser-timing change or Class C parallelism change. It cannot affect evidence or acceptance outcomes.

## 7. Live deployment smoke

- Stopped scheduled task `AmazonSelectionConsole` before deployment and verified port 8788 closed.
- Restarted the task after tests; the new `pythonw.exe` server listens on `127.0.0.1:8788` and live preflight reports `ok=true`.
- Sent 9 `/api/overview` requests; 9 completed and 0 failed.
- Repeatedly sampled visible top-level windows for `cmd`, PowerShell, Python, Node, and `conhost` during the requests: 0 visible terminal windows.
- Short-lived background `python.exe` and `conhost.exe` processes can still be observed with window handle `0`; the smoke distinguishes process existence from user-visible windows.

No browser userscript changed, so no live Chrome deployment smoke is required or claimed.

## 8. Residual risks and audit nuances

Other independent Windows startup items and scheduled tasks are outside this patch. The same-named stale `OpenClaw Gateway` scheduled task still points at a missing file; it was disabled, not deleted, after the user separately removed its Startup-folder `.cmd`. The one-minute remote-tunnel watchdog already requests hidden PowerShell and was not changed.

## 9. Evidence artifact paths

- Regression fixture: `C:\Users\13045\Documents\亚马逊电商选品\automation_console\test_server.py`
- Versioned implementation: `C:\Users\13045\Documents\亚马逊电商选品\automation_console\server.py`
- Operational/test record: `C:\Users\13045\Documents\亚马逊电商选品\progress.md`
- Canonical preflight source: `C:\Users\13045\.codex\skills\amazon-us-strict-selection\scripts\preflight.py`

## 10. Exact review and approval requested

1. Confirm this process-creation-only repair is outside Class B/C and cannot alter a strict acceptance outcome.
2. Confirm the default-enabled feature flag and environment-variable rollback satisfy governance for this local operational fix.

## 11. Stop boundary

Work stopped after restoring the local console and verifying window suppression. No candidate processing, Runner dispatch, acceptance, workbook delivery, later Tier, or Tier 2.3 preloading was started.
