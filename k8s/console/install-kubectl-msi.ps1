param(
    [switch]$Execute,
    [string]$InstallDir = "C:\Tools\kubectl"
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$Version = (Get-Content -LiteralPath (Join-Path $PSScriptRoot "kubectl-version.lock")).Trim()
$Target = Join-Path $InstallDir "kubectl.exe"
$Url = "https://dl.k8s.io/release/$Version/bin/windows/amd64/kubectl.exe"

Write-Host "[KUBECTL MSI INSTALL]"
Write-Host "Version: $Version"
Write-Host "Target: $Target"

if (-not $Execute) {
    Write-Host "Dry run only. Add -Execute to download kubectl."
    exit 0
}

New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
Invoke-WebRequest -Uri $Url -OutFile $Target
Write-Host "Downloaded kubectl to $Target"
