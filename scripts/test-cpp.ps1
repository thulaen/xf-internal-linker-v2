param(
    [switch]$Clean
)

$ErrorActionPreference = "Stop"

. (Join-Path $PSScriptRoot "dev-tools.ps1")

$repoRoot = Get-RepoRoot
$extensionsDir = Join-Path $repoRoot "backend\extensions"
$cmake = "C:\Program Files\Microsoft Visual Studio\2022\Community\Common7\IDE\CommonExtensions\Microsoft\CMake\CMake\bin\cmake.exe"

if (-not (Test-Path $cmake)) {
    throw "CMake was not found at $cmake."
}

$buildDir = Join-Path $extensionsDir "build_tests"

if ($Clean -and (Test-Path $buildDir)) {
    Remove-Item -Recurse -Force $buildDir
}

if (-not (Test-Path $buildDir)) {
    New-Item -ItemType Directory -Path $buildDir
}

Write-Host "Configuring C++ tests..."
Invoke-VsDevCommand -WorkingDirectory $buildDir -Command "`"$cmake`" .."

Write-Host "Building C++ tests..."
Invoke-VsDevCommand -WorkingDirectory $buildDir -Command "`"$cmake`" --build . --config Release"

Write-Host "Running C++ tests..."
$testFiles = Get-ChildItem (Join-Path $buildDir "Release") -Filter "test_*.exe"
foreach ($testFile in $testFiles) {
    Write-Host "Running $($testFile.Name)..."
    & $testFile.FullName
    if ($LASTEXITCODE -ne 0) {
        throw "Test $($testFile.Name) failed with exit code $LASTEXITCODE."
    }
}

Write-Host "C++ test suite completed."
