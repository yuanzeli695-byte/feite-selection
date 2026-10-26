[CmdletBinding()]
param(
  [Parameter(Mandatory = $true)][string]$Archive,
  [switch]$IncludeConsoleState,
  [switch]$Force,
  [switch]$DryRun
)

$ErrorActionPreference = 'Stop'
$Root = (Resolve-Path (Join-Path $PSScriptRoot '.')).Path
$RuntimeRoot = Join-Path $Root '.runtime'
$ServicePath = Join-Path $RuntimeRoot 'console-service.json'
$ServerPath = Join-Path $Root 'console\server.py'
$HistoryTarget = Join-Path $Root 'pipeline\history\strict_qualified_asins.json'

$AllowedPaths = @(
  'pipeline/history/strict_qualified_asins.json',
  'console/data/console.db',
  'console/data/batches.json'
)
$ConsoleStatePaths = @('console/data/console.db', 'console/data/batches.json')

function Get-HistoryCount([string]$Path) {
  $Payload = Get-Content -Raw -LiteralPath $Path -Encoding UTF8 | ConvertFrom-Json
  if ($Payload.PSObject.Properties.Name -contains 'count') { return [int]$Payload.count }
  if ($Payload.asins) { return @($Payload.asins).Count }
  return 0
}

if (-not (Test-Path -LiteralPath (Join-Path $Root 'console\server.py'))) {
  throw "当前目录不是 feite-selection checkout：$Root"
}
if (-not (Test-Path -LiteralPath $Archive)) {
  throw "找不到归档文件: $Archive"
}
$Archive = (Resolve-Path -LiteralPath $Archive).Path

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
  throw "控制台可能正在运行 (PID $($ServiceState.pid))。请先运行 .\stop-client.ps1 再导入历史。"
}

New-Item -ItemType Directory -Path $RuntimeRoot -Force | Out-Null
$TempRoot = Join-Path $RuntimeRoot ('history-import-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $TempRoot -Force | Out-Null

try {
  $ArchiveForExpand = $Archive
  if ([System.IO.Path]::GetExtension($Archive).ToLowerInvariant() -ne '.zip') {
    $ArchiveForExpand = Join-Path $TempRoot 'archive.zip'
    Copy-Item -LiteralPath $Archive -Destination $ArchiveForExpand -Force
  }
  Expand-Archive -LiteralPath $ArchiveForExpand -DestinationPath $TempRoot -Force

  $ManifestPath = Join-Path $TempRoot 'manifest.json'
  if (-not (Test-Path -LiteralPath $ManifestPath)) {
    throw '归档缺少 manifest.json，不是 export-client-history.ps1 导出的历史包。'
  }
  $Manifest = Get-Content -Raw -LiteralPath $ManifestPath -Encoding UTF8 | ConvertFrom-Json
  if ([string]$Manifest.schemaVersion -ne 'feiteClientHistoryArchive/v1') {
    throw "不支持的归档版本: $($Manifest.schemaVersion)"
  }
  $Entries = @($Manifest.files)
  if ($Entries.Count -eq 0) { throw '归档清单为空。' }

  $ConsoleEntries = 0
  $Plan = @()
  foreach ($Entry in $Entries) {
    $Relative = ([string]$Entry.path) -replace '\\', '/'
    if ($AllowedPaths -notcontains $Relative) {
      throw "归档包含不允许恢复的路径: $Relative"
    }
    if ($ConsoleStatePaths -contains $Relative) { $ConsoleEntries++ }
    $Source = Join-Path $TempRoot ($Relative -replace '/', '\')
    if (-not (Test-Path -LiteralPath $Source)) {
      throw "归档缺少文件: $Relative"
    }
    $Actual = (Get-FileHash -Algorithm SHA256 -LiteralPath $Source).Hash.ToUpperInvariant()
    $Expected = ([string]$Entry.sha256).ToUpperInvariant()
    if ($Actual -ne $Expected) {
      throw "文件校验失败（归档可能被改动）: $Relative"
    }
    $Plan += [ordered]@{
      relative = $Relative
      source = $Source
      target = (Join-Path $Root ($Relative -replace '/', '\'))
      sha256 = $Expected
      bytes = (Get-Item -LiteralPath $Source).Length
    }
  }

  if ($ConsoleEntries -gt 0 -and -not $IncludeConsoleState) {
    throw "归档包含控制台状态（批次数据库），恢复它会带入另一台机器的批次记录。确认需要时加 -IncludeConsoleState 重新运行。"
  }

  $Existing = @($Plan | Where-Object { Test-Path -LiteralPath $_.target })
  if ($Existing.Count -gt 0 -and -not $Force -and -not $DryRun) {
    $Names = ($Existing | ForEach-Object { $_.relative }) -join "`n  "
    throw "以下文件已存在，未覆盖：`n  $Names`n确认覆盖请加 -Force（会先备份为 .pre-import-<时间戳>.bak）。"
  }

  $SourceHistoryCount = 0
  if ($Manifest.source -and $Manifest.source.historyCount) { $SourceHistoryCount = [int]$Manifest.source.historyCount }

  if ($DryRun) {
    Write-Host "预检通过（-DryRun，未写入任何文件）: $Archive"
    Write-Host "归档导出时间: $($Manifest.exportedAt)"
    Write-Host "严格合格历史: $SourceHistoryCount 条"
    foreach ($Item in $Plan) {
      $State = if (Test-Path -LiteralPath $Item.target) { '[将覆盖，并先备份]' } else { '[新增]' }
      Write-Host ("  {0}  {1}" -f $Item.relative, $State)
    }
    return
  }

  $Stamp = [DateTime]::Now.ToString('yyyyMMdd-HHmmss')
  $Backups = @()
  foreach ($Item in $Plan) {
    New-Item -ItemType Directory -Path (Split-Path -Parent $Item.target) -Force | Out-Null
    if (Test-Path -LiteralPath $Item.target) {
      $BackupPath = $Item.target + '.pre-import-' + $Stamp + '.bak'
      Copy-Item -LiteralPath $Item.target -Destination $BackupPath -Force
      $Backups += $BackupPath
    }
    Copy-Item -LiteralPath $Item.source -Destination $Item.target -Force
    $Restored = (Get-FileHash -Algorithm SHA256 -LiteralPath $Item.target).Hash.ToUpperInvariant()
    if ($Restored -ne $Item.sha256) {
      throw "恢复后校验失败: $($Item.relative)"
    }
  }

  try { $HistoryCount = Get-HistoryCount $HistoryTarget } catch { throw "导入后的严格合格历史不是有效 JSON：$HistoryTarget（$($_.Exception.Message)）" }
} finally {
  Remove-Item -LiteralPath $TempRoot -Recurse -Force -ErrorAction SilentlyContinue
}

Write-Host "导入完成: $Archive"
Write-Host "严格合格历史: $HistoryCount 条"
foreach ($Item in $Plan) {
  Write-Host ("  {0}  ({1} bytes)" -f $Item.relative, $Item.bytes)
}
if ($Backups.Count -gt 0) {
  Write-Host '覆盖前的备份:'
  foreach ($Backup in $Backups) { Write-Host "  $Backup" }
}
Write-Host '下一步: .\doctor.ps1 与 .\verify-client.ps1 -NoServiceCheck 确认环境可用。'
