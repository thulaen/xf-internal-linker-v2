$ErrorActionPreference = "Stop"

$repoRoot = git rev-parse --show-toplevel
if ($LASTEXITCODE -ne 0) {
    throw "Could not find the repository root."
}

$gitBash = "C:\Program Files\Git\bin\bash.exe"
if (-not (Test-Path $gitBash)) {
    throw "Git Bash was not found at $gitBash."
}

Push-Location $repoRoot
try {
    & $gitBash scripts/run-tool-readiness.sh
    if ($LASTEXITCODE -ne 0) { throw "Docker tool-readiness failed." }

    docker compose config | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Docker Compose config check failed." }

    python scripts/bazel_default.py test //tools/quality:all
    if ($LASTEXITCODE -ne 0) { throw "Bazel quality checks failed." }

    git diff --check
    if ($LASTEXITCODE -ne 0) { throw "Whitespace check failed." }
} finally {
    Pop-Location
}
