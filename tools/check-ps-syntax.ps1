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

$ScopeNames = @(
  'env', 'global', 'script', 'local', 'private', 'using',
  'variable', 'function', 'alias', 'cert', 'hkml', 'wsman', 'registry'
)

$Results = @()
$Failures = 0
foreach ($File in $Files) {
  $Relative = $File.FullName.Substring($Root.Length).TrimStart([char[]]@('\', '/'))
  $Issues = @()

  $Bytes = [System.IO.File]::ReadAllBytes($File.FullName)
  $HasBom = $Bytes.Length -ge 3 -and $Bytes[0] -eq 0xEF -and $Bytes[1] -eq 0xBB -and $Bytes[2] -eq 0xBF
  $HasNonAscii = $false
  foreach ($Byte in $Bytes) {
    if ($Byte -gt 0x7F) { $HasNonAscii = $true; break }
  }
  if ($HasNonAscii -and -not $HasBom) {
    $Issues += '含非 ASCII 字符但没有 UTF-8 BOM：Windows PowerShell 5.1 会按 ANSI 代码页读取，中文会破坏字符串配对并导致解析失败'
  }

  $Text = [System.IO.File]::ReadAllText($File.FullName, [System.Text.Encoding]::UTF8)
  $Lines = $Text -split "`r?`n"
  for ($Index = 0; $Index -lt $Lines.Count; $Index++) {
    $Line = $Lines[$Index]
    $LineNumber = $Index + 1

    $ScopeMatch = [regex]::Match($Line, '(?<!\$)\$([A-Za-z_][A-Za-z0-9_]*):')
    if ($ScopeMatch.Success) {
      $Name = $ScopeMatch.Groups[1].Value
      if ($ScopeNames -notcontains $Name) {
        $Issues += ('第 ' + $LineNumber + ' 行：双引号内的 $' + $Name + ': 会被当作作用域/驱动器限定符，请写成 ${' + $Name + '}:')
      }
    }

    $HasAsciiQuote = $Line.IndexOf([char]34) -ge 0
    $HasCurlyQuote = ($Line.IndexOf([char]0x201C) -ge 0) -or ($Line.IndexOf([char]0x201D) -ge 0)
    if ($HasAsciiQuote -and $HasCurlyQuote) {
      $Issues += ('第 ' + $LineNumber + ' 行：同一行同时出现 ASCII 双引号与弯引号（U+201C/U+201D）；PowerShell 会把弯引号当作字符串定界符，请改用「」')
    }

    $SingleQuoted = [regex]::Matches($Line, "'(?:[^']|'')*'")
    $QuoteInsideString = $false
    foreach ($Candidate in $SingleQuoted) {
      if ($Candidate.Value.IndexOf([char]34) -ge 0) { $QuoteInsideString = $true; break }
    }
    if ($QuoteInsideString -and ($Line -match '&\s+\$' -or $Line -match '\$\w*(?:Probe|Snippet|Code|Script)\w*\s*=')) {
      $Issues += ('第 ' + $LineNumber + ' 行：单引号字符串内含双引号，且该值会作为原生命令参数；PowerShell 5.1 不会转义参数内的双引号，Python/Node 会收到被截断的代码。请把内层双引号改成两个连续单引号，或直接避免双引号')
    }
  }

  $ParseErrors = $null
  if ($HasNonAscii -and -not $HasBom) {
    [System.Management.Automation.Language.Parser]::ParseInput($Text, [ref]$null, [ref]$ParseErrors) | Out-Null
  } else {
    [System.Management.Automation.Language.Parser]::ParseFile($File.FullName, [ref]$null, [ref]$ParseErrors) | Out-Null
  }
  if ($ParseErrors) {
    foreach ($ParseError in $ParseErrors) {
      $Issues += ('第 ' + $ParseError.Extent.StartLineNumber + ' 行：' + $ParseError.Message)
    }
  }

  if ($Issues.Count -gt 0) {
    $Failures++
    $Results += [ordered]@{ file = $Relative; ok = $false; errors = @($Issues) }
  } else {
    $Results += [ordered]@{ file = $Relative; ok = $true; errors = @() }
  }
}

$Ok = $Failures -eq 0
if ($Json) {
  [ordered]@{
    schemaVersion = 'feitePsSyntaxCheck/v3'
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
    Write-Host "发现 $Failures 个脚本存在语法或编码问题。" -ForegroundColor Red
  }
}

if (-not $Ok) { exit 2 }
