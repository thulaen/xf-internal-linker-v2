param(
    [switch]$DryRun
)

if (-not $DryRun) {
    Write-Error "Refusing to create distributed Jobs in rehearsal. Re-run with -DryRun."
    exit 2
}

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
python (Join-Path $scriptRoot "distributed_test_coordinator.py") --dry-run --run-id dry-run
exit $LASTEXITCODE
