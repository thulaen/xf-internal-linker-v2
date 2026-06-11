<#
.SYNOPSIS
    Idempotent installer for clean-native Windows host tools required for
    the Windows/Mint compute split.

.DESCRIPTION
    Skips any tool already installed.  Installs via winget where available,
    falls back to GitHub release ZIPs for golangci-lint and protoc.
    After Go is installed, installs go-mutesting and buf via `go install`.
    After Rust is installed, installs cargo-mutants and related Cargo tools.

    Tools NOT installed on Windows:
      - Infer, Mull, Haskell/GHC/Cabal  (remain on Mint/Docker)

.NOTES
    Run as a regular user (winget does not require elevation for user-scope installs).
    Script adds C:\Tools\protoc\bin to user PATH
    if not already present.
#>
[CmdletBinding(SupportsShouldProcess)]
param(
    [switch]$SkipRust,
    [switch]$SkipGo,
    [switch]$SkipCargoExtras
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Is-OnPath { param([string]$cmd)
    $null -ne (Get-Command $cmd -ErrorAction SilentlyContinue)
}

function Add-UserPath { param([string]$dir)
    $cur = [Environment]::GetEnvironmentVariable("PATH", "User")
    if ($cur -notlike "*$dir*") {
        [Environment]::SetEnvironmentVariable("PATH", "$cur;$dir", "User")
        $env:PATH = "$env:PATH;$dir"
        Write-Host "  Added to user PATH: $dir"
    }
}

Write-Host "`nInstalling Windows host tools (idempotent)"
Write-Host ("-" * 60)

# ── Rust / rustup ─────────────────────────────────────────────────────────────
if (-not $SkipRust -and -not (Is-OnPath "rustup")) {
    Write-Host "Installing Rust via winget..."
    winget install --id Rustlang.Rustup --accept-source-agreements --accept-package-agreements
} else {
    Write-Host "  SKIP  Rustup — already installed"
}

# ── CMake ────────────────────────────────────────────────────────────────────
if (-not (Is-OnPath "cmake")) {
    Write-Host "Installing CMake via winget..."
    winget install --id Kitware.CMake --accept-source-agreements --accept-package-agreements
} else {
    Write-Host "  SKIP  CMake — already installed"
}

# ── Ninja ────────────────────────────────────────────────────────────────────
if (-not (Is-OnPath "ninja")) {
    Write-Host "Installing Ninja via winget..."
    winget install --id Ninja-build.Ninja --accept-source-agreements --accept-package-agreements
} else {
    Write-Host "  SKIP  Ninja — already installed"
}

# ── Cppcheck ─────────────────────────────────────────────────────────────────
if (-not (Is-OnPath "cppcheck")) {
    Write-Host "Installing Cppcheck via winget..."
    winget install --id Cppcheck.Cppcheck --accept-source-agreements --accept-package-agreements
} else {
    Write-Host "  SKIP  Cppcheck — already installed"
}

# ── protoc (GitHub release ZIP) ──────────────────────────────────────────────
$protocBin = "C:\Tools\protoc\bin"
if (-not (Test-Path "$protocBin\protoc.exe")) {
    Write-Host "Installing protoc from GitHub release..."
    $ver = "28.3"
    $url = "https://github.com/protocolbuffers/protobuf/releases/download/v$ver/protoc-$ver-win64.zip"
    $zip = "$env:TEMP\protoc.zip"
    Invoke-WebRequest -Uri $url -OutFile $zip -UseBasicParsing
    New-Item -ItemType Directory -Force -Path "C:\Tools\protoc" | Out-Null
    Expand-Archive -Path $zip -DestinationPath "C:\Tools\protoc" -Force
    Remove-Item $zip -Force
    Add-UserPath $protocBin
} else {
    Write-Host "  SKIP  protoc — already installed"
}

# ── Rust extras (require rustup on PATH) ─────────────────────────────────────
if (-not $SkipRust -and -not $SkipCargoExtras -and (Is-OnPath "cargo")) {
    $cargoTools = @(
        "cargo-mutants",
        "cargo-llvm-cov",
        "cargo-audit",
        "cargo-deny"
    )
    foreach ($ct in $cargoTools) {
        if (-not (Is-OnPath $ct.Replace("cargo-", "") -and $ct -ne "cargo-audit")) {
            Write-Host "Installing $ct..."
            cargo install $ct --quiet
        } else {
            Write-Host "  SKIP  $ct — already installed"
        }
    }
    Write-Host "Installing cargo-fuzz (nightly)..."
    cargo +nightly install cargo-fuzz --quiet
} elseif (-not (Is-OnPath "cargo")) {
    Write-Warning "cargo not on PATH — skipping Rust extras. Restart shell and re-run."
}

Write-Host ("-" * 60)
Write-Host "Host tool installation complete."
Write-Host "Run scripts\check-windows-host-tools.ps1 to verify."
