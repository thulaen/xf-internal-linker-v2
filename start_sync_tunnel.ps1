# XF Linker V2 — Cloudflare Sync Tunnel Watcher
# Starts the named tunnel when Docker Desktop opens, stops it when Docker closes.
# Runs fully hidden — no windows. Logs to $env:TEMP\xf-tunnel.log
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

$logFile = "$env:TEMP\xf-tunnel.log"

function Write-Log($msg) {
    $line = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')  $msg"
    Add-Content -Path $logFile -Value $line -ErrorAction SilentlyContinue
}

Write-Log "Watcher started. cloudflared=$cloudflared tunnel=$tunnelName"

# ── Cleanup on exit (Ctrl+C) ──────────────────────────────────────────────────
$tunnelProcess = $null

function Stop-Tunnel {
    if ($tunnelProcess -ne $null -and -not $tunnelProcess.HasExited) {
        Write-Log "Stopping tunnel (pid=$($tunnelProcess.Id))..."
        Stop-Process -Id $tunnelProcess.Id -Force -ErrorAction SilentlyContinue
        $script:tunnelProcess = $null
    }
}

function Start-Tunnel {
    Write-Log "Starting cloudflared tunnel..."
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName        = $cloudflared
    $psi.Arguments       = "tunnel --config `"$configFile`" run `"$tunnelName`""
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow  = $true
    $proc = [System.Diagnostics.Process]::Start($psi)
    Write-Log "Tunnel started (pid=$($proc.Id))"
    return $proc
}

$null = Register-EngineEvent -SourceIdentifier PowerShell.Exiting -Action { Stop-Tunnel }

# ── Main loop ─────────────────────────────────────────────────────────────────
Write-Log "Waiting for Docker Desktop..."

while ($true) {

    # ── Phase 1: Wait for Docker Desktop to start ─────────────────────────────
    while (-not (Get-Process "Docker Desktop" -ErrorAction SilentlyContinue)) {
        Start-Sleep -Seconds 5
    }

    Write-Log "Docker Desktop detected. Starting tunnel..."

    # ── Phase 2: Start the tunnel fully hidden ────────────────────────────────
    $tunnelProcess = Start-Tunnel

    Write-Log "Tunnel running (pid=$($tunnelProcess.Id))"

    # ── Phase 3: Watch for Docker Desktop to close ────────────────────────────
    while (Get-Process "Docker Desktop" -ErrorAction SilentlyContinue) {
        # Restart the tunnel if it died unexpectedly
        if ($tunnelProcess.HasExited) {
            Write-Log "Tunnel exited unexpectedly. Restarting..."
            $tunnelProcess = Start-Tunnel
            Write-Log "Tunnel restarted (pid=$($tunnelProcess.Id))"
        }
        Start-Sleep -Seconds 10
    }

    Write-Log "Docker Desktop closed. Stopping tunnel..."
    Stop-Tunnel

    # Loop back to Phase 1
    Write-Log "Waiting for Docker Desktop to start again..."
}
