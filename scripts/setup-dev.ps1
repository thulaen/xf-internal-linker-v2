param(
    [string]$PythonExe = "",
    [switch]$RecreateVenv
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$venvDir = Join-Path $repoRoot ".venv"
$venvCfg = Join-Path $venvDir "pyvenv.cfg"
$requirements = @(
    (Join-Path $repoRoot "backend\requirements.txt"),
    (Join-Path $repoRoot "backend\requirements-dev.txt")
)

function Get-PythonCandidate {
    param([string]$RequestedPath)

    $candidates = @()

    if ($RequestedPath) {
        $candidates += $RequestedPath
    }

    $candidates += @(
        (Join-Path $env:LOCALAPPDATA "Programs\Python\Python312\python.exe"),
        (Join-Path $env:LOCALAPPDATA "Programs\Python\Python313\python.exe"),
        "py -3.12",
        "py -3.13",
        "python"
    )

    foreach ($candidate in $candidates | Select-Object -Unique) {
        try {
            if ($candidate -like "* *" -and -not (Test-Path $candidate)) {
                $null = & cmd.exe /c "$candidate --version" 2>$null
            } else {
                $null = & $candidate --version 2>$null
            }

            return $candidate
        } catch {
            continue
        }
    }

    throw "No working Python interpreter found. Pass -PythonExe or install Python 3.12+."
}

function Read-VenvHome {
    param([string]$ConfigPath)

    if (-not (Test-Path $ConfigPath)) {
        return $null
    }

    $homeLine = Get-Content $ConfigPath | Where-Object { $_ -like "home = *" } | Select-Object -First 1
    if (-not $homeLine) {
        return $null
    }

    return $homeLine.Substring(7).Trim()
}

$brokenVenv = $false
$venvHome = Read-VenvHome -ConfigPath $venvCfg
if ($venvHome -and -not (Test-Path (Join-Path $venvHome "python.exe"))) {
    $brokenVenv = $true
}

if ($RecreateVenv -or $brokenVenv -or -not (Test-Path $venvCfg)) {
    if (Test-Path $venvDir) {
        Remove-Item -Recurse -Force $venvDir
    }

    $python = Get-PythonCandidate -RequestedPath $PythonExe
    Write-Host "Creating virtual environment with $python"

    if ($python -like "* *" -and -not (Test-Path $python)) {
        & cmd.exe /c "$python -m venv `"$venvDir`""
    } else {
        & $python -m venv $venvDir
    }
}

$venvPython = Join-Path $venvDir "Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    throw "Virtual environment was not created correctly: $venvPython not found."
}

& $venvPython -m pip install --upgrade pip
foreach ($requirement in $requirements) {
    & $venvPython -m pip install -r $requirement
}

Write-Host "Verifying required backend dependencies..."
& $venvPython -c "import drf_spectacular"

Write-Host "Preparing local SQLite test database..."
$previousDjangoSettings = $env:DJANGO_SETTINGS_MODULE
Push-Location (Join-Path $repoRoot "backend")
try {
    $env:DJANGO_SETTINGS_MODULE = "config.settings.test"
    & $venvPython manage.py migrate --settings=config.settings.test --noinput
} finally {
    if ($null -eq $previousDjangoSettings) {
        Remove-Item Env:DJANGO_SETTINGS_MODULE -ErrorAction SilentlyContinue
    } else {
        $env:DJANGO_SETTINGS_MODULE = $previousDjangoSettings
    }
    Pop-Location
}

Write-Host "Backend environment is ready."
Write-Host "Interpreter: $venvPython"
Write-Host "Tip: repo-local wrappers mirror the main local verification flow:"
Write-Host "  powershell -ExecutionPolicy Bypass -File scripts\\build-frontend.ps1"
Write-Host "  powershell -ExecutionPolicy Bypass -File scripts\\build-native-extensions.ps1"
Write-Host "  powershell -ExecutionPolicy Bypass -File scripts\\verify.ps1"
Write-Host "Verification now prunes build artifacts after it runs to help reclaim disk space."
Write-Host "Note: sandboxed shells can block local Node.js or Docker access even when they are installed."
Write-Host "If a wrapper reports an access or daemon error, rerun it outside the sandbox or with elevated access."
