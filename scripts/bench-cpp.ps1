param(
    [switch]$Clean
)

$ErrorActionPreference = "Stop"

. (Join-Path $PSScriptRoot "dev-tools.ps1")

$repoRoot = Get-RepoRoot
$benchDir = Join-Path $repoRoot "backend\extensions\benchmarks"
$cmake = "C:\Program Files\Microsoft Visual Studio\2022\Community\Common7\IDE\CommonExtensions\Microsoft\CMake\CMake\bin\cmake.exe"

if (-not (Test-Path $cmake)) {
    throw "CMake was not found at $cmake."
}

$buildDir = Join-Path $benchDir "build"

if ($Clean -and (Test-Path $buildDir)) {
    Remove-Item -Recurse -Force $buildDir
}

if (-not (Test-Path $buildDir)) {
    New-Item -ItemType Directory -Path $buildDir
}

Write-Host "Configuring C++ benchmarks..."
Invoke-VsDevCommand -WorkingDirectory $buildDir -Command "`"$cmake`" .."

Write-Host "Building C++ benchmarks..."
Invoke-VsDevCommand -WorkingDirectory $buildDir -Command "`"$cmake`" --build . --config Release"

Write-Host "Running C++ benchmarks..."
$benchFiles = Get-ChildItem (Join-Path $buildDir "Release") -Filter "bench_*.exe"
foreach ($benchFile in $benchFiles) {
    Write-Host "--------------------------------------------------------"
    Write-Host "Running $($benchFile.Name)..."
    & $benchFile.FullName
}

Write-Host "C++ benchmark suite completed."
