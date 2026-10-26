# Feite Selection

Private source package for the Feite Amazon US product-selection workflow.

This repository contains the local selection console, the strict candidate
pipeline, and the browser userscripts used by the current workflow. It is a
portable deployment package as well as a source archive: a fresh checkout can
be initialized on another Windows machine without copying this machine's live
data. It does not contain browser sessions, exported product data, or
credentials.

## Layout

- `console/` - local web console, Browser Bridge source, DangDang UI package,
  frontend assets, tests, and startup scripts.
- `pipeline/scripts/` - candidate normalization, strict filtering, history
  checks, Runner/Collector userscripts, Excel generation, and bridge helpers.
- `pipeline/config/` - non-secret filtering and pipeline configuration.
- `pipeline/docs/` - operational rules, evidence requirements, and rollback
  notes.
- `pipeline/tests/` - pipeline verification tests.

## Current browser pair

The approved local console pairing remains:

- Bridge `2.1.3`
- Collector `0.4.6.4`
- Runner `0.3.8.13`

These versions and the protected SHA-256 values are loaded at startup from
`pipeline/config/protected_script_hashes.json`. The console refuses to start
when that manifest is missing, malformed, or does not carry valid hashes for
all three scripts; it never falls back to built-in defaults.

The active Runner source is the `0.3.8.13` userscript under
`pipeline/scripts/`. The `0.3.8.12` userscript is not the active version and
must not be selected for normal operation.

The userscripts are evidence-collection components. They do not replace the
strict A-F replay and final workbook acceptance checks.

## Portable Windows startup

第一次使用请直接阅读中文新手步骤：[新手安装与首次运行](docs/beginner-quickstart-zh.md)。
下面是同一流程的简版命令。

On a fresh private checkout, run once in PowerShell:

```powershell
cd C:\path\to\feite-selection
Set-ExecutionPolicy -Scope Process Bypass
.\install-client.ps1
```

The installer creates empty runtime directories and an empty strict-history
file, then installs the two Python packages needed for workbook and image
handling into an isolated environment at `.runtime/venv` (it falls back to the
base interpreter only when that interpreter cannot create a venv). It never
imports another machine's database, pairing code, browser profile, or
credentials. Start and stop the service with:

```powershell
.\start-client.ps1                 # http://127.0.0.1:8788
.\stop-client.ps1
.\verify-client.ps1
```

Before the first start on a new machine, run the availability doctor. Unlike
the installer's existence checks, it verifies capability: real Python imports,
a real `import("@oai/artifact-tool")` against the required exports, SHA-256 for
the protected scripts, the strict preflight, directory and SQLite writability,
and whether port `8788` belongs to this checkout. Every failing check prints a
single `->` remediation hint.

```powershell
.\doctor.ps1                 # readable report; exit code 2 on blocking problems
.\doctor.ps1 -Json           # machine-readable feiteClientDoctor/v1 report
.\doctor.ps1 -NoServiceCheck # client is not running yet
```

The doctor is diagnostic only; `verify-client.ps1` remains the formal gate.

`start-client.ps1` resolves Python and Node.js from the installed toolchain or
the system PATH, sets the project root to this checkout's `pipeline/`, and
records a PID lease in `.runtime/`. Formal browser operation is fixed to
`127.0.0.1:8788` because the approved userscripts and their install URLs use
that callback. If `8788` is occupied, do not switch ports: inspect the owner
and stop it only when it is this checkout's `console/server.py`. The stop
script verifies the recorded command line before stopping anything; it will
refuse to touch an unrelated process. The console also accepts `AMAZON_CONSOLE_PROJECT_ROOT`,
`AMAZON_CONSOLE_PYTHON_EXE`, `AMAZON_CONSOLE_NODE_EXE`, and
`AMAZON_CONSOLE_PREFLIGHT_SCRIPT` for an explicitly managed external project
root.

The approved browser pair remains Bridge `2.1.3`, Collector `0.4.6.4`, and
Runner `0.3.8.13`. The console verifies the byte-level SHA-256 manifest before
declaring the pair technically ready; a changed or missing protected script
fails closed. The `0.3.8.12` Runner is retained only as historical source and
is never selected by the portable defaults.

The first overview after startup may show a conservative preflight state while
the read-only check runs. A real batch is still blocked unless the full strict
preflight and the existing A-F acceptance evidence pass.

## History migration

`pipeline/history/` and `console/data/` are excluded from Git, so a fresh
checkout starts with an empty strict-qualified registry. To carry the registry
to another machine, export it from the old client and import it on the new one.
Both scripts refuse to run while the console is up. The exporter records a
SHA-256 manifest for every file, the importer verifies it before writing, and
neither ever packages `browser_pairing.json`.

```powershell
# old machine, console stopped
.\stop-client.ps1
.\export-client-history.ps1                        # strict history only
.\export-client-history.ps1 -IncludeConsoleState   # also console.db / batches.json

# new machine, after install-client.ps1, console stopped
.\import-client-history.ps1 -Archive .\feite-client-history-<stamp>.zip -DryRun
.\import-client-history.ps1 -Archive .\feite-client-history-<stamp>.zip
```

Existing files are only replaced with `-Force`, and each replaced file is first
copied to `*.pre-import-<stamp>.bak`. An archive that contains console state is
rejected unless `-IncludeConsoleState` is passed, because it carries another
machine's batch records.

## Security boundary

This repository is intended to remain private. Do not add collaborators,
publish forks, or paste source files into public issue comments. Runtime data,
Bridge pairing tokens, SellerSprite credentials, browser profiles, local
databases, exports, logs, caches, and run artifacts are intentionally excluded.
See `SECURITY.md` for the handling policy.

## Verification

Run the repository checks after installing the local dependencies:

```powershell
python -m pytest pipeline/tests
corepack pnpm --dir console run test:ui
.\verify-client.ps1 -NoServiceCheck
.\tools\check-ps-syntax.ps1
```

`tools/check-ps-syntax.ps1` parses every PowerShell script with the built-in
PowerShell parser and exits non-zero on syntax errors. It needs no runtime
components (no Codex, no Python dependencies) and is safe to run in CI.

On a client machine, run `.\doctor.ps1` before these checks: it separates
deployment capability failures (private workbook package, SQLite writes, port
ownership) from repository test failures. `verify-client.ps1` remains the
formal gate; the doctor never replaces it.

The bundled `pipeline/scripts/preflight.py` is the same read-only strict
preflight used by the workflow. A passing package check does not authorize a
formal product-selection release; browser login, US delivery address, one
ASIN smoke, and paired real-ASIN evidence remain required.

Seven tests that analyze historical MCP/P2 evidence are skipped on a fresh
checkout when their intentionally excluded `runs/` artifacts are absent. If
those evidence bundles are supplied in a controlled audit workspace, the same
tests run and keep their original assertions.
