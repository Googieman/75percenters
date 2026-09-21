[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$renderPath = Join-Path $repoRoot "render.yaml"
$vercelPath = Join-Path $repoRoot "vercel.json"
$failures = [System.Collections.Generic.List[string]]::new()

function Require-Condition {
    param(
        [bool]$Condition,
        [string]$Message
    )
    if (-not $Condition) {
        $failures.Add($Message)
    }
}

$renderText = Get-Content -Raw -LiteralPath $renderPath
try {
    $null = & python -c "import pathlib, sys, yaml; yaml.safe_load(pathlib.Path(sys.argv[1]).read_text(encoding='utf-8'))" $renderPath 2>&1
    Require-Condition ($LASTEXITCODE -eq 0) "render.yaml is not valid YAML"
} catch {
    $failures.Add("render.yaml could not be parsed with the available Python YAML parser")
}

try {
    $vercel = Get-Content -Raw -LiteralPath $vercelPath | ConvertFrom-Json
} catch {
    $failures.Add("vercel.json is not valid JSON")
    $vercel = $null
}

Require-Condition ([regex]::Matches($renderText, '(?m)^\s*-\s+type:\s+web\s*$').Count -eq 1) "render.yaml must define exactly one web service"
Require-Condition ([regex]::Matches($renderText, '(?m)^\s*-\s+type:\s+worker\s*$').Count -eq 0) "render.yaml must not define a worker for free staging"
Require-Condition ([regex]::Matches($renderText, '(?m)^\s*-\s+name:\s+srm-attendance-db-staging\s*$').Count -eq 1) "render.yaml must define the staging database"
Require-Condition ($renderText -match '(?m)^\s*plan:\s+free\s*$') "render.yaml must use the free plan"
Require-Condition ($renderText -notmatch '(?m)^\s*preDeployCommand:') "render.yaml must not use the paid-only preDeployCommand"
Require-Condition ($renderText -match '(?m)^[ \t]*startCommand:[ \t]*.*alembic upgrade head.*uvicorn') "Render startCommand must run migrations before Uvicorn"
Require-Condition ($renderText -match '(?m)^\s*value:\s+on_demand\s*$') "Render staging must use on_demand execution"
Require-Condition ($renderText -match '(?m)^\s*value:\s+[\"'']false[\"'']\s*$') "Render staging must keep hosted acquisition disabled"

if ($null -ne $vercel) {
    Require-Condition ($vercel.installCommand -eq "npm --prefix frontend ci") "Vercel must use npm ci from the frontend lockfile"
    Require-Condition ($vercel.buildCommand -eq "npm --prefix frontend run build") "Vercel must build the frontend package"
    Require-Condition ($vercel.outputDirectory -eq "frontend/dist") "Vercel outputDirectory must be frontend/dist"
    Require-Condition ($vercel.rewrites[0].destination -match "srm-attendance-api-staging\.onrender\.com") "Vercel rewrite must target the staging Render hostname"
}

$package = Get-Content -Raw -LiteralPath (Join-Path $repoRoot "frontend/package.json") | ConvertFrom-Json
Require-Condition ($package.engines.node -eq "24.x") "frontend/package.json must pin Node 24.x"

$tracked = @(git -C $repoRoot ls-files)
Require-Condition (-not ($tracked -contains "AGENTS.md")) "AGENTS.md must remain untracked"
$highConfidenceSecretPatterns = @(
    '-----BEGIN (RSA|OPENSSH|EC|PRIVATE) KEY-----',
    '(ghp_|github_pat_|xox[baprs]-)',
    '(?m)^\s*SRM_TRACKER_SESSION_ENCRYPTION_KEY\s*=\s*[^\s#]+\s*$'
)
foreach ($pattern in $highConfidenceSecretPatterns) {
    $matches = @(git -C $repoRoot grep -n -I -E $pattern -- . ':!scripts/verify_staging_config.ps1' 2>$null)
    Require-Condition ($matches.Count -eq 0) "tracked files contain a high-confidence secret marker: $pattern"
}

if ($failures.Count -gt 0) {
    $failures | ForEach-Object { Write-Error $_ }
    exit 1
}

Write-Output "Free staging configuration checks passed."
