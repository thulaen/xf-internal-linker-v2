param()

$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$protectedPath = Join-Path $repoRoot "config\protected-data-stores.json"
$composePath = Join-Path $repoRoot "docker-compose.yml"

if (-not (Test-Path -LiteralPath $protectedPath)) {
    throw "Missing config\protected-data-stores.json."
}

$protected = Get-Content -LiteralPath $protectedPath -Raw | ConvertFrom-Json
$protectedVolumes = @($protected.docker_volumes)
$protectedHostPaths = @($protected.host_paths)
$composeText = Get-Content -LiteralPath $composePath -Raw

$missingVolumes = @()
$volumeBlock = $false
foreach ($line in ($composeText -split "(`r`n|`n|`r)")) {
    if ($line -match "^volumes:\s*$") {
        $volumeBlock = $true
        continue
    }
    if ($volumeBlock -and $line -match "^\S") {
        break
    }
    if ($volumeBlock -and $line -match "^\s{2}([A-Za-z0-9_.-]+):\s*$") {
        $name = $Matches[1]
        if ($protectedVolumes -notcontains $name) {
            $missingVolumes += $name
        }
    }
}

if ($missingVolumes.Count -gt 0) {
    throw "Docker volumes missing from protected-data-stores.json: $($missingVolumes -join ', ')"
}

foreach ($store in @($protected.future_data_stores)) {
    if (-not $store.name -or -not $store.required_storage -or -not $store.protected_by) {
        throw "Future data store entries need name, required_storage, and protected_by."
    }
}

foreach ($requiredPath in @(
    "backend/registry/data",
    "backend/registry/backups",
    "backend/telemetry/data",
    "backend/telemetry/backups"
)) {
    if ($protectedHostPaths -notcontains $requiredPath) {
        throw "Missing protected future host path: $requiredPath"
    }
}

$forbiddenPatterns = @(
    "docker\s+volume\s+prune",
    "docker\s+volume\s+rm",
    "docker\s+compose\s+down\s+-v",
    "docker-compose\s+down\s+-v",
    "docker\s+system\s+prune\s+.*--volumes",
    "docker\s+image\s+prune\s+-a"
)

$scriptFiles = Get-ChildItem -LiteralPath (Join-Path $repoRoot "scripts") -File -Recurse |
    Where-Object { $_.Extension -in @(".ps1", ".sh", ".py") }

foreach ($file in $scriptFiles) {
    # Read lines, drop pure comments, and strip quoted string literals
    # so a script that LISTS forbidden patterns (e.g.
    # `recover-docker-desktop-safe.ps1`'s `$ForbiddenCommandText`
    # array of strings to refuse) isn't itself flagged as if it ran
    # them. Quoted-mention is safe; bare command invocation is not.
    $rawLines = Get-Content -LiteralPath $file.FullName |
        Where-Object { $_ -notmatch '^\s*#' }
    $strippedLines = $rawLines | ForEach-Object {
        $line = $_
        $line = $line -replace '"[^"]*"', ''
        $line = $line -replace "'[^']*'", ''
        $line
    }
    $text = ($strippedLines | Out-String)
    foreach ($pattern in $forbiddenPatterns) {
        if ($text -match $pattern) {
            throw "Unsafe prune command found in $($file.FullName): $pattern"
        }
    }
}

Write-Host "Prune safety check passed. Protected volumes: $($protectedVolumes.Count)."
