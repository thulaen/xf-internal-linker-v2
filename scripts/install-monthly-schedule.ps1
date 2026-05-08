# install-monthly-schedule.ps1
#
# Run this ONCE (as Administrator) to register a Windows Scheduled Task that
# fires the monthly Top-50 link-suggestion job on the 1st of every month at
# 09:00 local time. The task simply invokes `run-monthly-top-50.ps1`, which
# in turn calls the Django management command inside the backend container.
#
# Belt-and-braces with the in-app sentient-schedule tracker: the tracker
# already catches up missed runs on Django boot + every 10 min, so the
# Windows scheduled task is optional. Install it if you want the job to
# fire even when Docker Desktop is not running (the task will start Docker
# Desktop indirectly via `docker compose exec` failing harmlessly until
# the user opens Docker Desktop the next morning).

#Requires -RunAsAdministrator

$taskName    = "XFLinker - Monthly Top-50 Link Suggestions"
$scriptPath  = (Resolve-Path "$PSScriptRoot\run-monthly-top-50.ps1").Path

$action      = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NonInteractive -ExecutionPolicy Bypass -File `"$scriptPath`""

# Run on the 1st of every month at 09:00 local time. The Celery Beat
# entry inside Django is at 09:00 UTC (cron `0 9 1 * *`); both fire,
# but the schedule_tracker's unique constraint on (task_name, scheduled_for)
# makes the second one a no-op.
$trigger     = New-ScheduledTaskTrigger -Monthly -DaysOfMonth 1 -At "09:00"

# Run as the current user (who has docker on PATH).
$principal   = New-ScheduledTaskPrincipal `
    -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) `
    -LogonType S4U `
    -RunLevel Highest

$settings    = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 30) `
    -StartWhenAvailable `
    -DontStopIfGoingOnBatteries

# Register (or update if it already exists).
if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
    Set-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings | Out-Null
    Write-Host "[task] Updated existing scheduled task '$taskName'." -ForegroundColor Cyan
} else {
    Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings | Out-Null
    Write-Host "[task] Registered scheduled task '$taskName'." -ForegroundColor Green
}

Write-Host "[task] The monthly Top-50 job will fire on the 1st of every month at 09:00."
Write-Host "[task] Reports land at docs/reports/monthly-suggestions-YYYY-MM.md."
Write-Host "[task] To run on demand, use: powershell -File scripts\run-monthly-top-50.ps1"
