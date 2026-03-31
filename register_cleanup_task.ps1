# XF Linker V2 - Register Docker Cleanup Task (run ONCE)
# Schedules docker_cleanup.ps1 to run silently every time you log in to Windows.

$taskName   = "XF Linker V2 - Docker Cleanup on Startup"
$scriptPath = Join-Path $PSScriptRoot "docker_cleanup.ps1"

if (-not (Test-Path $scriptPath)) {
    Write-Host "ERROR: docker_cleanup.ps1 not found at: $scriptPath" -ForegroundColor Red
    exit 1
}

$argument = '-WindowStyle Hidden -NonInteractive -ExecutionPolicy Bypass -File "' + $scriptPath + '"'

$action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument $argument

$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME

$settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 10) `
    -StartWhenAvailable

Register-ScheduledTask `
    -TaskName    $taskName `
    -Description "Removes Docker build cache and dangling images on every login. Safe - never touches volumes." `
    -Action      $action `
    -Trigger     $trigger `
    -Settings    $settings `
    -RunLevel    Limited `
    -Force | Out-Null

Write-Host ""
Write-Host "Done! Cleanup task registered." -ForegroundColor Green
Write-Host "Docker junk will be pruned silently every time you log in to Windows." -ForegroundColor Cyan
