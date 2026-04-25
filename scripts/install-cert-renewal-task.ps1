# install-cert-renewal-task.ps1
#
# Run this ONCE (as Administrator) to register a Windows Scheduled Task that
# checks the localhost cert monthly and auto-renews it 60 days before expiry.

#Requires -RunAsAdministrator

$taskName    = "XFLinker - Renew Dev SSL Cert"
$scriptPath  = (Resolve-Path "$PSScriptRoot\renew-dev-cert.ps1").Path
$action      = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NonInteractive -ExecutionPolicy Bypass -File `"$scriptPath`""

# Run on the 1st of every month at 09:00.
$trigger     = New-ScheduledTaskTrigger -Monthly -DaysOfMonth 1 -At "09:00"

# Run as the current user (who has docker + mkcert on PATH).
$principal   = New-ScheduledTaskPrincipal `
    -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) `
    -LogonType S4U `
    -RunLevel Highest

$settings    = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 5) `
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

Write-Host "[task] The cert will be checked on the 1st of every month at 09:00."
Write-Host "[task] It will only regenerate if expiry is within 60 days - no unnecessary churn."
