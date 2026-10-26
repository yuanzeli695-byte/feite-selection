[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$Root = (Resolve-Path (Join-Path $PSScriptRoot '.')).Path
$RuntimeRoot = Join-Path $Root '.runtime'
$ServicePath = Join-Path $RuntimeRoot 'console-service.json'
if (-not (Test-Path -LiteralPath $ServicePath)) {
  Write-Host '没有本项目登记的运行实例。'
  exit 0
}

$Service = Get-Content -Raw -LiteralPath $ServicePath | ConvertFrom-Json
$TargetPid = 0
if (-not [int]::TryParse([string]$Service.pid, [ref]$TargetPid) -or $TargetPid -le 0) { throw "运行登记文件中的 PID 无效: $ServicePath" }
$ExpectedServer = [IO.Path]::GetFullPath((Join-Path $Root 'console\server.py'))
$ProcessInfo = Get-CimInstance Win32_Process -Filter "ProcessId=$TargetPid" -ErrorAction SilentlyContinue
if (-not $ProcessInfo) {
  Write-Host "登记的进程 $TargetPid 已不存在，清理本项目运行登记。"
  [System.IO.File]::Delete($ServicePath)
  exit 0
}
$CommandLine = [string]$ProcessInfo.CommandLine
$NormalizedCommand = $CommandLine.Replace('/', '\').ToLowerInvariant()
if (-not $NormalizedCommand.Contains($ExpectedServer.ToLowerInvariant())) {
  throw "PID $TargetPid 的命令行不属于本项目，已拒绝停止。请手工确认后再处理。"
}

Stop-Process -Id $TargetPid -ErrorAction Stop
for ($Attempt = 0; $Attempt -lt 20; $Attempt++) {
  Start-Sleep -Milliseconds 250
  if (-not (Get-Process -Id $TargetPid -ErrorAction SilentlyContinue)) {
    [System.IO.File]::Delete($ServicePath)
    Write-Host "控制台已停止 (PID $TargetPid)。"
    exit 0
  }
}
throw "控制台进程 $TargetPid 未在等待时间内退出；未强制结束，请检查 .runtime 日志。"
