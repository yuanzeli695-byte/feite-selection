[CmdletBinding()]
param(
  [switch]$IncludeConsoleState,
  [string]$OutFile
)

$ErrorActionPreference = 'Stop'
$Root = (Resolve-Path (Join-Path $PSScriptRoot '.')).Path
$ConsoleData = Join-Path $Root 'console\data'
$RuntimeRoot = Join-Path $Root '.runtime'
$HistoryPath = Join-Path $Root 'pipeline\history\strict_qualified_asins.json'
$ServicePath = Join-Path $RuntimeRoot 'console-service.json'
$ServerPath = Join-Path $Root 'console\server.py'

function Get-HistoryCount([string]$Path) {
  $Payload = Get-Content -Raw -LiteralPath $Path -Encoding UTF8 | ConvertFrom-Json
  if ($Payload.PSObject.Properties.Name -contains 'count') { return [int]$Payload.count }
  if ($Payload.asins) { return @($Payload.asins).Count }
  return 0
}

function Test-ServiceRunning([string]$LeasePath, [string]$ExpectedServer) {
  if (-not (Test-Path -LiteralPath $LeasePath)) { return [ordered]@{ running = $false; pid = 0 } }
  try {
    $Lease = Get-Content -Raw -LiteralPath $LeasePath -Encoding UTF8 | ConvertFrom-Json
    if (-not $Lease.pid) { return [ordered]@{ running = $false; pid = 0 } }
    $LeasePid = [int]$Lease.pid
    if (-not (Get-Process -Id $LeasePid -ErrorAction SilentlyContinue)) { return [ordered]@{ running = $false; pid = $LeasePid } }
    $Info = Get-CimInstance Win32_Process -Filter "ProcessId=$LeasePid" -ErrorAction SilentlyContinue
    $Command = [string]$Info.CommandLine
    if (-not $Command) { return [ordered]@{ running = $true; pid = $LeasePid } }
    return [ordered]@{ running = $Command.Replace('/', '\').ToLowerInvariant().Contains($ExpectedServer.Replace('/', '\').ToLowerInvariant()); pid = $LeasePid }
  } catch {
    return [ordered]@{ running = $false; pid = 0 }
  }
}

$ServiceState = Test-ServiceRunning $ServicePath $ServerPath
if ($ServiceState.running) {
  throw "控制台可能正在运行 (PID $($ServiceState.pid))，数据库可能在写入中。请先运行 .\stop-client.ps1 再导出。"
}

if (-not (Test-Path -LiteralPath $HistoryPath)) {
  throw "未找到严格合格历史：$HistoryPath。请先运行 install-client.ps1。"
}
try { $HistoryCount = Get-HistoryCount $HistoryPath } catch { throw "严格合格历史不是有效 JSON：$HistoryPath（$($_.Exception.Message)）" }

if (-not $OutFile) {
  $OutFile = Join-Path $Root ('feite-client-history-' + [DateTime]::Now.ToString('yyyyMMdd-HHmmss') + '.zip')
} elseif (-not [System.IO.Path]::IsPathRooted($OutFile)) {
  $OutFile = Join-Path $Root $OutFile
}
if (Test-Path -LiteralPath $OutFile) {
  throw "目标文件已存在，未覆盖：$OutFile。请换一个 -OutFile，或先移走旧文件。"
}

$Targets = @([ordered]@{ relative = 'pipeline/history/strict_qualified_asins.json'; path = $HistoryPath })
$Skipped = @()
if ($IncludeConsoleState) {
  foreach ($Name in @('console.db', 'batches.json')) {
    $Candidate = Join-Path $ConsoleData $Name
    if (Test-Path -LiteralPath $Candidate) {
      $Targets += [ordered]@{ relative = "console/data/$Name"; path = $Candidate }
    } else {
      $Skipped += $Name
    }
  }
}

$Staging = Join-Path $RuntimeRoot ('history-export-' + [guid]::NewGuid().ToString('N'))
$IncludedConsoleState = $Targets.Count -gt 1
New-Item -ItemType Directory -Path $Staging -Force | Out-Null
try {
  $Files = @()
  foreach ($Target in $Targets) {
    $Destination = Join-Path $Staging ($Target.relative -replace '/', '\')
    New-Item -ItemType Directory -Path (Split-Path -Parent $Destination) -Force | Out-Null
    Copy-Item -LiteralPath $Target.path -Destination $Destination -Force
    $Files += [ordered]@{
      path = $Target.relative
      bytes = (Get-Item -LiteralPath $Destination).Length
      sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $Destination).Hash.ToUpperInvariant()
    }
  }

  $Manifest = [ordered]@{
    schemaVersion = 'feiteClientHistoryArchive/v1'
    exportedAt = [DateTime]::UtcNow.ToString('o')
    source = [ordered]@{ projectRoot = $Root; historyCount = $HistoryCount }
    includesConsoleState = [bool]$IncludedConsoleState
    files = $Files
  }
  $ManifestPath = Join-Path $Staging 'manifest.json'
  [System.IO.File]::WriteAllText($ManifestPath, ($Manifest | ConvertTo-Json -Depth 6), (New-Object System.Text.UTF8Encoding($false)))

  Compress-Archive -Path (Join-Path $Staging '*') -DestinationPath $OutFile -CompressionLevel Optimal
} finally {
  Remove-Item -LiteralPath $Staging -Recurse -Force -ErrorAction SilentlyContinue
}

if (-not (Test-Path -LiteralPath $OutFile) -or (Get-Item -LiteralPath $OutFile).Length -le 0) {
  throw "归档创建失败：$OutFile"
}

Write-Host "导出完成: $OutFile"
Write-Host "严格合格历史: $HistoryCount 条"
Write-Host "包含控制台状态: $(if ($IncludedConsoleState) { '是（console.db / batches.json，已排除 browser_pairing.json）' } else { '否（仅严格合格历史）' })"
foreach ($File in $Files) {
  Write-Host ("  {0}  ({1} bytes)" -f $File.path, $File.bytes)
}
if ($Skipped.Count -gt 0) {
  Write-Host "未找到、已跳过: $($Skipped -join ', ')" -ForegroundColor Yellow
}
Write-Host '把该 zip 复制到新机器后运行: .\import-client-history.ps1 -Archive <zip 路径>'
Write-Host '导入前请确认那台机器已停止控制台，且已运行过 install-client.ps1。'
