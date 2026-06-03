param(
    [Parameter(Mandatory = $true)]
    [string]$Command,
    [string]$MintHost = "mint",
    [string]$MintRepoPath = "/home/mint-helper-01/xf-internal-linker-v2"
)

$ErrorActionPreference = "Stop"

function ConvertTo-BashSingleQuoted {
    param([string]$Value)
    return "'" + ($Value -replace "'", "'\''") + "'"
}

$repoArg = ConvertTo-BashSingleQuoted $MintRepoPath
$commandArg = ConvertTo-BashSingleQuoted $Command

$remote = @"
set -e
cd $repoArg
docker inspect -f '{{.State.Running}}' xf_linker_compiled_tools 2>/dev/null | grep -q true || {
  echo 'Mint compiled-tools is not running. From Windows run: powershell -ExecutionPolicy Bypass -File scripts/start-mint-quality-tools.ps1' >&2
  exit 1
}
docker exec xf_linker_compiled_tools bash -lc $commandArg
"@

& ssh $MintHost $remote
if ($LASTEXITCODE -ne 0) {
    throw "Mint compiled-tools command failed."
}
