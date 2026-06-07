param(
    [string]$MintHost = "mint",
    [string]$MintRepoPath = "/home/mint-helper-01/xf-internal-linker-v2",
    [switch]$KeepWindowsCopies
)

$ErrorActionPreference = "Stop"
$MintQualityServices = "compiled-tools pyroscope"

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

if (-not $KeepWindowsCopies) {
    & docker --context desktop-linux compose stop compiled-tools pyroscope
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "Windows Docker did not stop one or more quality-tool services. Continuing with Mint start."
    }
    & docker --context desktop-linux compose rm -f -s compiled-tools pyroscope
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "Windows Docker did not remove one or more duplicate quality-tool containers. Continuing with Mint start."
    }
    Write-Host "[WINDOWS DUPLICATES REMOVED: services=compiled-tools,pyroscope volumes=preserved]"
}

Invoke-Mint "test -d '$MintRepoPath/.git' && test -f '$MintRepoPath/docker-compose.yml'"
$envValues = Read-LocalEnv

$secretLines = @()
$autoIssueTokenLine = ""
if ($envValues.ContainsKey("AUTOISSUE_INGEST_TOKEN") -and $envValues["AUTOISSUE_INGEST_TOKEN"]) {
    $autoIssueTokenLine = "AUTOISSUE_INGEST_TOKEN=$($envValues["AUTOISSUE_INGEST_TOKEN"])"
}
if (-not $autoIssueTokenLine) {
    throw "AUTOISSUE_INGEST_TOKEN is missing from Windows .env. Add a long random token, then rerun this script."
}
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
Invoke-Mint "cd '$MintRepoPath' && test -s .env.mint-quality && grep -q '^AUTOISSUE_INGEST_TOKEN=' .env.mint-quality"
Invoke-Mint "cd '$MintRepoPath' && POSTGRES_PASSWORD=mint-quality-not-used docker compose --env-file .env.mint-quality --profile mint-quality up -d --build $MintQualityServices"

Write-Host "[MINT QUALITY STARTED: host=$MintHost repo=$MintRepoPath services=compiled-tools,pyroscope]"
