param(
    [Parameter(Mandatory = $true)]
    [string]$RunId,

    [Parameter(Mandatory = $true)]
    [string[]]$CandidatesJson,

    [Parameter(Mandatory = $true)]
    [string]$ImageDir,

    [Parameter(Mandatory = $true)]
    [int]$Target,

    [string]$RunDate = (Get-Date -Format 'yyyy-MM-dd'),
    [int]$Port = 8765,
    [string]$OutputRoot = "",
    [string]$Token = ""
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path

if (-not $OutputRoot) {
    $OutputRoot = Join-Path $ProjectRoot (Join-Path 'runs' $RunId)
}

$Arguments = @(
    (Join-Path $PSScriptRoot 'selection_excel_bridge.py'),
    '--project-root', $ProjectRoot,
    '--output-root', $OutputRoot,
    '--image-dir', $ImageDir,
    '--run-id', $RunId,
    '--run-date', $RunDate,
    '--target', [string]$Target,
    '--port', [string]$Port
)

foreach ($Path in $CandidatesJson) {
    $Arguments += @('--candidates-json', $Path)
}

if ($Token) {
    $Arguments += @('--token', $Token)
}

Write-Host 'Starting strict-selection Excel bridge...' -ForegroundColor Cyan
Write-Host "Output directory: $OutputRoot"
Write-Host 'Accepted evidence: Runner 0.3.8.2 / Collector 0.4.6.2'
Write-Host 'Enter the displayed service URL and token in the Runner panel.'

& python @Arguments
exit $LASTEXITCODE
