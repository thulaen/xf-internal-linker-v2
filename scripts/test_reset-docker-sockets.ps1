# test_reset-docker-sockets.ps1
# Standalone PowerShell test for scripts/reset-docker-sockets.ps1.
#
# Why this test exists
# --------------------
# The 2026-04-26 cleanup script used `fsutil reparsepoint query` to detect
# orphan AF_UNIX sockets, but that call returns exit 0 on both healthy and
# orphan reparse points; the cleanup logged "clean" at every logon while
# the underlying bug (Docker Desktop hanging on Starting...) recurred. A
# follow-up `[System.IO.File]::Open` attempt false-positived because
# healthy AF_UNIX sockets also throw "cannot be accessed by the system".
#
# Investigation of an actual hang showed the decisive recovery was
# `wsl --terminate docker-desktop`, not the socket rename: a previous
# unclean Docker Desktop shutdown left the docker-desktop WSL distro
# running with orphan containerd-shim processes, and the next launch
# could not boot a fresh dockerd inside that distro. The 2026-05-24
# rewrite folds that recovery into the per-logon scheduled task. This
# test pins the new contract.

$ErrorActionPreference = "Stop"

$script:passed = 0
$script:failed = 0

function Assert-True {
    param([string]$Name, [bool]$Condition)
    if ($Condition) {
        Write-Output ("  PASS  " + $Name)
        $script:passed++
    } else {
        Write-Output ("  FAIL  " + $Name)
        $script:failed++
    }
}

# Dot-source the production script in library mode. The script must not
# run its main loop when dot-sourced from a test.
$prodScript = Join-Path $PSScriptRoot "reset-docker-sockets.ps1"
if (-not (Test-Path -LiteralPath $prodScript)) {
    throw "Production script not found: $prodScript"
}
$env:RESET_DOCKER_SOCKETS_LIBRARY_MODE = "1"
. $prodScript
$env:RESET_DOCKER_SOCKETS_LIBRARY_MODE = ""

# Library mode must skip the main loop so dot-source has no side effects.
Assert-True "library mode skips main loop on dot-source" (-not $script:reset_docker_sockets_main_ran)

# All required functions must exist after dot-sourcing.
$required = @(
    "Test-DockerDesktopRunning",
    "Test-DockerDesktopWslDistroRunning",
    "Test-DirIsUnenumerable",
    "Invoke-OrphanWslCleanup",
    "Invoke-SocketDirCleanup",
    "Invoke-Main",
    # Added 2026-05-25 for failure mode (3): com.docker.service Stopped.
    "Test-IsElevated",
    "Test-DockerServiceState",
    "Start-DockerServiceElevated",
    "Stop-DockerDesktopProcesses",
    "Start-DockerDesktop",
    "Wait-DockerEngineReady",
    "Invoke-FixStuckDocker"
)
$missing = @()
foreach ($name in $required) {
    $cmd = Get-Command $name -CommandType Function -ErrorAction SilentlyContinue
    Assert-True ($name + " is defined") ($null -ne $cmd)
    if ($null -eq $cmd) { $missing += $name }
}
if ($missing.Count -gt 0) {
    Write-Output ("Missing functions: " + ($missing -join ", "))
    Write-Output ("Results: passed=" + $script:passed + " failed=" + $script:failed)
    exit 1
}

Write-Output ""
Write-Output "=== Test-DirIsUnenumerable ==="

# 1. A directory with normal contents is enumerable (NOT orphan).
$cleanDir = New-Item -ItemType Directory -Path (Join-Path $env:TEMP ("xf-test-clean-" + [Guid]::NewGuid()))
try {
    "harmless" | Set-Content -LiteralPath (Join-Path $cleanDir.FullName "ordinary.txt")
    Assert-True "ordinary directory is enumerable (not orphan)" (-not (Test-DirIsUnenumerable -Path $cleanDir.FullName))
} finally {
    Remove-Item -LiteralPath $cleanDir.FullName -Recurse -Force -ErrorAction SilentlyContinue
}

# 2. A missing directory must NOT be flagged orphan (caller should skip).
$missingDir = Join-Path $env:TEMP ("xf-test-missing-dir-" + [Guid]::NewGuid())
Assert-True "missing directory is not flagged as orphan" (-not (Test-DirIsUnenumerable -Path $missingDir))

# 3. An empty directory is enumerable (the empty list is a valid result).
$emptyDir = New-Item -ItemType Directory -Path (Join-Path $env:TEMP ("xf-test-empty-" + [Guid]::NewGuid()))
try {
    Assert-True "empty directory is enumerable (not orphan)" (-not (Test-DirIsUnenumerable -Path $emptyDir.FullName))
} finally {
    Remove-Item -LiteralPath $emptyDir.FullName -Recurse -Force -ErrorAction SilentlyContinue
}

Write-Output ""
Write-Output "=== Test-DockerDesktopRunning ==="

# 4. The function returns a boolean (true xor false). We do not assert
#    the value because Docker Desktop may or may not be running during
#    this test run; we only assert the contract.
$result = Test-DockerDesktopRunning
Assert-True "Test-DockerDesktopRunning returns a boolean" ($result -is [bool])

Write-Output ""
Write-Output "=== Test-DockerDesktopWslDistroRunning ==="

# 5. Same contract check for the distro probe.
$result = Test-DockerDesktopWslDistroRunning
Assert-True "Test-DockerDesktopWslDistroRunning returns a boolean" ($result -is [bool])

Write-Output ""
Write-Output "=== Invoke-OrphanWslCleanup safety guard ==="

# 6. When Docker Desktop is running, the cleanup must NEVER terminate
#    the distro out from under it. We can prove the safety guard by
#    monkey-patching Test-DockerDesktopRunning to always return $true,
#    then asserting Invoke-OrphanWslCleanup returns $false (no action).
function script:Test-DockerDesktopRunning { return $true }
function script:Test-DockerDesktopWslDistroRunning { return $true }
$wslCleanupRan = Invoke-OrphanWslCleanup
Assert-True "wsl cleanup is skipped when Docker Desktop is running" ($wslCleanupRan -eq $false)

# 7. When DD is not running AND distro is not running, cleanup is also
#    skipped (the typical clean-logon case).
function script:Test-DockerDesktopRunning { return $false }
function script:Test-DockerDesktopWslDistroRunning { return $false }
$wslCleanupRan = Invoke-OrphanWslCleanup
Assert-True "wsl cleanup is skipped when nothing is running" ($wslCleanupRan -eq $false)

Write-Output ""
Write-Output "=== Test-IsElevated ==="

# 8. Contract: returns a boolean. Test runs may be elevated or not; the
#    value depends on how the user invoked the test, so we only assert
#    the shape.
$result = Test-IsElevated
Assert-True "Test-IsElevated returns a boolean" ($result -is [bool])

Write-Output ""
Write-Output "=== Test-DockerServiceState ==="

# 9. Contract: returns a pscustomobject with Installed (bool) and Status
#    (string). Service may be Running, Stopped, or missing; we assert
#    the shape, not the value.
$svc = Test-DockerServiceState
Assert-True "Test-DockerServiceState returns Installed property as bool" ($svc.Installed -is [bool])
Assert-True "Test-DockerServiceState returns Status property as string" ($svc.Status -is [string])
Assert-True "Test-DockerServiceState Status is non-empty" ($svc.Status.Length -gt 0)
if (-not $svc.Installed) {
    Assert-True "missing service reports Status='missing'" ($svc.Status -eq "missing")
}

Write-Output ""
Write-Output "=== -FixStuckDocker param block ==="

# 10. The param block must expose -FixStuckDocker as a switch. After
#     dot-sourcing the script (in library mode so the main loop does
#     not run), $FixStuckDocker should be defined and default to $false.
Assert-True "FixStuckDocker variable is defined after dot-source" (Test-Path Variable:FixStuckDocker)
if (Test-Path Variable:FixStuckDocker) {
    Assert-True "FixStuckDocker is a SwitchParameter" ($FixStuckDocker -is [System.Management.Automation.SwitchParameter])
    Assert-True "FixStuckDocker defaults to false" (-not $FixStuckDocker.ToBool())
}

Write-Output ""
Write-Output ("Results: passed=" + $script:passed + " failed=" + $script:failed)
if ($script:failed -gt 0) {
    exit 1
}
exit 0
