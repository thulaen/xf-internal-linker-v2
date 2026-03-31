# XF Linker V2 — Register Startup Task (run this ONCE)
# Registers a Windows Task Scheduler job that runs start_sync_tunnel.ps1
# silently in the background every time you log in to Windows.

$taskName        = "XF Linker V2 - Docker Tunnel Watcher"
$taskDescription = "Watches for Docker Desktop. Starts tunnel when Docker opens, stops it when Docker closes."
$scriptPath      = Join-Path $PSScriptRoot "start_sync_tunnel.ps1"

# Check the script exists
if (-not (Test-Path $scriptPath)) {
    Write-Host "ERROR: start_sync_tunnel.ps1 not found at: $scriptPath" -ForegroundColor Red
    exit 1
}

# Build the action: run PowerShell minimised, no window, executing the watcher
$action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-WindowStyle Hidden -NonInteractive -ExecutionPolicy Bypass -File `"$scriptPath`""

# Trigger: at current user logon
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME

# Settings: allow it to run indefinitely, don't stop after N minutes
$settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit (New-TimeSpan -Hours 0) `
    -MultipleInstances IgnoreNew `
    -StartWhenAvailable

# Register (replace if it already exists)
Register-ScheduledTask `
    -TaskName    $taskName `
    -Description $taskDescription `
    -Action      $action `
    -Trigger     $trigger `
    -Settings    $settings `
    -RunLevel    Limited `
    -Force | Out-Null

Write-Host ""
Write-Host "Task registered successfully!" -ForegroundColor Green
Write-Host "Name   : $taskName" -ForegroundColor Cyan
Write-Host "Script : $scriptPath" -ForegroundColor Cyan
Write-Host ""
Write-Host "The watcher will now start silently every time you log in to Windows." -ForegroundColor Green
Write-Host "You do not need to run this script again." -ForegroundColor Green
Write-Host ""
Write-Host "To remove the task later, run:" -ForegroundColor Yellow
Write-Host "  Unregister-ScheduledTask -TaskName '$taskName' -Confirm:`$false" -ForegroundColor Yellow
