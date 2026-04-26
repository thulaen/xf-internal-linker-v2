# start.ps1 - Start the XF Internal Linker app
# Run this to bring everything up. Nothing runs until you do.
#
# Boot flow (set 2026-04-26):
#   - Docker Desktop is NOT autostart-on-login. Laptop reboots leave
#     Docker idle, so there is no boot-time spin.
#   - When you click the Docker Desktop icon, the daemon comes up and
#     `restart: always` brings the linker stack back automatically — you
#     do NOT need to run this script after a fresh Docker Desktop click
#     unless `docker compose down` was run earlier.
#   - This script is for cold-start (post-`docker compose down`) and
#     for new checkouts where containers do not yet exist.

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
