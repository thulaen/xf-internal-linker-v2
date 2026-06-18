# run-monthly-top-50.ps1
#
# Tiny wrapper around the Django management command that produces the
# monthly Top-50 link-suggestions report. Used by the Windows Scheduled
# Task installed via `install-monthly-schedule.ps1`, AND can be invoked
# manually whenever the operator wants an off-cycle run.
#
# Strategy auto-detection happens inside the management command. This wrapper
# runs it through the Kubernetes backend pod.
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

python scripts/backend_manage.py run_monthly_top_50 "--month=$Month" "--strategy=$Strategy"
$code = $LASTEXITCODE

if ($code -eq 0) {
    Write-Host "[monthly-top-50] done — see docs/reports/monthly-suggestions-$Month.md" -ForegroundColor Green
} else {
    Write-Host "[monthly-top-50] failed with exit code $code" -ForegroundColor Red
}

exit $code
