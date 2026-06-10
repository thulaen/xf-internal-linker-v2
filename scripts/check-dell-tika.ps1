# Requires -RunAsAdministrator
$ErrorActionPreference = "Stop"

$status = docker --context dell inspect -f '{{.State.Status}}' xf_dell_tika 2>$null
if ($status -eq "running") {
    # Check the endpoint
    $response = docker --context dell exec xf_dell_tika curl -sS http://localhost:9998/tika
    if ($response) {
        Write-Host "[DELL TIKA STATUS: status=ok]" -ForegroundColor Green
    } else {
        Write-Host "[DELL TIKA STATUS: status=failed] - Container is running but endpoint failed" -ForegroundColor Red
    }
} else {
    Write-Host "[DELL TIKA STATUS: status=failed] - Container is not running" -ForegroundColor Red
}
