param(
    [string]$ConfigPath = (Join-Path $PSScriptRoot "..\config\aws-cache-buckets.json")
)

$ErrorActionPreference = "Stop"

$resolvedConfigPath = Resolve-Path -LiteralPath $ConfigPath
$config = Get-Content -LiteralPath $resolvedConfigPath -Raw | ConvertFrom-Json

if (-not $config.retention_days -or [int]$config.retention_days -lt 1) {
    throw "retention_days must be a positive integer in $resolvedConfigPath"
}

if (-not $config.buckets -or $config.buckets.Count -eq 0) {
    throw "buckets must list at least one cache bucket in $resolvedConfigPath"
}

$seen = @{}
foreach ($bucket in $config.buckets) {
    if (-not $bucket.name) {
        throw "Every cache bucket entry must have a name"
    }
    if ($seen.ContainsKey($bucket.name)) {
        throw "Duplicate cache bucket '$($bucket.name)' in $resolvedConfigPath"
    }
    $seen[$bucket.name] = $true
}

$days = [int]$config.retention_days
$ruleId = [string]$config.lifecycle_rule_id

foreach ($bucket in $config.buckets) {
    $lifecycle = @{
        Rules = @(
            @{
                ID = $ruleId
                Status = "Enabled"
                Filter = @{ Prefix = "" }
                Expiration = @{ Days = $days }
                NoncurrentVersionExpiration = @{ NoncurrentDays = $days }
                AbortIncompleteMultipartUpload = @{ DaysAfterInitiation = 7 }
            }
        )
    }

    $tempFile = New-TemporaryFile
    try {
        $lifecycle | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $tempFile -Encoding UTF8
        aws s3api put-bucket-lifecycle-configuration `
            --bucket $bucket.name `
            --lifecycle-configuration "file://$tempFile"
        Write-Host "Applied $days-day cache retention to $($bucket.name)"
    }
    finally {
        Remove-Item -LiteralPath $tempFile -Force -ErrorAction SilentlyContinue
    }
}
