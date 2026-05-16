param(
    [switch]$MutationOnly
)

$ErrorActionPreference = "Stop"

. (Join-Path $PSScriptRoot "dev-tools.ps1")

$repoRoot = Get-RepoRoot

if ($MutationOnly) {
    # Slice 1.5 — direct invocation of the mutation sub-script. This still
    # exists because some developer workflows want a fast mutation-only
    # iteration without running the full 9-stage chain.
    Write-Host "Running Go mutation checks in Docker..."
    & docker compose run --rm -T compiled-tools bash /repo/scripts/run-go-mutation.sh
} else {
    # Slice 1.5 — call the new stage-by-stage orchestrator that replaced
    # scripts/check_go_tools.py. The orchestrator runs gofmt + go vet +
    # staticcheck + golangci-lint + gosec + buf lint + go test (race +
    # coverage) + go-mutesting + go bench, one quality_evidence row each.
    Write-Host "Running Go quality chain..."
    & bash scripts/run-go-quality.sh
}
if ($LASTEXITCODE -ne 0) {
    throw "Docker Go checks failed."
}

Write-Host "Go checks completed."
