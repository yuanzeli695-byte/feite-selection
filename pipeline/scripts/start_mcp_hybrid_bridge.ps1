param(
    [Parameter(Mandatory = $true)]
    [string]$RunId,

    [int]$Port = 8766,
    [ValidateRange(1, 500)]
    [int]$RunBudget = 300,
    [string]$OutputRoot = "",
    [string]$Token = "",
    [switch]$TestMode
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$PolicyPath = Join-Path $ProjectRoot 'config\mcp_hybrid_policy.json'

if (-not $OutputRoot) {
    $OutputRoot = Join-Path $ProjectRoot (Join-Path 'runs' $RunId)
}

$Arguments = @(
    (Join-Path $PSScriptRoot 'mcp_hybrid_bridge.py'),
    '--project-root', $ProjectRoot,
    '--output-root', $OutputRoot,
    '--run-id', $RunId,
    '--policy', $PolicyPath,
    '--run-budget', [string]$RunBudget,
    '--port', [string]$Port
)

if ($Token) {
    $Arguments += @('--token', $Token)
}

if ($TestMode) {
    $Arguments += '--test-mode'
}

Write-Host 'Starting SellerSprite MCP Hybrid Bridge 0.3.2...' -ForegroundColor Cyan
Write-Host "Output directory: $OutputRoot"
Write-Host "Run call budget: $RunBudget"
Write-Host "Test mode: $($TestMode.IsPresent)"
Write-Host 'Mode: SHADOW; outbound MCP disabled; final authority disabled.'
Write-Host 'Default budget covers the 300-call primary pool. Conditional/emergency pools require explicit planning.'

& python @Arguments
exit $LASTEXITCODE
