# reset-docker-sockets.ps1
# Permanent fix for "Docker Desktop spins forever after every reboot."
#
# Why this exists
# ---------------
# Docker Desktop on Windows creates Unix-domain socket files under
# %LOCALAPPDATA% for its sub-services (Docker AI / Inference Manager,
# Secrets Engine, BuildKit, gRPC API gateway, etc). Windows implements
# AF_UNIX sockets via NTFS reparse points. When Docker Desktop is shut
# down uncleanly - Windows reboot, force-quit, hard power-off - those
# reparse points are left orphaned. On next startup, Docker tries to
# `remove(path)` before re-binding the socket, Windows refuses because
# the reparse target is invalid ("the file cannot be accessed by the
# system"), and Docker Desktop hangs on the "Starting..." spinner forever.
#
# The fix: before Docker Desktop starts, rename any directory that
# might hold an orphan reparse point. Docker recreates them clean.
#
# This script is idempotent - if the dirs are clean, it does nothing.
# It runs at every user logon via a Windows scheduled task installed by
# scripts\install-docker-socket-reset-task.ps1.
#
# Author: 2026-04-26
# ---------------------------------------------------------------------

$ErrorActionPreference = "Continue"
$logFile = Join-Path $env:LOCALAPPDATA "Docker\reset-docker-sockets.log"

function Write-Log {
    param([string]$Message)
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $line = "[$ts] $Message"
    Write-Output $line
    try {
        $logDir = Split-Path -Parent $logFile
        if (-not (Test-Path $logDir)) {
            New-Item -ItemType Directory -Force -Path $logDir | Out-Null
        }
        Add-Content -LiteralPath $logFile -Value $line -ErrorAction SilentlyContinue
    } catch {
        # Logging is best-effort; never fail the cleanup over a log write.
    }
}

# Directories Docker Desktop creates and that have been observed to
# contain orphan reparse points. Add new paths here if Docker Desktop
# adds new sub-services in future versions.
$candidateDirs = @(
    (Join-Path $env:LOCALAPPDATA "Docker\run"),
    (Join-Path $env:LOCALAPPDATA "docker-secrets-engine")
)

Write-Log "reset-docker-sockets starting"

# Helper: does a directory contain at least one orphan reparse point
# that Windows cannot read? If we cannot enumerate, treat as "yes" and
# rename to be safe.
function Test-HasOrphanReparsePoint {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) { return $false }
    try {
        $items = Get-ChildItem -LiteralPath $Path -Force -ErrorAction Stop
        foreach ($item in $items) {
            if ($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) {
                # Try to access the reparse target. If this fails with
                # "cannot be accessed by the system", it is orphaned.
                try {
                    $null = fsutil reparsepoint query $item.FullName 2>&1
                    if ($LASTEXITCODE -ne 0) { return $true }
                } catch {
                    return $true
                }
            }
        }
        return $false
    } catch {
        # If we cannot even list the directory, assume the worst.
        return $true
    }
}

$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$renamedAny = $false

foreach ($dir in $candidateDirs) {
    if (-not (Test-Path -LiteralPath $dir)) {
        Write-Log "skip (does not exist): $dir"
        continue
    }
    if (-not (Test-HasOrphanReparsePoint -Path $dir)) {
        Write-Log "clean (no orphan reparse points): $dir"
        continue
    }

    $stashName = (Split-Path -Leaf $dir) + ".orphaned-$timestamp"
    $stashPath = Join-Path (Split-Path -Parent $dir) $stashName
    try {
        Rename-Item -LiteralPath $dir -NewName $stashName -ErrorAction Stop
        Write-Log "renamed orphan dir: $dir -> $stashPath"
        $renamedAny = $true
    } catch {
        Write-Log ("rename FAILED for " + $dir + ": " + $_.Exception.Message)
    }
}

# Old archive directories - removed only when the file system actually
# lets us. Reparse-point orphans cannot be deleted by Windows tools at
# all, so we accept that these dirs may accumulate. They are harmless
# once renamed out of Docker's expected paths and total a few KB each.
# We do prune dirs older than 90 days that *can* be removed.
$dockerRoot = Join-Path $env:LOCALAPPDATA "Docker"
if (Test-Path -LiteralPath $dockerRoot) {
    $cutoff = (Get-Date).AddDays(-90)
    Get-ChildItem -LiteralPath $dockerRoot -Directory -ErrorAction SilentlyContinue |
        Where-Object {
            ($_.Name -like "run.orphaned-*" -or $_.Name -like "run.broken-*") -and
            $_.LastWriteTime -lt $cutoff
        } |
        ForEach-Object {
            try {
                Remove-Item -LiteralPath $_.FullName -Recurse -Force -ErrorAction Stop
                Write-Log "pruned old archive: $($_.FullName)"
            } catch {
                # Reparse-point orphans inside resist deletion. That is fine.
                Write-Log "could not prune (likely orphan reparse points): $($_.FullName)"
            }
        }
}

if ($renamedAny) {
    Write-Log "reset-docker-sockets finished - orphan dirs renamed; Docker Desktop will recreate them on next launch"
} else {
    Write-Log "reset-docker-sockets finished - nothing to do"
}
