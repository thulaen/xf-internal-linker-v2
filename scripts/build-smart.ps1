param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$BuildArgs
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$script = Join-Path $repoRoot "scripts\smart_build.py"

python $script @BuildArgs
exit $LASTEXITCODE
