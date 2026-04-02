param(
    [ValidateSet("Debug", "Release")]
    [string]$Configuration = "Release",
    [switch]$NoCache
)

$repoRoot = Split-Path -Parent $PSScriptRoot
$serviceDir = Join-Path $repoRoot "services/http-worker"
$dockerfile = Join-Path $serviceDir "Dockerfile"

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
    $serviceDir
)

& docker @args
exit $LASTEXITCODE
