# Feite Selection Portable Client

This document describes the supported Windows deployment for a fresh checkout
of the private `feite-selection` repository.

## What is portable

The checkout carries the console, strict-selection source, read-only
`pipeline/scripts/preflight.py`, the `direct_import_batch_to_replay.mjs`
handoff entry, and the approved browser scripts. No machine-specific database,
browser profile, SellerSprite credential, pairing token, export, or workbook is
copied into a new client.

The console's default project root is the checkout's `pipeline/` directory. An
explicit external project may be selected with
`AMAZON_CONSOLE_PROJECT_ROOT`, but that is an operator decision and must still
pass the same strict preflight.

## One-time install

Run from the repository root in Windows PowerShell:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\install-client.ps1
```

The installer:

- requires Python 3.11+ and Node.js 18+;
- prefers the current user's Codex runtime when present;
- checks for Codex's private `@oai/artifact-tool` module used by the workbook
  builder and creates a local `pipeline/node_modules` junction to that runtime;
- installs `pipeline/requirements.txt` only when `openpyxl` or `Pillow` is
  missing;
- creates empty `console/data`, `pipeline/runs`, `pipeline/cache`, and
  `pipeline/history` folders;
- creates an empty `strictQualifiedHistory/v1` registry when no history exists.

If the artifact tool is missing, installation stops. Do not download an
untrusted replacement or bypass the workbook builder's dependency check.

## Start, stop, verify

```powershell
.\start-client.ps1
.\stop-client.ps1
.\verify-client.ps1
```

The service is loopback-only at `http://127.0.0.1:8788`. Formal browser
operation must use `8788`: the approved Bridge, Collector, Runner and all
userscript install URLs call back to that fixed port. Do not switch to `8790`
or another port when `8788` is occupied. The start script never stops an
unrelated listener; inspect the owner and use `stop-client.ps1` only when it is
this checkout's `console/server.py`. It records a service lease in
`.runtime/`; the stop script checks the recorded PID command line before
stopping it.

`verify-client.ps1 -NoServiceCheck` is suitable for a stopped client. It runs
the bundled strict preflight against the checkout and compares SHA-256 hashes
against `pipeline/config/protected_script_hashes.json`.

## Browser pairing

Install the Bridge userscript served by the local console, then pair it with
the one-time code shown by the console. Keep exactly the approved pair:

- Bridge protocol `2.1.3` (userscript metadata `2.1.6`)
- Collector `0.4.6.4`
- Runner `0.3.8.13`

The `0.3.8.12` Runner is historical source only. A changed script hash, wrong
version, missing US delivery address, CAPTCHA, stale login, or incomplete
SellerSprite export leaves the workflow blocked. It does not silently fall
back to a weaker script or a fabricated export.

## Configuration overrides

Only use these when an operator intentionally keeps the formal project outside
the checkout:

```powershell
$env:AMAZON_CONSOLE_PROJECT_ROOT = 'D:\formal\amazon_products'
$env:AMAZON_CONSOLE_PYTHON_EXE = 'C:\Python311\python.exe'
$env:AMAZON_CONSOLE_NODE_EXE = 'C:\Program Files\nodejs\node.exe'
$env:AMAZON_CONSOLE_PREFLIGHT_SCRIPT = 'D:\formal\amazon_products\scripts\preflight.py'
```

The override values are process-local unless persisted by the operator. They
do not change the strict rules or browser pair. `AMAZON_CONSOLE_SELLERSPRITE_BRIDGE=0`
is the documented manual-upload rollback; it is not a way to skip validation.

## Troubleshooting

- **Port occupied**: do not use a different port for the formal browser flow.
  Inspect the listener on `8788`; stop it only if it belongs to this checkout's
  `console/server.py`. Keep unrelated listeners running and resolve that
  conflict with the machine administrator.
- **Preflight missing files**: run `install-client.ps1` and confirm the
  checkout's `pipeline/config`, `pipeline/scripts`, and empty `history` exist.
- **Artifact tool missing**: repair or reinstall the Codex desktop runtime;
  the package is private and is not vendored into this repository.
- **Hash mismatch**: reinstall the exact approved browser scripts from this
  private checkout and run `verify-client.ps1` again. Do not edit the scripts
  in place.
- **Excel generation blocked**: inspect `.runtime/console.stderr.log`, then
  rerun verification. A Runner JSON that has not passed the existing
  SHA-256/direct-import contract remains blocked by design.

## Rollback

Stop the client with `stop-client.ps1`, restore the previous Git commit, and
run `install-client.ps1` again. Browser script rollback is a separate explicit
operation; this deployment layer never rewrites the protected Bridge,
Collector, or Runner files.
