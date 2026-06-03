param(
    [string[]]$Language = @(),
    [string]$CodeQL = $(if ($env:CODEQL) { $env:CODEQL } else { "codeql" }),
    [string]$DatabaseRoot = "tmp/codeql/databases",
    [string]$SarifRoot = "reports/codeql"
)

$ErrorActionPreference = "Stop"

python scripts/codeql_language_inventory.py --format plain

$argsList = @(
    "scripts/run_codeql.py",
    "--codeql", $CodeQL,
    "--db-root", $DatabaseRoot,
    "--sarif-root", $SarifRoot
)

foreach ($item in $Language) {
    $argsList += @("--language", $item)
}

python @argsList
