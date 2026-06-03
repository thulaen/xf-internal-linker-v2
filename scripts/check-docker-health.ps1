param(
    [int]$TimeoutSeconds = 20,
    [switch]$NoFile
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$outDir = Join-Path $repoRoot ".tmp\docker-health"
$outFile = Join-Path $outDir "latest.json"
New-Item -ItemType Directory -Force -Path $outDir | Out-Null

function Invoke-DockerProbe {
    param(
        [string]$Target,
        [string]$HostLabel,
        [string]$Context,
        [string]$Probe
    )

    $commandText = "docker --context $Context $Probe"
    $job = Start-Job -ScriptBlock {
        param([string]$JobContext, [string]$JobProbe)
        $probeOutput = & docker --context $JobContext $JobProbe 2>&1 | Out-String
        [ordered]@{
            output = $probeOutput
            exitCode = $LASTEXITCODE
        }
    } -ArgumentList $Context, $Probe

    $completed = Wait-Job -Timeout $TimeoutSeconds -Job $job
    if (-not $completed) {
        Stop-Job -Job $job -ErrorAction SilentlyContinue
        Remove-Job -Job $job -Force -ErrorAction SilentlyContinue
        return [ordered]@{
            name = $Probe
            status = "timeout"
            command = $commandText
            expected = "Docker $Probe succeeds"
            output = ""
            error = "Docker $Probe on $HostLabel timed out after $TimeoutSeconds seconds."
            returncode = $null
        }
    }

    $result = Receive-Job -Job $job
    Remove-Job -Job $job -Force -ErrorAction SilentlyContinue
    $output = [string]$result.output
    $exitCode = [int]$result.exitCode
    if ($exitCode -eq 0) {
        return [ordered]@{
            name = $Probe
            status = "ok"
            command = $commandText
            expected = "Docker $Probe succeeds"
            output = ($output.Trim())
            error = ""
            returncode = 0
        }
    }
    return [ordered]@{
        name = $Probe
        status = "error"
        command = $commandText
        expected = "Docker $Probe succeeds"
        output = ""
        error = ($output.Trim())
        returncode = $exitCode
    }
}

function Invoke-DockerTarget {
    param(
        [string]$Target,
        [string]$HostLabel,
        [string]$Context
    )

    $probes = @(
        Invoke-DockerProbe -Target $Target -HostLabel $HostLabel -Context $Context -Probe "version"
        Invoke-DockerProbe -Target $Target -HostLabel $HostLabel -Context $Context -Probe "ps"
        Invoke-DockerProbe -Target $Target -HostLabel $HostLabel -Context $Context -Probe "info"
    )
    return [ordered]@{
        target = $Target
        host = $HostLabel
        probes = $probes
    }
}

$payload = [ordered]@{
    generated_at = (Get-Date).ToUniversalTime().ToString("o")
    results = @(
        Invoke-DockerTarget -Target "windows-docker-desktop" -HostLabel "Windows laptop Docker Desktop" -Context "desktop-linux"
        Invoke-DockerTarget -Target "mint-docker" -HostLabel "Mint helper Docker daemon" -Context "mint"
    )
}

$payload | ConvertTo-Json -Depth 8 | Set-Content -Path $outFile -Encoding UTF8

$backendPath = "/repo/.tmp/docker-health/latest.json"
$argsForManage = @("python", "manage.py", "check_docker_health", "--from-json", $backendPath, "--timeout-seconds", "$TimeoutSeconds")
if ($NoFile) {
    $argsForManage += "--no-file"
}

docker --context desktop-linux compose exec -T backend @argsForManage
