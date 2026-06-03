<#
.SYNOPSIS
    Run Python quality checks for the Windows-assigned shard using the repo .venv.

.DESCRIPTION
    Runs ruff, pylint, bandit, and mutmut on the Windows-assigned Python files.
    Writes outputs to C:\xf\temp-runs\<RunId>\python-quality\.
    Uploads each tool's output to Mint after completion.
    Enforces a 5-minute wall-clock cap per tool (matching run-python-quality.sh).

.PARAMETER RunId
    Unique run identifier (e.g. run-2026-001).

.PARAMETER ShardId
    Windows shard identifier (e.g. shard-0).

.PARAMETER ShardFiles
    Comma-separated list of repo-relative Python file paths for this shard.

.PARAMETER MintHost
    Mint SSH hostname (default: mint).

.PARAMETER SshUser
    Mint SSH username (default: xf).

.EXAMPLE
    & scripts\run-windows-python-quality.ps1 `
        -RunId "run-001" -ShardId "shard-0" `
        -ShardFiles "backend/apps/audit/tasks.py,backend/apps/audit/models.py"
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$RunId,
    [Parameter(Mandatory)][string]$ShardId,
    [string]$ShardFiles = "",
    [string]$MintHost   = "mint",
    [string]$SshUser    = "xf",
    [string]$RepoRoot   = $PSScriptRoot + "\..\"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ScriptDir  = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python     = Join-Path $ScriptDir "..\\.venv\\Scripts\\python.exe"
$OutputRoot = "C:\xf\temp-runs\$RunId\python-quality"
$TimeoutSec = 300   # 5-minute cap per tool

New-Item -ItemType Directory -Force -Path $OutputRoot | Out-Null

$Files = if ($ShardFiles) { $ShardFiles -split "," | ForEach-Object { $_.Trim() } } else { @() }
$FileArgs = $Files | ForEach-Object { $_ }

function Invoke-Tool {
    param([string]$ToolName, [scriptblock]$Command, [string]$OutFile)
    Write-Host "`n=== $ToolName ==="
    $job = Start-Job -ScriptBlock $Command
    $completed = Wait-Job $job -Timeout $TimeoutSec
    if (-not $completed) {
        Stop-Job $job
        Write-Warning "$ToolName timed out after $TimeoutSec seconds."
        "TIMEOUT after ${TimeoutSec}s" | Out-File $OutFile -Encoding utf8
        return $false
    }
    $output = Receive-Job $job
    $output | Out-File $OutFile -Encoding utf8
    Remove-Job $job
    Write-Host "$ToolName output: $OutFile"
    return $true
}

# ── ruff ─────────────────────────────────────────────────────────────────────
$ruffOut = Join-Path $OutputRoot "ruff.json"
if ($Files.Count -gt 0) {
    Invoke-Tool "ruff" {
        & python -m ruff check --output-format=json $using:FileArgs 2>&1
    } $ruffOut
} else {
    Invoke-Tool "ruff" {
        & python -m ruff check --output-format=json . 2>&1
    } $ruffOut
}

# ── pylint ────────────────────────────────────────────────────────────────────
$pylintOut = Join-Path $OutputRoot "pylint.json"
if ($Files.Count -gt 0) {
    Invoke-Tool "pylint" {
        & python -m pylint --output-format=json $using:FileArgs 2>&1
    } $pylintOut
} else {
    "[]" | Out-File $pylintOut -Encoding utf8
    Write-Host "pylint: no specific files, skipped"
}

# ── bandit ───────────────────────────────────────────────────────────────────
$banditOut = Join-Path $OutputRoot "bandit.json"
if ($Files.Count -gt 0) {
    Invoke-Tool "bandit" {
        & python -m bandit -f json $using:FileArgs 2>&1
    } $banditOut
} else {
    Invoke-Tool "bandit" {
        & python -m bandit -f json -r backend/ 2>&1
    } $banditOut
}

# ── Upload each artifact to Mint ──────────────────────────────────────────────
foreach ($outFile in @($ruffOut, $pylintOut, $banditOut)) {
    if (Test-Path $outFile) {
        $toolName  = [System.IO.Path]::GetFileNameWithoutExtension($outFile)
        $logicPath = "python-quality/$RunId/$toolName.json"
        try {
            & (Join-Path $ScriptDir "upload-artifacts-to-mint.ps1") `
                -LocalPath $outFile `
                -RunId $RunId -ShardId $ShardId `
                -Tool $toolName -LogicalPath $logicPath `
                -MintHost $MintHost -SshUser $SshUser
        } catch {
            Write-Warning "Upload failed for $toolName — continuing. Error: $_"
        }
    }
}

Write-Host "`nWindows Python quality checks complete for run=$RunId shard=$ShardId"
