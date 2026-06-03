param(
    [string]$InstallDir = "$env:LOCALAPPDATA\CodeQL",
    [switch]$AddToUserPath
)

$ErrorActionPreference = "Stop"

New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
$release = Invoke-RestMethod "https://api.github.com/repos/github/codeql-cli-binaries/releases/latest"
$asset = $release.assets | Where-Object { $_.name -eq "codeql-win64.zip" } | Select-Object -First 1
if (-not $asset) {
    throw "Could not find the official Windows CodeQL zip in the latest GitHub release."
}

$zipPath = Join-Path $env:TEMP "codeql-win64.zip"
Invoke-WebRequest -Uri $asset.browser_download_url -OutFile $zipPath
Expand-Archive -Path $zipPath -DestinationPath $InstallDir -Force

$bin = Join-Path $InstallDir "codeql\codeql.exe"
& $bin --version

if ($AddToUserPath) {
    $current = [Environment]::GetEnvironmentVariable("Path", "User")
    $codeqlDir = Split-Path $bin
    if ($current -notlike "*$codeqlDir*") {
        [Environment]::SetEnvironmentVariable("Path", "$current;$codeqlDir", "User")
    }
}
