param(
    [switch]$MutationOnly
)

$ErrorActionPreference = "Stop"

. (Join-Path $PSScriptRoot "dev-tools.ps1")

$repoRoot = Get-RepoRoot
$args = @("compose", "run", "--rm", "compiled-tools", "python", "/repo/scripts/check_go_tools.py")
if ($MutationOnly) {
    $args += "--mutation-only"
}

Write-Host "Running Go checks in Docker..."
& docker @args
if ($LASTEXITCODE -ne 0) {
    throw "Docker Go checks failed."
}

Write-Host "Go checks completed."
