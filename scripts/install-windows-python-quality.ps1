<#
.SYNOPSIS
    Fill Windows .venv Python quality gaps.
    Installs missing quality packages only -- skips already-installed ones.

.DESCRIPTION
    Uses the repo .venv at .venv\Scripts\python.exe.
    Checks each package with pip show before installing.
    Runs a smoke verification block after install.

.NOTES
    Packages that belong in the quality stage Docker image are NOT installed
    here (those run on Mint via backend-quality). This script fills only the
    packages needed for Windows host-side quality runs.
#>
[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python    = Join-Path $ScriptDir "..\\.venv\\Scripts\\python.exe"
if (-not (Test-Path $Python)) {
    Write-Error ".venv not found at expected location. Run: python -m venv .venv && pip install -r backend/requirements.txt"
    exit 1
}

$QualityPackages = @(
    "mutmut",
    "safety",
    "pylint",
    "hypothesis",
    "pytest-cov",
    "pytest-django",
    "pytest-asyncio",
    "pytest-randomly",
    "pytest-benchmark"
)

Write-Host ""
Write-Host "Filling Windows .venv Python quality gaps"
Write-Host ("-" * 50)

$Installed = 0
$Skipped   = 0

foreach ($pkg in $QualityPackages) {
    $found = $false
    try {
        $null = & $Python -m pip show $pkg 2>&1
        $found = ($LASTEXITCODE -eq 0)
    } catch { $found = $false }

    if ($found) {
        Write-Host "  SKIP     $pkg -- already installed"
        $Skipped++
    } else {
        Write-Host "  INSTALL  $pkg"
        try {
            & $Python -m pip install --no-cache-dir $pkg --quiet
        } catch {
            Write-Error "Failed to install $($pkg)"; exit 1
        }
        $Installed++
    }
}

Write-Host ("-" * 50)
Write-Host "Installed: $Installed   Skipped (already present): $Skipped"

Write-Host ""
Write-Host "Smoke verification:"
& $Python -m pytest --version 2>&1 | Select-Object -First 1 | Write-Host
& $Python -m ruff --version 2>&1 | Select-Object -First 1 | Write-Host
& $Python -c "import mutmut; print('mutmut ok')" 2>&1 | Write-Host
& $Python -m pip list 2>&1 | Select-String "pytest|ruff|mutmut|bandit|pylint|safety|hypothesis" | Write-Host

Write-Host ""
Write-Host "Python quality packages verified."
