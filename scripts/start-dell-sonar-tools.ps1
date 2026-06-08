param(
    [string]$SonarToken = $env:SONAR_TOKEN,
    [int]$AutoscanIntervalSeconds = $(if ($env:SONAR_AUTOSCAN_INTERVAL_SECONDS) { [int]$env:SONAR_AUTOSCAN_INTERVAL_SECONDS } else { 1800 }),
    [string]$BashExe = $(if (Test-Path "C:\Program Files\Git\bin\bash.exe") { "C:\Program Files\Git\bin\bash.exe" } else { "bash" })
)

$ErrorActionPreference = "Stop"

function Invoke-DellDocker {
    param(
        [Parameter(ValueFromRemainingArguments = $true)]
        [string[]]$DockerArgs
    )
    & docker --context dell @DockerArgs
    if ($LASTEXITCODE -ne 0) {
        throw "Dell Docker command failed: docker --context dell $($DockerArgs -join ' ')"
    }
}

function Read-LocalEnv {
    $values = @{}
    if (-not (Test-Path ".env")) {
        return $values
    }
    foreach ($line in Get-Content ".env") {
        if ($line -match "^\s*#" -or $line -notmatch "^\s*([^=]+)=(.*)$") {
            continue
        }
        $values[$Matches[1].Trim()] = $Matches[2]
    }
    return $values
}

$envValues = Read-LocalEnv
if (-not $SonarToken -and $envValues.ContainsKey("SONAR_TOKEN")) {
    $SonarToken = $envValues["SONAR_TOKEN"]
}
if (-not $SonarToken) {
    throw "SONAR_TOKEN is missing. Set it locally or in .env before starting Dell sonar-autoscan."
}

$networkListArgs = @("network", "ls", "--format", "{{.Name}}")
$networkNames = Invoke-DellDocker @networkListArgs
$networkExists = $networkNames -contains "xf_dell_quality"
if (-not $networkExists) {
    Invoke-DellDocker "network" "create" "xf_dell_quality"
}
foreach ($volume in @(
    "sonarqube_data",
    "sonarqube_extensions",
    "sonarqube_logs",
    "xf_dell_sonar_repo",
    "xf_dell_sonar_cache"
)) {
    Invoke-DellDocker "volume" "create" $volume
}

$containerListArgs = @(
    "container", "ls", "-a",
    "--filter", "name=^xf_linker_sonarqube$",
    "--filter", "name=^xf_linker_sonar_autoscan$",
    "--filter", "name=^xf_dell_sonar_repo_sync$",
    "--format", "{{.Names}}"
)
$existingContainers = Invoke-DellDocker @containerListArgs
if ($existingContainers.Count -gt 0) {
    $removeArgs = @("rm", "-f") + @($existingContainers)
    Invoke-DellDocker @removeArgs
}

$sonarqubeArgs = @(
    "run", "-d",
    "--name", "xf_linker_sonarqube",
    "--restart", "unless-stopped",
    "--network", "xf_dell_quality",
    "--network-alias", "sonarqube",
    "-m", "1536m",
    "-e", "SONAR_ES_BOOTSTRAP_CHECKS_DISABLE=true",
    "-p", "9000:9000",
    "-v", "sonarqube_data:/opt/sonarqube/data",
    "-v", "sonarqube_extensions:/opt/sonarqube/extensions",
    "-v", "sonarqube_logs:/opt/sonarqube/logs",
    "sonarqube:community"
)
Invoke-DellDocker @sonarqubeArgs

& $BashExe -lc "{ git ls-files -z -- backend frontend sonar-project.properties; printf '%s\0' scripts/dell-sonar-autoscan.sh; } | tar --null -T - -cf - | docker --context dell run --rm -i --name xf_dell_sonar_repo_sync -v xf_dell_sonar_repo:/repo alpine sh -c 'rm -rf /repo/backend /repo/frontend /repo/scripts /repo/sonar-project.properties && tar -xf - -C /repo'"
if ($LASTEXITCODE -ne 0) {
    throw "Failed to sync the source snapshot into the Dell SonarQube repo volume."
}

$autoscanArgs = @(
    "run", "-d",
    "--name", "xf_linker_sonar_autoscan",
    "--restart", "unless-stopped",
    "--network", "xf_dell_quality",
    "-m", "1g",
    "-e", "SONAR_HOST_URL=http://sonarqube:9000",
    "-e", "SONAR_TOKEN=$SonarToken",
    "-e", "SONAR_AUTOSCAN_INTERVAL_SECONDS=$AutoscanIntervalSeconds",
    "-e", "SONAR_SCANNER_OPTS=-Xmx768m",
    "-v", "xf_dell_sonar_repo:/repo:ro",
    "-v", "xf_dell_sonar_cache:/opt/sonar-scanner/.sonar/cache",
    "--entrypoint", "sh",
    "sonarsource/sonar-scanner-cli:latest",
    "/repo/scripts/dell-sonar-autoscan.sh"
)
Invoke-DellDocker @autoscanArgs

Write-Host "[DELL SONAR STARTED: context=dell services=sonarqube,sonar-autoscan url=http://dell:9000]"
