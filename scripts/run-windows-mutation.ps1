<#
.SYNOPSIS
    Run focused mutmut Python mutation tests on the Windows-assigned shard.

.DESCRIPTION
    Accepts a comma-separated list of repo-relative file paths, runs mutmut
    on each, writes results to C:\xf\temp-runs\<RunId>\mutation\results.json,
    uploads to Mint, then prunes the local temp.

.PARAMETER RunId
    Unique run identifier.

.PARAMETER ShardId
    Shard identifier.

.PARAMETER ShardFiles
    Comma-separated repo-relative Python paths assigned to this shard.

.PARAMETER MintHost
    Mint SSH hostname (default: mint).

.PARAMETER SshUser
    Mint SSH username (default: xf).

.EXAMPLE
    & scripts\run-windows-mutation.ps1 `
        -RunId "run-001" -ShardId "shard-0" `
        -ShardFiles "backend/apps/audit/tasks.py"
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$RunId,
    [Parameter(Mandatory)][string]$ShardId,
    [Parameter(Mandatory)][string]$ShardFiles,
    [string]$MintHost = "mint",
    [string]$SshUser  = "xf",
    [string]$RepoRoot = (Join-Path $PSScriptRoot "..")
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ScriptDir  = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python     = Join-Path $ScriptDir "..\\.venv\\Scripts\\python.exe"
$OutputDir  = "C:\xf\temp-runs\$RunId\mutation"
$TimeoutSec = 300  # 5-minute cap

New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

$Files = $ShardFiles -split "," | ForEach-Object { $_.Trim() } | Where-Object { $_ }

if ($Files.Count -eq 0) {
    Write-Error "No shard files provided. Pass -ShardFiles 'path/a.py,path/b.py'."
    exit 1
}

Write-Host "Running mutmut on $($Files.Count) file(s) for run=$RunId shard=$ShardId"
$Results = [System.Collections.Generic.List[hashtable]]::new()

foreach ($file in $Files) {
    $absFile = Join-Path $RepoRoot $file
    if (-not (Test-Path $absFile)) {
        Write-Warning "File not found, skipping: $file"
        continue
    }
    Write-Host "  mutmut: $file"
    $job = Start-Job -ScriptBlock {
        Set-Location $using:RepoRoot
        $backendRoot = Join-Path $using:RepoRoot "backend"
        $relativePath = $using:file
        if ($relativePath.StartsWith("backend/") -or $relativePath.StartsWith("backend\")) {
            $relativePath = $relativePath.Substring("backend/".Length)
        }
        $escapedPath = $relativePath.Replace("\", "/").Replace("'", "''")
        $config = @"
[tool.mutmut]
paths_to_mutate = ['$escapedPath']
also_copy = ['apps', 'config', 'pytest.ini', 'conftest.py']
pytest_add_cli_args = ['-o', 'addopts=', 'apps']
"@
        $workDir = Join-Path ([System.IO.Path]::GetTempPath()) ("xf-mutmut-" + [System.Guid]::NewGuid().ToString("N"))
        New-Item -ItemType Directory -Force -Path $workDir | Out-Null
        Copy-Item -Path (Join-Path $backendRoot "pytest.ini") -Destination $workDir -ErrorAction SilentlyContinue
        Copy-Item -Path (Join-Path $backendRoot "conftest.py") -Destination $workDir -ErrorAction SilentlyContinue
        New-Item -ItemType SymbolicLink -Path (Join-Path $workDir "apps") -Target (Join-Path $backendRoot "apps") | Out-Null
        New-Item -ItemType SymbolicLink -Path (Join-Path $workDir "config") -Target (Join-Path $backendRoot "config") | Out-Null
        Set-Content -Path (Join-Path $workDir "pyproject.toml") -Value $config -Encoding UTF8
        Set-Location $workDir
        & python -m mutmut run --max-children 2 2>&1
        & python -m mutmut results 2>&1
    }
    $completed = Wait-Job $job -Timeout $TimeoutSec
    $output = if ($completed) { Receive-Job $job } else { Stop-Job $job; "TIMEOUT" }
    Remove-Job $job -Force

    $Results.Add(@{
        file    = $file
        output  = ($output -join "`n")
        timeout = (-not $completed)
    })
}

# Write JSON results file.
$resultsFile = Join-Path $OutputDir "results.json"
$Results | ConvertTo-Json -Depth 5 | Out-File $resultsFile -Encoding utf8

Write-Host "Mutation results written to $resultsFile"

# Upload to Mint.
& (Join-Path $ScriptDir "upload-artifacts-to-mint.ps1") `
    -LocalPath $resultsFile `
    -RunId $RunId -ShardId $ShardId `
    -Tool "mutmut" -LogicalPath "mutation/$RunId/results.json" `
    -MediaType "application/json" `
    -MintHost $MintHost -SshUser $SshUser

Write-Host "Windows mutation shard complete: run=$RunId shard=$ShardId"
