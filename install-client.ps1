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

function Test-StoreAlias([string]$Path) {
  return [bool]$Path -and ($Path -like '*\WindowsApps\*')
}

function Resolve-PythonPath {
  if (Test-Path -LiteralPath $CodexPython) { return $CodexPython }
  $Candidate = Find-Executable @('python.exe', 'python')
  if ($Candidate -and -not (Test-StoreAlias $Candidate)) { return $Candidate }
  $PyLauncher = Find-Executable @('py.exe', 'py')
  if ($PyLauncher) {
    $Launched = & $PyLauncher '-3' '-c' 'import sys; print(sys.executable)' 2>$null
    if ($LASTEXITCODE -eq 0 -and $Launched) { return ([string]($Launched | Select-Object -First 1)).Trim() }
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

$PythonPath = Resolve-PythonPath
if (-not $PythonPath -or -not (Test-Path -LiteralPath $PythonPath)) {
  $StoreAlias = Find-Executable @('python.exe', 'python')
  if ($StoreAlias -and (Test-StoreAlias $StoreAlias)) {
    throw "PATH 中的 python.exe 是 Windows 商店占位别名，不是真实解释器：$StoreAlias`n请在「设置 > 应用执行别名」中关闭 python.exe/python3.exe，或安装 python.org 版本后重新运行 install-client.ps1。"
  }
  throw '未找到 Python 3。请安装 Python 3.11 或更高版本后重新运行 install-client.ps1。'
}

$NodePath = if (Test-Path -LiteralPath $CodexNode) { $CodexNode } else { Find-Executable @('node.exe', 'node') }
if (-not $NodePath) {
  throw '未找到 Node.js。请安装 Node.js 18 或更高版本后重新运行 install-client.ps1。'
}

$PythonVersion = ''
try { $PythonVersion = (& $PythonPath '-c' 'import sys; print(sys.version_info.major, sys.version_info.minor, sep=chr(46))' 2>$null).Trim() } catch { $PythonVersion = '' }
if (-not $PythonVersion) {
  throw "无法运行 Python: $PythonPath。请确认它是 python.org 安装的 3.11 或更高版本。"
}
$PythonParts = $PythonVersion.Split('.')
if ([int]$PythonParts[0] -lt 3 -or (([int]$PythonParts[0] -eq 3) -and ([int]$PythonParts[1] -lt 11))) {
  throw "需要 Python 3.11 或更高版本，当前为 $PythonVersion。"
}
$NodeVersion = ''
try { $NodeVersion = (& $NodePath '--version' 2>$null).Trim().TrimStart('v') } catch { $NodeVersion = '' }
if (-not $NodeVersion) {
  throw "无法运行 Node.js: $NodePath。请安装 Node.js 18 或更高版本后重试。"
}
if ([int]$NodeVersion.Split('.')[0] -lt 18) {
  throw "需要 Node.js 18 或更高版本，当前为 v$NodeVersion。"
}

if (-not (Test-Path -LiteralPath (Join-Path $CodexNodeModules '@oai\artifact-tool\package.json'))) {
  throw "未找到 Codex 自带的 @oai/artifact-tool：$CodexNodeModules。请先打开 Codex Desktop 完成本机运行时初始化，再重新运行 install-client.ps1；不要下载替代包。"
}
if (-not (Test-Path -LiteralPath $PipelineNodeModules)) {
  New-Item -ItemType Junction -Path $PipelineNodeModules -Target $CodexNodeModules | Out-Null
}
if (-not (Test-Path -LiteralPath (Join-Path $PipelineNodeModules '@oai\artifact-tool\package.json'))) {
  throw "pipeline\node_modules 已存在但不包含 @oai/artifact-tool；未覆盖该目录，请人工确认后重试。"
}

$VenvRoot = Join-Path $RuntimeRoot 'venv'
$VenvPython = Join-Path $VenvRoot 'Scripts\python.exe'
$PythonRuntime = $PythonPath
$Isolation = 'none'

if (-not $SkipDependencyInstall -and -not (Test-Path -LiteralPath $VenvPython)) {
  Write-Host "正在创建依赖隔离环境: $VenvRoot"
  & $PythonPath '-m' 'venv' $VenvRoot 2>&1 | Out-Null
  if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $VenvPython)) {
    $SystemPython = Find-Executable @('python.exe', 'python')
    if ($SystemPython -and -not (Test-StoreAlias $SystemPython) -and $SystemPython -ne $PythonPath) {
      Write-Host "当前 Python 无法创建 venv，改用系统 Python: $SystemPython"
      & $SystemPython '-m' 'venv' $VenvRoot 2>&1 | Out-Null
    }
  }
}
if (Test-Path -LiteralPath $VenvPython) {
  $VenvVersion = ''
  try { $VenvVersion = (& $VenvPython '-c' 'import sys; print(sys.version_info.major, sys.version_info.minor, sep=chr(46))' 2>$null).Trim() } catch { $VenvVersion = '' }
  $VenvParts = $VenvVersion.Split('.')
  if (-not $VenvVersion -or [int]$VenvParts[0] -lt 3 -or (([int]$VenvParts[0] -eq 3) -and ([int]$VenvParts[1] -lt 11))) {
    throw "venv 解释器版本不满足要求: $VenvVersion ($VenvPython)。请删除 .runtime\venv 后改用 Python 3.11+ 重跑安装器。"
  }
  $PythonRuntime = $VenvPython
  $Isolation = 'venv'
} elseif (-not $SkipDependencyInstall) {
  Write-Warning "无法创建 venv（解释器可能缺少 venv 模块）。退回直接安装到 $PythonPath。"
}

if (-not $SkipDependencyInstall) {
  $DependencyCheck = & $PythonRuntime '-c' 'import openpyxl, PIL' 2>&1
  if ($LASTEXITCODE -ne 0) {
    if (-not (Test-Path -LiteralPath $RequirementsPath)) { throw "缺少依赖清单: $RequirementsPath" }
    Write-Host "正在安装 Python 运行依赖（openpyxl、Pillow）到 $PythonRuntime ..."
    & $PythonRuntime '-m' 'pip' 'install' '--disable-pip-version-check' '-r' $RequirementsPath
    if ($LASTEXITCODE -ne 0) { throw 'Python 依赖安装失败，未启动控制台。' }
  }
}

$Toolchain = [ordered]@{
  schemaVersion = 'feiteClientToolchain/v1'
  projectRoot = $Root
  consoleRoot = $ConsoleRoot
  pipelineRoot = $PipelineRoot
  python = $PythonRuntime
  basePython = $PythonPath
  pythonIsolation = $Isolation
  node = $NodePath
  artifactToolNodeModules = $CodexNodeModules
  installedAt = [DateTime]::UtcNow.ToString('o')
}
if ($Isolation -eq 'venv') { $Toolchain['venvRoot'] = $VenvRoot }
$Toolchain | ConvertTo-Json -Depth 3 | Set-Content -LiteralPath $ToolchainPath -Encoding UTF8

Write-Host "安装完成。Python: $PythonRuntime"
if ($Isolation -eq 'venv') {
  Write-Host "依赖隔离: $VenvRoot（删除该目录后重跑安装器即可重建）"
} else {
  Write-Host '依赖隔离: 未启用（依赖安装在基础解释器中）'
}
Write-Host "Node.js: $NodePath"
Write-Host "Excel 组件: $CodexNodeModules"
Write-Host '下一步运行 .\start-client.ps1，然后打开 http://127.0.0.1:8788。'
