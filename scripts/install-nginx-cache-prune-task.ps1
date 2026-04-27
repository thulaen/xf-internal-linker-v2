# install-nginx-cache-prune-task.ps1
#
# Run this ONCE (as Administrator) to register the Scheduled Task that
# trims /var/cache/nginx every fortnight. The task fires hourly during
# 11:00-23:00 local time; the underlying script gates real work behind
# a 14-day work-rate gate, so missed runs on travel days catch up
# automatically without churn on the live container.
#
# Behaviour summary:
#   * Trigger: daily at 11:00 with hourly repetition for 12 hours.
#   * StartWhenAvailable so a missed run is picked up after the laptop wakes.
#   * No DontStopIfGoingOnBatteries — pruning a docker container while on
#     battery is fine; the task does no real work most ticks anyway.
#   * Runs as the current user (Docker Desktop runs in user-space).
#   * Idempotent — re-running this installer updates the existing task.

#Requires -RunAsAdministrator

$ErrorActionPreference = 'Stop'

$taskName = 'XFLinker - Prune Nginx Cache'
$scriptPath = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot 'prune-nginx-cache.ps1')).Path

$action = New-ScheduledTaskAction `
    -Execute 'powershell.exe' `
    -Argument ('-NoProfile -NonInteractive -ExecutionPolicy Bypass -File "' + $scriptPath + '"')

# Hourly repetition during 11:00-23:00. PS 5.1 has no -RepetitionInterval
# on the daily trigger, so we use -Once + repetition.
$trigger = New-ScheduledTaskTrigger `
    -Once -At '11:00' `
    -RepetitionInterval (New-TimeSpan -Minutes 60) `
    -RepetitionDuration (New-TimeSpan -Hours 12)

$principal = New-ScheduledTaskPrincipal `
    -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) `
    -LogonType S4U `
    -RunLevel Highest

$settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 5) `
    -StartWhenAvailable `
    -DontStopIfGoingOnBatteries

if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
    Set-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings | Out-Null
    Write-Host "[task] Updated existing scheduled task '$taskName'." -ForegroundColor Cyan
} else {
    Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings | Out-Null
    Write-Host "[task] Registered scheduled task '$taskName'." -ForegroundColor Green
}

Write-Host "[task] Task fires hourly 11:00-23:00. Real pruning runs at most once every 14 days."
