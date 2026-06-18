param(
    [Parameter(Mandatory = $true)]
    [string]$Source,

    [string]$Destination = "$env:USERPROFILE\.kube\config",

    [switch]$Execute
)

$ErrorActionPreference = "Stop"
Write-Host "[KUBECONFIG MSI PLACE]"
Write-Host "Source: $Source"
Write-Host "Destination: $Destination"

if (-not (Test-Path -LiteralPath $Source)) {
    throw "Source kubeconfig does not exist."
}

if (-not $Execute) {
    Write-Host "Dry run only. Add -Execute to copy the kubeconfig."
    exit 0
}

New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Destination) | Out-Null
Copy-Item -LiteralPath $Source -Destination $Destination -Force
Write-Host "Kubeconfig copied."
