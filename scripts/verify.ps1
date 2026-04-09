$ErrorActionPreference = "Stop"

. (Join-Path $PSScriptRoot "dev-tools.ps1")

$repoRoot = Get-RepoRoot
$python = Get-VenvPython

try {
    # Lint ALL languages first — fail fast before wasting time on tests.
    Write-Host "Running all linters (ruff, mypy, bandit, ESLint, cppcheck, C# strict)..."
    & (Join-Path $PSScriptRoot "lint-all.ps1")
    if ($LASTEXITCODE -ne 0) {
        throw "Linting failed. Fix the errors above before pushing."
    }

    & (Join-Path $PSScriptRoot "build-native-extensions.ps1")
    if ($LASTEXITCODE -ne 0) {
        throw "Native extension build failed."
    }

    Write-Host "Running backend tests..."
    $previousPipelineBenchmarkSetting = $env:PIPELINE_RUN_BENCHMARKS
    $previousGraphBenchmarkSetting = $env:XF_RUN_BENCHMARKS
    $env:PIPELINE_RUN_BENCHMARKS = "1"
    $env:XF_RUN_BENCHMARKS = "1"
    $env:DJANGO_SETTINGS_MODULE = "config.settings.test"
    Push-Location (Join-Path $repoRoot "backend")
    try {
        & $python manage.py test apps.content apps.core apps.crawler apps.diagnostics apps.graph apps.pipeline apps.suggestions apps.sync --verbosity 2
        if ($LASTEXITCODE -ne 0) {
            throw "Backend test suite failed."
        }
    } finally {
        if ($null -eq $previousPipelineBenchmarkSetting) {
            Remove-Item Env:PIPELINE_RUN_BENCHMARKS -ErrorAction SilentlyContinue
        } else {
            $env:PIPELINE_RUN_BENCHMARKS = $previousPipelineBenchmarkSetting
        }

        if ($null -eq $previousGraphBenchmarkSetting) {
            Remove-Item Env:XF_RUN_BENCHMARKS -ErrorAction SilentlyContinue
        } else {
            $env:XF_RUN_BENCHMARKS = $previousGraphBenchmarkSetting
        }
        Pop-Location
    }

    Write-Host "Running frontend build..."
    & (Join-Path $PSScriptRoot "build-frontend.ps1")
    if ($LASTEXITCODE -ne 0) {
        throw "Frontend build failed."
    }

    & (Join-Path $PSScriptRoot "test-frontend.ps1")
    if ($LASTEXITCODE -ne 0) {
        throw "Frontend unit tests failed."
    }

    Write-Host "Running HttpWorker build + tests..."
    & (Join-Path $PSScriptRoot "test-http-worker.ps1") -Configuration Release
    if ($LASTEXITCODE -ne 0) {
        throw "HttpWorker verification failed."
    }

    Write-Host "Verification completed."
} finally {
    Write-Host "Pruning verification artifacts to reclaim disk space..."
    & (Join-Path $PSScriptRoot "prune-verification-artifacts.ps1")
}
