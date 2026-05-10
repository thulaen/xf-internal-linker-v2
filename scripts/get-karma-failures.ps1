Set-Location 'c:\Users\goldm\Dev\xf-internal-linker-v2\frontend'
$output = npm run test:ci 2>&1
$output | Where-Object { $_ -match 'TOTAL:|Executed \d+ of \d+' } | Select-Object -Last 5
Write-Host "--- FAILURES:"
$output | Where-Object { $_ -match 'FAILED' -and $_ -notmatch 'Executed' } | Select-Object -First 10
