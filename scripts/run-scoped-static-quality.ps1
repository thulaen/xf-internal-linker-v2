<#
.SYNOPSIS
    Parallel quality orchestrator — DELL ONLY.

    Fans out every per-language quality runner at once. Each runner
    (run-python-quality.sh, run-python-repo-mutation.sh, run-rust-quality.sh,
    run-angular-quality.sh) already syncs its source to the Dell helper and runs
    the heavy work THERE, fail-CLOSED (no Windows fallback). This script just
    start them in parallel and waits, so a push runs all quality on Dell at
    once. The old Windows-local jobs, Mint/icecc, and the compiled-language
    shard paths are gone.

.DESCRIPTION
    Invoked by the push path (scripts/prepush-docker.sh). Local pre-commit still
    uses the fast scope-gated precommit-docker.sh.

.PARAMETER ScopeMode
    Commit scope mode passed to the runners: staged, push, or worktree.
#>
[CmdletBinding()]
param(
    [string]$ScopeMode = $(if ($env:COMMIT_SCOPE_MODE) { $env:COMMIT_SCOPE_MODE } else { "push" })
)
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = git rev-parse --show-toplevel
Set-Location $repoRoot

$BashExe = "bash"
$GitBash = "C:\Program Files\Git\bin\bash.exe"
if (Test-Path $GitBash) { $BashExe = $GitBash }

# Dell is REQUIRED — all quality runs on Dell, fail-CLOSED. Stop early with a
# clear message if Dell is unreachable (each runner also enforces this).
$dellOk = $false
try { docker --context dell info *>$null; $dellOk = $true } catch {}
if (-not $dellOk) {
    Write-Error "[orchestrator] Dell Docker context is required (all quality runs on Dell) and is not reachable. Wake/fix Dell and retry — it will NOT fall back to Windows."
    exit 2
}

# Every per-language runner self-dispatches its heavy work to Dell. Start them
# all in parallel; Dell's scheduler shares its 20 threads across them.
$runners = @(
    "scripts/run-python-mutation.sh",
    "scripts/run-python-repo-mutation.sh",
    "scripts/run-rust-mutation.sh",
    "scripts/run-angular-mutation.sh"
)
$jobs = @()
foreach ($script in $runners) {
    if (-not (Test-Path $script)) { continue }
    $jobs += Start-Job -Name $script -ScriptBlock {
        param($root, $s, $mode, $bashExe)
        Set-Location $root
        $env:COMMIT_SCOPE_MODE = $mode
        $env:XF_QUALITY_ENV    = "ci"
        & $bashExe $s 2>&1
        if ($LASTEXITCODE -ne 0) { throw "$s failed with exit code $LASTEXITCODE" }
    } -ArgumentList $repoRoot, $script, $ScopeMode, $BashExe
}

Write-Host "[orchestrator] $($jobs.Count) quality runner(s) started in parallel on Dell. Waiting..."
$jobs | Wait-Job | Out-Null

$failed = @()
foreach ($job in $jobs) {
    Write-Host "`n----- $($job.Name) [$($job.State)] -----"
    try { Receive-Job $job -ErrorAction Continue | Out-Host } catch { Write-Host $_ }
    if ($job.State -ne 'Completed') { $failed += $job.Name }
    Remove-Job $job -Force
}

if ($failed.Count -gt 0) {
    Write-Error "[orchestrator] Quality runner(s) failed on Dell: $($failed -join ', ')"
    exit 1
}
Write-Host "`n[orchestrator] All quality runners passed on Dell."
