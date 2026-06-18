param(
    [int]$TimeoutSeconds = 20,
    [switch]$NoFile
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$outDir = Join-Path $repoRoot ".tmp\cluster-helper-health"
$outFile = Join-Path $outDir "latest.json"
$mintSshHost = if ($env:XF_MINT_SSH_HOST) { $env:XF_MINT_SSH_HOST } else { "mint-wifi" }
New-Item -ItemType Directory -Force -Path $outDir | Out-Null

function Invoke-CommandProbe {
    param(
        [string]$Name,
        [string]$Expected,
        [string[]]$Command
    )

    $job = Start-Job -ScriptBlock {
        param([string[]]$JobCommand)
        $probeOutput = & $JobCommand[0] $JobCommand[1..($JobCommand.Length - 1)] 2>&1 | Out-String
        [ordered]@{
            output = $probeOutput
            exitCode = $LASTEXITCODE
        }
    } -ArgumentList (,$Command)

    $completed = Wait-Job -Timeout $TimeoutSeconds -Job $job
    if (-not $completed) {
        Stop-Job -Job $job -ErrorAction SilentlyContinue
        Remove-Job -Job $job -Force -ErrorAction SilentlyContinue
        return [ordered]@{
            name = $Name
            status = "timeout"
            command = ($Command -join " ")
            expected = $Expected
            output = ""
            error = "$Name timed out after $TimeoutSeconds seconds."
            returncode = $null
        }
    }

    $result = Receive-Job -Job $job
    Remove-Job -Job $job -Force -ErrorAction SilentlyContinue
    $output = [string]$result.output
    $exitCode = [int]$result.exitCode
    if ($exitCode -eq 0) {
        return [ordered]@{
            name = $Name
            status = "ok"
            command = ($Command -join " ")
            expected = $Expected
            output = ($output.Trim())
            error = ""
            returncode = 0
        }
    }
    return [ordered]@{
        name = $Name
        status = "error"
        command = ($Command -join " ")
        expected = $Expected
        output = ""
        error = ($output.Trim())
        returncode = $exitCode
    }
}

$payload = [ordered]@{
    generated_at = (Get-Date).ToUniversalTime().ToString("o")
    results = @(
        [ordered]@{
            target = "kubernetes-cluster"
            host = "MSI kubectl to live cluster"
            probes = @(
                Invoke-CommandProbe -Name "kubectl-nodes" -Expected "Kubernetes nodes are reachable" -Command @("kubectl", "get", "nodes")
                Invoke-CommandProbe -Name "backend-health" -Expected "Backend responds through Kubernetes" -Command @("python", "scripts/backend_manage.py", "check")
            )
        }
        [ordered]@{
            target = "dell-helper"
            host = "Dell helper over SSH"
            probes = @(
                Invoke-CommandProbe -Name "dell-docker-version" -Expected "Dell Docker answers over SSH" -Command @("ssh", "dell", "docker", "version")
                Invoke-CommandProbe -Name "dell-docker-ps" -Expected "Dell can list helper containers" -Command @("ssh", "dell", "docker", "ps")
            )
        }
        [ordered]@{
            target = "mint-helper"
            host = "Mint helper over SSH"
            probes = @(
                Invoke-CommandProbe -Name "mint-kubelet" -Expected "Mint cluster helper answers SSH" -Command @("ssh", $mintSshHost, "systemctl", "is-active", "k3s")
            )
        }
    )
}

$payload | ConvertTo-Json -Depth 8 | Set-Content -Path $outFile -Encoding UTF8

if (-not $NoFile) {
    $namespace = if ($env:XF_BACKEND_MANAGE_NAMESPACE) { $env:XF_BACKEND_MANAGE_NAMESPACE } else { "xf-app" }
    $selector = if ($env:XF_BACKEND_MANAGE_SELECTOR) { $env:XF_BACKEND_MANAGE_SELECTOR } else { "app=backend" }
    $pod = kubectl -n $namespace get pod -l $selector -o jsonpath='{.items[0].metadata.name}'
    if (-not $pod) {
        throw "Could not find a Kubernetes backend pod for health report import."
    }
    kubectl -n $namespace cp $outFile "$pod`:/tmp/cluster-helper-health-latest.json"
    python scripts/backend_manage.py check_docker_health --from-json /tmp/cluster-helper-health-latest.json --timeout-seconds "$TimeoutSeconds"
}
