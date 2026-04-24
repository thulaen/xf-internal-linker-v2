param()

$ErrorActionPreference = "Stop"

. (Join-Path $PSScriptRoot "dev-tools.ps1")

$repoRoot = Get-RepoRoot

# Gemini guard — strip [extensions] worktreeConfig = true from .git/config if present.
# This runs first so a broken Gemini session can recover as soon as the prune runs.
$gitConfigGuard = Join-Path $PSScriptRoot "ensure-git-config-clean.ps1"
if (Test-Path $gitConfigGuard) {
    & $gitConfigGuard
}

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
    # cmd.exe rd handles Windows junction points / symlinks inside Angular
    # dist output reliably where Remove-Item -Recurse can fail mid-tree.
    $cmdPath = $Path -replace '/', '\'
    cmd /c "rd /s /q `"$cmdPath`"" 2>$null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  rd /s /q failed (exit $LASTEXITCODE); retrying with Remove-Item..."
        Remove-Item -LiteralPath $Path -Recurse -Force -ErrorAction Continue
    }
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
    # `docker system prune -f` removes stopped containers, unused networks, dangling images, and build cache in one call.
    # It never touches named volumes, so pgdata / redis-data / media_files / staticfiles (and thus embeddings) are always safe.
    Write-Host "Pruning Docker (stopped containers, unused networks, dangling images, build cache)..."
    & $dockerSafe system prune -f
    if ($LASTEXITCODE -ne 0) {
        throw "Docker system prune failed with exit code $LASTEXITCODE."
    }
} else {
    Write-Host "Skipping Docker prune. $(Get-DockerUnavailableMessage -Availability $dockerAvailability)"
}

# Attempt VHDX compaction so Windows actually reclaims the freed space.
# The compact script auto-skips if any container is running, so this is safe to always call.
$compactScript = Join-Path $PSScriptRoot "..\docker_compact_vhd.ps1"
if (Test-Path $compactScript) {
    Write-Host "Attempting VHDX compaction (auto-skips if containers are running)..."
    try {
        & powershell -ExecutionPolicy Bypass -File $compactScript
    } catch {
        Write-Host "VHDX compaction step reported an error (non-fatal): $_"
    }
}

Write-Host "Verification artifact prune completed."
