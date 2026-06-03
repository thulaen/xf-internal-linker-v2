param(
    [string]$MintHost = "mint",
    [string]$MintRepoPath = "/home/mint-helper-01/xf-internal-linker-v2",
    [switch]$SkipHaskell,
    [switch]$Repair
)

$ErrorActionPreference = "Stop"
$MintQualityServices = "compiled-tools sonarqube sonar-autoscan pyroscope pyroscope-ebpf-profiler multi-lang-observability-picker"

function Invoke-MintText {
    param([string]$Command)
    $output = & ssh $MintHost $Command
    if ($LASTEXITCODE -ne 0) {
        throw "Mint command failed: $Command"
    }
    return ($output -join "`n")
}

function Repair-MintQualityServices {
    $before = Invoke-MintText "cd '$MintRepoPath' && docker inspect -f '{{.Name}} {{.State.Running}} {{.State.Health.Status}} {{.RestartCount}}' xf_linker_compiled_tools xf_linker_sonarqube xf_linker_sonar_autoscan xf_linker_pyroscope xf_linker_pyroscope_ebpf_profiler xf_linker_multi_lang_observability_picker 2>/dev/null || true"
    Write-Host "[MINT QUALITY REPAIR: before=$($before -replace "`n", "; ")]"
    Invoke-MintText "cd '$MintRepoPath' && POSTGRES_PASSWORD=mint-quality-not-used docker compose --env-file .env.mint-quality --profile mint-quality up -d $MintQualityServices" | Out-Null
    $after = Invoke-MintText "cd '$MintRepoPath' && docker inspect -f '{{.Name}} {{.State.Running}} {{.State.Health.Status}} {{.RestartCount}}' xf_linker_compiled_tools xf_linker_sonarqube xf_linker_sonar_autoscan xf_linker_pyroscope xf_linker_pyroscope_ebpf_profiler xf_linker_multi_lang_observability_picker 2>/dev/null || true"
    Write-Host "[MINT QUALITY REPAIR: after=$($after -replace "`n", "; ")]"
}

Invoke-MintText "test -d '$MintRepoPath/.git' && test -f '$MintRepoPath/docker-compose.yml'" | Out-Null
Invoke-MintText "cd '$MintRepoPath' && test -s .env.mint-quality && grep -q '^SONAR_TOKEN=' .env.mint-quality && grep -q '^AUTOISSUE_INGEST_TOKEN=' .env.mint-quality" | Out-Null

if ($Repair) {
    Repair-MintQualityServices
}

$ps = Invoke-MintText "cd '$MintRepoPath' && POSTGRES_PASSWORD=mint-quality-not-used docker compose --env-file .env.mint-quality --profile mint-quality ps compiled-tools sonarqube sonar-autoscan pyroscope pyroscope-ebpf-profiler multi-lang-observability-picker"
Write-Host $ps

Invoke-MintText "docker exec xf_linker_compiled_tools bash -lc 'python /repo/scripts/ensure_compiled_artifacts.py --check && command -v cabal >/dev/null 2>&1 && command -v ghc >/dev/null 2>&1'" | Out-Null

if (-not $SkipHaskell) {
    Invoke-MintText "docker exec xf_linker_compiled_tools bash /repo/scripts/run-haskell-quality.sh" | Out-Null
}

$sonarStatus = Invoke-MintText "curl -fsS http://127.0.0.1:9000/api/system/status"
Write-Host "[MINT SONARQUBE STATUS: $sonarStatus]"
$sonarAutoscanStartedAt = Invoke-MintText "docker inspect -f '{{.State.StartedAt}}' xf_linker_sonar_autoscan"
$sonarAutoscanLogs = Invoke-MintText "docker logs --since '$sonarAutoscanStartedAt' xf_linker_sonar_autoscan 2>&1 | tail -n 120"
if ($sonarAutoscanLogs -match "401 Unauthorized" -or $sonarAutoscanLogs -match "HTTP 401") {
    throw "Sonar auto-scan has authentication failures in recent logs. The scan failed with HTTP 401 Unauthorized; refresh SONAR_TOKEN on Mint before treating Sonar healthy."
}
if ($sonarAutoscanLogs -match "scan failed" -and $sonarAutoscanLogs -notmatch "EXECUTION SUCCESS") {
    throw "Sonar auto-scan has recent scan failed logs and no later EXECUTION SUCCESS marker."
}
if ($sonarAutoscanLogs -match "EXECUTION SUCCESS") {
    Write-Host "[MINT SONAR AUTOSCAN: status=ok recent_success=yes]"
}
else {
    Write-Host "[MINT SONAR AUTOSCAN: status=pending recent_success=no]"
}
$pyroscopeStatus = Invoke-MintText "curl -fsS http://127.0.0.1:4040/ready"
Write-Host "[MINT PYROSCOPE STATUS: $pyroscopeStatus]"
$ebpfStatus = Invoke-MintText "curl -fsS http://127.0.0.1:12346/-/healthy"
Write-Host "[MINT PYROSCOPE EBPF STATUS: $ebpfStatus]"
Invoke-MintText "docker inspect -f '{{.State.Running}}' xf_linker_multi_lang_observability_picker | grep -q true" | Out-Null
$pickerLogs = Invoke-MintText "docker logs --tail 20 xf_linker_multi_lang_observability_picker 2>&1 | tail -n 20"
if ($pickerLogs -notmatch "\[multi-lang-picker\] sent=") {
    throw "Mint multi-language observability picker has not emitted a sender status line yet."
}
if ($pickerLogs -notmatch "pprof_cpu_sample_rate_hz compiled=500 python=250") {
    throw "Mint multi-language observability picker has not logged the required pprof sample rates."
}
Write-Host "[MINT PICKER STATUS: multi_lang_observability_picker=running sender=active pprof_compiled_hz=500 pprof_python_hz=250]"

$freeOutput = Invoke-MintText "free -m"
$memLine = ($freeOutput -split "`n" | Where-Object { $_ -match "^Mem:" } | Select-Object -First 1)
if (-not $memLine) {
    throw "Mint memory output did not include a Mem line."
}
$memParts = $memLine -split "\s+"
$ram = "total_mb=$($memParts[1]) used_mb=$($memParts[2]) free_mb=$($memParts[3]) available_mb=$($memParts[6])"
Write-Host "[MINT RAM: $ram]"
Write-Host "[MINT QUALITY CHECK: status=ok host=$MintHost services=compiled-tools,sonarqube,sonar-autoscan,pyroscope,pyroscope-ebpf-profiler,multi-lang-observability-picker]"
