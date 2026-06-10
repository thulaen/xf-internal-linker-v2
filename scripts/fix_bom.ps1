$bytes = [IO.File]::ReadAllBytes('C:\Users\goldm\Dev\xf-internal-linker-v2\postgres\postgresql.conf')
if ($bytes.Length -ge 3 -and $bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF) {
    $bytes = $bytes[3..($bytes.Length - 1)]
    [IO.File]::WriteAllBytes('C:\Users\goldm\Dev\xf-internal-linker-v2\postgres\postgresql.conf', $bytes)
    Write-Host "BOM stripped."
} else {
    Write-Host "No BOM found."
}
