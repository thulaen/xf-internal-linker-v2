$ErrorActionPreference = 'Stop'
$path = 'C:\Users\goldm\Dev\xf-internal-linker-v2\frontend\signal-control-macc.html'
$c = Get-Content -Raw -Path $path
$c = $c.Replace('>macc 14<', '>macc 15<')

# replace font-size="X" -> "Y" only inside one page's slice of the file
function Fix([string]$src, [string]$page, [string]$old, [string]$new) {
  $start = $src.IndexOf('data-page="' + $page + '"')
  if ($start -lt 0) { Write-Output ("  !! page not found: " + $page); return $src }
  $next = $src.IndexOf('data-page="', $start + 20)
  if ($next -lt 0) { $next = $src.Length }
  $slice = $src.Substring($start, $next - $start)
  $n = ([regex]::Matches($slice, [regex]::Escape('font-size="' + $old + '"'))).Count
  $slice2 = $slice.Replace('font-size="' + $old + '"', 'font-size="' + $new + '"')
  Write-Output ("  " + $page + ": font-size " + $old + " -> " + $new + "  (" + $n + " hits)")
  return $src.Substring(0, $start) + $slice2 + $src.Substring($next)
}

$c = Fix $c 'embeddings'      '9'  '21'
$c = Fix $c 'test-dashboard'  '9'  '17'
$c = Fix $c 'authority-flow'  '10' '18'
$c = Fix $c 'command'         '10' '15'
$c = Fix $c 'command'         '14' '17'
$c = Fix $c 'analytics'       '10' '12'
$c = Fix $c 'monthly-reports' '10' '11'

Set-Content -Path $path -Value $c -NoNewline -Encoding UTF8
Write-Output ('macc 15: ' + ([regex]'>macc 15<').IsMatch($c))
