param(
    [switch]$Clean
)

$ErrorActionPreference = "Stop"

. (Join-Path $PSScriptRoot "dev-tools.ps1")

$repoRoot = Get-RepoRoot
$cleanArg = if ($Clean) { "--clean" } else { "" }

Write-Host "Running C++ tests in Docker..."
docker compose run --rm compiled-tools bash /repo/scripts/run-cpp-tests.sh $cleanArg
if ($LASTEXITCODE -ne 0) {
    throw "Docker C++ test suite failed."
}

Write-Host "C++ test suite completed."
