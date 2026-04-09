Set-StrictMode -Version Latest

function Get-RepoRoot {
    return (Split-Path -Parent $PSScriptRoot)
}

function Get-VenvPython {
    $python = Join-Path (Get-RepoRoot) ".venv\Scripts\python.exe"
    if (-not (Test-Path $python)) {
        throw "Repo virtual environment is missing. Run scripts/setup-dev.ps1 first."
    }
    return $python
}

function Resolve-CommandLocation {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Command
    )

    if (Test-Path $Command) {
        return (Resolve-Path $Command).Path
    }

    try {
        $resolved = Get-Command -Name $Command -ErrorAction Stop | Select-Object -First 1
        if ($null -ne $resolved) {
            if ($resolved.Path) {
                return $resolved.Path
            }

            if ($resolved.Source) {
                return $resolved.Source
            }
        }
    } catch {
        return $null
    }

    return $null
}

function Get-SummaryMessageLine {
    param(
        [string]$Text
    )

    if ([string]::IsNullOrWhiteSpace($Text)) {
        return $null
    }

    $lines = @(
        $Text -split "(`r`n|`n|`r)" |
            Where-Object { -not [string]::IsNullOrWhiteSpace($_) } |
            ForEach-Object { $_.Trim() }
    )

    if ($lines.Count -eq 0) {
        return $null
    }

    $priorityPatterns = @(
        '(?i)access is denied',
        '(?i)permission denied',
        '(?i)cannot connect',
        '(?i)error during connect',
        '(?i)daemon',
        '(?i)failed',
        '(?i)error',
        '(?i)not found'
    )

    foreach ($pattern in $priorityPatterns) {
        $match = $lines | Where-Object { $_ -match $pattern } | Select-Object -First 1
        if ($match) {
            return $match
        }
    }

    return $lines[0]
}

function Test-HostTool {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Command,
        [string[]]$Arguments = @("--version")
    )

    $resolvedPath = Resolve-CommandLocation -Command $Command

    try {
        $output = & $Command @Arguments 2>&1 | Out-String
        $exitCode = $LASTEXITCODE
    } catch {
        $message = $_.Exception.Message.Trim()
        if ([string]::IsNullOrWhiteSpace($message)) {
            $message = ($_ | Out-String).Trim()
        }

        $status = "failed"
        if ($message -match '(?i)access is denied|permission denied') {
            $status = "access_denied"
        } elseif (($_.FullyQualifiedErrorId -like '*CommandNotFoundException*') -or ((-not $resolvedPath) -and ($message -match '(?i)not recognized as the name|cannot find|no such file'))) {
            $status = "missing"
        }

        return [pscustomobject]@{
            Status  = $status
            Command = $Command
            Path    = $resolvedPath
            ExitCode = $null
            Message = (Get-SummaryMessageLine -Text $message)
            Output  = $message
        }
    }

    if ($exitCode -eq 0) {
        return [pscustomobject]@{
            Status  = "ok"
            Command = $Command
            Path    = $resolvedPath
            ExitCode = $exitCode
            Message = (Get-SummaryMessageLine -Text $output)
            Output  = $output
        }
    }

    return [pscustomobject]@{
        Status  = "failed"
        Command = $Command
        Path    = $resolvedPath
        ExitCode = $exitCode
        Message = (Get-SummaryMessageLine -Text $output)
        Output  = $output
    }
}

function Get-NodeRuntimeState {
    $candidates = @(
        [pscustomobject]@{
            Node = (Join-Path $env:LOCALAPPDATA "Programs\nodejs\node.exe")
            Npm  = (Join-Path $env:LOCALAPPDATA "Programs\nodejs\npm.cmd")
            Mode = "local"
        },
        [pscustomobject]@{
            Node = "node"
            Npm  = "npm"
            Mode = "path"
        }
    )

    $probeResults = @()

    foreach ($candidate in $candidates) {
        $probe = Test-HostTool -Command $candidate.Node -Arguments @("--version")
        if ($probe.Status -eq "ok") {
            return [pscustomobject]@{
                Status  = "ok"
                Node    = $candidate.Node
                Npm     = $candidate.Npm
                Mode    = $candidate.Mode
                Path    = $(if ($probe.Path) { $probe.Path } else { $candidate.Node })
                Message = $probe.Message
            }
        }

        $probeResults += [pscustomobject]@{
            Candidate = $candidate
            Probe     = $probe
        }
    }

    $accessDenied = $probeResults | Where-Object { $_.Probe.Status -eq "access_denied" } | Select-Object -First 1
    if ($accessDenied) {
        $blockedPath = if ($accessDenied.Probe.Path) { $accessDenied.Probe.Path } else { $accessDenied.Candidate.Node }
        return [pscustomobject]@{
            Status  = "access_denied"
            Node    = $accessDenied.Candidate.Node
            Npm     = $accessDenied.Candidate.Npm
            Mode    = $accessDenied.Candidate.Mode
            Path    = $blockedPath
            Message = "Node.js is installed at '$blockedPath', but this shell is not allowed to execute it. Rerun outside the sandbox or with elevated access."
        }
    }

    $failedProbe = $probeResults | Where-Object { $_.Probe.Status -eq "failed" } | Select-Object -First 1
    if ($failedProbe) {
        $failedPath = if ($failedProbe.Probe.Path) { $failedProbe.Probe.Path } else { $failedProbe.Candidate.Node }
        $failedReason = if ($failedProbe.Probe.Message) { $failedProbe.Probe.Message } else { "Unknown probe failure." }
        return [pscustomobject]@{
            Status  = "failed"
            Node    = $failedProbe.Candidate.Node
            Npm     = $failedProbe.Candidate.Npm
            Mode    = $failedProbe.Candidate.Mode
            Path    = $failedPath
            Message = "Node.js probe failed for '$failedPath'. $failedReason"
        }
    }

    return [pscustomobject]@{
        Status  = "missing"
        Node    = $null
        Npm     = $null
        Mode    = $null
        Path    = $null
        Message = "No working Node.js runtime found. Expected a local install under AppData or a PATH-based node/npm."
    }
}

function Get-NodePaths {
    $state = Get-NodeRuntimeState
    if ($state.Status -ne "ok") {
        throw $state.Message
    }

    return [pscustomobject]@{
        Node = $state.Node
        Npm  = $state.Npm
        Mode = $state.Mode
        Path = $state.Path
    }
}

function Get-DockerSafeScript {
    $script = Join-Path $PSScriptRoot "docker-safe.ps1"
    if (-not (Test-Path $script)) {
        throw "Docker helper script was not found at $script."
    }
    return $script
}

function Get-DockerAvailability {
    $dockerProbe = Test-HostTool -Command "docker" -Arguments @("--version")
    if ($dockerProbe.Status -eq "missing") {
        return [pscustomobject]@{
            Status  = "binary_missing"
            Path    = $null
            Message = "Docker is not installed or not on PATH."
            Output  = $null
        }
    }

    if ($dockerProbe.Status -eq "access_denied") {
        $blockedPath = if ($dockerProbe.Path) { $dockerProbe.Path } else { "docker" }
        return [pscustomobject]@{
            Status  = "access_denied"
            Path    = $blockedPath
            Message = "Docker is installed at '$blockedPath', but this shell is not allowed to execute it. Rerun outside the sandbox or with elevated access."
            Output  = $dockerProbe.Output
        }
    }

    if ($dockerProbe.Status -eq "failed") {
        return [pscustomobject]@{
            Status  = "failed"
            Path    = $dockerProbe.Path
            Message = "Docker is installed, but the client probe failed. $($dockerProbe.Message)"
            Output  = $dockerProbe.Output
        }
    }

    $dockerSafe = Get-DockerSafeScript

    try {
        $output = & $dockerSafe version 2>&1 | Out-String
        $exitCode = $LASTEXITCODE
    } catch {
        $message = $_.Exception.Message.Trim()
        if ([string]::IsNullOrWhiteSpace($message)) {
            $message = ($_ | Out-String).Trim()
        }

        if ($message -match '(?i)permission denied while trying to connect|error during connect|cannot connect to the docker daemon|open //\./pipe/docker_engine|daemon is not running|docker daemon') {
            return [pscustomobject]@{
                Status  = "daemon_inaccessible"
                Path    = $dockerProbe.Path
                Message = if ((Get-SummaryMessageLine -Text $message)) { Get-SummaryMessageLine -Text $message } else { "Docker is installed, but the daemon is not reachable from this shell." }
                Output  = $message
            }
        }

        if ($message -match '(?i)access is denied') {
            $blockedPath = if ($dockerProbe.Path) { $dockerProbe.Path } else { "docker" }
            return [pscustomobject]@{
                Status  = "access_denied"
                Path    = $blockedPath
                Message = "Docker is installed at '$blockedPath', but this shell is not allowed to execute it. Rerun outside the sandbox or with elevated access."
                Output  = $message
            }
        }

        return [pscustomobject]@{
            Status  = "failed"
            Path    = $dockerProbe.Path
            Message = "Docker availability check failed. $(Get-SummaryMessageLine -Text $message)"
            Output  = $message
        }
    }

    if ($exitCode -eq 0) {
        return [pscustomobject]@{
            Status  = "ok"
            Path    = $dockerProbe.Path
            Message = $null
            Output  = $output
        }
    }

    $summary = Get-SummaryMessageLine -Text $output
    if ($output -match '(?i)permission denied while trying to connect|error during connect|cannot connect to the docker daemon|open //\./pipe/docker_engine|daemon is not running|docker daemon') {
        return [pscustomobject]@{
            Status  = "daemon_inaccessible"
            Path    = $dockerProbe.Path
            Message = if ($summary) { $summary } else { "Docker is installed, but the daemon is not reachable from this shell." }
            Output  = $output
        }
    }

    return [pscustomobject]@{
        Status  = "failed"
        Path    = $dockerProbe.Path
        Message = if ($summary) { $summary } else { "Docker version check failed." }
        Output  = $output
    }
}

function Test-DockerAvailable {
    $availability = Get-DockerAvailability
    return ($availability.Status -eq "ok")
}

function Get-DockerUnavailableMessage {
    param(
        [Parameter(Mandatory = $true)]
        $Availability
    )

    switch ($Availability.Status) {
        "binary_missing" {
            return "Docker is not installed or not on PATH."
        }
        "access_denied" {
            return $Availability.Message
        }
        "daemon_inaccessible" {
            return "Docker is installed, but the daemon is not reachable from this shell. Start Docker Desktop or rerun outside the sandbox. Details: $($Availability.Message)"
        }
        default {
            return "Docker is installed, but the availability check failed. Details: $($Availability.Message)"
        }
    }
}

function Get-DotnetRuntimeState {
    $candidates = @(
        [pscustomobject]@{
            Command = (Join-Path $env:ProgramFiles "dotnet\dotnet.exe")
        },
        [pscustomobject]@{
            Command = "dotnet"
        }
    )

    $probeResults = @()

    foreach ($candidate in $candidates) {
        $probe = Test-HostTool -Command $candidate.Command -Arguments @("--version")
        if ($probe.Status -eq "ok") {
            return [pscustomobject]@{
                Status  = "ok"
                Command = $candidate.Command
                Path    = $(if ($probe.Path) { $probe.Path } else { $candidate.Command })
                Message = $probe.Message
            }
        }

        $probeResults += [pscustomobject]@{
            Candidate = $candidate
            Probe     = $probe
        }
    }

    $accessDenied = $probeResults | Where-Object { $_.Probe.Status -eq "access_denied" } | Select-Object -First 1
    if ($accessDenied) {
        $blockedPath = if ($accessDenied.Probe.Path) { $accessDenied.Probe.Path } else { $accessDenied.Candidate.Command }
        return [pscustomobject]@{
            Status  = "access_denied"
            Command = $accessDenied.Candidate.Command
            Path    = $blockedPath
            Message = "The .NET SDK is installed at '$blockedPath', but this shell is not allowed to execute it. Rerun outside the sandbox or with elevated access."
        }
    }

    $failedProbe = $probeResults | Where-Object { $_.Probe.Status -eq "failed" } | Select-Object -First 1
    if ($failedProbe) {
        $failedPath = if ($failedProbe.Probe.Path) { $failedProbe.Probe.Path } else { $failedProbe.Candidate.Command }
        $failedReason = if ($failedProbe.Probe.Message) { $failedProbe.Probe.Message } else { "Unknown probe failure." }
        return [pscustomobject]@{
            Status  = "failed"
            Command = $failedProbe.Candidate.Command
            Path    = $failedPath
            Message = ".NET SDK probe failed for '$failedPath'. $failedReason"
        }
    }

    return [pscustomobject]@{
        Status  = "missing"
        Command = $null
        Path    = $null
        Message = "No working .NET SDK was found. Install .NET 8 or ensure 'dotnet' is available on PATH."
    }
}

function Get-DotnetCommand {
    $state = Get-DotnetRuntimeState
    if ($state.Status -ne "ok") {
        throw $state.Message
    }

    return $state
}

function Invoke-HostDotnet {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments,
        [string]$WorkingDirectory = (Get-RepoRoot)
    )

    $dotnet = Get-DotnetCommand

    Push-Location $WorkingDirectory
    try {
        & $dotnet.Command @Arguments
        if ($LASTEXITCODE -ne 0) {
            $commandText = "dotnet $($Arguments -join ' ')"
            throw "Host .NET command failed: $commandText (exit code $LASTEXITCODE). If .NET is installed and this only fails in a sandboxed shell, rerun outside the sandbox or with elevated access so the SDK can reach its user-level caches, workload manifests, and test host."
        }
    } finally {
        Pop-Location
    }
}

function Invoke-FrontendNpmInDocker {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments,
        [string]$WorkingDirectory = (Join-Path (Get-RepoRoot) "frontend"),
        [string]$Reason = "Host Node.js is unavailable."
    )

    $repoRoot = Get-RepoRoot
    $frontendDir = Join-Path $repoRoot "frontend"
    if ((Resolve-Path $WorkingDirectory).Path -ne (Resolve-Path $frontendDir).Path) {
        throw "Docker fallback only supports the repo frontend directory."
    }

    $dockerAvailability = Get-DockerAvailability
    if ($dockerAvailability.Status -ne "ok") {
        throw (Get-DockerUnavailableMessage -Availability $dockerAvailability)
    }

    $dockerSafe = Get-DockerSafeScript
    $dockerArguments = @($Arguments)
    if ($dockerArguments.Count -ge 2 -and $dockerArguments[0] -eq 'run' -and $dockerArguments[1] -eq 'test:ci') {
        $dockerArguments = @('run', 'test:ci:docker')
    }
    $npmCommand = $dockerArguments -join " "
    $frontendContainerId = ''

    try {
        $frontendContainerId = (& $dockerSafe compose ps -q frontend | Out-String).Trim()
    } catch {
        $frontendContainerId = ''
    }

    Write-Host "$Reason Using Docker for frontend command: npm $npmCommand"
    if ($frontendContainerId) {
        & $dockerSafe compose exec -T frontend sh -lc "cd /app && npm $npmCommand"
    } else {
        & $dockerSafe compose run --rm --no-deps frontend sh -lc "cd /app && npm $npmCommand"
    }
    if ($LASTEXITCODE -ne 0) {
        throw "Docker frontend command failed with exit code $LASTEXITCODE."
    }
}

function Invoke-FrontendNpm {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments,
        [string]$WorkingDirectory = (Join-Path (Get-RepoRoot) "frontend")
    )

    $nodePaths = $null
    $preferDockerValue = ''
    if ($null -ne $env:XF_FRONTEND_USE_DOCKER) {
        $preferDockerValue = $env:XF_FRONTEND_USE_DOCKER.ToLowerInvariant()
    }
    $preferDocker = @('1', 'true', 'yes', 'on') -contains $preferDockerValue
    if ($preferDocker) {
        $dockerAvailability = Get-DockerAvailability
        if ($dockerAvailability.Status -eq "ok") {
            Invoke-FrontendNpmInDocker -Arguments $Arguments -WorkingDirectory $WorkingDirectory -Reason "XF_FRONTEND_USE_DOCKER is enabled."
            return
        }
        throw "XF_FRONTEND_USE_DOCKER is enabled, but $(Get-DockerUnavailableMessage -Availability $dockerAvailability)"
    }

    $nodeState = Get-NodeRuntimeState
    if ($nodeState.Status -eq "access_denied") {
        throw $nodeState.Message
    }

    if ($nodeState.Status -eq "failed") {
        throw $nodeState.Message
    }

    if ($nodeState.Status -eq "missing") {
        $dockerAvailability = Get-DockerAvailability
        if ($dockerAvailability.Status -eq "ok") {
            Invoke-FrontendNpmInDocker -Arguments $Arguments -WorkingDirectory $WorkingDirectory -Reason "Host Node.js was not found."
            return
        }

        throw "$($nodeState.Message) Docker fallback is unavailable. $(Get-DockerUnavailableMessage -Availability $dockerAvailability)"
    }

    $nodePaths = [pscustomobject]@{
        Node = $nodeState.Node
        Npm  = $nodeState.Npm
        Mode = $nodeState.Mode
        Path = $nodeState.Path
    }

    if ($nodePaths.Npm -eq "npm") {
        Push-Location $WorkingDirectory
        try {
            & npm @Arguments
        } finally {
            Pop-Location
        }
        if ($LASTEXITCODE -ne 0) {
            throw "npm $($Arguments -join ' ') failed with exit code $LASTEXITCODE."
        }
        return
    }

    $npmCli = Join-Path (Split-Path -Parent $nodePaths.Npm) "node_modules\npm\bin\npm-cli.js"
    if (-not (Test-Path $npmCli)) {
        throw "npm-cli.js was not found next to the local Node.js install."
    }

    Push-Location $WorkingDirectory
    try {
        & $nodePaths.Node $npmCli @Arguments
        if ($LASTEXITCODE -ne 0) {
            throw "Local npm command failed with exit code $LASTEXITCODE."
        }
    } finally {
        Pop-Location
    }
}

function Invoke-VsDevCommand {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Command,
        [string]$WorkingDirectory = (Get-RepoRoot)
    )

    $vsdev = "C:\Program Files\Microsoft Visual Studio\2022\Community\Common7\Tools\VsDevCmd.bat"
    if (-not (Test-Path $vsdev)) {
        throw "Visual Studio developer command prompt was not found at $vsdev."
    }

    Push-Location $WorkingDirectory
    try {
        $cmd = "`"$vsdev`" -arch=x64 -host_arch=x64 && $Command"
        & cmd.exe /c $cmd
        if ($LASTEXITCODE -ne 0) {
            throw "Developer-shell command failed with exit code $LASTEXITCODE."
        }
    } finally {
        Pop-Location
    }
}
