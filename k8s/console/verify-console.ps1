param(
    [string]$ExpectedNodes = "minthelper01-lenovo-c50-30,dell-ubuntu-01-optiplex-micro-7010"
)

$ErrorActionPreference = "Stop"
$Kubectl = Get-Command kubectl -ErrorAction SilentlyContinue
if (-not $Kubectl) {
    throw "kubectl is not installed or is not on PATH."
}

$Kubeconfig = Join-Path $env:USERPROFILE ".kube\config"
if (-not (Test-Path -LiteralPath $Kubeconfig)) {
    throw "Kubeconfig is missing at $Kubeconfig."
}

$nodes = kubectl get nodes -o jsonpath="{range .items[*]}{.metadata.name}{'\n'}{end}"
foreach ($node in $ExpectedNodes.Split(",")) {
    if ($nodes -notmatch [regex]::Escape($node.Trim())) {
        throw "Expected node is missing: $node"
    }
}

Write-Host "[KUBECTL CONSOLE: ready]"
