<#
.SYNOPSIS
    Report presence and version of clean-native Windows host tools.
    Does NOT install -- use install-windows-host-tools.ps1 for that.

.DESCRIPTION
    Checks each required host tool and prints PRESENT or MISSING.
    Exits 0 when all required tools are present; exits 1 if any required
    tool is missing.

    Prepends known install locations so the check works whether or not the
    caller's shell has already refreshed the PATH after installation.
#>
[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Continue"

# Prepend known locations so the check works regardless of caller PATH state
$knownPaths = @(
    "C:\Users\$env:USERNAME\.cargo\bin",
    "C:\Program Files\CMake\bin",
    "$env:LOCALAPPDATA\Microsoft\WinGet\Packages\Ninja-build.Ninja_Microsoft.Winget.Source_8wekyb3d8bbwe",
    "C:\Program Files\Cppcheck",
    "C:\Tools\protoc\bin",
    "C:\Tools\cargo-mutants"
)
foreach ($p in $knownPaths) {
    if ((Test-Path $p) -and ($env:PATH -notlike "*$p*")) {
        $env:PATH = "$p;$env:PATH"
    }
}

$Missing  = [System.Collections.Generic.List[string]]::new()
$Present  = [System.Collections.Generic.List[string]]::new()

function Check-Tool {
    param(
        [string]$Name,
        [string]$Command,
        [string[]]$VersionArgs,
        [string]$VersionPattern = "."
    )
    $found = Get-Command $Command -ErrorAction SilentlyContinue
    if (-not $found) {
        $script:Missing.Add($Name)
        Write-Host "  MISSING  $Name"
        return
    }
    try {
        $ver = (& $Command @VersionArgs 2>&1 | Select-Object -First 1) -as [string]
        $ver = $ver.Trim()
        $script:Present.Add("$Name ($ver)")
        Write-Host "  PRESENT  $Name -- $ver"
    } catch {
        $script:Present.Add("$Name (version unknown)")
        Write-Host "  PRESENT  $Name -- (found at $($found.Source), version check skipped)"
    }
}

Write-Host ""
Write-Host "Windows host tool presence report"
Write-Host ("-" * 50)

Check-Tool "Rust/cargo"    "cargo"         @("--version")
Check-Tool "CMake"         "cmake"         @("--version")
Check-Tool "Ninja"         "ninja"         @("--version")
Check-Tool "Cppcheck"      "cppcheck"      @("--version")
Check-Tool "protoc"        "protoc"        @("--version")
Check-Tool "cargo-mutants" "cargo-mutants" @("mutants", "--version")

Write-Host ("-" * 50)
Write-Host "Present: $($Present.Count)   Missing: $($Missing.Count)"

if ($Missing.Count -gt 0) {
    Write-Host ""
    Write-Host "Missing tools: $($Missing -join ', ')"
    Write-Host "Run: scripts\install-windows-host-tools.ps1"
    exit 1
}

Write-Host ""
Write-Host "All required host tools are present."
exit 0
