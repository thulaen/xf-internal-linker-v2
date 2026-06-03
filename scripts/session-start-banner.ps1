# Session-start banner — prints HANDOFF top-line + open auto-issues + open
# Report Registry headings. Designed to be the first thing an agent runs
# before responding to a new task per the ABSOLUTE rule in CLAUDE.md.
#
# Usage (host PowerShell): pwsh ./scripts/session-start-banner.ps1
# Auto-runs from .githooks/_session-start.sh on shell init when present.
# The Python wrapper may start refresh_session_start_payload in the background.

$ErrorActionPreference = 'SilentlyContinue'

$payload = python scripts/session_start_payload.py 2>$null
if ($LASTEXITCODE -eq 0 -and $payload) {
    $payload
    exit 0
}

Write-Host "=== HANDOFF (top entry) ===" -ForegroundColor Cyan
Get-Content -Path 'AGENT-HANDOFF.md' -TotalCount 3

Write-Host ""
Write-Host "=== OPEN AUTO-ISSUES ===" -ForegroundColor Cyan
docker compose exec -T backend python manage.py print_open_issues --limit 10 2>$null |
    Where-Object { $_ -match '^\[REGISTRY READ:|^\s+#' }

Write-Host ""
Write-Host "=== RECENT RESOLUTIONS (last 14 days) ===" -ForegroundColor Cyan
docker compose exec -T backend python manage.py print_resolved_issues --limit 5 --days 14 2>$null |
    Where-Object { $_ -match '^\[RESOLVED HISTORY:|^\s+#' }

Write-Host ""
Write-Host "=== OPEN REGISTRY FINDINGS (titles only) ===" -ForegroundColor Cyan
$content = Get-Content -Path 'docs/reports/REPORT-REGISTRY.md' -Raw
# Extract sections under "## Open Reports" / "## Open Individual Issues" until next H2.
$openSection = [regex]::Match($content,
    '(?ms)^## Open (Reports|Individual Issues).*?(?=^## |\z)').Value
if ($openSection) {
    $openSection -split "`r?`n" |
        Where-Object { $_ -match '^### (RPT-|ISS-)' } |
        ForEach-Object { "  $_" }
} else {
    Write-Host "  (none)"
}

Write-Host ""
Write-Host "Per the ABSOLUTE rule in CLAUDE.md: pick TWO of the above to fix before starting the user's task." -ForegroundColor Yellow
