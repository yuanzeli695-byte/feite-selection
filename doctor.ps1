[CmdletBinding()]
param(
  [switch]$Json,
  [switch]$NoServiceCheck
)

$ErrorActionPreference = 'Continue'
$Root = (Resolve-Path (Join-Path $PSScriptRoot '.')).Path
$ConsoleRoot = Join-Path $Root 'console'
$PipelineRoot = Join-Path $Root 'pipeline'
$RuntimeRoot = Join-Path $Root '.runtime'
$ToolchainPath = Join-Path $RuntimeRoot 'toolchain.json'
$ServicePath = Join-Path $RuntimeRoot 'console-service.json'
$ServerPath = Join-Path $ConsoleRoot 'server.py'
$PreflightPath = Join-Path $PipelineRoot 'scripts\preflight.py'
$WorkbookScript = Join-Path $PipelineRoot 'scripts\build_replay_workbooks.mjs'
$DirectImportScript = Join-Path $Root 'direct_import_batch_to_replay.mjs'
$HashManifestPath = Join-Path $PipelineRoot 'config\protected_script_hashes.json'
$DataDir = Join-Path $ConsoleRoot 'data'
$Port = 8788

$CodexDependencies = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies'
$CodexPython = Join-Path $CodexDependencies 'python\python.exe'
$CodexNode = Join-Path $CodexDependencies 'node\bin\node.exe'

$Results = [System.Collections.Generic.List[object]]::new()

function Add-Check {
  param(
    [string]$Id,
    [string]$Title,
    [string]$Status,
    [string]$Detail = '',
    [string]$Hint = ''
  )
  $Results.Add([ordered]@{ id = $Id; title = $Title; status = $Status; detail = $Detail; hint = $Hint })
}

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

function Resolve-ToolchainPath([string]$Key, [string]$Fallback) {
  $Recorded = $null
  $ToolchainPresent = Test-Path -LiteralPath $ToolchainPath
  if ($ToolchainPresent) {
    try {
      $Toolchain = Get-Content -Raw -LiteralPath $ToolchainPath | ConvertFrom-Json
      $Recorded = [string]$Toolchain.$Key
    } catch { $Recorded = $null }
  }
  if ($Recorded -and (Test-Path -LiteralPath $Recorded)) { return [ordered]@{ path = $Recorded; source = 'toolchain.json'; stale = $false } }
  $Resolved = if (Test-Path -LiteralPath $Fallback) { $Fallback } else { Find-Executable @($(Split-Path -Leaf $Fallback), ($(Split-Path -Leaf $Fallback) -replace '\.exe$', '')) }
  $Stale = $ToolchainPresent -and (-not $Recorded -or -not (Test-Path -LiteralPath $Recorded))
  return [ordered]@{ path = $Resolved; source = '探测'; stale = $Stale }
}

$MissingFiles = @()
foreach ($Path in @($ServerPath, $PreflightPath, $WorkbookScript, $DirectImportScript, $HashManifestPath)) {
  if (-not (Test-Path -LiteralPath $Path)) { $MissingFiles += $Path }
}
if ($MissingFiles) {
  Add-Check 'files' '关键文件' 'fail' ("缺少: " + (($MissingFiles | ForEach-Object { Split-Path -Leaf $_ }) -join ', ')) '确认当前目录是完整 checkout；缺失文件请重新 git clone，不要手工补齐。'
} else {
  Add-Check 'files' '关键文件' 'ok' 'server.py / preflight.py / 工作簿构建器 / direct import / 哈希清单齐全'
}

$PythonFallback = if (Test-Path -LiteralPath (Join-Path $RuntimeRoot 'venv\Scripts\python.exe')) { Join-Path $RuntimeRoot 'venv\Scripts\python.exe' } else { $CodexPython }
$PythonInfo = Resolve-ToolchainPath 'python' $PythonFallback
$NodeInfo = Resolve-ToolchainPath 'node' $CodexNode
$PythonPath = $PythonInfo.path
$NodePath = $NodeInfo.path
$PythonOk = $false
$NodeOk = $false

if (-not $PythonPath) {
  Add-Check 'python' 'Python 解释器' 'fail' '未找到 python.exe / python' '安装 Python 3.11+ 并勾选 Add to PATH，然后重新运行 install-client.ps1。'
} elseif (Test-StoreAlias $PythonPath) {
  Add-Check 'python' 'Python 解释器' 'fail' "命中 Windows 商店占位别名: $PythonPath" '这不是真实解释器。安装 python.org 版本，或在“设置 > 应用执行别名”里关闭 python.exe/python3.exe 后重试。'
} else {
  $PythonVersion = ''
  try { $PythonVersion = (& $PythonPath '-c' 'import sys; print("%d.%d" % sys.version_info[:2])' 2>$null).Trim() } catch { $PythonVersion = '' }
  $PythonExit = $LASTEXITCODE
  if ($PythonExit -ne 0 -or -not $PythonVersion) {
    Add-Check 'python' 'Python 解释器' 'fail' "无法执行: $PythonPath" '该路径不能正常运行 Python，请改用 python.org 安装的 3.11+ 解释器。'
  } else {
    $PythonParts = $PythonVersion.Split('.')
    $PythonOk = ([int]$PythonParts[0] -gt 3) -or (([int]$PythonParts[0] -eq 3) -and ([int]$PythonParts[1] -ge 11))
    if ($PythonOk) {
      Add-Check 'python' 'Python 解释器' 'ok' "$PythonVersion ($($PythonInfo.source)) $PythonPath"
    } else {
      Add-Check 'python' 'Python 解释器' 'fail' "版本过低: $PythonVersion ($PythonPath)" '需要 3.11 或更高版本。'
    }
  }
}

if (-not $NodePath) {
  Add-Check 'node' 'Node.js' 'fail' '未找到 node.exe / node' '安装 Node.js 18+（LTS）后重新运行 install-client.ps1。'
} else {
  $NodeVersion = ''
  try { $NodeVersion = (& $NodePath '--version' 2>$null).Trim().TrimStart('v') } catch { $NodeVersion = '' }
  $NodeExit = $LASTEXITCODE
  if ($NodeExit -ne 0 -or -not $NodeVersion) {
    Add-Check 'node' 'Node.js' 'fail' "无法执行: $NodePath" '该路径不能正常运行 Node.js，请安装官方 18+ 版本。'
  } else {
    $NodeParts = $NodeVersion.Split('.')
    $NodeOk = ([int]$NodeParts[0] -ge 18)
    if ($NodeOk) {
      Add-Check 'node' 'Node.js' 'ok' "v$NodeVersion ($($NodeInfo.source)) $NodePath"
    } else {
      Add-Check 'node' 'Node.js' 'fail' "版本过低: v$NodeVersion ($NodePath)" '需要 Node.js 18 或更高版本。'
    }
  }
}

if ($PythonInfo.stale -or $NodeInfo.stale) {
  Add-Check 'toolchain' 'toolchain.json 一致性' 'warn' "$ToolchainPath 记录的路径已失效，本次改用运行时探测" '重新运行 install-client.ps1 刷新记录，避免后续启动脚本回退到错误的解释器。'
} elseif (Test-Path -LiteralPath $ToolchainPath) {
  Add-Check 'toolchain' 'toolchain.json 一致性' 'ok' '记录的 Python / Node 路径均有效'
} else {
  Add-Check 'toolchain' 'toolchain.json 一致性' 'warn' '尚未执行 install-client.ps1' '先运行 install-client.ps1 建立运行记录与空历史。'
}

if (-not $PythonOk) {
  Add-Check 'pythonDeps' 'Python 运行依赖' 'skip' '跳过：Python 不可用'
} else {
  $DepsOutput = & $PythonPath '-c' 'import openpyxl, PIL; print(openpyxl.__version__ + " / " + PIL.__version__)' 2>&1
  if ($LASTEXITCODE -ne 0) {
    Add-Check 'pythonDeps' 'Python 运行依赖' 'fail' (($DepsOutput | Out-String).Trim()) "运行 & `"$PythonPath`" -m pip install -r `"$PipelineRoot\requirements.txt`" 后重试。"
  } else {
    Add-Check 'pythonDeps' 'Python 运行依赖' 'ok' "openpyxl / Pillow 可导入 ($(($DepsOutput | Out-String).Trim()))"
  }
}

if (-not $NodeOk) {
  Add-Check 'nodeDeps' 'Excel 私有依赖' 'skip' '跳过：Node.js 不可用'
} elseif (-not (Test-Path -LiteralPath (Join-Path $PipelineRoot 'node_modules'))) {
  Add-Check 'nodeDeps' 'Excel 私有依赖' 'fail' "缺少 $PipelineRoot\node_modules 联接" '运行 install-client.ps1 创建到 Codex 运行时的联接。'
} else {
  $ProbeDir = Join-Path $PipelineRoot 'runs'
  New-Item -ItemType Directory -Path $ProbeDir -Force | Out-Null
  $ProbePath = Join-Path $ProbeDir '.doctor-artifact-probe.mjs'
  $ProbeSource = @'
try {
  const mod = await import("@oai/artifact-tool");
  const missing = ["Workbook", "SpreadsheetFile"].filter((name) => !(name in mod));
  if (missing.length > 0) {
    console.error("缺少导出: " + missing.join(", "));
    process.exit(3);
  }
  console.log("exports=" + Object.keys(mod).length);
} catch (error) {
  console.error(String((error && error.message) || error));
  process.exit(4);
}
'@
  $ProbeCode = 1
  $ProbeOutput = @()
  try {
    [System.IO.File]::WriteAllText($ProbePath, $ProbeSource, (New-Object System.Text.UTF8Encoding($false)))
    $ProbeOutput = & $NodePath $ProbePath 2>&1
    $ProbeCode = $LASTEXITCODE
  } catch {
    $ProbeOutput = @($_.Exception.Message)
  } finally {
    Remove-Item -LiteralPath $ProbePath -Force -ErrorAction SilentlyContinue
  }
  if ($ProbeCode -eq 0) {
    Add-Check 'nodeDeps' 'Excel 私有依赖' 'ok' "@oai/artifact-tool 可导入 ($(($ProbeOutput | Out-String).Trim()))"
  } else {
    Add-Check 'nodeDeps' 'Excel 私有依赖' 'fail' (($ProbeOutput | Out-String).Trim()) '打开 Codex Desktop 等本机运行时初始化完成后重新运行 install-client.ps1；不要下载替代包。'
  }
}

if (Test-Path -LiteralPath $HashManifestPath) {
  try {
    $Manifest = Get-Content -Raw -LiteralPath $HashManifestPath | ConvertFrom-Json
    $Mismatched = @()
    foreach ($Name in @('bridge', 'collector', 'runner')) {
      $Entry = $Manifest.files.$Name
      $Target = Join-Path $Root ([string]$Entry.path)
      $Actual = if (Test-Path -LiteralPath $Target) { (Get-FileHash -Algorithm SHA256 -LiteralPath $Target).Hash.ToUpperInvariant() } else { $null }
      if ($Actual -ne ([string]$Entry.sha256).ToUpperInvariant()) { $Mismatched += $Name }
    }
    if ($Mismatched.Count -eq 0) {
      Add-Check 'userscriptHashes' '受保护脚本哈希' 'ok' 'Bridge / Collector / Runner 与清单逐字节一致'
    } else {
      Add-Check 'userscriptHashes' '受保护脚本哈希' 'fail' ("不匹配: " + ($Mismatched -join ', ')) '从本次私有 checkout 重新安装批准的浏览器脚本；不要就地编辑文件。'
    }
  } catch {
    Add-Check 'userscriptHashes' '受保护脚本哈希' 'fail' $_.Exception.Message '确认 pipeline\config\protected_script_hashes.json 是有效 JSON。'
  }
} else {
  Add-Check 'userscriptHashes' '受保护脚本哈希' 'fail' '缺少哈希清单' '重新 clone 仓库。'
}

if (-not $PythonOk -or -not (Test-Path -LiteralPath $PreflightPath)) {
  Add-Check 'preflight' '严格预检' 'skip' '跳过：Python 或预检脚本不可用'
} else {
  $env:AMAZON_PRODUCTS_ROOT = $PipelineRoot
  $PreflightOutput = & $PythonPath $PreflightPath '--project-root' $PipelineRoot 2>$null
  $PreflightReport = $null
  try { $PreflightReport = ($PreflightOutput -join "`n") | ConvertFrom-Json } catch { $PreflightReport = $null }
  if (-not $PreflightReport) {
    Add-Check 'preflight' '严格预检' 'fail' '预检输出不是有效 JSON' '单独运行 python pipeline\scripts\preflight.py --project-root pipeline 查看完整报错。'
  } elseif ($PreflightReport.ok) {
    Add-Check 'preflight' '严格预检' 'ok' '规则、历史、受保护文件均通过'
  } else {
    $PreflightErrors = @($PreflightReport.errors)
    Add-Check 'preflight' '严格预检' 'fail' (($PreflightErrors -join '; ')) '按错误项修复；历史文件缺失时先运行 install-client.ps1。'
  }
}

$DirectoryProblems = @()
foreach ($Directory in @($RuntimeRoot, $DataDir, (Join-Path $PipelineRoot 'runs'), (Join-Path $PipelineRoot 'cache'), (Join-Path $PipelineRoot 'history'))) {
  try {
    New-Item -ItemType Directory -Path $Directory -Force | Out-Null
    $ProbeFile = Join-Path $Directory ('.doctor-' + [guid]::NewGuid().ToString('N') + '.tmp')
    Set-Content -LiteralPath $ProbeFile -Value 'ok' -Encoding ASCII
    Remove-Item -LiteralPath $ProbeFile -Force
  } catch {
    $DirectoryProblems += "$Directory: $($_.Exception.Message)"
  }
}
if ($DirectoryProblems.Count -eq 0) {
  Add-Check 'writableDirs' '运行目录可写' 'ok' '.runtime / console\data / pipeline\runs|cache|history'
} else {
  Add-Check 'writableDirs' '运行目录可写' 'fail' ($DirectoryProblems -join '; ') '解除只读属性或更换 checkout 位置（避免受保护目录与企业策略目录）。'
}

if (-not $PythonOk) {
  Add-Check 'sqlite' 'SQLite 可写' 'skip' '跳过：Python 不可用'
} else {
  New-Item -ItemType Directory -Path $DataDir -Force | Out-Null
  $DbProbe = Join-Path $DataDir ('.doctor-' + [guid]::NewGuid().ToString('N') + '.db')
  $SqliteOutput = & $PythonPath '-c' 'import sqlite3, sys; connection = sqlite3.connect(sys.argv[1]); connection.execute("create table if not exists probe(x integer)"); connection.commit(); connection.close(); print("ok")' $DbProbe 2>&1
  $SqliteCode = $LASTEXITCODE
  Remove-Item -LiteralPath $DbProbe -Force -ErrorAction SilentlyContinue
  if ($SqliteCode -eq 0) {
    Add-Check 'sqlite' 'SQLite 可写' 'ok' 'console\data 下可创建并提交数据库'
  } else {
    Add-Check 'sqlite' 'SQLite 可写' 'fail' (($SqliteOutput | Out-String).Trim()) '检查 console\data 权限，或确认 Python 自带 sqlite3 模块未被裁剪。'
  }
}

try {
  $Listener = Get-NetTCPConnection -LocalAddress '127.0.0.1' -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
} catch {
  $Listener = $null
}
if ($Listener) {
  $OwnerInfo = Get-CimInstance Win32_Process -Filter "ProcessId=$($Listener.OwningProcess)" -ErrorAction SilentlyContinue
  $OwnerCommand = ([string]$OwnerInfo.CommandLine).Replace('/', '\').ToLowerInvariant()
  $OurServer = $ServerPath.Replace('/', '\').ToLowerInvariant()
  if ($OwnerCommand.Contains($OurServer)) {
    Add-Check 'port' '端口 8788' 'ok' "已被本项目 console\server.py 占用 (PID $($Listener.OwningProcess))"
  } else {
    Add-Check 'port' '端口 8788' 'fail' "被其他进程占用 (PID $($Listener.OwningProcess)): $($OwnerInfo.CommandLine)" '不要改用其他端口：Bridge/Collector/Runner 固定回连 8788。只有确认属于本仓库的 server.py 时才用 stop-client.ps1 停止。'
  }
} else {
  Add-Check 'port' '端口 8788' 'ok' '空闲，可由 start-client.ps1 接管'
}

if ($NoServiceCheck) {
  Add-Check 'service' '控制台服务' 'skip' '按参数跳过服务检查'
} elseif (-not (Test-Path -LiteralPath $ServicePath)) {
  Add-Check 'service' '控制台服务' 'skip' '尚未启动（无 .runtime\console-service.json）'
} else {
  $Service = $null
  try { $Service = Get-Content -Raw -LiteralPath $ServicePath | ConvertFrom-Json } catch { $Service = $null }
  if (-not $Service -or -not $Service.pid) {
    Add-Check 'service' '控制台服务' 'fail' '运行登记文件无效' '删除 .runtime\console-service.json 后重新运行 start-client.ps1。'
  } elseif (-not (Get-Process -Id ([int]$Service.pid) -ErrorAction SilentlyContinue)) {
    Add-Check 'service' '控制台服务' 'fail' "登记的 PID $($Service.pid) 已不存在" '运行 stop-client.ps1 清理登记，再运行 start-client.ps1。'
  } else {
    $OverviewCode = 0
    $BridgeCode = 0
    try { $OverviewCode = (Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$($Service.port)/api/overview" -TimeoutSec 3).StatusCode } catch { $OverviewCode = 0 }
    try { $BridgeCode = (Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$($Service.port)/browser-bridge.user.js" -TimeoutSec 3).StatusCode } catch { $BridgeCode = 0 }
    if ($OverviewCode -eq 200 -and $BridgeCode -eq 200) {
      Add-Check 'service' '控制台服务' 'ok' "PID $($Service.pid) 运行中，/api/overview 与脚本分发均返回 200"
    } else {
      Add-Check 'service' '控制台服务' 'fail' "PID $($Service.pid) 存在但接口异常 (overview=$OverviewCode, bridge=$BridgeCode)" "查看 $RuntimeRoot\console.stderr.log 后运行 stop-client.ps1 / start-client.ps1。"
    }
  }
}

$Failures = @($Results | Where-Object { $_.status -eq 'fail' })
$Warnings = @($Results | Where-Object { $_.status -eq 'warn' })
$OverallOk = $Failures.Count -eq 0

if ($Json) {
  [ordered]@{
    schemaVersion = 'feiteClientDoctor/v1'
    ok = $OverallOk
    root = $Root
    generatedAt = [DateTime]::UtcNow.ToString('o')
    failureCount = $Failures.Count
    warningCount = $Warnings.Count
    checks = $Results
  } | ConvertTo-Json -Depth 8
} else {
  Write-Host ''
  Write-Host "Feite Selection 可用性自检"
  Write-Host "根目录: $Root"
  Write-Host ('-' * 72)
  foreach ($Check in $Results) {
    if ($Check.status -eq 'ok') {
      Write-Host ("[ OK ] {0,-18} {1}" -f $Check.title, $Check.detail) -ForegroundColor Green
    } elseif ($Check.status -eq 'fail') {
      Write-Host ("[FAIL] {0,-18} {1}" -f $Check.title, $Check.detail) -ForegroundColor Red
    } elseif ($Check.status -eq 'warn') {
      Write-Host ("[WARN] {0,-18} {1}" -f $Check.title, $Check.detail) -ForegroundColor Yellow
    } else {
      Write-Host ("[SKIP] {0,-18} {1}" -f $Check.title, $Check.detail) -ForegroundColor DarkGray
    }
    if ($Check.hint) { Write-Host ("       -> $($Check.hint)") -ForegroundColor DarkGray }
  }
  Write-Host ('-' * 72)
  if ($OverallOk) {
    if ($Warnings.Count -gt 0) {
      Write-Host "可用：没有阻断项，但有 $($Warnings.Count) 条警告。" -ForegroundColor Yellow
    } else {
      Write-Host '可用：所有可用性检查通过。' -ForegroundColor Green
    }
  } else {
    Write-Host "不可用：发现 $($Failures.Count) 项阻断问题，按上面的 -> 提示处理后重跑本脚本。" -ForegroundColor Red
  }
}

if (-not $OverallOk) { exit 2 }
