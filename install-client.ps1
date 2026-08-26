[CmdletBinding()]
param(
  [switch]$SkipDependencyInstall
)

$ErrorActionPreference = 'Stop'
$Root = (Resolve-Path (Join-Path $PSScriptRoot '.')).Path
$ConsoleRoot = Join-Path $Root 'console'
$PipelineRoot = Join-Path $Root 'pipeline'
$RuntimeRoot = Join-Path $Root '.runtime'
$HistoryPath = Join-Path $PipelineRoot 'history\strict_qualified_asins.json'
$RequirementsPath = Join-Path $PipelineRoot 'requirements.txt'
$ToolchainPath = Join-Path $RuntimeRoot 'toolchain.json'
$CodexDependencies = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies'
$CodexPython = Join-Path $CodexDependencies 'python\python.exe'
$CodexNode = Join-Path $CodexDependencies 'node\bin\node.exe'
$CodexNodeModules = Join-Path $CodexDependencies 'node\node_modules'
$PipelineNodeModules = Join-Path $PipelineRoot 'node_modules'

function Find-Executable([string[]]$Names) {
  foreach ($Name in $Names) {
    $Command = Get-Command $Name -ErrorAction SilentlyContinue | Where-Object { $_.CommandType -eq 'Application' } | Select-Object -First 1
    if ($Command) { return $Command.Source }
  }
  return $null
}

foreach ($Path in @(
  $RuntimeRoot,
  (Join-Path $ConsoleRoot 'data'),
  (Join-Path $PipelineRoot 'runs'),
  (Join-Path $PipelineRoot 'cache'),
  (Join-Path $PipelineRoot 'history')
)) {
  New-Item -ItemType Directory -Path $Path -Force | Out-Null
}

if (-not (Test-Path -LiteralPath $HistoryPath)) {
  '{"schemaVersion":"strictQualifiedHistory/v1","count":0,"asins":[]}' | Set-Content -LiteralPath $HistoryPath -Encoding UTF8
}

$PythonPath = if (Test-Path -LiteralPath $CodexPython) { $CodexPython } else { Find-Executable @('python.exe', 'python') }
if (-not $PythonPath) {
  $PyLauncher = Find-Executable @('py.exe', 'py')
  if ($PyLauncher) { $PythonPath = (& $PyLauncher '-3' '-c' 'import sys; print(sys.executable)').Trim() }
}
if (-not $PythonPath -or -not (Test-Path -LiteralPath $PythonPath)) {
  throw '未找到 Python 3。请安装 Python 3.11 或更高版本后重新运行 install-client.ps1。'
}

$NodePath = if (Test-Path -LiteralPath $CodexNode) { $CodexNode } else { Find-Executable @('node.exe', 'node') }
if (-not $NodePath) {
  throw '未找到 Node.js。请安装 Node.js 18 或更高版本后重新运行 install-client.ps1。'
}

$PythonVersion = (& $PythonPath '-c' 'import sys; print(".".join(map(str, sys.version_info[:3])))').Trim()
if ($LASTEXITCODE -ne 0 -or [version]$PythonVersion -lt [version]'3.11') { throw "需要 Python 3.11 或更高版本，当前为 $PythonVersion。" }
$NodeVersion = (& $NodePath '--version').Trim().TrimStart('v')
if ($LASTEXITCODE -ne 0 -or [version]$NodeVersion -lt [version]'18.0') { throw "需要 Node.js 18 或更高版本，当前为 $NodeVersion。" }

if (-not (Test-Path -LiteralPath (Join-Path $CodexNodeModules '@oai\artifact-tool\package.json'))) {
  throw "未找到 Codex 自带的 @oai/artifact-tool：$CodexNodeModules。请先完成 Codex 桌面端运行时安装。"
}
if (-not (Test-Path -LiteralPath $PipelineNodeModules)) {
  New-Item -ItemType Junction -Path $PipelineNodeModules -Target $CodexNodeModules | Out-Null
}
if (-not (Test-Path -LiteralPath (Join-Path $PipelineNodeModules '@oai\artifact-tool\package.json'))) {
  throw "pipeline\node_modules 已存在但不包含 @oai/artifact-tool；未覆盖该目录，请人工确认后重试。"
}

if (-not $SkipDependencyInstall) {
  $DependencyCheck = & $PythonPath '-c' 'import openpyxl, PIL' 2>&1
  if ($LASTEXITCODE -ne 0) {
    if (-not (Test-Path -LiteralPath $RequirementsPath)) { throw "缺少依赖清单: $RequirementsPath" }
    Write-Host '正在安装 Python 运行依赖（openpyxl、Pillow）...'
    & $PythonPath '-m' 'pip' 'install' '--disable-pip-version-check' '-r' $RequirementsPath
    if ($LASTEXITCODE -ne 0) { throw 'Python 依赖安装失败，未启动控制台。' }
  }
}

$Toolchain = [ordered]@{
  schemaVersion = 'feiteClientToolchain/v1'
  projectRoot = $Root
  consoleRoot = $ConsoleRoot
  pipelineRoot = $PipelineRoot
  python = $PythonPath
  node = $NodePath
  artifactToolNodeModules = $CodexNodeModules
  installedAt = [DateTime]::UtcNow.ToString('o')
}
$Toolchain | ConvertTo-Json -Depth 3 | Set-Content -LiteralPath $ToolchainPath -Encoding UTF8

Write-Host "安装完成。Python: $PythonPath"
Write-Host "Node.js: $NodePath"
Write-Host "Excel 组件: $CodexNodeModules"
Write-Host '下一步运行 .\start-client.ps1，然后打开 http://127.0.0.1:8788。'
