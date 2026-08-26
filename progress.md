# Progress

## 2026-08-26 - Portable client deployment bootstrap

### What was done

- Fast-forwarded context to remote `origin/main` (`108af5d`) without merging
  unrelated local history and created branch
  `codex/client-portable-deployment`.
- Restored the complete pipeline source tree from the private source archive,
  bundled the read-only strict preflight and direct-import handoff entry, and
  added `pipeline/requirements.txt`.
- Removed console hard-coded user paths; defaults now resolve from the checkout
  and can be explicitly overridden with `AMAZON_CONSOLE_*` environment vars.
- Added fail-closed SHA-256 verification for the protected Bridge, Collector,
  and Runner files. The approved Runner remains `0.3.8.13`.
- Added `install-client.ps1`, `start-client.ps1`, `stop-client.ps1`, and
  `verify-client.ps1` with PID ownership checks and alternate-port handling.
- Added the portable deployment guide and updated the source manifest/README.

### Testing

- Baseline strict preflight passed against the existing formal project before
  the deployment changes.
- Remaining verification is recorded below after the local portable bootstrap
  is initialized: Python/Node checks, UI tests, pipeline tests, alternate-port
  API smoke, strict preflight, and protected-script hash comparison.

### Notes

- Protected userscripts were not edited. Their pre-change SHA-256 values are
  recorded in `pipeline/config/protected_script_hashes.json`.
- Rollback: stop the portable service, switch back to the previous committed
  branch/commit, and do not touch the formal project data directory.

## 2026-08-26 - Portable deployment verification

### What was done

- Initialized the checkout on an alternate port (`8790`) without changing the
  existing `8788` service.
- Verified the bundled preflight and current browser pair through
  `/api/overview`; the checkout reports `0.4.6.4/0.3.8.13` and all protected
  script hashes match.
- Added a repository `pytest.ini` import root and explicit skips for seven
  tests that require intentionally excluded historical `runs/` evidence.

### Testing

- `verify-client.ps1 -NoServiceCheck`: passed.
- UI tests: 29 passed.
- Console Python tests: 97 passed.
- Pipeline tests: 213 passed, 7 skipped because optional historical evidence
  is absent from this portable source package.
- Python and Node syntax checks: passed.
- Portable API smoke on `http://127.0.0.1:8790`: passed.
- Safe-stop check: portable PID 44792 stopped; existing `8788` listener PID
  11880 remained running.

### Notes

- The protected Bridge, Collector, and Runner userscripts were never edited;
  temporary tamper testing used copies outside the checkout.
- The local verification venv and `.runtime/` lease/toolchain files are
  ignored and will not be committed.

## 2026-08-26 - Fixed-port browser compatibility

### What was done

- Confirmed that the approved Bridge, Collector, Runner, and installation
  userscripts call back to `127.0.0.1:8788`.
- Changed the portable launcher to fail closed for non-`8788` ports instead of
  presenting a console that browser scripts could not reach.
- Updated the portable deployment, console, and root README instructions to
  explain the fixed port and project-owned PID check.
- Removed remaining machine-specific build and credential paths from the
  console README.

### Testing

- The compatibility fix is pending the final verification run below; protected
  script bytes remain unchanged.

### Notes

- A port conflict must be resolved by identifying the listener and stopping it
  only when it is this checkout's `console/server.py`; unrelated processes are
  never stopped by the launcher.

## 2026-08-26 - Final portable checkout verification

### What was done

- Completed the fixed-port compatibility update without changing the approved
  Bridge, Collector, or Runner userscripts.
- Confirmed the source checkout is self-contained for code and configuration;
  machine-specific runtime state remains excluded and is created by the
  installer.

### Testing

- PowerShell parser: 5 scripts passed.
- `verify-client.ps1 -NoServiceCheck`: passed; strict preflight and all three
  protected SHA-256 checks passed.
- Console Python tests: 98 passed.
- Portable deployment tests: included in the 98-test console run and passed,
  including tamper fail-closed coverage.
- Pipeline tests: 213 passed, 7 skipped only for absent optional historical
  evidence, with 18 subtests passed.
- DangDang UI tests: 29 passed.
- Python and Node syntax checks: passed.
- Non-`8788` launcher guard: correctly rejected `-Port 8790` with exit code 1.

### Notes

- No live production browser session, Bridge pairing, or existing `8788`
  service was stopped or modified during this verification.
