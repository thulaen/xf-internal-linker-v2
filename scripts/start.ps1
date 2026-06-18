# start.ps1 - Verify the live XF Internal Linker app path.
#
# The app runtime moved off MSI. This script no longer starts local Docker.
# It checks the Kubernetes app path that MSI now uses.

$ErrorActionPreference = "Stop"

Write-Host "Checking live XF Internal Linker..." -ForegroundColor Cyan

kubectl -n xf-app rollout status deploy/backend --timeout=120s
kubectl -n xf-app rollout status deploy/frontend --timeout=120s
python scripts/backend_manage.py check

$frontendUrl = if ($env:XF_FRONTEND_URL) { $env:XF_FRONTEND_URL } else { "http://192.168.0.91:30080/" }
$response = Invoke-WebRequest -UseBasicParsing -Uri $frontendUrl -TimeoutSec 20
if ($response.StatusCode -ne 200) {
    throw "Frontend returned HTTP $($response.StatusCode) from $frontendUrl."
}

Write-Host ""
Write-Host "Live app is reachable." -ForegroundColor Green
Write-Host "Frontend: $frontendUrl" -ForegroundColor Green
