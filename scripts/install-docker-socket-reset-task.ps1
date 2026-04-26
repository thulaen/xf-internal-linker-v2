# install-docker-socket-reset-task.ps1
# Registers a Windows Scheduled Task that runs reset-docker-sockets.ps1
# at every user logon, so Docker Desktop boot is always clean.
#
# Run this once. It does not require admin - it creates a USER-level
# Scheduled Task. To remove it later, run:
#   Unregister-ScheduledTask -TaskName "XFLinker-ResetDockerSockets" -Confirm:$false
#
# Author: 2026-04-26
# ---------------------------------------------------------------------

$ErrorActionPreference = "Stop"

$taskName       = "XFLinker-ResetDockerSockets"
$taskDescription = "Wipe orphan AF_UNIX socket reparse points before Docker Desktop launches. Prevents the 'Docker Desktop spinning forever' bug after laptop reboots."
$resetScript    = Join-Path $PSScriptRoot "reset-docker-sockets.ps1"

if (-not (Test-Path -LiteralPath $resetScript)) {
    throw "reset-docker-sockets.ps1 not found at: $resetScript. Run this script from the repo's scripts/ directory."
}

# Build the action: run powershell with -NoProfile -ExecutionPolicy
# Bypass and our cleanup script. Hidden window so the user never sees
# a console flash at logon.
$psExe = Join-Path $env:WINDIR "System32\WindowsPowerShell\v1.0\powershell.exe"
$action = New-ScheduledTaskAction `
    -Execute $psExe `
    -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$resetScript`""

# Trigger: every time the current user logs on.
$trigger = New-ScheduledTaskTrigger -AtLogOn -User "$env:USERDOMAIN\$env:USERNAME"

# Settings: run quickly, do not retry, do not start if on battery is fine
# (the cleanup is cheap), allow the task to be killed if it hangs.
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 2) `
    -MultipleInstances IgnoreNew

# Principal: run as the current interactive user, NOT SYSTEM. The
# orphan files live under the user's %LOCALAPPDATA%, so we need user
# context to access them.
$principal = New-ScheduledTaskPrincipal `
    -UserId "$env:USERDOMAIN\$env:USERNAME" `
    -LogonType Interactive `
    -RunLevel Limited

# If the task already exists, replace it (idempotent install).
$existing = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if ($existing) {
    Write-Output "Task '$taskName' already exists - replacing."
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
}

Register-ScheduledTask `
    -TaskName $taskName `
    -Description $taskDescription `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal | Out-Null

Write-Output "Registered scheduled task: $taskName"
Write-Output "It will run at every logon and clean Docker's orphan socket dirs."
Write-Output ""
Write-Output "To verify: Get-ScheduledTask -TaskName $taskName"
Write-Output "To remove: Unregister-ScheduledTask -TaskName $taskName -Confirm:`$false"
Write-Output "To run now: Start-ScheduledTask -TaskName $taskName"
