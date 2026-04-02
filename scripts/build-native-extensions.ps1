param(
    [switch]$Clean
)

$ErrorActionPreference = "Stop"

. (Join-Path $PSScriptRoot "dev-tools.ps1")

$repoRoot = Get-RepoRoot
$extensionsDir = Join-Path $repoRoot "backend\extensions"
$python = Get-VenvPython

if ($Clean) {
    $buildDir = Join-Path $extensionsDir "build"
    if (Test-Path $buildDir) {
        Remove-Item -Recurse -Force $buildDir
    }
}

Write-Host "Building native extensions in place..."
Invoke-VsDevCommand -WorkingDirectory $extensionsDir -Command "`"$python`" setup.py build_ext --inplace"

Write-Host "Native extension build completed."
