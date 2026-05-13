param(
    [switch]$Clean
)

$ErrorActionPreference = "Stop"

. (Join-Path $PSScriptRoot "dev-tools.ps1")

$repoRoot = Get-RepoRoot
$cleanCommand = if ($Clean) { "rm -rf /opt/xf/compiled/extensions /tmp/xf-build/cpp-runtime && " } else { "" }
$command = @'
set -euo pipefail
__CLEAN_COMMAND__python /repo/scripts/ensure_compiled_artifacts.py
'@
$command = $command.Replace("__CLEAN_COMMAND__", $cleanCommand)

Write-Host "Building Docker-managed native extensions..."
docker compose run --rm --no-deps backend bash -lc $command
if ($LASTEXITCODE -ne 0) {
    throw "Docker-managed native extension build failed."
}

Write-Host "Native extension artifacts are ready in Docker storage."
