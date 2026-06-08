param(
    [string]$SonarBaseUrl = $env:SONAR_HOST_URL,
    [switch]$Repair
)

$ErrorActionPreference = "Stop"

if ($Repair) {
    powershell -ExecutionPolicy Bypass -File scripts\start-dell-sonar-tools.ps1
}

$inspect = docker --context dell inspect -f '{{.Name}} {{.State.Running}} {{if .State.Health}}{{.State.Health.Status}}{{end}} {{.RestartCount}}' xf_linker_sonarqube xf_linker_sonar_autoscan
if ($LASTEXITCODE -ne 0) {
    throw "Dell SonarQube containers are missing. Run scripts/start-dell-sonar-tools.ps1."
}
Write-Host ($inspect -join "`n")

$statusBody = if ($SonarBaseUrl) {
    Invoke-RestMethod -Uri "$SonarBaseUrl/api/system/status" -TimeoutSec 30 |
        ConvertTo-Json -Compress
}
else {
    docker --context dell exec xf_linker_sonarqube bash -lc "curl -fsS http://localhost:9000/api/system/status"
}
if ($LASTEXITCODE -ne 0) {
    throw "Dell SonarQube status check failed."
}
$sonarStatus = $statusBody | ConvertFrom-Json
if ($sonarStatus.status -ne "UP") {
    throw "Dell SonarQube is reachable but not UP. Current status: $($sonarStatus.status)"
}
Write-Host "[DELL SONARQUBE STATUS: {""status"":""$($sonarStatus.status)""}]"

$startedAt = docker --context dell inspect -f '{{.State.StartedAt}}' xf_linker_sonar_autoscan
if ($LASTEXITCODE -ne 0) {
    throw "Could not read Dell sonar-autoscan start time."
}
$previousErrorActionPreference = $ErrorActionPreference
$ErrorActionPreference = "Continue"
try {
    $logs = docker --context dell logs --since "$startedAt" xf_linker_sonar_autoscan 2>&1 |
        Select-Object -Last 160
}
finally {
    $ErrorActionPreference = $previousErrorActionPreference
}
$joinedLogs = $logs -join "`n"
if ($joinedLogs -match "401 Unauthorized" -or $joinedLogs -match "HTTP 401") {
    throw "Dell sonar-autoscan has authentication failures in recent logs. Refresh SONAR_TOKEN."
}
if ($joinedLogs -match "scan failed" -and $joinedLogs -notmatch "EXECUTION SUCCESS") {
    throw "Dell sonar-autoscan has recent scan failures and no later EXECUTION SUCCESS marker."
}
if ($joinedLogs -match "EXECUTION SUCCESS") {
    Write-Host "[DELL SONAR AUTOSCAN: status=ok recent_success=yes]"
}
else {
    Write-Host "[DELL SONAR AUTOSCAN: status=pending recent_success=no]"
}

$reportedUrl = if ($SonarBaseUrl) { $SonarBaseUrl } else { "docker-context:dell/xf_linker_sonarqube" }
Write-Host "[DELL SONAR CHECK: status=ok url=$reportedUrl services=sonarqube,sonar-autoscan]"
