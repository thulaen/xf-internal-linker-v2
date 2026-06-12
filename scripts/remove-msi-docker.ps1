param(
    [Parameter(Mandatory = $true)]
    [string]$ProofFile,

    [switch]$Execute,

    [string]$ConfirmPhrase = ""
)

$ErrorActionPreference = "Stop"
$ExpectedPhrase = "REMOVE MSI DOCKER AFTER VERIFIED CUTOVER"
$RepoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Verifier = Join-Path $RepoRoot "scripts\msi_docker_cutover.py"

python $Verifier verify-proof --proof-file $ProofFile
if ($LASTEXITCODE -ne 0) {
    throw "MSI Docker removal refused because the cutover proof is incomplete."
}

if (-not $Execute) {
    Write-Host "[MSI DOCKER REMOVAL: dry-run]"
    Write-Host "Would uninstall Docker Desktop, remove Docker contexts, remove Docker WSL data, and verify the docker command is unavailable."
    Write-Host "Run again with -Execute and the exact confirmation phrase after the proof file passes."
    exit 0
}

if ($ConfirmPhrase -ne $ExpectedPhrase) {
    throw "MSI Docker removal refused because the confirmation phrase did not match."
}

Write-Host "[MSI DOCKER REMOVAL: executing]"
Write-Host "Stopping Docker Desktop processes if present."
Get-Process "Docker Desktop", "com.docker.backend", "com.docker.service" -ErrorAction SilentlyContinue | Stop-Process -Force

Write-Host "Removing Docker Desktop application through winget if available."
if (Get-Command winget -ErrorAction SilentlyContinue) {
    winget uninstall --id Docker.DockerDesktop --silent --accept-source-agreements
}

Write-Host "Removing Docker WSL distributions if present."
$wslList = wsl --list --quiet 2>$null
foreach ($distro in $wslList) {
    if ($distro -in @("docker-desktop", "docker-desktop-data")) {
        wsl --unregister $distro
    }
}

Write-Host "Removing per-user Docker command contexts and settings."
$DockerConfig = Join-Path $env:USERPROFILE ".docker"
if (Test-Path $DockerConfig) {
    Remove-Item -LiteralPath $DockerConfig -Recurse -Force
}

Write-Host "Verifying docker is unavailable."
$dockerCommand = Get-Command docker -ErrorAction SilentlyContinue
if ($dockerCommand) {
    throw "Docker command is still available at $($dockerCommand.Source). Remove the remaining installation path."
}

Write-Host "[MSI DOCKER REMOVAL: complete]"
