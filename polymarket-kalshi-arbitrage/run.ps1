$ErrorActionPreference = "Stop"

$paths = @($PSScriptRoot)
$localDeps = Join-Path $PSScriptRoot ".deps"
if (Test-Path -LiteralPath $localDeps) {
    $paths += $localDeps
}
$env:PYTHONPATH = ($paths -join [System.IO.Path]::PathSeparator)
$port = if ($env:ARBITRAGE_PORT) { $env:ARBITRAGE_PORT } else { "8011" }
$serverArgs = @("-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", $port)
if ($env:ARBITRAGE_RELOAD -and $env:ARBITRAGE_RELOAD.ToLower() -in @("1", "true", "yes", "on")) {
    $serverArgs += "--reload"
}

$venvPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
$bundledPython = "C:\Users\Pichau\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"

if (Test-Path -LiteralPath $venvPython) {
    & $venvPython @serverArgs
} elseif (Test-Path -LiteralPath $bundledPython) {
    & $bundledPython @serverArgs
} else {
    python @serverArgs
}
