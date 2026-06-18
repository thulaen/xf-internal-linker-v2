param(
    [string]$MinioImage = "minio/minio:latest"
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

# Ensure persistent volume exists
Invoke-DellDocker "volume" "create" "xf_dell_minio_data"

# Remove existing container if present
$containerListArgs = @(
    "container", "ls", "-a",
    "--filter", "name=^xf_dell_minio$",
    "--format", "{{.Names}}"
)
$existingContainers = Invoke-DellDocker @containerListArgs
if ($existingContainers.Count -gt 0) {
    $removeArgs = @("rm", "-f") + @($existingContainers)
    Invoke-DellDocker @removeArgs
}

# Start MinIO container
$runArgs = @(
    "run", "-d",
    "--name", "xf_dell_minio",
    "--network", "xf_dell_quality",
    "-m", "256m",
    "--restart", "unless-stopped",
    "-p", "9000:9000",
    "-p", "9001:9001",
    "-v", "xf_dell_minio_data:/data",
    "-e", "MINIO_ROOT_USER=xflinker",
    "-e", "MINIO_ROOT_PASSWORD=xflinker-minio-secret",
    $MinioImage,
    "server", "/data", "--console-address", ":9001"
)
Invoke-DellDocker @runArgs

Write-Host "[DELL MINIO STARTED: context=dell container=xf_dell_minio port_api=9000 port_console=9001 image=$MinioImage]"
