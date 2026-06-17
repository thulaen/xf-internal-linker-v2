<#
.SYNOPSIS
    SLICE-21 GO-LIVE CLOSEOUT — mark old monitoring Docker volumes as retired,
    while keeping them available for rollback.

.DESCRIPTION
    Plain English: after monitoring history has been copied into the cluster and
    the cluster restore Jobs have succeeded, the old Docker volumes should no
    longer be written to. This script records that state in a JSON manifest. It
    does not delete, prune, or rename any Docker volume.

    Run only after go-live. The required -ConfirmGoLiveComplete switch prevents
    accidental rehearsal use.
#>

[CmdletBinding()]
param(
    [string]$StagingTarget = '\\10.10.10.91\cluster\obs-history-staging',
    [string]$ManifestPath = '',
    [switch]$ConfirmGoLiveComplete
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
. "$PSScriptRoot\obs-history-lib.ps1"

function Resolve-ManifestPath {
    if (-not [string]::IsNullOrWhiteSpace($ManifestPath)) {
        return $ManifestPath
    }
    if (Test-XfScpTarget -Target $StagingTarget) {
        throw 'ManifestPath is required when StagingTarget is an scp destination.'
    }
    return Join-Path $StagingTarget 'retired-volumes-manifest.json'
}

function Get-StagedSha {
    param([Parameter(Mandatory)] [string]$Volume)
    $shaFileName = "$Volume.tar.gz.sha256"
    $sha = Get-XfStagedSha256 -Target $StagingTarget -ShaFileName $shaFileName
    if ([string]::IsNullOrWhiteSpace($sha)) {
        throw "staged fingerprint missing for $Volume at $StagingTarget"
    }
    return $sha
}

function Get-DockerVolumeInfo {
    param([Parameter(Mandatory)] [string]$Volume)
    $raw = docker volume inspect $Volume
    if ($LASTEXITCODE -ne 0) {
        throw "Docker volume not found: $Volume"
    }
    return ($raw | ConvertFrom-Json)[0]
}

if (-not $ConfirmGoLiveComplete) {
    throw 'Refusing to retire volumes without -ConfirmGoLiveComplete.'
}

$map = Get-XfHistoryVolumeMap
$records = @()
foreach ($entry in $map.volumes) {
    $volume = [string]$entry.volume
    $info = Get-DockerVolumeInfo -Volume $volume
    $records += [ordered]@{
        volume = $volume
        pvc = [string]$entry.pvc
        staged_sha256 = Get-StagedSha -Volume $volume
        docker_mountpoint = [string]$info.Mountpoint
        retired_kept = $true
    }
}

$manifest = [ordered]@{
    retired_at = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
    note = 'Old monitoring Docker volumes are retired from writes and kept for rollback. No delete was performed.'
    volumes = $records
}

$out = Resolve-ManifestPath
$parent = Split-Path -Parent $out
if ($parent -and -not (Test-Path -LiteralPath $parent)) {
    New-Item -ItemType Directory -Path $parent -Force | Out-Null
}
$manifest | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $out -Encoding utf8
Write-Host "retirement manifest written: $out"
Write-Host 'old Docker volumes were kept; no delete, prune, or rename was run.'
