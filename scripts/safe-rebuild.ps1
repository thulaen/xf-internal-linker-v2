# safe-rebuild.ps1 — The one-button safe Docker rebuild.
#
# What this script does, in plain English:
#   1. Checks the pgdata volume exists. If it's missing the script
#      refuses to continue — rebuilding without it would create an
#      empty database.
#   2. Takes a fresh Postgres snapshot BEFORE shutting down. The
#      snapshot lives in backups/snapshot-YYYYMMDD-HHMMSS.dump and
#      can be restored later with `manage.py restore_db_snapshot
#      --latest --confirm`.
#   3. Records how many users you have right now (the baseline).
#   4. Stops the stack with `docker compose down` (NEVER `-v`).
#   5. Builds and starts the stack again with `--build`.
#   6. Cleans up dangling images with `docker system prune -f`.
#      Named volumes are NEVER touched.
#   7. Waits for the backend healthcheck to come back green.
#   8. Verifies your user count is still at least the baseline. If a
#      user vanished, the script stops red and tells you the exact
#      restore command.
#
# Use this script for every Docker rebuild from now on. Never run
# `docker compose down -v` manually — that's the only thing that
# can wipe pgdata.
#
# Usage:
#   .\scripts\safe-rebuild.ps1               # safe rebuild
#   .\scripts\safe-rebuild.ps1 -AutoRestore  # if a user vanished, also auto-run restore_db_snapshot --latest --confirm

param(
    [switch]$AutoRestore = $false,
    [int]$HealthcheckTimeoutSeconds = 180
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

$pgdataVolume = "xf-internal-linker-v2_pgdata"
$composeProjectDirName = Split-Path -Leaf $repoRoot
$backendContainer = "xf_linker_backend"

function Write-Step {
    param([int]$Num, [string]$Msg)
    Write-Host ""
    Write-Host ("[Step {0}/8] {1}" -f $Num, $Msg) -ForegroundColor Cyan
}

function Write-Ok    { param([string]$Msg) Write-Host ("  OK: {0}" -f $Msg)   -ForegroundColor Green }
function Write-Stop  { param([string]$Msg) Write-Host ("  STOP: {0}" -f $Msg) -ForegroundColor Red }
function Write-Note  { param([string]$Msg) Write-Host ("  Note: {0}" -f $Msg) -ForegroundColor Yellow }

function Invoke-DockerExecBackendJson {
    param([string[]]$ManagePyArgs)
    $allArgs = @("compose", "exec", "-T", "backend", "python", "manage.py") + $ManagePyArgs
    $output = & docker @allArgs 2>&1
    $exitCode = $LASTEXITCODE
    # The backend prints DEBUG/INFO log lines to stdout before our JSON.
    # Our management commands always emit JSON as the LAST stdout line.
    # Pull the last non-empty line.
    $lines = $output | ForEach-Object { $_ -as [string] } | Where-Object { $_ -and $_.Trim() }
    $jsonLine = if ($lines) { $lines[-1] } else { $null }
    [pscustomobject]@{
        ExitCode = $exitCode
        JsonLine = $jsonLine
        Raw      = $output
    }
}

# ─── Step 1: pgdata volume must exist ──────────────────────────────────
Write-Step 1 "Checking that the pgdata volume exists"

$null = & docker volume inspect $pgdataVolume 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Stop "The pgdata volume '$pgdataVolume' is missing."
    Write-Stop "Refusing to rebuild — this would create a brand-new empty database."
    Write-Note "If this is a fresh checkout, run: .\scripts\start.ps1"
    Write-Note "If you wiped the volume by accident, restore from a snapshot in backups/."
    exit 2
}
Write-Ok  "pgdata volume present."

# ─── Step 2: fresh snapshot BEFORE rebuild ─────────────────────────────
Write-Step 2 "Taking a fresh Postgres snapshot"

$snapshot = Invoke-DockerExecBackendJson -ManagePyArgs @("backup_db_now")
if ($snapshot.ExitCode -ne 0) {
    Write-Stop "Snapshot failed. Refusing to rebuild without a known-good backup."
    Write-Note "Output was:"
    $snapshot.Raw | Write-Host
    exit 3
}
Write-Ok  ("snapshot result: " + $snapshot.JsonLine)

# ─── Step 3: record baseline auth_user count ───────────────────────────
Write-Step 3 "Recording the baseline auth_user count"

$baselineRun = Invoke-DockerExecBackendJson -ManagePyArgs @("verify_users_present", "--min", "0")
if ($baselineRun.ExitCode -ne 0) {
    Write-Stop "Could not read the auth_user count. Aborting."
    $baselineRun.Raw | Write-Host
    exit 3
}
try {
    $baseline = (ConvertFrom-Json $baselineRun.JsonLine).auth_user_count
} catch {
    Write-Stop ("Could not parse JSON: " + $baselineRun.JsonLine)
    exit 3
}
Write-Ok ("baseline auth_user_count = " + $baseline)

# ─── Step 4: safe stop (NEVER -v) ──────────────────────────────────────
Write-Step 4 "Stopping the stack (docker compose down — never -v)"

& docker compose down
if ($LASTEXITCODE -ne 0) {
    Write-Stop "docker compose down failed."
    exit 4
}
Write-Ok "stack stopped (volumes intact)."

# ─── Step 5: build + up ────────────────────────────────────────────────
Write-Step 5 "Building images and starting the stack"

& docker compose --env-file .env up --build -d
if ($LASTEXITCODE -ne 0) {
    Write-Stop "docker compose up --build failed."
    exit 5
}
Write-Ok "stack built and started."

# ─── Step 6: prune dangling images (volumes untouched) ─────────────────
Write-Step 6 "Pruning dangling images / build cache (volumes are NOT touched)"

& docker system prune -f | Out-Host
Write-Ok "prune complete."

# ─── Step 7: wait for backend healthcheck ──────────────────────────────
Write-Step 7 ("Waiting for the backend healthcheck (max " + $HealthcheckTimeoutSeconds + "s)")

$start = Get-Date
$healthy = $false
while (((Get-Date) - $start).TotalSeconds -lt $HealthcheckTimeoutSeconds) {
    $state = & docker inspect --format='{{.State.Health.Status}}' $backendContainer 2>$null
    if ($LASTEXITCODE -eq 0 -and $state -eq "healthy") {
        $healthy = $true
        break
    }
    Start-Sleep -Seconds 3
}
if (-not $healthy) {
    Write-Stop ("Backend did not become healthy within " + $HealthcheckTimeoutSeconds + "s.")
    Write-Note "Container state: $state"
    Write-Note "Check logs: docker compose logs backend --tail 100"
    exit 7
}
Write-Ok "backend healthy."

# ─── Step 8: post-rebuild verification ─────────────────────────────────
Write-Step 8 "Verifying user count is still at least the baseline"

$postRun = Invoke-DockerExecBackendJson -ManagePyArgs @("verify_users_present", "--min", "$baseline")
if ($postRun.ExitCode -eq 0) {
    Write-Ok ("post-rebuild auth_user count: " + $postRun.JsonLine)
    Write-Host ""
    Write-Host "================================================================" -ForegroundColor Green
    Write-Host " GREEN: rebuild safe. auth_user count preserved at $baseline." -ForegroundColor Green
    Write-Host "================================================================" -ForegroundColor Green
    exit 0
}

# Data loss path.
Write-Host ""
Write-Host "================================================================" -ForegroundColor Red
Write-Host " RED: auth_user count dropped below the baseline of $baseline." -ForegroundColor Red
Write-Host "================================================================" -ForegroundColor Red
Write-Note "Latest output:"
$postRun.Raw | Write-Host

if ($AutoRestore) {
    Write-Note "AutoRestore was passed — restoring the latest snapshot."
    & docker compose exec -T backend python manage.py restore_db_snapshot --latest --confirm
    if ($LASTEXITCODE -eq 0) {
        Write-Ok "Restore completed. Re-verifying."
        $reRun = Invoke-DockerExecBackendJson -ManagePyArgs @("verify_users_present", "--min", "$baseline")
        if ($reRun.ExitCode -eq 0) {
            Write-Ok ("post-restore auth_user count: " + $reRun.JsonLine)
            exit 0
        }
        Write-Stop "Even after the restore the count is below baseline. Manual review required."
        exit 8
    } else {
        Write-Stop "Restore command failed."
        exit 8
    }
}

Write-Note "To restore the latest snapshot now, run:"
Write-Host  "  docker compose exec backend python manage.py restore_db_snapshot --latest --confirm" -ForegroundColor Yellow
Write-Note "Or re-run safe-rebuild with auto-restore:"
Write-Host  "  .\scripts\safe-rebuild.ps1 -AutoRestore" -ForegroundColor Yellow
exit 8
