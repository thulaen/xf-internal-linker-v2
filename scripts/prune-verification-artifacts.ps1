param()

$ErrorActionPreference = "Stop"

. (Join-Path $PSScriptRoot "dev-tools.ps1")

$repoRoot = Get-RepoRoot

$pruneSafety = Join-Path $PSScriptRoot "check-prune-safety.ps1"
if (Test-Path $pruneSafety) {
    & $pruneSafety
}

$protectedMap = Join-Path $repoRoot "config\protected-data-stores.json"
if (Test-Path $protectedMap) {
    $protected = Get-Content -LiteralPath $protectedMap -Raw | ConvertFrom-Json
    Write-Host "Protected Docker volumes never pruned: $($protected.docker_volumes -join ', ')"
    Write-Host "Protected host paths never pruned: $($protected.host_paths -join ', ')"
}

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

Write-Host "Skipping Docker prune. MSI Docker is retired; remote helper cleanup is handled on Dell or Mint."

# Attempt Windows-space reclaim without stopping the app.
# Full virtual-disk compaction is intentionally skipped here because it
# requires stopping Docker or WSL.
$reclaimScript = Join-Path $PSScriptRoot "reclaim-docker-windows-space.ps1"
if (Test-Path $reclaimScript) {
    Write-Host "Attempting Docker Windows-space reclaim without stopping the app..."
    try {
        & powershell -ExecutionPolicy Bypass -File $reclaimScript
    } catch {
        Write-Host "Docker Windows-space reclaim reported an error (non-fatal): $_"
    }
}

Write-Host "Verification artifact prune completed."
