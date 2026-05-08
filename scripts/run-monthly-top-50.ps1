# run-monthly-top-50.ps1
#
# Tiny wrapper around the Django management command that produces the
# monthly Top-50 link-suggestions report. Used by the Windows Scheduled
# Task installed via `install-monthly-schedule.ps1`, AND can be invoked
# manually whenever the operator wants an off-cycle run.
#
# Strategy auto-detection happens INSIDE the management command (see
# `apps.pipeline.services.strategy_router.pick_strategy`), so this wrapper
# stays trivial: it just shells `docker compose exec` so the run lands
# inside the container that already has Django + the picker + DB access.
#
# Usage:
#   powershell -File scripts\run-monthly-top-50.ps1                # current month, auto strategy
#   powershell -File scripts\run-monthly-top-50.ps1 -Month 2026-05 # specific month
#   powershell -File scripts\run-monthly-top-50.ps1 -Strategy python

param(
    [string]$Month = "",
    [ValidateSet("auto", "python", "claude_code")]
    [string]$Strategy = "auto"
)

$ErrorActionPreference = "Stop"

$RepoRoot = Resolve-Path "$PSScriptRoot\.."
Set-Location $RepoRoot

# Default to the current UTC month (matches the cron slot the scheduled task fires in).
if (-not $Month) {
    $Month = (Get-Date).ToUniversalTime().ToString("yyyy-MM")
}

Write-Host "[monthly-top-50] month=$Month strategy=$Strategy" -ForegroundColor Cyan

# `docker compose exec -T` disables TTY allocation so the script runs unattended.
$cmd = @(
    "compose", "exec", "-T", "backend",
    "python", "manage.py", "run_monthly_top_50",
    "--month=$Month",
    "--strategy=$Strategy"
)

& docker @cmd
$code = $LASTEXITCODE

if ($code -eq 0) {
    Write-Host "[monthly-top-50] done — see docs/reports/monthly-suggestions-$Month.md" -ForegroundColor Green
} else {
    Write-Host "[monthly-top-50] failed with exit code $code" -ForegroundColor Red
}

exit $code
