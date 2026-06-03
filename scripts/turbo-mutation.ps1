<#
.SYNOPSIS
    Turbo mutation runner — 65/35 split across Windows + Mint for one language.

.DESCRIPTION
    Wraps turbo_mutation.py so you can call it from PowerShell without quoting
    Python syntax.  Each language fires its own tool independently; asking for
    --language python will never start C++ or Go tests.

    Set XF_TURBO_MUTATION=1 to activate turbo mode from existing quality scripts.

.PARAMETER Language
    Which language to mutate: python, cpp, go, typescript, rust, haskell.

.PARAMETER DryRun
    Parse + count survivors but do not write AutoIssues.

.PARAMETER Cores
    Override auto-detected CPU count on each machine (0 = auto).

.EXAMPLE
    .\scripts\turbo-mutation.ps1 -Language python
    .\scripts\turbo-mutation.ps1 -Language cpp -DryRun
    .\scripts\turbo-mutation.ps1 -Language go  -Cores 8
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("python", "cpp", "go", "typescript", "rust", "haskell")]
    [string]$Language,

    [switch]$DryRun,

    [int]$Cores = 0
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$script    = Join-Path $repoRoot "scripts\turbo_mutation.py"

if (-not (Test-Path $script)) {
    Write-Error "turbo_mutation.py not found at $script"
    exit 1
}

# Build argument list
$pyArgs = @("--language", $Language)
if ($DryRun)    { $pyArgs += "--dry-run" }
if ($Cores -gt 0) { $pyArgs += @("--cores", "$Cores") }

Write-Host "[turbo-mutation] Starting language=$Language dry_run=$($DryRun.IsPresent) cores=$Cores" -ForegroundColor Cyan
Write-Host "[turbo-mutation] Weighted split: Dell up to 60% / Windows 30% / Mint 10%; an unreachable machine redistributes automatically." -ForegroundColor Cyan

$start = Get-Date

# Stream output in real time
$proc = Start-Process -FilePath "python" -ArgumentList (@($script) + $pyArgs) `
    -WorkingDirectory $repoRoot `
    -NoNewWindow -PassThru -Wait

$elapsed = [math]::Round(((Get-Date) - $start).TotalSeconds)

if ($proc.ExitCode -ne 0) {
    Write-Host "[turbo-mutation] FAILED (exit $($proc.ExitCode)) after ${elapsed}s" -ForegroundColor Red
    exit $proc.ExitCode
}

Write-Host "[turbo-mutation] Completed in ${elapsed}s" -ForegroundColor Green

# Remind about kill-rate gates
$configPath = Join-Path $repoRoot "config\mutation-routing.json"
if (Test-Path $configPath) {
    $cfg  = Get-Content $configPath -Raw | ConvertFrom-Json
    $gate = $cfg.kill_rate_gates.$Language
    if ($null -ne $gate) {
        Write-Host "[turbo-mutation] Kill-rate gate for ${Language}: $([math]::Round($gate * 100))% - check AutoIssues for survivors." -ForegroundColor Yellow
    }
}
