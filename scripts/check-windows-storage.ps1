<#
.SYNOPSIS
    Check Windows storage roots against their declared caps and print warnings.
    Emits warnings but does NOT fail — informational only.

.DESCRIPTION
    Delegates to scripts/windows_storage.py --check-caps.
    Intended to run at the start of each quality session.
#>
[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Continue"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python    = Join-Path $ScriptDir "..\\.venv\\Scripts\\python.exe"
if (-not (Test-Path $Python)) {
    $Python = "python"
}

Write-Host "`nWindows storage cap check"
Write-Host ("─" * 50)

& $Python (Join-Path $ScriptDir "windows_storage.py") --check-caps

Write-Host ("─" * 50)
Write-Host "Storage check complete (warnings above = approaching or over cap)."
# Exit 0 — warnings only, never hard-fail on cap.
exit 0
