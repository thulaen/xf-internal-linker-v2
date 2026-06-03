param(
    [switch]$Clean
)

$ErrorActionPreference = "Stop"

. (Join-Path $PSScriptRoot "dev-tools.ps1")

$repoRoot = Get-RepoRoot
$cleanArg = if ($Clean) { "--clean" } else { "" }

# compiled-tools moved to the Mint helper (mint-quality profile). If its image
# isn't here, don't silently rebuild ~5 GB on Windows — compiled-language
# quality runs on Mint via the turbo 65/35 split.
if (-not (docker image inspect xf-linker-compiled-tools:latest 2>$null)) {
    Write-Warning "compiled-tools is not on this machine — C++ quality runs on the Mint helper now."
    Write-Host "Run it on Mint:  bash scripts/run-mint-quality-shard.sh   (the turbo split routes compiled work to Mint)"
    throw "Refusing to rebuild the ~5 GB compiled-tools image on Windows. Use the Mint workflow."
}

Write-Host "Running C++ tests in Docker..."
docker compose run --rm compiled-tools bash /repo/scripts/run-cpp-tests.sh $cleanArg
if ($LASTEXITCODE -ne 0) {
    throw "Docker C++ test suite failed."
}

Write-Host "C++ test suite completed."
