# stop.ps1 - Stop the XF Internal Linker app and kill all processes
# Run this when you are done. Everything shuts down cleanly.

Write-Host "Stopping XF Internal Linker..." -ForegroundColor Cyan

& "$PSScriptRoot\docker-safe.ps1" compose down

if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "All processes stopped. Nothing is running." -ForegroundColor Green
} else {
    Write-Host "Something went wrong stopping the app." -ForegroundColor Red
}
