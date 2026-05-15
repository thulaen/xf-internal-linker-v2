param(
    [switch]$AllowDowntime
)

$ErrorActionPreference = "Stop"

. (Join-Path $PSScriptRoot "dev-tools.ps1")

function Get-FreeGigabytes {
    $drive = [System.IO.DriveInfo]::GetDrives() |
        Where-Object { $_.Name -eq "C:\" } |
        Select-Object -First 1
    if ($null -eq $drive) {
        return $null
    }
    return [math]::Round($drive.AvailableFreeSpace / 1GB, 2)
}

function Invoke-SafeDockerPrune {
    $dockerAvailability = Get-DockerAvailability
    if ($dockerAvailability.Status -ne "ok") {
        Write-Host "Skipping Docker prune. $(Get-DockerUnavailableMessage -Availability $dockerAvailability)"
        return
    }

    $dockerSafe = Get-DockerSafeScript
    Write-Host "Pruning Docker disposable data without touching volumes..."
    & $dockerSafe system prune -f
    if ($LASTEXITCODE -ne 0) {
        throw "Docker system prune failed with exit code $LASTEXITCODE."
    }
}

function Enable-WslSparseDisksIfPresent {
    $wsl = Resolve-CommandLocation -Command "wsl"
    if (-not $wsl) {
        Write-Host "Skipping WSL sparse setting because wsl.exe was not found."
        return
    }

    $rawList = (& wsl --list --quiet 2>$null | Out-String)
    $distros = @(
        $rawList -split "(`r`n|`n|`r)" |
            ForEach-Object { $_.Trim([char]0x00).Trim() } |
            Where-Object { $_ -match "docker-desktop" }
    )
    if ($distros.Count -eq 0) {
        Write-Host "No Docker WSL distribution was listed, so sparse-disk auto-reclaim could not be enabled here."
        return
    }

    foreach ($distro in $distros) {
        Write-Host "Enabling sparse virtual disk auto-reclaim for WSL distribution '$distro'..."
        & wsl --manage $distro --set-sparse true
        if ($LASTEXITCODE -ne 0) {
            Write-Host "Could not enable sparse mode for '$distro'. Continuing without stopping Docker."
        }
    }
}

function Invoke-DowntimeCompactionIfAllowed {
    if (-not $AllowDowntime) {
        Write-Host "Skipping full virtual-disk compaction because it requires stopping Docker or WSL."
        Write-Host "Run this script with -AllowDowntime only when the app may be stopped safely."
        return
    }

    $compactScript = Join-Path $PSScriptRoot "..\docker_compact_vhd.ps1"
    if (-not (Test-Path $compactScript)) {
        Write-Host "Skipping full compaction because docker_compact_vhd.ps1 was not found."
        return
    }

    & powershell -ExecutionPolicy Bypass -File $compactScript
}

$before = Get-FreeGigabytes
if ($null -ne $before) {
    Write-Host "Windows free space before reclaim: $before GB"
}

Invoke-SafeDockerPrune
Enable-WslSparseDisksIfPresent
Invoke-DowntimeCompactionIfAllowed

$after = Get-FreeGigabytes
if ($null -ne $after) {
    Write-Host "Windows free space after reclaim attempt: $after GB"
}

Write-Host "Docker Windows-space reclaim finished."
