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

$repoRoot = Split-Path -Parent $PSScriptRoot
$pgdataVolume = "xf-internal-linker-v2_pgdata"
$backupDirs = @(
    (Join-Path $repoRoot "backups"),
    (Join-Path $repoRoot "backend\backups")
)

& docker volume inspect $pgdataVolume *> $null
if ($LASTEXITCODE -ne 0) {
    $hasBackups = $false
    foreach ($dir in $backupDirs) {
        if (Test-Path -LiteralPath $dir) {
            $hasBackups = $hasBackups -or [bool](
                Get-ChildItem -LiteralPath $dir -Filter "*.dump" -File -ErrorAction SilentlyContinue
            )
        }
    }

    if ($hasBackups) {
        Write-Host "Refusing to start a blank database." -ForegroundColor Red
        Write-Host "The protected pgdata volume is missing, but database backups exist." -ForegroundColor Red
        Write-Host "Ask Codex or Claude to restore the backup before starting the app." -ForegroundColor Yellow
        exit 2
    }

    & docker volume create --name $pgdataVolume --label xf.protected=true --label xf.data=postgres | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Could not create the protected pgdata volume." -ForegroundColor Red
        exit 2
    }
}

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
