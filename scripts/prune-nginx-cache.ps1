# prune-nginx-cache.ps1
#
# Trims old files under /var/cache/nginx inside the running nginx container.
# Safe-by-construction:
#   * Hard-coded path (/var/cache/nginx) — never touches pgdata, redis-data,
#     media_files, staticfiles, frontend_dist, or anything in the repo.
#   * 14-day file-age threshold; empty directories are deleted afterwards.
#   * Time gate: only does work between 11:00 and 23:00 local time.
#   * Work-rate gate: skips unless the previous successful prune was >= 14
#     days ago (state lives outside the repo, in %LOCALAPPDATA%).
#   * Mutex gate: a second concurrent run exits silently with code 0.
#
# The Scheduled Task fires hourly during the window so a missed run on a
# travel day catches up automatically; the work-rate gate keeps the actual
# pruning on a real fortnightly cadence.
#
# Usage:
#   powershell.exe -NoProfile -ExecutionPolicy Bypass -File prune-nginx-cache.ps1
#   powershell.exe -NoProfile -File prune-nginx-cache.ps1 -Force   (skip both gates)

param(
    [switch]$Force
)

$ErrorActionPreference = 'Stop'

# ── Mutex gate ──────────────────────────────────────────────────────
# Global\ ensures the mutex is visible across user sessions; needed because
# the Scheduled Task runs as the current user but Docker Desktop processes
# may run with a slightly different security context.
$mutexName = 'Global\XFLinker-PruneNginxCache'
$mutex = New-Object System.Threading.Mutex($false, $mutexName)
$haveMutex = $false
try {
    try {
        $haveMutex = $mutex.WaitOne(0)
    } catch [System.Threading.AbandonedMutexException] {
        # Previous holder died without releasing — we own it now.
        $haveMutex = $true
    }
    if (-not $haveMutex) {
        Write-Host '[nginx-prune] Another instance is running. Exiting.' -ForegroundColor DarkGray
        exit 0
    }

    # ── Time-of-day gate ────────────────────────────────────────────
    $now = Get-Date
    $hour = $now.Hour
    if (-not $Force) {
        if ($hour -lt 11 -or $hour -ge 23) {
            Write-Host "[nginx-prune] Outside the 11:00-23:00 window (hour=$hour). Exiting." -ForegroundColor DarkGray
            exit 0
        }
    }

    # ── Work-rate gate (state outside repo) ─────────────────────────
    $stateDir = Join-Path $env:LOCALAPPDATA 'XFLinker'
    if (-not (Test-Path -LiteralPath $stateDir)) {
        New-Item -ItemType Directory -Path $stateDir -Force | Out-Null
    }
    $stateFile = Join-Path $stateDir 'nginx-prune-state.json'

    $lastSuccessEpoch = 0
    if (Test-Path -LiteralPath $stateFile) {
        try {
            $state = Get-Content -LiteralPath $stateFile -Raw | ConvertFrom-Json
            if ($state -and $state.lastSuccess) {
                $lastSuccessEpoch = [int64]$state.lastSuccess
            }
        } catch {
            # Corrupt state file — treat as never run.
            $lastSuccessEpoch = 0
        }
    }

    $epochOrigin = [DateTime]::SpecifyKind('1970-01-01', [DateTimeKind]::Utc)
    $nowEpoch = [int64]([DateTime]::UtcNow - $epochOrigin).TotalSeconds
    $secondsSinceLast = $nowEpoch - $lastSuccessEpoch
    $fourteenDays = 14 * 24 * 60 * 60

    if (-not $Force) {
        if ($secondsSinceLast -lt $fourteenDays) {
            $daysAgo = [math]::Round($secondsSinceLast / 86400.0, 1)
            Write-Host "[nginx-prune] Last successful prune was $daysAgo day(s) ago. Skipping." -ForegroundColor DarkGray
            exit 0
        }
    }

    # ── Probe: is the nginx container actually running? ─────────────
    $repoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
    $probe = & docker compose --project-directory $repoRoot ps --status running --services 2>$null
    if ($LASTEXITCODE -ne 0 -or -not ($probe -match '(?m)^nginx$')) {
        Write-Host '[nginx-prune] nginx container is not running. Exiting.' -ForegroundColor DarkGray
        exit 0
    }

    # ── Do the prune. Hard-coded container path; never touches host volumes. ─
    Write-Host '[nginx-prune] Pruning /var/cache/nginx files older than 14 days...' -ForegroundColor Cyan
    $shellCmd = 'find /var/cache/nginx -type f -mtime +14 -delete 2>/dev/null; find /var/cache/nginx -mindepth 1 -type d -empty -delete 2>/dev/null; echo done'
    & docker compose --project-directory $repoRoot exec -T nginx sh -c $shellCmd | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-Warning '[nginx-prune] docker exec returned non-zero. Not updating last-success state.'
        exit 1
    }

    # ── Persist last-success ────────────────────────────────────────
    $newState = @{ lastSuccess = $nowEpoch }
    $newState | ConvertTo-Json -Compress | Out-File -LiteralPath $stateFile -Encoding utf8 -Force
    Write-Host '[nginx-prune] Done. Last-success timestamp recorded.' -ForegroundColor Green
}
finally {
    if ($haveMutex) {
        try { $mutex.ReleaseMutex() } catch { }
    }
    $mutex.Dispose()
}
