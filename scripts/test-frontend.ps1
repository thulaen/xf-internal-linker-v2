param(
    [switch]$Install
)

$ErrorActionPreference = "Stop"

. (Join-Path $PSScriptRoot "dev-tools.ps1")

$frontendDir = Join-Path (Get-RepoRoot) "frontend"

if ($Install -or -not (Test-Path (Join-Path $frontendDir "node_modules"))) {
    Write-Host "Installing frontend packages..."
    Invoke-FrontendNpm -Arguments @("ci") -WorkingDirectory $frontendDir
}

Write-Host "Running frontend unit tests..."
Invoke-FrontendNpm -Arguments @("run", "test:ci") -WorkingDirectory $frontendDir

Write-Host "Frontend unit tests completed."
