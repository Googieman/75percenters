[CmdletBinding()]
param(
    [switch]$SkipNode
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$backendDir = Join-Path $repoRoot "backend"
$frontendDir = Join-Path $repoRoot "frontend"
$connectorDir = Join-Path $repoRoot "connector"
$venvDir = Join-Path $backendDir ".venv"
$pythonExe = Join-Path $venvDir "Scripts\python.exe"

if (-not (Test-Path -LiteralPath $pythonExe)) {
    $pythonLauncher = Get-Command py -ErrorAction SilentlyContinue
    if ($null -ne $pythonLauncher) {
        & $pythonLauncher.Source -3.13 -m venv $venvDir
    } else {
        & python -m venv $venvDir
    }
}

if (-not (Test-Path -LiteralPath $pythonExe)) {
    throw "Python 3.13 virtual environment was not created at $pythonExe"
}

& $pythonExe -m pip install --disable-pip-version-check --requirement (Join-Path $backendDir "requirements.lock")
& $pythonExe -m pip install --disable-pip-version-check --editable $backendDir --no-deps

if (-not $SkipNode) {
    & npm --prefix $frontendDir ci
    & npm --prefix $connectorDir ci
}

& $pythonExe -m pip check

Write-Output "Development dependencies are ready."
Write-Output "Backend interpreter: $pythonExe"
if ($SkipNode) {
    Write-Output "Node dependency installation was skipped."
}
