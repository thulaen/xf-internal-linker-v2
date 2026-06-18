param(
    [switch]$Rebuild
)

$ErrorActionPreference = "Stop"

function Invoke-DellDocker {
    param(
        [Parameter(ValueFromRemainingArguments = $true)]
        [string[]]$DockerArgs
    )
    & ssh dell docker @DockerArgs
    if ($LASTEXITCODE -ne 0) {
        throw "Dell Docker command failed: ssh dell docker $($DockerArgs -join ' ')"
    }
}

# Ensure network exists
$networkListArgs = @("network", "ls", "--format", "{{.Name}}")
$networkNames = Invoke-DellDocker @networkListArgs
$networkExists = $networkNames -contains "xf_dell_quality"
if (-not $networkExists) {
    Invoke-DellDocker "network" "create" "xf_dell_quality"
}

# Remove existing container if present
$containerListArgs = @(
    "container", "ls", "-a",
    "--filter", "name=^xf_dell_docs$",
    "--format", "{{.Names}}"
)
$existingContainers = Invoke-DellDocker @containerListArgs
if ($existingContainers.Count -gt 0) {
    $removeArgs = @("rm", "-f") + @($existingContainers)
    Invoke-DellDocker @removeArgs
}

if ($Rebuild) {
    Write-Host "Building xf_docs_image through smart build routing..."
    $smartBuild = Join-Path $PSScriptRoot "smart_build.py"
    python $smartBuild --target docs-site
    if ($LASTEXITCODE -ne 0) {
        throw "Smart build failed for docs-site."
    }
}

# Start Docs container
$runArgs = @(
    "run", "-d",
    "--name", "xf_dell_docs",
    "--network", "xf_dell_quality",
    "-m", "256m",
    "--restart", "unless-stopped",
    "-p", "3000:80",
    "xf_docs_image"
)
Invoke-DellDocker @runArgs

Write-Host "[DELL DOCS STARTED: context=dell container=xf_dell_docs port=3000]"
