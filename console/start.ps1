param(
  [int]$Port = 8788
)

$python = 'C:\Users\13045\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
$server = Join-Path $PSScriptRoot 'server.py'
& $python $server --host 127.0.0.1 --port $Port
