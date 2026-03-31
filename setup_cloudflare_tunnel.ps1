# XF Linker V2 — Cloudflare Named Tunnel Setup
# Run this ONE TIME ONLY to create a permanent tunnel on goldmidi.com.
# After this, your webhook URL is fixed forever: https://xf-sync.goldmidi.com/...

$tunnelName = "xf-linker-sync"
$hostname   = "xf-sync.goldmidi.com"
$configDir  = "$env:USERPROFILE\.cloudflared"
$configFile = "$configDir\config.yml"

# ── Resolve cloudflared ───────────────────────────────────────────────────────
$cloudflared = $null
if (Get-Command "cloudflared" -ErrorAction SilentlyContinue) {
    $cloudflared = "cloudflared"
} else {
    $localBin = Join-Path $PSScriptRoot "tools\cloudflared.exe"
    if (Test-Path $localBin) {
        $cloudflared = $localBin
    } else {
        Write-Host "ERROR: cloudflared not found." -ForegroundColor Red
        exit 1
    }
}

Write-Host ""
Write-Host "=== XF Linker — Cloudflare Tunnel Setup ===" -ForegroundColor Cyan
Write-Host ""

# ── Step 1: Login ─────────────────────────────────────────────────────────────
Write-Host "STEP 1: Log in to Cloudflare" -ForegroundColor Yellow
Write-Host "A browser window will open. Select goldmidi.com when asked." -ForegroundColor White
Write-Host "Press Enter to continue..."
$null = Read-Host

& $cloudflared tunnel login
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Login failed. Please try again." -ForegroundColor Red
    exit 1
}
Write-Host "Login successful." -ForegroundColor Green
Write-Host ""

# ── Step 2: Create tunnel ─────────────────────────────────────────────────────
Write-Host "STEP 2: Creating tunnel '$tunnelName'..." -ForegroundColor Yellow

$createOutput = & $cloudflared tunnel create $tunnelName 2>&1
Write-Host $createOutput

# Parse the tunnel ID from the output line:
# "Created tunnel xf-linker-sync with id <uuid>"
$tunnelId = $null
foreach ($line in $createOutput) {
    if ($line -match "with id ([0-9a-f\-]{36})") {
        $tunnelId = $Matches[1]
        break
    }
}

if (-not $tunnelId) {
    # Tunnel may already exist — try to fetch its ID
    Write-Host "Could not parse tunnel ID from output. Checking if tunnel already exists..." -ForegroundColor Yellow
    $listOutput = & $cloudflared tunnel list 2>&1 | Select-String $tunnelName
    if ($listOutput -match "([0-9a-f\-]{36})") {
        $tunnelId = $Matches[1]
        Write-Host "Found existing tunnel ID: $tunnelId" -ForegroundColor Cyan
    } else {
        Write-Host "ERROR: Could not create or find tunnel '$tunnelName'." -ForegroundColor Red
        Write-Host "Output was: $createOutput"
        exit 1
    }
}

Write-Host "Tunnel ID: $tunnelId" -ForegroundColor Green
Write-Host ""

# ── Step 3: Write config.yml ──────────────────────────────────────────────────
Write-Host "STEP 3: Writing tunnel config..." -ForegroundColor Yellow

$credFile = "$configDir\$tunnelId.json"

$configContent = @"
tunnel: $tunnelId
credentials-file: $credFile

ingress:
  - hostname: $hostname
    service: http://localhost:8000
  - service: http_status:404
"@

New-Item -ItemType Directory -Force -Path $configDir | Out-Null
Set-Content -Path $configFile -Value $configContent -Encoding UTF8

Write-Host "Config written to: $configFile" -ForegroundColor Green
Write-Host ""

# ── Step 4: Create DNS record ─────────────────────────────────────────────────
Write-Host "STEP 4: Adding DNS record xf-sync.goldmidi.com -> tunnel..." -ForegroundColor Yellow

& $cloudflared tunnel route dns $tunnelName $hostname
if ($LASTEXITCODE -ne 0) {
    Write-Host "WARNING: DNS route command returned an error." -ForegroundColor Yellow
    Write-Host "This may be fine if the DNS record already exists." -ForegroundColor Yellow
} else {
    Write-Host "DNS record created." -ForegroundColor Green
}
Write-Host ""

# ── Done ──────────────────────────────────────────────────────────────────────
Write-Host "============================================" -ForegroundColor Cyan
Write-Host " SETUP COMPLETE" -ForegroundColor Green
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Your permanent webhook URL (paste this into XenForo ONCE):" -ForegroundColor White
Write-Host ""
Write-Host "  https://$hostname/api/sync/webhooks/xenforo/" -ForegroundColor Yellow
Write-Host ""
Write-Host "Webhook secret: MySuperSecretSync123" -ForegroundColor Yellow
Write-Host ""
Write-Host "The tunnel watcher (start_sync_tunnel.ps1) will now use this" -ForegroundColor White
Write-Host "permanent tunnel automatically every time Docker starts." -ForegroundColor White
Write-Host ""
Write-Host "You do NOT need to run this script again." -ForegroundColor Green
