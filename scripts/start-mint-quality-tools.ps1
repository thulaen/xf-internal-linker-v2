param(
    [string]$MintHost = "mint",
    [string]$MintRepoPath = "/home/mint-helper-01/xf-internal-linker-v2",
    [string]$SonarAdminUser = $env:SONAR_ADMIN_USER,
    [string]$SonarAdminPassword = $env:SONAR_ADMIN_PASSWORD,
    [string]$SonarTokenName = $env:SONAR_TOKEN_NAME,
    [string]$SonarBaseUrl = $env:SONAR_HOST_URL,
    [switch]$RefreshSonarToken,
    [switch]$KeepWindowsCopies
)

$ErrorActionPreference = "Stop"
$MintQualityServices = "compiled-tools sonarqube sonar-autoscan pyroscope pyroscope-ebpf-profiler multi-lang-observability-picker"

function Invoke-Mint {
    param([string]$Command)
    & ssh $MintHost $Command
    if ($LASTEXITCODE -ne 0) {
        throw "Mint command failed: $Command"
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

function Resolve-Setting {
    param(
        [hashtable]$Values,
        [string]$Name,
        [string]$CurrentValue,
        [string]$DefaultValue = ""
    )
    if ($CurrentValue) {
        return $CurrentValue
    }
    if ($Values.ContainsKey($Name) -and $Values[$Name]) {
        return $Values[$Name]
    }
    return $DefaultValue
}

function New-SonarToken {
    param(
        [string]$BaseUrl,
        [string]$AdminUser,
        [string]$AdminPassword,
        [string]$TokenName
    )

    if (-not $AdminUser -or -not $AdminPassword) {
        throw "SONAR_TOKEN is missing and SONAR_ADMIN_USER/SONAR_ADMIN_PASSWORD were not provided. Set them locally, then rerun this script."
    }

    $pair = "{0}:{1}" -f $AdminUser, $AdminPassword
    $encoded = [Convert]::ToBase64String([Text.Encoding]::ASCII.GetBytes($pair))
    $lastError = ""
    foreach ($attempt in 1..30) {
        try {
            $response = Invoke-RestMethod `
                -Method Post `
                -Uri "$BaseUrl/api/user_tokens/generate" `
                -Headers @{ Authorization = "Basic $encoded" } `
                -Body @{ name = $TokenName } `
                -TimeoutSec 30
            if (-not $response.token) {
                throw "SonarQube did not return a token from /api/user_tokens/generate."
            }
            return $response.token
        }
        catch {
            $statusCode = $null
            if ($_.Exception.Response -and $_.Exception.Response.StatusCode) {
                $statusCode = $_.Exception.Response.StatusCode.value__
            }
            if ($statusCode -eq 401 -or $statusCode -eq 403) {
                throw "SonarQube admin credentials were rejected while generating the autoscan token."
            }
            $lastError = $_.Exception.Message
            Start-Sleep -Seconds 5
        }
    }
    throw "SonarQube token generation did not become ready after retries: $lastError"
}

if (-not $KeepWindowsCopies) {
    & docker --context desktop-linux compose stop compiled-tools sonarqube sonar-autoscan pyroscope pyroscope-ebpf-profiler multi-lang-observability-picker
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "Windows Docker did not stop one or more quality-tool services. Continuing with Mint start."
    }
    & docker --context desktop-linux compose rm -f -s compiled-tools sonarqube sonar-autoscan pyroscope pyroscope-ebpf-profiler multi-lang-observability-picker
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "Windows Docker did not remove one or more duplicate quality-tool containers. Continuing with Mint start."
    }
    Write-Host "[WINDOWS DUPLICATES REMOVED: services=compiled-tools,sonarqube,sonar-autoscan,pyroscope,pyroscope-ebpf-profiler,multi-lang-observability-picker volumes=preserved]"
}

Invoke-Mint "test -d '$MintRepoPath/.git' && test -f '$MintRepoPath/docker-compose.yml'"
$envValues = Read-LocalEnv
$SonarAdminUser = Resolve-Setting -Values $envValues -Name "SONAR_ADMIN_USER" -CurrentValue $SonarAdminUser
$SonarAdminPassword = Resolve-Setting -Values $envValues -Name "SONAR_ADMIN_PASSWORD" -CurrentValue $SonarAdminPassword
$SonarTokenName = Resolve-Setting -Values $envValues -Name "SONAR_TOKEN_NAME" -CurrentValue $SonarTokenName -DefaultValue "xf-mint-autoscan"
$SonarBaseUrl = Resolve-Setting -Values $envValues -Name "SONAR_HOST_URL" -CurrentValue $SonarBaseUrl -DefaultValue "http://$MintHost`:9000"

$secretLines = @()
$sonarTokenLine = ""
if ($envValues.ContainsKey("SONAR_TOKEN") -and $envValues["SONAR_TOKEN"]) {
    $sonarTokenLine = "SONAR_TOKEN=$($envValues["SONAR_TOKEN"])"
}
$autoIssueTokenLine = ""
if ($envValues.ContainsKey("AUTOISSUE_INGEST_TOKEN") -and $envValues["AUTOISSUE_INGEST_TOKEN"]) {
    $autoIssueTokenLine = "AUTOISSUE_INGEST_TOKEN=$($envValues["AUTOISSUE_INGEST_TOKEN"])"
}
if (-not $autoIssueTokenLine) {
    throw "AUTOISSUE_INGEST_TOKEN is missing from Windows .env. Add a long random token, then rerun this script."
}
if ($RefreshSonarToken -or -not $sonarTokenLine) {
    Invoke-Mint "cd '$MintRepoPath' && POSTGRES_PASSWORD=mint-quality-not-used docker compose --profile mint-quality up -d sonarqube"
    $sonarToken = New-SonarToken `
        -BaseUrl $SonarBaseUrl `
        -AdminUser $SonarAdminUser `
        -AdminPassword $SonarAdminPassword `
        -TokenName $SonarTokenName
    $sonarTokenLine = "SONAR_TOKEN=$sonarToken"
    Write-Host "[MINT SONAR TOKEN: generated name=$SonarTokenName token=hidden]"
}
$secretLines += $sonarTokenLine
$secretLines += $autoIssueTokenLine
$tempEnv = New-TemporaryFile
try {
    Set-Content -Path $tempEnv -Value ($secretLines -join "`n") -NoNewline
    & scp $tempEnv.FullName "${MintHost}:${MintRepoPath}/.env.mint-quality"
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to copy the Mint-only Sonar token file."
    }
}
finally {
    Remove-Item -LiteralPath $tempEnv -Force -ErrorAction SilentlyContinue
}
Invoke-Mint "cd '$MintRepoPath' && test -s .env.mint-quality && grep -q '^SONAR_TOKEN=' .env.mint-quality && grep -q '^AUTOISSUE_INGEST_TOKEN=' .env.mint-quality"
Invoke-Mint "cd '$MintRepoPath' && POSTGRES_PASSWORD=mint-quality-not-used docker compose --env-file .env.mint-quality --profile mint-quality up -d --build $MintQualityServices"

Write-Host "[MINT QUALITY STARTED: host=$MintHost repo=$MintRepoPath services=compiled-tools,sonarqube,sonar-autoscan,pyroscope,pyroscope-ebpf-profiler,multi-lang-observability-picker]"
