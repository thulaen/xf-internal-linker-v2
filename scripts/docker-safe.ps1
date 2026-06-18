param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$DockerArgs
)

Write-Error "MSI local Docker is retired. Use Kubernetes, scripts/backend_manage.py, or ssh dell docker for remote helper work."
exit 2
