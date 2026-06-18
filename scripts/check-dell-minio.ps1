param(
    [switch]$Repair
)

$ErrorActionPreference = "Stop"

if ($Repair) {
    powershell -ExecutionPolicy Bypass -File scripts\start-dell-minio.ps1
}

# Check container exists and is running
$inspect = ssh dell docker inspect -f '{{.Name}} {{.State.Running}} {{.RestartCount}}' xf_dell_minio
if ($LASTEXITCODE -ne 0) {
    throw "Dell MinIO container is missing. Run scripts/start-dell-minio.ps1."
}
Write-Host $inspect

# Parse running state
$parts = $inspect.Trim() -split '\s+'
$isRunning = $parts[1]
if ($isRunning -ne "true") {
    throw "Dell MinIO container exists but is not running. State: $inspect"
}

# Hit the MinIO health endpoint
$healthResponse = ssh dell docker run --rm --network xf_dell_quality alpine wget --header="Host: localhost" -qO- http://xf_dell_minio:9000/minio/health/live
if ($LASTEXITCODE -ne 0) {
    throw "Dell MinIO health check failed - the /minio/health/live endpoint is not responding."
}

Write-Host "[DELL MINIO STATUS: status=ok endpoint=http://xf_dell_minio:9000]"
Write-Host "[DELL MINIO CHECK: status=ok container=xf_dell_minio]"
