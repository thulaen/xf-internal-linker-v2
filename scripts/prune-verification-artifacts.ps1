param()

$ErrorActionPreference = "Stop"

. (Join-Path $PSScriptRoot "dev-tools.ps1")

$repoRoot = Get-RepoRoot

function Remove-DirectoryIfExists {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,
        [Parameter(Mandatory = $true)]
        [string]$Label
    )

    if (-not (Test-Path -LiteralPath $Path)) {
        return
    }

    Write-Host "Pruning $Label..."
    Remove-Item -LiteralPath $Path -Recurse -Force
}

# ── Frontend artifacts ────────────────────────────────────────────
Remove-DirectoryIfExists -Path (Join-Path $repoRoot "frontend\dist") -Label "frontend dist output"
Remove-DirectoryIfExists -Path (Join-Path $repoRoot "frontend\.angular\cache") -Label "Angular build cache"
Remove-DirectoryIfExists -Path (Join-Path $repoRoot "frontend\coverage") -Label "Karma coverage output"
$eslintCache = Join-Path $repoRoot "frontend\.eslintcache"
if (Test-Path -LiteralPath $eslintCache) {
    Write-Host "Pruning ESLint cache..."
    Remove-Item -LiteralPath $eslintCache -Force
}

# ── Backend artifacts ─────────────────────────────────────────────
Remove-DirectoryIfExists -Path (Join-Path $repoRoot "backend\extensions\build") -Label "native extension build cache"
Remove-DirectoryIfExists -Path (Join-Path $repoRoot "backend\extensions\__pycache__") -Label "native extension Python cache"
Remove-DirectoryIfExists -Path (Join-Path $repoRoot "backend\.mypy_cache") -Label "mypy cache"
Remove-DirectoryIfExists -Path (Join-Path $repoRoot "backend\.ruff_cache") -Label "ruff cache"
Remove-DirectoryIfExists -Path (Join-Path $repoRoot "backend\.pytest_cache") -Label "pytest cache"
Remove-DirectoryIfExists -Path (Join-Path $repoRoot "backend\htmlcov") -Label "pytest-cov HTML output"


$dockerAvailability = Get-DockerAvailability
if ($dockerAvailability.Status -eq "ok") {
    $dockerSafe = Get-DockerSafeScript
    Write-Host "Pruning Docker builder cache..."
    & $dockerSafe builder prune -f
    if ($LASTEXITCODE -ne 0) {
        throw "Docker builder prune failed with exit code $LASTEXITCODE."
    }

    Write-Host "Pruning dangling Docker images..."
    & $dockerSafe image prune -f
    if ($LASTEXITCODE -ne 0) {
        throw "Docker image prune failed with exit code $LASTEXITCODE."
    }
} else {
    Write-Host "Skipping Docker prune. $(Get-DockerUnavailableMessage -Availability $dockerAvailability)"
}

Write-Host "Verification artifact prune completed."
