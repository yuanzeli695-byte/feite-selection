[CmdletBinding()]
param(
  [switch]$Json
)

$ErrorActionPreference = 'Stop'
$Root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$Files = @(Get-ChildItem -LiteralPath $Root -Filter '*.ps1' -File -Recurse |
  Where-Object { $_.FullName -notmatch '[\\/](\.git|node_modules|\.runtime)[\\/]' } |
  Sort-Object FullName)

if ($Files.Count -eq 0) { throw "未找到任何 .ps1 脚本: $Root" }

$Results = @()
$Failures = 0
foreach ($File in $Files) {
  $Errors = $null
  [System.Management.Automation.Language.Parser]::ParseFile($File.FullName, [ref]$null, [ref]$Errors) | Out-Null
  $Relative = $File.FullName.Substring($Root.Length).TrimStart([char[]]@('\', '/'))
  if ($Errors -and $Errors.Count -gt 0) {
    $Failures++
    $Messages = @($Errors | ForEach-Object { "第 $($_.Extent.StartLineNumber) 行: $($_.Message)" })
    $Results += [ordered]@{ file = $Relative; ok = $false; errors = $Messages }
  } else {
    $Results += [ordered]@{ file = $Relative; ok = $true; errors = @() }
  }
}

$Ok = $Failures -eq 0
if ($Json) {
  [ordered]@{
    schemaVersion = 'feitePsSyntaxCheck/v1'
    ok = $Ok
    root = $Root
    checked = $Files.Count
    failures = $Failures
    results = $Results
  } | ConvertTo-Json -Depth 5
} else {
  foreach ($Result in $Results) {
    if ($Result.ok) {
      Write-Host ("[ OK ] " + $Result.file) -ForegroundColor Green
    } else {
      Write-Host ("[FAIL] " + $Result.file) -ForegroundColor Red
      foreach ($Message in $Result.errors) { Write-Host ("       " + $Message) -ForegroundColor DarkGray }
    }
  }
  Write-Host ''
  if ($Ok) {
    Write-Host "语法检查通过：$($Files.Count) 个脚本。" -ForegroundColor Green
  } else {
    Write-Host "发现 $Failures 个脚本存在语法错误。" -ForegroundColor Red
  }
}

if (-not $Ok) { exit 2 }
