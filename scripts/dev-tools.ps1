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

function Invoke-FrontendNpm {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments,
        [string]$WorkingDirectory = (Join-Path (Get-RepoRoot) "frontend")
    )

    $nodePaths = Get-NodePaths

    if ($nodePaths.Npm -eq "npm") {
        & npm @Arguments
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

