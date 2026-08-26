param(
  [int]$Port = 8788
)

$startScript = Join-Path (Split-Path -Parent $PSScriptRoot) 'start-client.ps1'
if (-not (Test-Path -LiteralPath $startScript)) {
  throw "找不到便携启动脚本: $startScript"
}
& $startScript -Port $Port
