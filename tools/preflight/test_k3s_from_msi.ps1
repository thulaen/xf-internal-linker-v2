<# 
SLICE-05 MSI-side verification.

Plain English: checks whether Windows can run kubectl against Mint's k3s API.
#>

$ErrorActionPreference = "Stop"

try {
    $nodes = kubectl get nodes --request-timeout=10s 2>&1
} catch {
    Write-Error "FAIL: MSI kubectl could not read cluster nodes. $($_.Exception.Message)"
    exit 1
}

if ($LASTEXITCODE -ne 0) {
    Write-Error "FAIL: MSI kubectl returned exit code $LASTEXITCODE. $nodes"
    exit 1
}

if ($nodes -notmatch "Ready") {
    Write-Error "FAIL: MSI kubectl returned nodes but no Ready node was shown. $nodes"
    exit 1
}

Write-Output "PASS: MSI kubectl reaches the k3s API and sees Ready nodes."
