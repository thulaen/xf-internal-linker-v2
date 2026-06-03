# install-agent-progress-task.ps1
#
# Run this ONCE to register the "XFLinker - Agent Progress" Scheduled Task.
# Every 10 minutes it refreshes audit/agent_progress_latest.txt (the shared
# cross-agent progress line) and pops a desktop alert if something has stalled.
# This is what makes the 10-minute pulse work for EVERY agent — and even when
# no agent is replying — instead of only when one happens to be typing.
#
# Behaviour summary:
#   * Trigger: once at install time, then repeats every 10 minutes indefinitely.
#   * User-level (no admin needed): runs as the current user, interactive logon,
#     limited privileges — it only reads git/docker and writes one file + a balloon.
#   * StartWhenAvailable so a missed tick is picked up after the laptop wakes.
#   * Idempotent — re-running this installer updates the existing task.
#
# Uninstall:  Unregister-ScheduledTask -TaskName 'XFLinker - Agent Progress' -Confirm:$false

$ErrorActionPreference = 'Stop'

$taskName = 'XFLinker - Agent Progress'
$scriptPath = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot 'run-agent-progress.ps1')).Path

$action = New-ScheduledTaskAction `
    -Execute 'powershell.exe' `
    -Argument ('-NoProfile -NonInteractive -ExecutionPolicy Bypass -File "' + $scriptPath + '"')

# PS 5.1 has no -RepetitionInterval on a recurring trigger, so use -Once +
# repetition for an effectively indefinite 10-minute cadence.
$trigger = New-ScheduledTaskTrigger `
    -Once -At (Get-Date) `
    -RepetitionInterval (New-TimeSpan -Minutes 10) `
    -RepetitionDuration (New-TimeSpan -Days 3650)

$principal = New-ScheduledTaskPrincipal `
    -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) `
    -LogonType Interactive `
    -RunLevel Limited

$settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 2) `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries

if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
    Set-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings | Out-Null
    Write-Host "[task] Updated '$taskName' — refreshes the progress pulse every 10 minutes." -ForegroundColor Cyan
} else {
    Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings | Out-Null
    Write-Host "[task] Registered '$taskName' — refreshes the progress pulse every 10 minutes." -ForegroundColor Green
}

Write-Host "[task] Every agent should read audit/agent_progress_latest.txt at the start of a reply."
