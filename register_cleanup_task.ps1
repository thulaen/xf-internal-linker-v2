# XF Linker V2 - Register Docker Maintenance Tasks (run ONCE)
# Schedules safe Docker cleanup every 2 days plus a backup login cleanup.

$cleanupTaskName = "XF Linker V2 - Docker Cleanup Every 2 Days"
$compactTaskName = "XF Linker V2 - Docker Disk Compaction"
$backupTaskName = "XF Linker V2 - Backup Cleanup on Login"
$cleanupScriptPath = Join-Path $PSScriptRoot "docker_cleanup.ps1"
$compactScriptPath = Join-Path $PSScriptRoot "docker_compact_vhd.ps1"

if (-not (Test-Path $cleanupScriptPath)) {
    Write-Host "ERROR: docker_cleanup.ps1 not found at: $cleanupScriptPath" -ForegroundColor Red
    exit 1
}

if (-not (Test-Path $compactScriptPath)) {
    Write-Host "ERROR: docker_compact_vhd.ps1 not found at: $compactScriptPath" -ForegroundColor Red
    exit 1
}

$cleanupArgument = '-WindowStyle Hidden -NonInteractive -ExecutionPolicy Bypass -File "' + $cleanupScriptPath + '"'
$compactArgument = '-WindowStyle Hidden -NonInteractive -ExecutionPolicy Bypass -File "' + $compactScriptPath + '"'

$cleanupAction = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument $cleanupArgument

$compactAction = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument $compactArgument

$backupAction = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument $cleanupArgument

$cleanupTrigger = New-ScheduledTaskTrigger -Daily -DaysInterval 2 -At 9:00am

$compactTrigger = New-ScheduledTaskTrigger -Daily -DaysInterval 2 -At 10:00am

$backupTrigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME

$cleanupSettings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 10) `
    -StartWhenAvailable

$compactSettings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 20) `
    -StartWhenAvailable

$backupSettings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 10) `
    -StartWhenAvailable

Register-ScheduledTask `
    -TaskName    $cleanupTaskName `
    -Description "Removes old Docker build cache and dangling images every 2 days. Safe - never touches volumes." `
    -Action      $cleanupAction `
    -Trigger     $cleanupTrigger `
    -Settings    $cleanupSettings `
    -RunLevel    Limited `
    -Force | Out-Null

Register-ScheduledTask `
    -TaskName    $compactTaskName `
    -Description "Compacts Docker's virtual disk every 2 days, but only if no containers are running. Safe - never touches volumes." `
    -Action      $compactAction `
    -Trigger     $compactTrigger `
    -Settings    $compactSettings `
    -RunLevel    Limited `
    -Force | Out-Null

Register-ScheduledTask `
    -TaskName    $backupTaskName `
    -Description "Backup cleanup on login. Safe Docker cleanup if the daytime schedule was missed." `
    -Action      $backupAction `
    -Trigger     $backupTrigger `
    -Settings    $backupSettings `
    -RunLevel    Limited `
    -Force | Out-Null

Write-Host ""
Write-Host "Done! Docker maintenance tasks registered." -ForegroundColor Green
Write-Host "Docker build cache cleanup will run every 2 days at 9:00 AM." -ForegroundColor Cyan
Write-Host "Docker disk compaction will run every 2 days at 10:00 AM, but only when no containers are active." -ForegroundColor Cyan
Write-Host "Backup cleanup on login is also registered in case the daytime schedule was missed." -ForegroundColor Cyan
