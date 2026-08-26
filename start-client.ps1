[CmdletBinding()]
param(
  [int]$Port = 8788
)

$ErrorActionPreference = 'Stop'
if ($Port -ne 8788) {
  throw '正式浏览器流程固定使用 127.0.0.1:8788；Bridge、Collector、Runner 和页面安装地址均回连 8788，不能用备用端口启动正式客户端。请先确认 8788 的占用者，再停止本项目旧服务或处理端口冲突。'
}
$Root = (Resolve-Path (Join-Path $PSScriptRoot '.')).Path
$ConsoleRoot = Join-Path $Root 'console'
$PipelineRoot = Join-Path $Root 'pipeline'
$RuntimeRoot = Join-Path $Root '.runtime'
$ToolchainPath = Join-Path $RuntimeRoot 'toolchain.json'
$ServicePath = Join-Path $RuntimeRoot 'console-service.json'
$StdoutPath = Join-Path $RuntimeRoot 'console.stdout.log'
$StderrPath = Join-Path $RuntimeRoot 'console.stderr.log'
$ServerPath = (Resolve-Path (Join-Path $ConsoleRoot 'server.py')).Path

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
  try {
    $Toolchain = Get-Content -Raw -LiteralPath $ToolchainPath | ConvertFrom-Json
    if ($Toolchain.python -and (Test-Path -LiteralPath $Toolchain.python)) { $PythonPath = $Toolchain.python }
    if ($Toolchain.node -and (Test-Path -LiteralPath $Toolchain.node)) { $NodePath = $Toolchain.node }
  } catch { }
}
if (-not $PythonPath) { $PythonPath = Find-Executable @('python.exe', 'python') }
if (-not $NodePath) { $NodePath = Find-Executable @('node.exe', 'node') }
if (-not $PythonPath -or -not (Test-Path -LiteralPath $PythonPath)) { throw '未找到 Python。先运行 install-client.ps1。' }
if (-not $NodePath) { throw '未找到 Node.js。先运行 install-client.ps1。' }

$ExistingService = $null
if (Test-Path -LiteralPath $ServicePath) {
  try { $ExistingService = Get-Content -Raw -LiteralPath $ServicePath | ConvertFrom-Json } catch { $ExistingService = $null }
}
if ($ExistingService -and $ExistingService.pid) {
  $ExistingProcess = Get-Process -Id ([int]$ExistingService.pid) -ErrorAction SilentlyContinue
  if ($ExistingProcess) {
    $ExistingInfo = Get-CimInstance Win32_Process -Filter "ProcessId=$($ExistingProcess.Id)" -ErrorAction SilentlyContinue
    $ExistingCommand = ([string]$ExistingInfo.CommandLine).Replace('/', '\').ToLowerInvariant()
    if (-not $ExistingCommand.Contains($ServerPath.ToLowerInvariant())) {
      throw "登记的 PID $($ExistingProcess.Id) 不属于本项目，未复用或停止该进程。请检查 $ServicePath。"
    }
    if ([int]$ExistingService.port -eq $Port) {
      Write-Host "控制台已在运行: http://127.0.0.1:$Port (PID $($ExistingProcess.Id))"
      exit 0
    }
    throw "本项目已有控制台运行在端口 $($ExistingService.port)，请使用对应端口或先运行 stop-client.ps1。"
  }
}

$PortProbe = Get-NetTCPConnection -LocalAddress '127.0.0.1' -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if ($PortProbe) { throw "端口 $Port 已被占用；为避免误杀，未停止该进程。请先确认占用者是否为本项目的 console/server.py，再运行 .\stop-client.ps1；若不是本项目进程，请保留它并由管理员解决端口冲突。" }

New-Item -ItemType Directory -Path $RuntimeRoot -Force | Out-Null
$env:AMAZON_CONSOLE_PROJECT_ROOT = $PipelineRoot
$env:AMAZON_CONSOLE_PYTHON_EXE = $PythonPath
$env:AMAZON_CONSOLE_NODE_EXE = $NodePath
$env:AMAZON_CONSOLE_PREFLIGHT_SCRIPT = Join-Path $PipelineRoot 'scripts\preflight.py'

$Arguments = "`"$ServerPath`" --host 127.0.0.1 --port $Port"
$Process = Start-Process -FilePath $PythonPath -ArgumentList $Arguments -WorkingDirectory $Root -WindowStyle Hidden -PassThru -RedirectStandardOutput $StdoutPath -RedirectStandardError $StderrPath
$Service = [ordered]@{
  schemaVersion = 'feiteClientService/v1'
  pid = $Process.Id
  port = $Port
  root = $Root
  server = $ServerPath
  startedAt = [DateTime]::UtcNow.ToString('o')
}
$Service | ConvertTo-Json -Depth 3 | Set-Content -LiteralPath $ServicePath -Encoding UTF8

$Ready = $false
for ($Attempt = 0; $Attempt -lt 30; $Attempt++) {
  Start-Sleep -Milliseconds 300
  if ($Process.HasExited) { break }
  try {
    $Response = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$Port/api/overview" -TimeoutSec 1
    if ($Response.StatusCode -eq 200) { $Ready = $true; break }
  } catch { }
}
if (-not $Ready) {
  $ErrorTail = if (Test-Path -LiteralPath $StderrPath) { Get-Content -Tail 20 -LiteralPath $StderrPath -ErrorAction SilentlyContinue } else { @() }
  throw "控制台未能在预期时间内启动。请查看 $StderrPath。`n$($ErrorTail -join [Environment]::NewLine)"
}
Write-Host "控制台已启动: http://127.0.0.1:$Port (PID $($Process.Id))"
