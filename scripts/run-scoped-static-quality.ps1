<#
.SYNOPSIS
    Parallel quality orchestrator - starts all quality checks simultaneously.
    Windows and Dell run quality checks at the same time. MegaLinter runs on Dell.
    Mint is removed from the compute path (storage/observability host only).

.DESCRIPTION
    This replaces the sequential precommit-docker.sh pattern for CI and push.
    Local pre-commit still uses precommit-docker.sh (fast, scope-gated).

    Windows background jobs:
      run-python-quality.sh, run-python-repo-mutation.sh,
      run-angular-quality.sh, run-lua-quality.sh,
      language-specific checks only; Docker images are reused, not rebuilt.

    Dell (via Docker context): compiled-language checks and 100% of MegaLinter.
    (Mint, the storage/observability host, may still lend CPU for distributed
    C++ compilation via icecc — that is best-effort and never blocks a commit.)

.PARAMETER ScopeMode
    Commit scope mode passed to the shard planner: staged, push, or worktree.

.PARAMETER MintHost
    Hostname or IP of the Mint machine (default: mint, override via MINT_HOST).

.PARAMETER MintRepoPath
    Absolute path to the repo checkout on Mint (default: /home/mint-helper-01/xf-internal-linker-v2).
#>
[CmdletBinding()]
param(
    [string]$ScopeMode    = $(if ($env:COMMIT_SCOPE_MODE) { $env:COMMIT_SCOPE_MODE } else { "push" }),
    [string]$MintHost     = $(if ($env:MINT_HOST) { $env:MINT_HOST } else { "mint" }),
    [string]$MintRepoPath = $(if ($env:MINT_REPO_PATH) { $env:MINT_REPO_PATH } else { "/home/mint-helper-01/xf-internal-linker-v2" })
)
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = git rev-parse --show-toplevel
Set-Location $repoRoot
$env:XF_QUALITY_NO_BUILD = "1"
$env:XF_TURBO_MUTATION = "1"

$BashExe = "bash"
$GitBash = "C:\Program Files\Git\bin\bash.exe"
if (Test-Path $GitBash) {
    $BashExe = $GitBash
}

# --- Preflight: Docker must be running on Windows ---
$dockerOk = $false
try { docker info *>$null; $dockerOk = $true } catch {}
if (-not $dockerOk) {
    Write-Error "Docker Desktop is not running or not found. Start Docker Desktop and retry."
    exit 2
}

# --- Resolve Mint hostname to IP for icecc.
#     Docker containers cannot always resolve bare hostnames via DNS, but they
#     can always reach an IP.  We resolve once on the Windows host, then pass
#     the IP as ICECC_SCHEDULER so the compiled-tools container (run by
#     run-cpp-quality.sh) can connect directly to the Mint icecc daemon.
#     Spec: docs/specs/fr-icecc-distributed-cpp.md
$MintIP = ""
try {
    $addrs = [System.Net.Dns]::GetHostAddresses($MintHost) |
             Where-Object { $_.AddressFamily -eq "InterNetwork" }
    if ($addrs) { $MintIP = ($addrs | Select-Object -First 1).IPAddressToString }
} catch {}
if ($MintIP) {
    $env:ICECC_SCHEDULER = $MintIP
    Write-Host "[orchestrator] ICECC_SCHEDULER=$MintIP (Mint distributed C++ endpoint)"
} else {
    Write-Host "[orchestrator] Cannot resolve $MintHost to an IP - icecc disabled (local C++ build only)."
}

# --- 1. Plan MegaLinter file scope. MegaLinter runs on Dell only. ---
Write-Host "[orchestrator] Planning scoped quality shards (mode=$ScopeMode)..."
$manifestJson = cmd.exe /c "python scripts\plan-scoped-quality-shards.py --mode $ScopeMode 2>NUL"
if ($LASTEXITCODE -ne 0) {
    Write-Error "[orchestrator] Shard planning failed."
    exit $LASTEXITCODE
}
$manifest = $manifestJson | ConvertFrom-Json
Write-Host "[orchestrator] Dell:    $($manifest.dell_megalinter_paths.Count) files ($($manifest.weight_proof.dell_pct)%)"

# --- 2. Start Windows quality jobs (all in parallel) ---
$jobs = @()

# Language quality scripts
foreach ($script in @(
    "scripts/run-python-quality.sh",
    "scripts/run-python-repo-mutation.sh",
    "scripts/run-angular-quality.sh",
    "scripts/run-lua-quality.sh"
)) {
    $jobs += Start-Job -Name $script -ScriptBlock {
        param($root, $s, $mode, $bashExe)
        Set-Location $root
        $env:COMMIT_SCOPE_MODE = $mode
        $env:XF_QUALITY_ENV   = "ci"
        $env:XF_QUALITY_NO_BUILD = "1"
        $env:XF_TURBO_MUTATION = "1"
        & $bashExe $s 2>&1
        if ($LASTEXITCODE -ne 0) {
            throw "$s failed with exit code $LASTEXITCODE"
        }
    } -ArgumentList $repoRoot, $script, $ScopeMode, $BashExe
}

# --- 3. Start the Dell job. Dell syncs its own source tree inside the shard
#        script (run-dell-quality-shard.sh) and runs the compiled-language
#        checks plus 100% of MegaLinter. Mint is no longer a shard, so there is
#        no tar-over-ssh source sync to race the commit. ---
$dellJob = Start-Job -Name "dell-shard" -ScriptBlock {
    param($root, $json, $mode, $bashExe)
    Set-Location $root
    $env:COMMIT_SCOPE_MODE = $mode
    docker --context dell info *>$null
    $json | & $bashExe scripts/run-dell-quality-shard.sh 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "dell-shard failed with exit code $LASTEXITCODE"
    }
} -ArgumentList $repoRoot, $manifestJson, $ScopeMode, $BashExe

$allJobs = $jobs + $dellJob

# --- 4. Wait for everything and collect output ---
Write-Host "[orchestrator] All quality checks running. Waiting for completion..."
foreach ($job in $allJobs) {
    Receive-Job $job -Wait -AutoRemoveJob
}

# --- 5. Check for any failed jobs ---
$failed = $allJobs | Where-Object { $_.State -eq "Failed" }
$failedCount = @($failed).Count
if ($failedCount -gt 0) {
    Write-Error "[orchestrator] $failedCount quality job(s) failed. Review output above."
    exit 1
}

Write-Host "[orchestrator] All quality checks passed. MegaLinter on Dell $($manifest.weight_proof.dell_pct)% (Mint removed from compute)."
