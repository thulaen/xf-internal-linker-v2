param(
    [string]$MintHost = "mint",
    [string]$MintRepoPath = "/home/mint-helper-01/xf-internal-linker-v2",
    [switch]$SkipHaskell,
    [switch]$Repair
)

$ErrorActionPreference = "Stop"
$MintQualityServices = "compiled-tools pyroscope"

function Invoke-MintText {
    param([string]$Command)
    $output = & ssh $MintHost $Command
    if ($LASTEXITCODE -ne 0) {
        throw "Mint command failed: $Command"
    }
    return ($output -join "`n")
}

function Repair-MintQualityServices {
    $before = Invoke-MintText "cd '$MintRepoPath' && docker inspect -f '{{.Name}} {{.State.Running}} {{.State.Health.Status}} {{.RestartCount}}' xf_linker_compiled_tools xf_linker_pyroscope 2>/dev/null || true"
    Write-Host "[MINT QUALITY REPAIR: before=$($before -replace "`n", "; ")]"
    Invoke-MintText "cd '$MintRepoPath' && POSTGRES_PASSWORD=mint-quality-not-used docker compose --env-file .env.mint-quality --profile mint-quality up -d $MintQualityServices" | Out-Null
    $after = Invoke-MintText "cd '$MintRepoPath' && docker inspect -f '{{.Name}} {{.State.Running}} {{.State.Health.Status}} {{.RestartCount}}' xf_linker_compiled_tools xf_linker_pyroscope 2>/dev/null || true"
    Write-Host "[MINT QUALITY REPAIR: after=$($after -replace "`n", "; ")]"
}

Invoke-MintText "test -d '$MintRepoPath/.git' && test -f '$MintRepoPath/docker-compose.yml'" | Out-Null
Invoke-MintText "cd '$MintRepoPath' && test -s .env.mint-quality && grep -q '^AUTOISSUE_INGEST_TOKEN=' .env.mint-quality" | Out-Null

if ($Repair) {
    Repair-MintQualityServices
}

$ps = Invoke-MintText "cd '$MintRepoPath' && POSTGRES_PASSWORD=mint-quality-not-used docker compose --env-file .env.mint-quality --profile mint-quality ps compiled-tools pyroscope"
Write-Host $ps

Invoke-MintText "docker exec xf_linker_compiled_tools bash -lc 'python /repo/scripts/ensure_compiled_artifacts.py --check'" | Out-Null

$pyroscopeStatus = Invoke-MintText "curl -fsS http://127.0.0.1:4040/ready"
Write-Host "[MINT PYROSCOPE STATUS: $pyroscopeStatus]"

$freeOutput = Invoke-MintText "free -m"
$memLine = ($freeOutput -split "`n" | Where-Object { $_ -match "^Mem:" } | Select-Object -First 1)
if (-not $memLine) {
    throw "Mint memory output did not include a Mem line."
}
$memParts = $memLine -split "\s+"
$ram = "total_mb=$($memParts[1]) used_mb=$($memParts[2]) free_mb=$($memParts[3]) available_mb=$($memParts[6])"
Write-Host "[MINT RAM: $ram]"
Write-Host "[MINT QUALITY CHECK: status=ok host=$MintHost services=compiled-tools,pyroscope]"
