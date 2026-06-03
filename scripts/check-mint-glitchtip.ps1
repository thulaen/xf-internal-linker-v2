param(
    [string]$MintHost = "mint",
    [string]$MintRepoPath = "/home/mint-helper-01/xf-internal-linker-v2",
    [string]$BaseUrl = "http://10.10.10.91:1337",
    [string]$LoginEmail = $env:GLITCHTIP_LOGIN_EMAIL,
    [string]$LoginPassword = $env:GLITCHTIP_LOGIN_PASSWORD
)

$ErrorActionPreference = "Stop"

function Invoke-MintText {
    param([string]$Command)
    $output = & ssh $MintHost $Command
    if ($LASTEXITCODE -ne 0) {
        throw "Mint command failed: $Command"
    }
    return ($output -join "`n")
}

function Convert-ToSingleQuotedShellValue {
    param([string]$Value)
    return "'" + $Value.Replace("'", "'\''") + "'"
}

Invoke-MintText "test -d '$MintRepoPath/.git' && test -f '$MintRepoPath/docker-compose.yml'" | Out-Null
Invoke-MintText "cd '$MintRepoPath' && test -s .env.mint-glitchtip && grep -q '^POSTGRES_PASSWORD=' .env.mint-glitchtip && grep -q '^GLITCHTIP_SECRET_KEY=' .env.mint-glitchtip" | Out-Null

$ps = Invoke-MintText "cd '$MintRepoPath' && docker compose --env-file .env.mint-glitchtip --profile mint-quality ps glitchtip glitchtip-worker"
Write-Host $ps

$homeStatus = Invoke-MintText "curl -fsS -o /dev/null -w '%{http_code}' $BaseUrl/"
if ($homeStatus -ne "200") {
    throw "Mint GlitchTip home check failed with HTTP $homeStatus."
}
Write-Host "[MINT GLITCHTIP HTTP: status=200 url=$BaseUrl]"

$userCount = & docker --context desktop-linux compose exec -T postgres psql -U xf_linker_user -d glitchtip -tAc "select count(*) from users_user;"
if ($LASTEXITCODE -ne 0) {
    throw "Windows GlitchTip database user-count check failed."
}
$userCountText = ($userCount -join "").Trim()
if ($userCountText -lt 1) {
    throw "Windows GlitchTip database has no login users."
}
Write-Host "[MINT GLITCHTIP DATABASE: users=$userCountText source=windows-postgres]"

if (-not $LoginEmail -or -not $LoginPassword) {
    throw "GLITCHTIP_LOGIN_EMAIL and GLITCHTIP_LOGIN_PASSWORD are required for the login e2e check."
}

$emailArg = Convert-ToSingleQuotedShellValue $LoginEmail
$passwordArg = Convert-ToSingleQuotedShellValue $LoginPassword
$loginScript = "import os; from django.contrib.auth import authenticate; user = authenticate(username=os.environ['GLITCHTIP_LOGIN_EMAIL'], password=os.environ['GLITCHTIP_LOGIN_PASSWORD']); print('Login successful' if user else 'Login failed')"
$loginResult = Invoke-MintText "docker exec --env GLITCHTIP_LOGIN_EMAIL=$emailArg --env GLITCHTIP_LOGIN_PASSWORD=$passwordArg xf_linker_glitchtip python manage.py shell -c `"$loginScript`""
if ($loginResult -notmatch "Login successful") {
    throw "Mint GlitchTip rejected the supplied login credentials."
}
Write-Host "[MINT GLITCHTIP LOGIN: Login successful email=$LoginEmail source=windows-postgres]"
Write-Host "[MINT GLITCHTIP CHECK: status=ok host=$MintHost url=$BaseUrl]"
