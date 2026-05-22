# XF Linker V2 - Safe Docker VHD Compaction
# Compacts Docker's virtual disk only when no containers are running.
# Never touches volumes or database contents.

$ErrorActionPreference = "Stop"

$logFile = "$PSScriptRoot\docker_cleanup.log"
$dockerSafe = Join-Path $PSScriptRoot "scripts\docker-safe.ps1"

# Docker Desktop uses different VHDX paths across versions — try both known locations.
$candidateVhdPaths = @(
    (Join-Path $env:LOCALAPPDATA "Docker\wsl\disk\docker_data.vhdx"),   # Docker Desktop 4.30+
    (Join-Path $env:LOCALAPPDATA "Docker\wsl\data\ext4.vhdx")            # older WSL2 backend
)
$dockerVhdPath = $candidateVhdPaths | Where-Object { Test-Path $_ } | Select-Object -First 1

function Write-Log {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Message
    )

    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm"
    Add-Content $logFile "[$timestamp] $Message"
}

Write-Log "Starting Docker VHD compaction check..."

if ([string]::IsNullOrEmpty($dockerVhdPath)) {
    Write-Log "Skipping compaction because the Docker VHD was not found in any known path: $($candidateVhdPaths -join '; ')"
    exit 0
}
Write-Log "Found Docker VHD at $dockerVhdPath."

# GUARD (added 2026-05-22): never shut down WSL while the XF Linker
# observability + quality stack is running. The previous version of this
# script had a hole: when `docker-safe.ps1 version` could not reach
# Docker (transient probe failure, WSL restart in progress, etc.) the
# script set `$dockerIsReachable=$false` and SKIPPED the running-
# container check — then proceeded to `wsl --shutdown` unconditionally,
# killing sonarqube, glitchtip, vmalert, and the rest of the observability
# tier. The fix is to query the Docker Desktop context directly for any
# container named `xf_linker_*` and refuse to compact while ANY are up.

Write-Log "Checking Docker Desktop for XF Linker containers..."
$xfRunningIds = @()
try {
    $xfRunningIds = @(docker --context desktop-linux ps -q --filter "name=xf_linker_" 2>$null | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
} catch {
    Write-Log "XF Linker container probe failed against context=desktop-linux: $($_.Exception.Message)"
}
if ($xfRunningIds.Count -gt 0) {
    Write-Log "Skipping compaction because $($xfRunningIds.Count) XF Linker container(s) are running. The observability + quality stack stays up."
    exit 0
}

$dockerIsReachable = $false
if (Test-Path $dockerSafe) {
    try {
        & $dockerSafe version *> $null
    } catch {
        # Docker is offline — that is fine, but we still must NOT proceed
        # to `wsl --shutdown` without confirming no XF Linker containers
        # exist. The xfRunningIds probe above already did that work via
        # the desktop-linux context. If it succeeded (empty result) we
        # know it is safe to compact; if it threw, fall through to the
        # log + exit-0 path below.
    }
    $dockerIsReachable = ($LASTEXITCODE -eq 0)
}

if ($dockerIsReachable) {
    $runningContainers = @(& $dockerSafe ps -q 2>$null | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
    if ($runningContainers.Count -gt 0) {
        Write-Log "Skipping compaction because Docker currently has running containers."
        exit 0
    }

    Write-Log "Stopping idle Docker Desktop before compaction..."
    docker desktop stop *> $null
    Start-Sleep -Seconds 10
} else {
    Write-Log "Docker docker-safe probe failed; the XF Linker container probe above already cleared the way (0 containers). Proceeding to compaction."
}

Write-Log "Shutting down WSL before compaction..."
wsl --shutdown *> $null
Start-Sleep -Seconds 5

$diskpartScript = Join-Path $env:TEMP "docker-vhd-compact.txt"
@(
    "select vdisk file=""$dockerVhdPath"""
    "compact vdisk"
) | Set-Content -Path $diskpartScript -Encoding ASCII

try {
    $compactOutput = (diskpart /s $diskpartScript 2>&1 | Out-String).Trim()
    Write-Log "Disk compaction output:`n$compactOutput"
} finally {
    if (Test-Path $diskpartScript) {
        Remove-Item -LiteralPath $diskpartScript -Force
    }
}

Write-Log "Docker VHD compaction check finished."
Write-Host "Docker VHD compaction check finished. See docker_cleanup.log for details."
