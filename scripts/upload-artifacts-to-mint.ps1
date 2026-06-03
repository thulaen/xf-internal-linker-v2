<#
.SYNOPSIS
    Upload a local shard artifact to the Mint SHA-256 blob store and prune the
    local temp copy after confirmed upload.

.DESCRIPTION
    Wrapper around scripts/mint_blob_store.py (Python).
    Refuses to delete any path outside C:\xf\ or %TEMP% — safety guard.

.PARAMETER LocalPath
    Path to the local artifact file to upload. Must be under C:\xf\temp-runs\.

.PARAMETER RunId
    Unique run identifier (e.g. run-2026-001).

.PARAMETER ShardId
    Shard identifier within the run (e.g. shard-0).

.PARAMETER Tool
    Quality tool that produced this artifact (e.g. mutmut, ruff, bandit).

.PARAMETER LogicalPath
    Logical artifact path in the run manifest (e.g. mutation/backend/results.json).

.PARAMETER MintHost
    Mint SSH hostname (default: mint).

.PARAMETER SshUser
    Mint SSH username (default: xf).

.PARAMETER MintRoot
    Mint artifact root path (default: /srv/xf).

.PARAMETER MediaType
    MIME type of the artifact (default: application/octet-stream).

.PARAMETER OptionalForMerge
    If set, marks the artifact as required_for_merge=false. Default is required.

.EXAMPLE
    & scripts\upload-artifacts-to-mint.ps1 `
        -LocalPath "C:\xf\temp-runs\run-001\mutmut\results.json" `
        -RunId "run-001" -ShardId "shard-0" `
        -Tool "mutmut" -LogicalPath "mutation/backend/results.json"
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$LocalPath,
    [Parameter(Mandatory)][string]$RunId,
    [Parameter(Mandatory)][string]$ShardId,
    [Parameter(Mandatory)][string]$Tool,
    [Parameter(Mandatory)][string]$LogicalPath,
    [string]$MintHost    = "mint",
    [string]$SshUser     = "xf",
    [string]$MintRoot    = "/srv/xf",
    [string]$MediaType   = "application/octet-stream",
    [switch]$OptionalForMerge
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python    = Join-Path $ScriptDir "..\\.venv\\Scripts\\python.exe"
if (-not (Test-Path $Python)) {
    $Python = "python"
}

# Validate path before any destructive action.
& $Python (Join-Path $ScriptDir "windows_storage.py") --validate-path $LocalPath
if ($LASTEXITCODE -ne 0) {
    Write-Error "Path validation failed — aborting upload."
    exit 1
}

# Build upload command.
$uploadArgs = @(
    (Join-Path $ScriptDir "mint_blob_store_cli.py"),
    "--local-path",  $LocalPath,
    "--run-id",      $RunId,
    "--shard-id",    $ShardId,
    "--tool",        $Tool,
    "--logical-path",$LogicalPath,
    "--mint-host",   $MintHost,
    "--ssh-user",    $SshUser,
    "--mint-root",   $MintRoot,
    "--media-type",  $MediaType
)
if ($OptionalForMerge) {
    $uploadArgs += "--optional"
}

& $Python @uploadArgs
if ($LASTEXITCODE -ne 0) {
    Write-Error "Upload to Mint failed (exit $LASTEXITCODE). Shard fails clearly — local artifact NOT deleted."
    exit 1
}

# Prune local temp only after confirmed upload.
Write-Host "Upload confirmed. Pruning local artifact: $LocalPath"
& $Python (Join-Path $ScriptDir "windows_storage.py") --validate-path $LocalPath
if ($LASTEXITCODE -ne 0) {
    Write-Error "Final path validation failed — NOT deleting: $LocalPath"
    exit 1
}

if (Test-Path -LiteralPath $LocalPath -PathType Container) {
    Remove-Item -Recurse -Force -LiteralPath $LocalPath -Confirm:$false
} else {
    Remove-Item -Force -LiteralPath $LocalPath -Confirm:$false
}
Write-Host "Pruned: $LocalPath"
