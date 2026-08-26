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
    [int]$Port = 8769,
    [string]$OutputRoot = "",
    [string]$Token = ""
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path

if (-not $OutputRoot) {
    $OutputRoot = Join-Path $ProjectRoot (Join-Path 'runs' $RunId)
}

$Arguments = @(
    (Join-Path $PSScriptRoot 'selection_excel_bridge_aggregate_traffic.py'),
    '--project-root', $ProjectRoot,
    '--output-root', $OutputRoot,
    '--image-dir', $ImageDir,
    '--run-id', $RunId,
    '--run-date', $RunDate,
    '--target', [string]$Target,
    '--port', [string]$Port,
    '--rules', (Join-Path $ProjectRoot 'config\rules_aggregate_natural_traffic.json'),
    '--runner-version', '0.3.8.6',
    '--collector-version', '0.4.6.3'
)

foreach ($Path in $CandidatesJson) {
    $Arguments += @('--candidates-json', $Path)
}

if ($Token) {
    $Arguments += @('--token', $Token)
}

Write-Host 'Starting aggregate-natural-traffic strict-selection Excel bridge...' -ForegroundColor Cyan
Write-Host "Output directory: $OutputRoot"
Write-Host 'Accepted evidence: Runner 0.3.8.6 / Collector 0.4.6.3'
Write-Host 'Enter the displayed service URL and token in the Runner panel.'

& python @Arguments
exit $LASTEXITCODE
