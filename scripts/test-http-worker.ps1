param(
    [ValidateSet("Debug", "Release")]
    [string]$Configuration = "Release",
    [switch]$NoCache,
    [switch]$UseDocker
)

$ErrorActionPreference = "Stop"

. (Join-Path $PSScriptRoot "dev-tools.ps1")

$repoRoot = Split-Path -Parent $PSScriptRoot
$serviceDir = Join-Path $repoRoot "services/http-worker"
$dockerfile = Join-Path $serviceDir "Dockerfile"

if ($UseDocker) {
    $dockerAvailability = Get-DockerAvailability
    if ($dockerAvailability.Status -ne "ok") {
        throw (Get-DockerUnavailableMessage -Availability $dockerAvailability)
    }

    $dockerSafe = Get-DockerSafeScript
    $args = @(
        "build",
        "--target", "test",
        "-f", $dockerfile
    )

    if ($NoCache) {
        $args += "--no-cache"
    }

    $args += @(
        "--build-arg", "CONFIGURATION=$Configuration",
        "--build-arg", "RUN_BENCHMARKS=1",
        $serviceDir
    )

    Write-Host "Running HttpWorker tests in Docker..."
    & $dockerSafe @args
    if ($LASTEXITCODE -ne 0) {
        throw "HttpWorker Docker test image failed with exit code $LASTEXITCODE."
    }

    return
}

if ($NoCache) {
    Write-Warning "-NoCache only applies when -UseDocker is set."
}

Write-Host "Building HttpWorker solution on the host..."
$previousBenchmarkSetting = $env:HTTPWORKER_RUN_BENCHMARKS
$env:HTTPWORKER_RUN_BENCHMARKS = "1"

try {
    Invoke-HostDotnet -WorkingDirectory $serviceDir -Arguments @(
        "build",
        "HttpWorker.sln",
        "--configuration", $Configuration,
        "--nologo"
    )

    Write-Host "Running HttpWorker tests on the host..."
    Invoke-HostDotnet -WorkingDirectory $serviceDir -Arguments @(
        "test",
        "HttpWorker.sln",
        "--no-build",
        "--configuration", $Configuration,
        "--verbosity", "normal",
        "--nologo"
    )
} finally {
    if ($null -eq $previousBenchmarkSetting) {
        Remove-Item Env:HTTPWORKER_RUN_BENCHMARKS -ErrorAction SilentlyContinue
    } else {
        $env:HTTPWORKER_RUN_BENCHMARKS = $previousBenchmarkSetting
    }
}
