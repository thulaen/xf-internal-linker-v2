# renew-dev-cert.ps1
#
# Checks whether the mkcert localhost certificate will expire within 60 days.
# Parses + runs under Windows PowerShell 5.1 (no `?.` / `??` operators).

$ErrorActionPreference = 'Continue'

$certPath = Join-Path $PSScriptRoot '..\nginx\certs\localhost.pem'
$keyPath  = Join-Path $PSScriptRoot '..\nginx\certs\localhost-key.pem'
$DAYS_BEFORE_EXPIRY = 60

# Resolve to absolute so docker/mkcert paths are unambiguous. The cert may
# not exist yet on a fresh checkout; fall back to the literal path so mkcert
# can write to it.
function Resolve-OrLiteral {
    param(
        [Parameter(Mandatory)][string]$Path,
        [Parameter(Mandatory)][string]$Fallback
    )
    $resolved = Resolve-Path -LiteralPath $Path -ErrorAction SilentlyContinue
    if ($null -ne $resolved) {
        return $resolved.Path
    }
    return $Fallback
}

$certPath = Resolve-OrLiteral -Path $certPath -Fallback (Join-Path $PSScriptRoot '..\nginx\certs\localhost.pem')
$keyPath  = Resolve-OrLiteral -Path $keyPath  -Fallback (Join-Path $PSScriptRoot '..\nginx\certs\localhost-key.pem')

function Get-CertExpiry {
    param([string]$Path)
    try {
        $cert = New-Object System.Security.Cryptography.X509Certificates.X509Certificate2 $Path
        return $cert.NotAfter
    } catch {
        return $null
    }
}

$expiry = Get-CertExpiry $certPath
if ($null -eq $expiry) {
    Write-Host "[cert-renew] Certificate not found at $certPath - generating fresh cert." -ForegroundColor Yellow
} else {
    $daysLeft = ($expiry - (Get-Date)).Days
    Write-Host "[cert-renew] Certificate expires $expiry ($daysLeft days remaining)."
    if ($daysLeft -gt $DAYS_BEFORE_EXPIRY) {
        Write-Host "[cert-renew] No renewal needed. Run again after $(($expiry).AddDays(-$DAYS_BEFORE_EXPIRY).ToString('yyyy-MM-dd'))." -ForegroundColor Green
        exit 0
    }
    Write-Host "[cert-renew] Expiry within $DAYS_BEFORE_EXPIRY days - renewing." -ForegroundColor Yellow
}

# Regenerate the cert.
& mkcert -cert-file $certPath -key-file $keyPath localhost 127.0.0.1
if ($LASTEXITCODE -ne 0) {
    Write-Error "[cert-renew] mkcert failed. Check that mkcert is installed and the CA is still valid."
    exit 1
}
Write-Host "[cert-renew] Certificate renewed successfully." -ForegroundColor Green

# Reload Nginx (graceful - no dropped connections).
$projectRoot = (Resolve-Path "$PSScriptRoot\..").Path
Write-Host "[cert-renew] Reloading Nginx..."
& docker compose --project-directory $projectRoot exec nginx nginx -s reload
if ($LASTEXITCODE -eq 0) {
    Write-Host "[cert-renew] Nginx reloaded. New cert is live." -ForegroundColor Green
} else {
    Write-Warning "[cert-renew] Nginx reload failed - you may need to run 'docker compose restart nginx' manually."
}
