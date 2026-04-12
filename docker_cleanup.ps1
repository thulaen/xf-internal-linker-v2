# XF Linker V2 - Safe Docker Cleanup
# Removes unused build cache and dangling images only.
# Never touches volumes (your database and media files are safe).

$ErrorActionPreference = "Stop"

$logFile = "$PSScriptRoot\docker_cleanup.log"
$dockerSafe = Join-Path $PSScriptRoot "scripts\docker-safe.ps1"

function Write-Log {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Message
    )

    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm"
    Add-Content $logFile "[$timestamp] $Message"
}

function Wait-ForDockerDesktop {
    param(
        [int]$TimeoutSeconds = 600,
        [int]$PollSeconds = 30
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        & $dockerSafe version *> $null
        if ($LASTEXITCODE -eq 0) {
            return $true
        }

        Start-Sleep -Seconds $PollSeconds
    }

    return $false
}

Write-Log "Starting Docker cleanup..."

if (-not (Test-Path $dockerSafe)) {
    Write-Log "Skipping cleanup because scripts\\docker-safe.ps1 was not found."
    exit 0
}

if (-not (Wait-ForDockerDesktop)) {
    Write-Log "Skipping cleanup because Docker Desktop was not ready within 10 minutes."
    Write-Host "Docker cleanup skipped because Docker Desktop is not ready yet."
    exit 0
}

# Remove all unused build cache (safe to delete, but may slow the next rebuild).
$result1 = (& $dockerSafe builder prune -a -f 2>&1 | Out-String).Trim()
Write-Log "Builder prune (all unused build cache): $result1"

# Remove dangling images (old leftover copies from rebuilds)
$result2 = (& $dockerSafe image prune -f 2>&1 | Out-String).Trim()
Write-Log "Image prune: $result2"

# Show current state
$df = (& $dockerSafe system df 2>&1 | Out-String).Trim()
Write-Log "Disk usage after cleanup:`n$df"
Write-Log "Done."

Write-Host "Docker cleanup complete. See docker_cleanup.log for details."
