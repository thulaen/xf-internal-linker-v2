param(
    [string]$Prompt = "",
    [switch]$Continue,
    [switch]$Interactive,
    [switch]$NoSandbox,
    [switch]$DryRun,
    [string[]]$ExtraArgs = @()
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$blockedArgs = @("--dangerously-skip-permissions")

foreach ($arg in $ExtraArgs) {
    if ($blockedArgs -contains $arg) {
        throw "Unsafe Antigravity permission bypass is not allowed for this repo."
    }
}

$agy = Get-Command agy -ErrorAction Stop
$agyArgs = @()
if (-not $NoSandbox) {
    $agyArgs += "--sandbox"
}
$agyArgs += @("--add-dir", $repoRoot)

if ($Continue) {
    $agyArgs += "--continue"
} elseif ($Interactive) {
    $agyArgs += "--prompt-interactive"
    if ($Prompt) {
        $agyArgs += $Prompt
    }
} elseif ($Prompt) {
    $agyArgs += @("--print", $Prompt)
} else {
    $agyArgs += "--prompt-interactive"
}

$agyArgs += $ExtraArgs

if ($DryRun) {
    [pscustomobject]@{
        executable = $agy.Source
        working_directory = $repoRoot
        arguments = $agyArgs
    } | ConvertTo-Json -Depth 4
    exit 0
}

Set-Location $repoRoot
& $agy.Source @agyArgs
exit $LASTEXITCODE
