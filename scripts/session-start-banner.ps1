# Session-start banner — prints the fast session-start payload only.
# Detailed live issue lists are intentionally left for explicit debugging.
#
# Usage (host PowerShell): pwsh ./scripts/session-start-banner.ps1
# Auto-runs from .githooks/_session-start.sh on shell init when present.

$ErrorActionPreference = 'SilentlyContinue'

python scripts/session_start_payload.py
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "Session-start payload failed. For live startup debugging, run:" -ForegroundColor Yellow
    Write-Host "  python scripts/session_start_payload.py --timeout 60" -ForegroundColor Yellow
    exit $LASTEXITCODE
}
