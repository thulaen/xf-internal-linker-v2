##############################################################################
# lint-all.ps1 — Run ALL linters across every language in the project.
#
# Called by verify.ps1 BEFORE tests so lint failures abort fast.
# Each step prints a header and aborts on first failure.
# NOTHING is skipped. Every check is mandatory. No exceptions.
#
# Required tools (must be installed):
#   - Python: ruff, mypy, bandit  (pip install -r requirements-dev.txt)
#   - Node:   Angular CLI + ESLint (npm ci in frontend/)
#   - .NET:   dotnet 8.0+
#   - C++:    cppcheck             (choco install cppcheck)
#
# Checks (in order):
#   1. Python ruff check       (lint + dead code + style)
#   2. Python ruff format      (formatting consistency)
#   3. Python mypy             (type safety)
#   4. Python bandit           (security scan)
#   5. Angular ESLint          (TS lint + template accessibility)
#   6. C++ cppcheck            (static analysis)
#   7. C# dotnet build strict  (Roslyn warnings as errors)
##############################################################################

param()

$ErrorActionPreference = "Stop"

. (Join-Path $PSScriptRoot "dev-tools.ps1")

$repoRoot = Get-RepoRoot
$python   = Get-VenvPython

function Write-Step {
    param([string]$Label)
    Write-Host ""
    Write-Host "--- [$Label] ---" -ForegroundColor Cyan
}

function Assert-ToolExists {
    param([string]$Name, [string]$InstallHint)
    $cmd = Get-Command $Name -ErrorAction SilentlyContinue
    if (-not $cmd) {
        throw "$Name is not installed. Install it: $InstallHint"
    }
}

function Get-Cppcheck {
    # cppcheck may be in PATH or at the default Windows install location.
    $cmd = Get-Command cppcheck -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    $defaultPath = "C:\Program Files\Cppcheck\cppcheck.exe"
    if (Test-Path $defaultPath) { return $defaultPath }
    throw "cppcheck is not installed. Install it: winget install cppcheck"
}

# ── Pre-flight: verify all tools are available ────────────────────
Assert-ToolExists "dotnet" "https://dotnet.microsoft.com/download"
Assert-ToolExists "npx"    "Install Node.js 22 LTS"
$cppcheckExe = Get-Cppcheck

# ── 1. Python ruff check ──────────────────────────────────────────
Write-Step "1/7  Python: ruff check (lint + dead code)"
Push-Location (Join-Path $repoRoot "backend")
try {
    & $python -m ruff check .
    if ($LASTEXITCODE -ne 0) {
        throw "ruff check failed. Fix the lint errors above."
    }
} finally {
    Pop-Location
}

# ── 2. Python ruff format check ───────────────────────────────────
Write-Step "2/7  Python: ruff format --check (formatting)"
Push-Location (Join-Path $repoRoot "backend")
try {
    & $python -m ruff format --check .
    if ($LASTEXITCODE -ne 0) {
        throw "ruff format check failed. Run 'cd backend && ruff format .' to auto-fix."
    }
} finally {
    Pop-Location
}

# ── 3. Python mypy (type safety) ─────────────────────────────────
Write-Step "3/7  Python: mypy type check"
Push-Location (Join-Path $repoRoot "backend")
try {
    $env:DJANGO_SETTINGS_MODULE = "config.settings.test"
    $env:DJANGO_SECRET_KEY = "lint-only-key"
    # Ensure mypy + Django stubs are installed (they may be missing in some envs).
    $ErrorActionPreference = "Continue"
    & $python -m pip install --quiet mypy django-stubs djangorestframework-stubs 2>&1 | Out-Null
    # Run mypy — redirect stderr to suppress Django startup noise.
    $mypyOutput = & $python -m mypy apps/crawler/ --config-file mypy.ini --follow-imports=silent 2>&1
    $mypyExitCode = $LASTEXITCODE
    $ErrorActionPreference = "Stop"
    $mypyOutput | Where-Object { $_ -notmatch "OperationalError|Plugin loading|faiss|RuntimeWarning|Traceback|sqlite3|^$" } | Write-Host
    if ($mypyExitCode -ne 0) {
        throw "mypy type check failed. Fix the type errors above."
    }
} finally {
    Pop-Location
}

# ── 4. Python bandit (security scan) ──────────────────────────────
Write-Step "4/7  Python: bandit security scan"
Push-Location (Join-Path $repoRoot "backend")
try {
    $ErrorActionPreference = "Continue"
    & $python -m pip install --quiet bandit 2>&1 | Out-Null
    $banditOutput = & $python -m bandit -r apps/ -c bandit.yml --quiet 2>&1
    $banditExitCode = $LASTEXITCODE
    $ErrorActionPreference = "Stop"
    if ($banditOutput) { $banditOutput | Write-Host }
    if ($banditExitCode -ne 0) {
        throw "bandit found security issues. Fix the findings above."
    }
} finally {
    Pop-Location
}

# ── 5. Angular ESLint ─────────────────────────────────────────────
Write-Step "5/7  Angular: ESLint (TypeScript + templates)"
Push-Location (Join-Path $repoRoot "frontend")
try {
    $ErrorActionPreference = "Continue"
    & npx ng lint
    $eslintExitCode = $LASTEXITCODE
    $ErrorActionPreference = "Stop"
    if ($eslintExitCode -ne 0) {
        throw "Angular ESLint failed. Fix the lint errors above."
    }
} finally {
    Pop-Location
}

# ── 6. C++ cppcheck ──────────────────────────────────────────────
Write-Step "6/7  C++: cppcheck static analysis"
$extensionsDir = Join-Path (Join-Path $repoRoot "backend") "extensions"
$ErrorActionPreference = "Continue"
& $cppcheckExe `
    --enable=warning,performance,portability `
    --std=c++17 `
    --error-exitcode=1 `
    --suppress=missingIncludeSystem `
    --quiet `
    "$extensionsDir"
$cppExitCode = $LASTEXITCODE
$ErrorActionPreference = "Stop"
if ($cppExitCode -ne 0) {
    throw "cppcheck found issues. Fix the C++ warnings above."
}

# ── 7. C# strict build (TreatWarningsAsErrors) ───────────────────
Write-Step "7/7  C#: dotnet build with TreatWarningsAsErrors"
$httpWorkerDir = Join-Path (Join-Path $repoRoot "services") "http-worker"
Push-Location $httpWorkerDir
try {
    $ErrorActionPreference = "Continue"
    & dotnet build HttpWorker.sln -p:TreatWarningsAsErrors=true --nologo --verbosity quiet
    $csExitCode = $LASTEXITCODE
    $ErrorActionPreference = "Stop"
    if ($csExitCode -ne 0) {
        throw "C# build with strict warnings failed. Fix the warnings above."
    }
} finally {
    Pop-Location
}

Write-Host ""
Write-Host "All 7 linting checks passed." -ForegroundColor Green
