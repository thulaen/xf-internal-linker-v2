param(
    [switch]$Clean,
    [string]$DellRepoPath = "/home/goldm/Dev/xf-internal-linker-v2"
)

$ErrorActionPreference = "Stop"

. (Join-Path $PSScriptRoot "dev-tools.ps1")

$repoRoot = Get-RepoRoot
$forceFlag = if ($Clean) { "--force" } else { "" }
$command = @'
set -euo pipefail
python /repo/scripts/ensure_compiled_artifacts.py __FORCE_FLAG__
python /repo/scripts/ensure_compiled_artifacts.py --prune-stale --retention-days 0
'@
$command = $command.Replace("__FORCE_FLAG__", $forceFlag)

Write-Host "Building native extensions on Dell over SSH..."
$escapedCommand = $command.Replace("'", "'\''")
ssh dell "cd '$DellRepoPath' && docker compose run --rm --no-deps backend bash -lc '$escapedCommand'"
if ($LASTEXITCODE -ne 0) {
    throw "Dell native extension build failed."
}

Write-Host "Native extension artifacts are ready on Dell."
