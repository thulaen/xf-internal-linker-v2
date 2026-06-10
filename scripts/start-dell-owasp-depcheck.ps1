# Requires -RunAsAdministrator
$ErrorActionPreference = "Stop"

Write-Host "Starting OWASP Dependency-Check on Dell..." -ForegroundColor Cyan

try {
    docker --context dell rm -f xf_dell_owasp_depcheck > $null 2>&1
} catch {}

docker --context dell run --rm `
  --name xf_dell_owasp_depcheck `
  --memory 768m `
  --network xf_dell_quality `
  -v xf_dell_sonar_repo:/repo:ro `
  -v xf_dell_owasp_reports:/reports `
  -v xf_dell_owasp_data:/usr/share/dependency-check/data `
  owasp/dependency-check:latest `
  --project xf-internal-linker `
  --scan /repo `
  --format HTML --format JSON --out /reports

Write-Host "[DELL OWASP DEPCHECK: scan completed]" -ForegroundColor Green
