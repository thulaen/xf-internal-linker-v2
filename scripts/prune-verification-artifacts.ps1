param()

$ErrorActionPreference = "Stop"

. (Join-Path $PSScriptRoot "dev-tools.ps1")

$repoRoot = Get-RepoRoot

function Remove-DirectoryIfExists {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,
        [Parameter(Mandatory = $true)]
        [string]$Label
    )

    if (-not (Test-Path -LiteralPath $Path)) {
        return
    }

    Write-Host "Pruning $Label..."
    Remove-Item -LiteralPath $Path -Recurse -Force
}

Remove-DirectoryIfExists -Path (Join-Path $repoRoot "frontend\dist") -Label "frontend dist output"
Remove-DirectoryIfExists -Path (Join-Path $repoRoot "frontend\.angular\cache") -Label "Angular build cache"
Remove-DirectoryIfExists -Path (Join-Path $repoRoot "backend\extensions\build") -Label "native extension build cache"
Remove-DirectoryIfExists -Path (Join-Path $repoRoot "backend\extensions\__pycache__") -Label "native extension Python cache"

$httpWorkerRoot = Join-Path $repoRoot "services\http-worker"
$dotnetArtifactDirs = Get-ChildItem -Path $httpWorkerRoot -Directory -Recurse |
    Where-Object { $_.Name -in @("bin", "obj") } |
    Sort-Object -Property FullName -Descending

foreach ($dir in $dotnetArtifactDirs) {
    Remove-DirectoryIfExists -Path $dir.FullName -Label "HttpWorker $($dir.Name) folder at $($dir.FullName)"
}

$dockerAvailability = Get-DockerAvailability
if ($dockerAvailability.Status -eq "ok") {
    $dockerSafe = Get-DockerSafeScript
    Write-Host "Pruning Docker builder cache..."
    & $dockerSafe builder prune -f
    if ($LASTEXITCODE -ne 0) {
        throw "Docker builder prune failed with exit code $LASTEXITCODE."
    }

    Write-Host "Pruning dangling Docker images..."
    & $dockerSafe image prune -f
    if ($LASTEXITCODE -ne 0) {
        throw "Docker image prune failed with exit code $LASTEXITCODE."
    }
} else {
    Write-Host "Skipping Docker prune. $(Get-DockerUnavailableMessage -Availability $dockerAvailability)"
}

Write-Host "Verification artifact prune completed."
