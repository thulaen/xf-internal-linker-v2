# start.ps1 - Start the XF Internal Linker app
# Run this to bring everything up. Nothing runs until you do.

Write-Host "Starting XF Internal Linker..." -ForegroundColor Cyan

& "$PSScriptRoot\docker-safe.ps1" -DockerArgs @("compose", "up", "-d")

if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "App is running." -ForegroundColor Green
    Write-Host "Open your browser at: http://localhost:4200" -ForegroundColor Green
    Write-Host ""
    Write-Host "To stop everything, run: .\scripts\stop.ps1" -ForegroundColor Yellow
} else {
    Write-Host "Something went wrong. Is Docker Desktop running?" -ForegroundColor Red
}
