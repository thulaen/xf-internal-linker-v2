# safe-rebuild.ps1 - retired local Compose rebuild helper.
#
# The app runtime has moved to Kubernetes and Dell-backed services. MSI no
# longer rebuilds or restarts the app through local Docker.

Write-Error "safe-rebuild.ps1 is retired. Use the Kubernetes rollout, Dell build, and rollback runbooks instead of MSI Docker rebuilds."
exit 2
