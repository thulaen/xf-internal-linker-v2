param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$DockerArgs
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$dockerConfigDir = Join-Path $repoRoot "tmp\docker-config"
$dockerConfigFile = Join-Path $dockerConfigDir "config.json"

if (-not (Test-Path $dockerConfigDir)) {
    New-Item -ItemType Directory -Force -Path $dockerConfigDir | Out-Null
}

if (-not (Test-Path $dockerConfigFile)) {
    Set-Content -Path $dockerConfigFile -Value "{}"
}

$baseArgs = @(
    "--config", $dockerConfigDir,
    "--context", "default"
)

& docker @baseArgs @DockerArgs
exit $LASTEXITCODE
