# stop.ps1 - MSI no longer stops the live app.
#
# The app runtime moved to Kubernetes and Dell. This script refuses to stop
# cluster services from MSI because doing so would interrupt the live system.

Write-Host "No local MSI app runtime is running to stop." -ForegroundColor Green
Write-Host "Live services run in Kubernetes. Use an explicit Kubernetes rollback or scale command if you really need to stop them." -ForegroundColor Yellow
exit 0
