param()

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$runId = [Guid]::NewGuid().ToString("N")
$containerName = "srm-tracker-e2e-$runId"
$databaseName = "srm_tracker_e2e_$($runId.Substring(0, 12))"
$runLabel = "srm-tracker-e2e-$runId"
$databasePort = 0
$apiPort = 0
$frontendPort = 0
$containerStarted = $false
$apiProcess = $null
$frontendProcess = $null
$failure = $null
$tempRoot = Join-Path ([IO.Path]::GetTempPath()) "srm-tracker-e2e-$runId"
New-Item -ItemType Directory -Path $tempRoot -Force | Out-Null

function Get-FreePort {
  $listener = [Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback, 0)
  try {
    $listener.Start()
    return $listener.LocalEndpoint.Port
  } finally {
    $listener.Stop()
  }
}

function Invoke-Checked([string]$FilePath, [string[]]$Arguments, [string]$WorkingDirectory) {
  Push-Location $WorkingDirectory
  try {
    & $FilePath @Arguments
    if ($LASTEXITCODE -ne 0) {
      throw "$FilePath $($Arguments -join ' ') exited with code $LASTEXITCODE"
    }
  } finally {
    Pop-Location
  }
}

function Wait-ForHttp([string]$Url, [int]$TimeoutSeconds = 30) {
  $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
  do {
    try {
      $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 2
      if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 500) { return }
    } catch { }
    Start-Sleep -Milliseconds 250
  } while ((Get-Date) -lt $deadline)
  throw "Timed out waiting for $Url"
}

function Wait-ForDatabase([int]$TimeoutSeconds = 45) {
  $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
  do {
    try {
      docker exec $containerName pg_isready -U srm_tracker -d $databaseName | Out-Null
      if ($LASTEXITCODE -eq 0) { return }
    } catch { }
    Start-Sleep -Milliseconds 500
  } while ((Get-Date) -lt $deadline)
  throw "Timed out waiting for PostgreSQL container $containerName"
}

try {
  $databasePort = Get-FreePort
  $apiPort = Get-FreePort
  $frontendPort = Get-FreePort
  $python = if ($env:SRM_TRACKER_E2E_PYTHON) {
    $env:SRM_TRACKER_E2E_PYTHON
  } elseif (Test-Path (Join-Path $repoRoot "backend\.venv\Scripts\python.exe")) {
    Join-Path $repoRoot "backend\.venv\Scripts\python.exe"
  } else {
    (Get-Command python).Source
  }
  if (-not (Test-Path $python) -and -not (Get-Command $python -ErrorAction SilentlyContinue)) {
    throw "Python executable not found; set SRM_TRACKER_E2E_PYTHON or create backend\.venv"
  }

  $databaseUrl = "postgresql+psycopg://srm_tracker:srm_tracker@127.0.0.1:$databasePort/$databaseName"
  docker run --detach --rm --name $containerName --label "com.srm-tracker.e2e=$runLabel" `
    --env POSTGRES_DB=$databaseName --env POSTGRES_USER=srm_tracker --env POSTGRES_PASSWORD=srm_tracker `
    --publish "127.0.0.1:${databasePort}:5432" --tmpfs /var/lib/postgresql/data postgres:16 | Out-Null
  if ($LASTEXITCODE -ne 0) { throw "Unable to start runner-owned PostgreSQL container" }
  $containerStarted = $true
  Wait-ForDatabase

  $env:SRM_TRACKER_DATABASE_URL = $databaseUrl
  $env:SRM_TRACKER_ENVIRONMENT = "test"
  $env:SRM_TRACKER_FRONTEND_ORIGIN = "http://127.0.0.1:$frontendPort"
  $env:E2E_ACCOUNT_EMAIL = "e2e-owner@example.com"
  $env:E2E_ACCOUNT_PASSWORD = "e2e-password-1234"
  $env:E2E_DATABASE_NAME = $databaseName
  $env:E2E_DATABASE_PORT = "$databasePort"
  $env:E2E_CONTAINER_NAME = $containerName
  $env:E2E_CONTAINER_LABEL = $runLabel
  $env:E2E_REPO_ROOT = $repoRoot

  Invoke-Checked $python @("-m", "alembic", "upgrade", "head") (Join-Path $repoRoot "backend")
  Invoke-Checked $python @("scripts/e2e_support.py", "bootstrap") (Join-Path $repoRoot "backend")

  $apiLog = Join-Path $tempRoot "api.log"
  $apiError = Join-Path $tempRoot "api.error.log"
  $apiProcess = Start-Process -FilePath $python -WorkingDirectory (Join-Path $repoRoot "backend") `
    -ArgumentList @("-m", "uvicorn", "srm_tracker.main:create_app", "--factory", "--app-dir", "src", "--host", "127.0.0.1", "--port", "$apiPort") `
    -RedirectStandardOutput $apiLog -RedirectStandardError $apiError -PassThru -WindowStyle Hidden
  Wait-ForHttp "http://127.0.0.1:$apiPort/api/v1/health"

  $frontendLog = Join-Path $tempRoot "frontend.log"
  $frontendError = Join-Path $tempRoot "frontend.error.log"
  $env:VITE_API_PROXY_TARGET = "http://127.0.0.1:$apiPort"
  $frontendProcess = Start-Process -FilePath "npm.cmd" -WorkingDirectory (Join-Path $repoRoot "frontend") `
    -ArgumentList @("run", "dev", "--", "--host", "127.0.0.1", "--port", "$frontendPort") `
    -RedirectStandardOutput $frontendLog -RedirectStandardError $frontendError -PassThru -WindowStyle Hidden
  Wait-ForHttp "http://127.0.0.1:$frontendPort"

  $connectorOutput = Join-Path $tempRoot "connector"
  $env:CONNECTOR_OUTPUT_DIR = $connectorOutput
  Invoke-Checked "npm.cmd" @("run", "build", "--", "http://127.0.0.1:$apiPort") (Join-Path $repoRoot "connector")
  $builtConnector = $connectorOutput
  if (-not (Test-Path (Join-Path $builtConnector "manifest.json"))) { throw "Connector build did not produce manifest.json" }

  $env:E2E_FRONTEND_URL = "http://127.0.0.1:$frontendPort"
  $env:E2E_CONNECTOR_DIR = $builtConnector
  $env:E2E_SUPPORT_PYTHON = $python
  Invoke-Checked "npx.cmd" @("playwright", "install", "chromium") (Join-Path $repoRoot "frontend")
  Invoke-Checked "npx.cmd" @("playwright", "test", "--workers=1", "--retries=0") (Join-Path $repoRoot "frontend")
} catch {
  $failure = $_
} finally {
  if ($frontendProcess) { taskkill /PID $frontendProcess.Id /T /F 2>$null | Out-Null }
  if ($apiProcess) { taskkill /PID $apiProcess.Id /T /F 2>$null | Out-Null }
  if ($containerStarted) {
    docker rm --force $containerName | Out-Null
  }
  if ($failure) {
    Write-Error $failure
    Write-Host "E2E diagnostics retained at $tempRoot"
    exit 1
  }
  Remove-Item -LiteralPath $tempRoot -Recurse -Force -ErrorAction SilentlyContinue
}
