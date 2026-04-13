param(
    [switch]$Apply,
    [int]$MinimumAgeDays = 7
)

$ErrorActionPreference = "Stop"

function Get-TargetSizeBytes {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    if (-not (Test-Path -LiteralPath $Path)) {
        return 0
    }

    $item = Get-Item -LiteralPath $Path -Force
    if (-not $item.PSIsContainer) {
        return $item.Length
    }

    $sum = (
        Get-ChildItem -LiteralPath $Path -Force -Recurse -ErrorAction SilentlyContinue |
            Where-Object { -not $_.PSIsContainer } |
            Measure-Object -Property Length -Sum
    ).Sum

    if ($null -eq $sum) {
        return 0
    }

    return [int64]$sum
}

function Format-Bytes {
    param(
        [Parameter(Mandatory = $true)]
        [int64]$Bytes
    )

    if ($Bytes -ge 1GB) {
        return ("{0:N2} GB" -f ($Bytes / 1GB))
    }

    if ($Bytes -ge 1MB) {
        return ("{0:N2} MB" -f ($Bytes / 1MB))
    }

    if ($Bytes -ge 1KB) {
        return ("{0:N2} KB" -f ($Bytes / 1KB))
    }

    return "$Bytes B"
}

function Get-StaleChildren {
    param(
        [Parameter(Mandatory = $true)]
        [string]$RootPath,
        [Parameter(Mandatory = $true)]
        [datetime]$Cutoff,
        [string[]]$ExcludedPaths = @(),
        [string[]]$ExcludedNamePatterns = @()
    )

    if (-not (Test-Path -LiteralPath $RootPath)) {
        return @()
    }

    return Get-ChildItem -LiteralPath $RootPath -Force -ErrorAction SilentlyContinue |
        Where-Object {
            $_.LastWriteTime -lt $Cutoff -and
            $_.FullName -notin $ExcludedPaths -and
            -not (Test-ExcludedTarget -Item $_ -ExcludedNamePatterns $ExcludedNamePatterns)
        }
}

function Test-ExcludedTarget {
    param(
        [Parameter(Mandatory = $true)]
        [System.IO.FileSystemInfo]$Item,
        [string[]]$ExcludedNamePatterns = @()
    )

    foreach ($pattern in $ExcludedNamePatterns) {
        if ($Item.Name -like $pattern) {
            return $true
        }
    }

    return $false
}

function Remove-StaleTargets {
    param(
        [Parameter(Mandatory = $true)]
        [string]$RootPath,
        [Parameter(Mandatory = $true)]
        [string]$Label,
        [Parameter(Mandatory = $true)]
        [datetime]$Cutoff,
        [Parameter(Mandatory = $true)]
        [bool]$ApplyChanges,
        [string[]]$ExcludedPaths = @(),
        [string[]]$ExcludedNamePatterns = @()
    )

    $targets = @(
        Get-StaleChildren -RootPath $RootPath -Cutoff $Cutoff -ExcludedPaths $ExcludedPaths -ExcludedNamePatterns $ExcludedNamePatterns
    )
    if ($targets.Count -eq 0) {
        Write-Host "${Label}: nothing older than $($Cutoff.ToString('yyyy-MM-dd'))."
        return [pscustomobject]@{
            Label        = $Label
            RootPath     = $RootPath
            CandidateCnt = 0
            CandidateB   = [int64]0
            DeletedCnt   = 0
            DeletedB     = [int64]0
            SkippedCnt   = 0
        }
    }

    $candidateBytes = [int64]0
    foreach ($target in $targets) {
        $candidateBytes += Get-TargetSizeBytes -Path $target.FullName
    }

    if (-not $ApplyChanges) {
        Write-Host "$Label preview: $($targets.Count) item(s), $(Format-Bytes -Bytes $candidateBytes) reclaimable."
        return [pscustomobject]@{
            Label        = $Label
            RootPath     = $RootPath
            CandidateCnt = $targets.Count
            CandidateB   = $candidateBytes
            DeletedCnt   = 0
            DeletedB     = [int64]0
            SkippedCnt   = 0
        }
    }

    $deletedCount = 0
    $deletedBytes = [int64]0
    $skippedCount = 0

    foreach ($target in $targets) {
        $targetBytes = Get-TargetSizeBytes -Path $target.FullName
        try {
            Remove-Item -LiteralPath $target.FullName -Recurse -Force -ErrorAction Stop
            $deletedCount += 1
            $deletedBytes += $targetBytes
        } catch {
            $skippedCount += 1
            Write-Warning "Skipped locked or protected item: $($target.FullName)"
        }
    }

    Write-Host "$Label cleanup: deleted $deletedCount item(s), $(Format-Bytes -Bytes $deletedBytes) reclaimed; skipped $skippedCount."
    return [pscustomobject]@{
        Label        = $Label
        RootPath     = $RootPath
        CandidateCnt = $targets.Count
        CandidateB   = $candidateBytes
        DeletedCnt   = $deletedCount
        DeletedB     = $deletedBytes
        SkippedCnt   = $skippedCount
    }
}

$localAppData = [Environment]::GetFolderPath("LocalApplicationData")
$tempPath = Join-Path $localAppData "Temp"
$wslCrashPath = Join-Path $tempPath "wsl-crashes"
$cutoff = (Get-Date).AddDays(-1 * $MinimumAgeDays)
$tempExcludedPatterns = @(
    "DockerDesktop",
    "docker-*",
    "docker_*",
    "com.docker*",
    "dockerdesktop*"
)

Write-Host "Safe host cleanup targets:"
Write-Host " - $tempPath"
Write-Host " - $wslCrashPath"
Write-Host "Claude app data is intentionally excluded."
Write-Host "Docker-related Temp folders are intentionally excluded."
Write-Host ""

$results = @()
$results += Remove-StaleTargets -RootPath $wslCrashPath -Label "WSL crash dumps" -Cutoff $cutoff -ApplyChanges:$Apply
$results += Remove-StaleTargets -RootPath $tempPath -Label "Temp root items" -Cutoff $cutoff -ApplyChanges:$Apply -ExcludedPaths @($wslCrashPath) -ExcludedNamePatterns $tempExcludedPatterns

$candidateTotal = ($results | Measure-Object -Property CandidateB -Sum).Sum
$deletedTotal = ($results | Measure-Object -Property DeletedB -Sum).Sum

Write-Host ""
if ($Apply) {
    Write-Host "Safe host cleanup finished. Deleted $(Format-Bytes -Bytes $deletedTotal)."
} else {
    Write-Host "Preview only. Potential reclaimable space: $(Format-Bytes -Bytes $candidateTotal)."
    Write-Host "Re-run with -Apply to delete stale Temp items and WSL crash dumps."
}
