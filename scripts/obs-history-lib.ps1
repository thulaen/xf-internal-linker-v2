$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function Get-XfRepoRoot {
    return (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
}

function Get-XfHistoryVolumeMap {
    $mapPath = Join-Path (Get-XfRepoRoot) 'k8s\obs\history-copy\volume-map.json'
    if (-not (Test-Path -LiteralPath $mapPath)) {
        throw "volume map not found: $mapPath"
    }
    return Get-Content -LiteralPath $mapPath -Raw | ConvertFrom-Json
}

function Get-XfDefaultHistoryVolumes {
    $map = Get-XfHistoryVolumeMap
    return @($map.volumes | ForEach-Object { $_.volume })
}

function Test-XfScpTarget {
    param([Parameter(Mandatory)] [string]$Target)
    return ($Target -match '^[^\\/]+@[^:]+:.+$') -or
           ($Target -match '^[A-Za-z0-9._-]{2,}:/.+$')
}

function Get-XfStagedSha256 {
    param(
        [Parameter(Mandatory)] [string]$Target,
        [Parameter(Mandatory)] [string]$ShaFileName
    )
    if (Test-XfScpTarget -Target $Target) {
        $parts = $Target -split ':', 2
        $host_ = $parts[0]
        $path = $parts[1].TrimEnd('/')
        $remote = & ssh -o BatchMode=yes $host_ "cat '$path/$ShaFileName' 2>/dev/null"
        if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($remote)) { return $null }
        return ($remote -split '\s+')[0].Trim().ToLower()
    }
    $remotePath = Join-Path $Target $ShaFileName
    if (-not (Test-Path -LiteralPath $remotePath)) { return $null }
    return ((Get-Content -LiteralPath $remotePath -Raw) -split '\s+')[0].Trim().ToLower()
}
