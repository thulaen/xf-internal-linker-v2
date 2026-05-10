$ErrorActionPreference = "Stop"

. (Join-Path $PSScriptRoot "dev-tools.ps1")

$repoRoot = Get-RepoRoot
$python = Get-VenvPython

try {
    # Lint ALL languages first — fail fast before wasting time on tests.
    Write-Host "Running all linters (ruff, mypy, bandit, ESLint, cppcheck)..."
    & (Join-Path $PSScriptRoot "lint-all.ps1")
    if ($LASTEXITCODE -ne 0) {
        throw "Linting failed. Fix the errors above before pushing."
    }

    # ── Rule 26: Test existence check for new modules ───────────────
    Write-Host ""
    Write-Host "--- [Test existence check for new modules] ---" -ForegroundColor Cyan
    $base = "origin/master"
    $null = git -C $repoRoot rev-parse --verify $base 2>$null
    if ($LASTEXITCODE -ne 0) { $base = "HEAD~1" }
    $newFiles = @(git -C $repoRoot diff --name-only --diff-filter=A "$base...HEAD" 2>$null)
    $missingTests = @()
    foreach ($f in $newFiles) {
        # Python: new .py file in apps/ (not __init__, migrations, admin, urls, apps)
        if ($f -match '^backend/apps/([^/]+)/(?!tests|migrations|__init__|admin|urls|apps|manage)(\w+)\.py$') {
            $appName = $Matches[1]
            $testFile = "backend/apps/$appName/tests.py"
            $testDir  = "backend/apps/$appName/tests/"
            $hasNewTest = @($newFiles | Where-Object { $_ -match "backend/apps/$appName/test" }).Count -gt 0
            if (-not $hasNewTest) {
                $tfPath = Join-Path $repoRoot ($testFile -replace '/', '\')
                $tdPath = Join-Path $repoRoot ($testDir -replace '/', '\')
                if (-not (Test-Path $tfPath) -and -not (Test-Path $tdPath)) {
                    $missingTests += $f
                }
            }
        }
    }
    if ($missingTests.Count -gt 0) {
        $missingTests | ForEach-Object { Write-Host "  No test coverage: $_" -ForegroundColor Yellow }
        throw "Found $($missingTests.Count) new source file(s) without corresponding tests."
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
        # Match CI exactly — run all backend tests, no app filter. The
        # explicit list previously skipped apps.api / apps.notifications
        # / apps.health / apps.realtime / apps.scheduled_updates /
        # apps.analytics / apps.benchmarks / apps.plugins / apps.sources
        # / apps.training, so failures in those apps escaped to CI.
        & $python manage.py test --verbosity 2
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

    # NO-DUPLICATES.md CI gate. Confirms every per-content artefact table
    # still satisfies the (content_hash, signal_version) + supersede +
    # retention pattern. Catches regressions where a later migration
    # drops a hash column or a new artefact table forgets to declare.
    Write-Host "Running NO-DUPLICATES invariant audit (verify_dedup_invariant.py)..."
    Push-Location (Join-Path $repoRoot "backend")
    try {
        & $python (Join-Path $repoRoot "scripts\verify_dedup_invariant.py")
        if ($LASTEXITCODE -ne 0) {
            throw "NO-DUPLICATES invariant audit failed."
        }
    } finally {
        Pop-Location
    }

    # Dead-service sweep. Finds backend/apps/*/services/*.py files that
    # nothing imports — typical cause is a refactor that moved logic but
    # left the old file behind. Exits non-zero if any orphan turns up.
    # Each legitimate single-file kept-for-management-command service can
    # opt out with a top-of-file `# verify-unused-python: kept-for-<reason>`.
    Write-Host "Running dead-service sweep (verify_unused_python.py)..."
    & $python (Join-Path $repoRoot "scripts\verify_unused_python.py")
    if ($LASTEXITCODE -ne 0) {
        throw "Dead-service sweep found orphaned service files."
    }

    Write-Host "Verification completed."
} finally {
    Write-Host "Pruning verification artifacts to reclaim disk space..."
    & (Join-Path $PSScriptRoot "prune-verification-artifacts.ps1")
}
