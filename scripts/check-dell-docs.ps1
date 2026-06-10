param(
    [switch]$Repair
)

$ErrorActionPreference = "Stop"

if ($Repair) {
    powershell -ExecutionPolicy Bypass -File scripts\start-dell-docs.ps1 -Rebuild
}

# Check container exists and is running
$inspect = docker --context dell inspect -f '{{.Name}} {{.State.Running}} {{.RestartCount}}' xf_dell_docs
if ($LASTEXITCODE -ne 0) {
    throw "Dell Docs container is missing. Run scripts/start-dell-docs.ps1."
}

# Parse running state
$parts = $inspect.Trim() -split '\s+'
$isRunning = $parts[1]
if ($isRunning -ne "true") {
    throw "Dell Docs container exists but is not running. State: $inspect"
}

# Hit the Docs endpoint
$healthResponse = docker --context dell run --rm --network xf_dell_quality alpine wget -qO- http://xf_dell_docs:80
if ($LASTEXITCODE -ne 0) {
    throw "Dell Docs health check failed - the web server is not responding."
}

Write-Host "[DELL DOCS STATUS: status=ok endpoint=http://xf_dell_docs:3000]"
Write-Host "[DELL DOCS CHECK: status=ok container=xf_dell_docs]"
