[CmdletBinding()]
param(
  [switch]$NoServiceCheck
)

$ErrorActionPreference = 'Stop'
$Root = (Resolve-Path (Join-Path $PSScriptRoot '.')).Path
$ConsoleRoot = Join-Path $Root 'console'
$PipelineRoot = Join-Path $Root 'pipeline'
$RuntimeRoot = Join-Path $Root '.runtime'
$ToolchainPath = Join-Path $RuntimeRoot 'toolchain.json'
$ServicePath = Join-Path $RuntimeRoot 'console-service.json'
$PreflightPath = Join-Path $PipelineRoot 'scripts\preflight.py'
$HashManifestPath = Join-Path $PipelineRoot 'config\protected_script_hashes.json'

function Find-Executable([string[]]$Names) {
  foreach ($Name in $Names) {
    $Command = Get-Command $Name -ErrorAction SilentlyContinue | Where-Object { $_.CommandType -eq 'Application' } | Select-Object -First 1
    if ($Command) { return $Command.Source }
  }
  return $null
}

$PythonPath = $null
$NodePath = $null
if (Test-Path -LiteralPath $ToolchainPath) {
  $Toolchain = Get-Content -Raw -LiteralPath $ToolchainPath | ConvertFrom-Json
  if ($Toolchain.python -and (Test-Path -LiteralPath $Toolchain.python)) { $PythonPath = $Toolchain.python }
  if ($Toolchain.node -and (Test-Path -LiteralPath $Toolchain.node)) { $NodePath = $Toolchain.node }
}
if (-not $PythonPath) {
  $VenvPython = Join-Path $RuntimeRoot 'venv\Scripts\python.exe'
  $PythonPath = if (Test-Path -LiteralPath $VenvPython) { $VenvPython } else { Find-Executable @('python.exe', 'python') }
}
if (-not $NodePath) { $NodePath = Find-Executable @('node.exe', 'node') }
$Checks = [ordered]@{}
$Checks.python = [bool]$PythonPath -and (Test-Path -LiteralPath $PythonPath)
$Checks.node = [bool]$NodePath
$Checks.preflight = Test-Path -LiteralPath $PreflightPath
$Checks.directImport = Test-Path -LiteralPath (Join-Path $Root 'direct_import_batch_to_replay.mjs')

$HashReport = [ordered]@{}
if (Test-Path -LiteralPath $HashManifestPath) {
  $Checks.hashManifest = $true
  $Manifest = Get-Content -Raw -LiteralPath $HashManifestPath | ConvertFrom-Json
  foreach ($Name in @('bridge', 'collector', 'runner')) {
    $Entry = $Manifest.files.$Name
    $Path = Join-Path $Root ([string]$Entry.path)
    $Actual = if (Test-Path -LiteralPath $Path) { (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash.ToUpperInvariant() } else { $null }
    $HashReport[$Name] = [ordered]@{ path = $Path; expected = [string]$Entry.sha256; actual = $Actual; ok = ($Actual -eq [string]$Entry.sha256) }
  }
} else {
  $Checks.hashManifest = $false
}
$Checks.hashes = $false
if ($HashReport.Count -gt 0) { $Checks.hashes = @($HashReport.Values | Where-Object { -not $_.ok }).Count -eq 0 }

$Preflight = $null
if ($Checks.python -and $Checks.preflight) {
  $env:AMAZON_PRODUCTS_ROOT = $PipelineRoot
  $PreflightOutput = & $PythonPath $PreflightPath '--project-root' $PipelineRoot 2>&1
  try { $Preflight = ($PreflightOutput -join [Environment]::NewLine) | ConvertFrom-Json; $Checks.strictPreflight = [bool]$Preflight.ok } catch { $Checks.strictPreflight = $false }
} else { $Checks.strictPreflight = $false }

if (-not $NoServiceCheck) {
  $Service = $null
  if (Test-Path -LiteralPath $ServicePath) { try { $Service = Get-Content -Raw -LiteralPath $ServicePath | ConvertFrom-Json } catch { } }
  if ($Service -and $Service.pid) {
    $Checks.service = [bool](Get-Process -Id ([int]$Service.pid) -ErrorAction SilentlyContinue)
    $Checks.serviceUrl = "http://127.0.0.1:$($Service.port)"
  } else { $Checks.service = $false }
}

$OverallOk = @($Checks.Values | Where-Object { $_ -is [bool] -and -not $_ }).Count -eq 0
$Report = [ordered]@{ schemaVersion = 'feiteClientVerification/v1'; ok = $OverallOk; root = $Root; checks = $Checks; protectedScripts = $HashReport; preflight = $Preflight }
$Report | ConvertTo-Json -Depth 8
if (-not $OverallOk) { exit 2 }
