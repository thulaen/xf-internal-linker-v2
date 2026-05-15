param(
    [switch]$Clean
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

Write-Host "Building Docker-managed native extensions..."
docker compose run --rm --no-deps backend bash -lc $command
if ($LASTEXITCODE -ne 0) {
    throw "Docker-managed native extension build failed."
}

Write-Host "Native extension artifacts are ready in Docker storage."
