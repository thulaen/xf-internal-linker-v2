param(
    [switch]$Rebuild
)

$ErrorActionPreference = "Stop"

function Invoke-DellDocker {
    param(
        [Parameter(ValueFromRemainingArguments = $true)]
        [string[]]$DockerArgs
    )
    & docker --context dell @DockerArgs
    if ($LASTEXITCODE -ne 0) {
        throw "Dell Docker command failed: docker --context dell $($DockerArgs -join ' ')"
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

# Rebuild image if requested (building directly on Dell)
# The docs-site must be synced to Dell first, but for now we build via buildx or local daemon
if ($Rebuild) {
    Write-Host "Building xf_docs_image locally and transferring to Dell..."
    # Build locally
    docker build -t xf_docs_image docs-site
    if ($LASTEXITCODE -ne 0) { throw "Local build failed." }
    
    # Save, transfer and load
    Write-Host "Transferring image..."
    $tempTar = Join-Path $env:TEMP "xf_docs_image.tar"
    docker save -o $tempTar xf_docs_image
    docker --context dell load -i $tempTar
    Remove-Item $tempTar -ErrorAction SilentlyContinue
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
