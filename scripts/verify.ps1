param(
    [switch]$SkipExtensions,
    [switch]$SkipFrontend,
    [switch]$SkipFrontendUnit
)

$ErrorActionPreference = "Stop"

. (Join-Path $PSScriptRoot "dev-tools.ps1")

$repoRoot = Get-RepoRoot
$python = Get-VenvPython

if (-not $SkipExtensions) {
    & (Join-Path $PSScriptRoot "build-native-extensions.ps1")
    if ($LASTEXITCODE -ne 0) {
        throw "Native extension build failed."
    }
}

Write-Host "Running backend tests..."
$env:DJANGO_SETTINGS_MODULE = "config.settings.test"
Push-Location (Join-Path $repoRoot "backend")
try {
    & $python manage.py test apps.content apps.core apps.diagnostics apps.graph apps.pipeline apps.suggestions apps.sync --verbosity 2
    if ($LASTEXITCODE -ne 0) {
        throw "Backend test suite failed."
    }
} finally {
    Pop-Location
}

if (-not $SkipFrontend) {
    Write-Host "Running frontend build..."
    & (Join-Path $PSScriptRoot "build-frontend.ps1")
    if ($LASTEXITCODE -ne 0) {
        throw "Frontend build failed."
    }

    if (-not $SkipFrontendUnit) {
        Write-Host "Running frontend unit tests..."
        Invoke-FrontendNpm -Arguments @("run", "test:ci") -WorkingDirectory (Join-Path $repoRoot "frontend")
    }
}

Write-Host "Verification completed."
