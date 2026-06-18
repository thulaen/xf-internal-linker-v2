# Requires -RunAsAdministrator
$ErrorActionPreference = "Stop"

# Check if the reports volume exists and has recent data
$output = ssh dell docker run --rm -v xf_dell_owasp_reports:/reports alpine sh -c "ls -l /reports/dependency-check-report.html 2>/dev/null"

if ($output -match "dependency-check-report.html") {
    $date = ssh dell docker run --rm -v xf_dell_owasp_reports:/reports alpine stat -c %y /reports/dependency-check-report.html
    Write-Host "[DELL OWASP DEPCHECK: status=ok last_scan=$date]" -ForegroundColor Green
} else {
    Write-Host "[DELL OWASP DEPCHECK: status=warning] - No recent reports found. Run start-dell-owasp-depcheck.ps1" -ForegroundColor Yellow
}
