# XF Linker V2 — Cloudflare Sync Tunnel Watcher
# Starts the named tunnel when Docker Desktop opens, stops it when Docker closes.
# Loops forever. Safe to Ctrl+C at any time.
#
# PRE-REQUISITE: Run setup_cloudflare_tunnel.ps1 once before using this.

$ErrorActionPreference = "SilentlyContinue"

$tunnelName  = "xf-linker-sync"
$webhookUrl  = "https://xf-sync.goldmidi.com/api/sync/webhooks/xenforo/"
$configFile  = "$env:USERPROFILE\.cloudflared\config.yml"

# ── Resolve cloudflared binary ────────────────────────────────────────────────
$cloudflared = $null

if (Get-Command "cloudflared" -ErrorAction SilentlyContinue) {
    $cloudflared = "cloudflared"
} else {
    $localBin = Join-Path $PSScriptRoot "tools\cloudflared.exe"
    if (Test-Path $localBin) {
        $cloudflared = $localBin
    } else {
        Write-Host "ERROR: cloudflared not found in PATH or tools\cloudflared.exe" -ForegroundColor Red
        exit 1
    }
}

# ── Sanity check: setup has been run ─────────────────────────────────────────
if (-not (Test-Path $configFile)) {
    Write-Host "ERROR: Tunnel config not found at $configFile" -ForegroundColor Red
    Write-Host "Please run setup_cloudflare_tunnel.ps1 first." -ForegroundColor Yellow
    exit 1
}

Write-Host "Using cloudflared : $cloudflared" -ForegroundColor Cyan
Write-Host "Tunnel name       : $tunnelName" -ForegroundColor Cyan
Write-Host "Webhook URL       : $webhookUrl" -ForegroundColor Cyan
Write-Host ""

# ── Cleanup on exit (Ctrl+C) ──────────────────────────────────────────────────
$tunnelProcess = $null

function Stop-Tunnel {
    if ($tunnelProcess -ne $null -and -not $tunnelProcess.HasExited) {
        Write-Host ""
        Write-Host "Stopping tunnel..." -ForegroundColor Yellow
        Stop-Process -Id $tunnelProcess.Id -Force -ErrorAction SilentlyContinue
        $script:tunnelProcess = $null
    }
}

$null = Register-EngineEvent -SourceIdentifier PowerShell.Exiting -Action { Stop-Tunnel }

# ── Main loop ─────────────────────────────────────────────────────────────────
Write-Host "XF Linker Tunnel Watcher started. Waiting for Docker Desktop..." -ForegroundColor Green

while ($true) {

    # ── Phase 1: Wait for Docker Desktop to start ─────────────────────────────
    while (-not (Get-Process "Docker Desktop" -ErrorAction SilentlyContinue)) {
        Start-Sleep -Seconds 5
    }

    Write-Host ""
    Write-Host "Docker Desktop detected. Starting Cloudflare tunnel..." -ForegroundColor Green

    # ── Phase 2: Start the named tunnel in a new visible window ───────────────
    $tunnelProcess = Start-Process `
        -FilePath "powershell.exe" `
        -ArgumentList "-NoExit", "-Command", "& '$cloudflared' tunnel --config '$configFile' run '$tunnelName'" `
        -PassThru `
        -WindowStyle Normal

    Write-Host ""
    Write-Host "Tunnel is running." -ForegroundColor Cyan
    Write-Host "Webhook URL (already set in XenForo): $webhookUrl" -ForegroundColor Yellow
    Write-Host "Secret: MySuperSecretSync123" -ForegroundColor Yellow
    Write-Host ""

    # ── Phase 3: Watch for Docker Desktop to close ────────────────────────────
    while (Get-Process "Docker Desktop" -ErrorAction SilentlyContinue) {
        # Also restart the tunnel if it died unexpectedly
        if ($tunnelProcess.HasExited) {
            Write-Host "Tunnel exited unexpectedly. Restarting..." -ForegroundColor Yellow
            $tunnelProcess = Start-Process `
                -FilePath "powershell.exe" `
                -ArgumentList "-NoExit", "-Command", "& '$cloudflared' tunnel --config '$configFile' run '$tunnelName'" `
                -PassThru `
                -WindowStyle Normal
        }
        Start-Sleep -Seconds 10
    }

    Write-Host "Docker closed. Tunnel stopped." -ForegroundColor Red
    Stop-Tunnel

    # Loop back to Phase 1
    Write-Host "Waiting for Docker Desktop to start again..." -ForegroundColor Green
}
