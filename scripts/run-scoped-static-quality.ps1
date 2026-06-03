<#
.SYNOPSIS
    Parallel quality orchestrator - starts all quality checks simultaneously.
    Windows and Mint run quality checks at the same time. MegaLinter runs on Mint.

.DESCRIPTION
    This replaces the sequential precommit-docker.sh pattern for CI and push.
    Local pre-commit still uses precommit-docker.sh (fast, scope-gated).

    Windows background jobs:
      run-python-quality.sh, run-python-repo-mutation.sh,
      run-angular-quality.sh, run-lua-quality.sh,
      language-specific checks only; Docker images are reused, not rebuilt.

    Mint (via SSH): run-cpp-quality.sh, run-go-quality.sh,
      run-haskell-quality.sh, run-rust-quality.sh, and MegaLinter on the changed file set.

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

# --- 1. Plan MegaLinter file scope. MegaLinter itself runs on Mint. ---
Write-Host "[orchestrator] Planning scoped quality shards (mode=$ScopeMode)..."
$manifestJson = cmd.exe /c "python scripts\plan-scoped-quality-shards.py --mode $ScopeMode 2>NUL"
if ($LASTEXITCODE -ne 0) {
    Write-Error "[orchestrator] Shard planning failed."
    exit $LASTEXITCODE
}
$manifest = $manifestJson | ConvertFrom-Json
Write-Host "[orchestrator] Windows: $($manifest.windows_megalinter_paths.Count) files ($($manifest.weight_proof.windows_pct)%)"
Write-Host "[orchestrator] Mint:    $($manifest.mint_megalinter_paths.Count) files ($($manifest.weight_proof.mint_pct)%)"

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

# --- 2b. Push the CURRENT working tree to Mint BEFORE the shard runs ---
#     Mint builds compiled-language quality (Rust/Go/Haskell/C++) against its OWN
#     checkout, so without this sync it would build Mint's stale copy and miss the
#     edits we are trying to verify. rsync is not installed on the Windows host and
#     PowerShell corrupts binary pipes, so the helper streams a tarball over ssh
#     through git-bash. This must complete before the Mint shard ssh call.
Write-Host "[orchestrator] Syncing working tree to Mint before compiled-language shard..."
& $BashExe -c "MINT_HOST='$MintHost' MINT_REPO_PATH='$MintRepoPath' bash scripts/sync-tree-to-mint.sh"
if ($LASTEXITCODE -ne 0) {
    Write-Error "[orchestrator] Source sync to Mint failed (exit $LASTEXITCODE) - Mint would build stale code. Aborting."
    exit 1
}

# --- 3. Start Mint job (one SSH call - Mint runner handles everything in parallel) ---
$mintJob = Start-Job -Name "mint-shard" -ScriptBlock {
    param($mintHost, $repoPath, $json, $mode)
    $env:COMMIT_SCOPE_MODE = $mode
    $json | ssh "mint-helper-01@$mintHost" "COMMIT_SCOPE_MODE=$mode bash $repoPath/scripts/run-mint-quality-shard.sh" 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "mint-shard failed with exit code $LASTEXITCODE"
    }
} -ArgumentList $MintHost, $MintRepoPath, $manifestJson, $ScopeMode

$allJobs = $jobs + $mintJob

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

Write-Host "[orchestrator] All quality checks passed. Windows $($manifest.weight_proof.windows_pct)% / Mint $($manifest.weight_proof.mint_pct)%."
