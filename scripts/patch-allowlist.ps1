$file = '.githooks\check-glossary.py'
$content = Get-Content $file -Raw
$old = "    `"KDD`", `"LTR`", `"UAI`", `"ICDM`", `"SIAM`", `"CACM`","
$new = "    `"KDD`", `"LTR`", `"UAI`", `"ICDM`", `"SIAM`", `"CACM`",`r`n    # Karma helper script output headings - plain English not jargon.`r`n    `"TOTAL`", `"FAILURES`","
if ($content -like "*$old*") {
    $content = $content.Replace($old, $new)
    Set-Content $file -Value $content -Encoding UTF8 -NoNewline
    Write-Host "Done"
} else {
    Write-Host "Pattern not found"
    ($content -split "`n" | Select-Object -Skip 259 -First 5) -join "`n"
}
