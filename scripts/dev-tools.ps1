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

function Get-NodePaths {
    $repoRoot = Get-RepoRoot
    $frontendDir = Join-Path $repoRoot "frontend"
    $candidates = @(
        @{
            Node = (Join-Path $env:LOCALAPPDATA "Programs\nodejs\node.exe")
            Npm = (Join-Path $env:LOCALAPPDATA "Programs\nodejs\npm.cmd")
        },
        @{
            Node = "node"
            Npm = "npm"
        }
    )

    foreach ($candidate in $candidates) {
        try {
            $nodeCommand = $candidate.Node
            if (Test-Path $nodeCommand) {
                $null = & $nodeCommand --version 2>$null
            } else {
                $null = & $nodeCommand --version 2>$null
            }
            return $candidate
        } catch {
            continue
        }
    }

    throw "No working Node.js runtime found. Expected a local install under AppData or a PATH-based node/npm."
}

function Get-DockerSafeScript {
    $script = Join-Path $PSScriptRoot "docker-safe.ps1"
    if (-not (Test-Path $script)) {
        throw "Docker helper script was not found at $script."
    }
    return $script
}

function Test-DockerAvailable {
    try {
        $dockerSafe = Get-DockerSafeScript
        & $dockerSafe version *> $null
        return ($LASTEXITCODE -eq 0)
    } catch {
        return $false
    }
}

function Invoke-FrontendNpmInDocker {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments,
        [string]$WorkingDirectory = (Join-Path (Get-RepoRoot) "frontend")
    )

    $repoRoot = Get-RepoRoot
    $frontendDir = Join-Path $repoRoot "frontend"
    if ((Resolve-Path $WorkingDirectory).Path -ne (Resolve-Path $frontendDir).Path) {
        throw "Docker fallback only supports the repo frontend directory."
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

    Write-Host "No working host Node.js runtime found. Falling back to Docker for frontend command: npm $npmCommand"
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
        if (Test-DockerAvailable) {
            Invoke-FrontendNpmInDocker -Arguments $Arguments -WorkingDirectory $WorkingDirectory
            return
        }
        throw "XF_FRONTEND_USE_DOCKER is enabled, but Docker is not available."
    }

    try {
        $nodePaths = Get-NodePaths
    } catch {
        if (Test-DockerAvailable) {
            Invoke-FrontendNpmInDocker -Arguments $Arguments -WorkingDirectory $WorkingDirectory
            return
        }
        throw
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
