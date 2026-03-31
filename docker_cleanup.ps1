# XF Linker V2 — Monthly Docker Cleanup
# Removes build cache and dangling images only.
# Never touches volumes (your database and media files are safe).

$logFile = "$PSScriptRoot\docker_cleanup.log"
$timestamp = Get-Date -Format "yyyy-MM-dd HH:mm"

Add-Content $logFile "[$timestamp] Starting Docker cleanup..."

# Remove build cache (biggest space saver)
$result1 = docker builder prune -f 2>&1
Add-Content $logFile "[$timestamp] Builder prune: $result1"

# Remove dangling images (old leftover copies from rebuilds)
$result2 = docker image prune -f 2>&1
Add-Content $logFile "[$timestamp] Image prune: $result2"

# Show current state
$df = docker system df 2>&1
Add-Content $logFile "[$timestamp] Disk usage after cleanup:`n$df"
Add-Content $logFile "[$timestamp] Done."

Write-Host "Docker cleanup complete. See docker_cleanup.log for details."
