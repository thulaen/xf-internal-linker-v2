param(
    [string]$MintHost = "mint",
    [string]$MintRepoPath = "/home/mint-helper-01/xf-internal-linker-v2",
    [switch]$KeepWindowsCopies
)

$ErrorActionPreference = "Stop"
$MintGlitchTipServices = "glitchtip-init glitchtip-migrate glitchtip glitchtip-worker"

function Invoke-Mint {
    param([string]$Command)
    & ssh $MintHost $Command
    if ($LASTEXITCODE -ne 0) {
        throw "Mint command failed: $Command"
    }
}

& docker --context desktop-linux compose up -d postgres redis
if ($LASTEXITCODE -ne 0) {
    throw "Windows Postgres and Redis must be running before Mint GlitchTip starts."
}

if (-not $KeepWindowsCopies) {
    & docker --context desktop-linux compose stop glitchtip glitchtip-worker
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "Windows Docker did not stop GlitchTip cleanly. Continuing with Mint start."
    }
    & docker --context desktop-linux compose rm -f -s glitchtip glitchtip-worker
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "Windows Docker did not remove one or more duplicate GlitchTip containers. Continuing with Mint start."
    }
    Write-Host "[WINDOWS DUPLICATES REMOVED: services=glitchtip,glitchtip-worker volumes=preserved]"
}

Invoke-Mint "test -d '$MintRepoPath/.git' && test -f '$MintRepoPath/docker-compose.yml'"
$secretLines = @()
if (Test-Path ".env") {
    $envLines = Get-Content ".env"
    foreach ($key in "POSTGRES_USER", "POSTGRES_PASSWORD", "GLITCHTIP_SECRET_KEY") {
        $secretLines += $envLines |
            Where-Object { $_ -match "^$key=.+" } |
            Select-Object -First 1
    }
}
if (-not ($secretLines | Where-Object { $_ -match "^POSTGRES_PASSWORD=.+" })) {
    throw "POSTGRES_PASSWORD is missing from Windows .env. Mint GlitchTip uses the Windows GlitchTip database."
}
if (-not ($secretLines | Where-Object { $_ -match "^GLITCHTIP_SECRET_KEY=.+" })) {
    throw "GLITCHTIP_SECRET_KEY is missing from Windows .env. Mint GlitchTip needs the same key."
}

$tempEnv = New-TemporaryFile
try {
    Set-Content -Path $tempEnv -Value ($secretLines -join "`n") -NoNewline
    & scp $tempEnv.FullName "${MintHost}:${MintRepoPath}/.env.mint-glitchtip"
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to copy the Mint-only GlitchTip environment file."
    }
}
finally {
    Remove-Item -LiteralPath $tempEnv -Force -ErrorAction SilentlyContinue
}

Invoke-Mint "cd '$MintRepoPath' && test -s .env.mint-glitchtip && grep -q '^POSTGRES_PASSWORD=' .env.mint-glitchtip && grep -q '^GLITCHTIP_SECRET_KEY=' .env.mint-glitchtip"
Invoke-Mint "timeout 3 bash -lc 'cat < /dev/null > /dev/tcp/10.10.10.10/5432'"
Invoke-Mint "timeout 3 bash -lc 'cat < /dev/null > /dev/tcp/10.10.10.10/6379'"
Invoke-Mint "cd '$MintRepoPath' && docker compose --env-file .env.mint-glitchtip --profile mint-quality up -d $MintGlitchTipServices"

Write-Host "[MINT GLITCHTIP STARTED: host=$MintHost repo=$MintRepoPath services=glitchtip-init,glitchtip-migrate,glitchtip,glitchtip-worker url=http://10.10.10.91:1337 database=windows-postgres redis=windows-redis]"
