# Requires -RunAsAdministrator
$ErrorActionPreference = "Stop"

Write-Host "Starting Apache Tika on Dell..." -ForegroundColor Cyan

try {
    docker --context dell rm -f xf_dell_tika > $null 2>&1
} catch {}

docker --context dell run -d `
  --name xf_dell_tika `
  --memory 512m `
  --network xf_dell_quality `
  -p 9998:9998 `
  --restart unless-stopped `
  -v xf_dell_tika_data:/config `
  apache/tika:latest

Write-Host "Tika container started. Allowing 3 seconds for boot..."
Start-Sleep -Seconds 3

# Check status
$status = docker --context dell inspect -f '{{.State.Status}}' xf_dell_tika
if ($status -eq "running") {
    Write-Host "[DELL TIKA STATUS: status=ok]" -ForegroundColor Green
} else {
    Write-Host "[DELL TIKA STATUS: status=failed]" -ForegroundColor Red
}
