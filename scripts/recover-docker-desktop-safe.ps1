# Safe Docker Desktop recovery for the local Windows workstation.
#
# This script never deletes Docker volumes, unregisters WSL distributions,
# resets the database, or runs Docker factory reset.

param(
    [switch]$AdminServiceRestart,
    [int]$TimeoutSeconds = 240
)

$ErrorActionPreference = "Continue"
$ForbiddenCommandText = @(
    "docker compose down -v",
    "docker volume prune",
    "docker volume rm",
    "wsl --unregister",
    "docker factory reset"
)

function Write-Step {
    param([string]$Message)
    $stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Write-Output "[$stamp] $Message"
}

function Test-DockerHealthy {
    docker ps -a > $null 2>&1
    $containersOk = $LASTEXITCODE -eq 0
    docker volume ls > $null 2>&1
    $volumesOk = $LASTEXITCODE -eq 0
    return ($containersOk -and $volumesOk)
}

function Wait-DockerHealthy {
    param([int]$TimeoutSeconds)
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        if (Test-DockerHealthy) {
            return $true
        }
        Start-Sleep -Seconds 10
    }
    return $false
}

function Stop-DockerDesktopSafely {
    $dockerCli = "C:\Program Files\Docker\Docker\DockerCli.exe"
    if (Test-Path -LiteralPath $dockerCli) {
        Write-Step "Asking Docker Desktop to shut down normally."
        & $dockerCli -Shutdown
        Start-Sleep -Seconds 10
    }
}

function Restart-DockerServiceIfRequested {
    if (-not $AdminServiceRestart) {
        return
    }
    Write-Step "Stopping Docker helper processes. This does not delete Docker data."
    Get-Process -Name "Docker Desktop", "com.docker.backend", "com.docker.build", "docker-sandbox" `
        -ErrorAction SilentlyContinue |
        Stop-Process -Force -ErrorAction Continue
    Start-Sleep -Seconds 5
    Write-Step "Restarting the Docker Desktop Windows service."
    Stop-Service -Name "com.docker.service" -Force -ErrorAction Continue
    Start-Sleep -Seconds 5
    Start-Service -Name "com.docker.service" -ErrorAction Continue
    Start-Sleep -Seconds 5
}

function Start-DockerDesktop {
    $dockerDesktop = "C:\Program Files\Docker\Docker\Docker Desktop.exe"
    if (-not (Test-Path -LiteralPath $dockerDesktop)) {
        Write-Step "Docker Desktop.exe was not found."
        return $false
    }
    Write-Step "Starting Docker Desktop."
    Start-Process -FilePath $dockerDesktop
    return $true
}

Write-Step "Starting safe Docker Desktop recovery."
Write-Step ("Forbidden commands for this script: " + ($ForbiddenCommandText -join "; "))

if (Test-DockerHealthy) {
    Write-Step "Docker already lists containers and volumes. No recovery needed."
    exit 0
}

Stop-DockerDesktopSafely

Write-Step "Terminating only the docker-desktop WSL distribution."
wsl --terminate docker-desktop

Write-Step "Resetting Docker socket folders if orphaned socket files exist."
powershell -ExecutionPolicy Bypass -File "$PSScriptRoot\reset-docker-sockets.ps1"

Restart-DockerServiceIfRequested

if (-not (Start-DockerDesktop)) {
    exit 1
}

if (Wait-DockerHealthy -TimeoutSeconds $TimeoutSeconds) {
    Write-Step "Docker is healthy. Containers and volumes can be listed."
    docker ps -a
    docker volume ls
    exit 0
}

Write-Step "Docker did not become healthy before the timeout."
Write-Step "If this was not run as Administrator, rerun it from Administrator PowerShell with -AdminServiceRestart."
exit 1
