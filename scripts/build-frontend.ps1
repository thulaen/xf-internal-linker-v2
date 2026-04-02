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

Write-Host "Building frontend..."
Invoke-FrontendNpm -Arguments @("run", "build") -WorkingDirectory $frontendDir

Write-Host "Frontend build completed."
