<#
.SYNOPSIS
    SLICE-21 GO-LIVE STEP — copy the OLD monitoring history off the Windows (MSI)
    Docker named volumes and stage it for the Kubernetes cluster.

.DESCRIPTION
    Plain English: today the monitoring history (metrics, logs, traces, Grafana
    settings, profiles) lives inside Docker named volumes on this Windows machine.
    When we move monitoring into the cluster for real ("go-live"), that history
    must come along. This script does the FIRST half of the move on Windows:

      1. For each named volume, pack it into one compressed tarball.
      2. Compute a SHA-256 fingerprint of the tarball and save it next to it.
      3. Copy the tarball + fingerprint to the Mint NFS staging folder.
      4. Re-read the copied fingerprint and compare. If it does not match, RETRY
         (up to -MaxRetries times). If it still does not match, FAIL LOUDLY — it
         NEVER reports a broken copy as "done".
      5. Skip a volume whose staged fingerprint already matches (resumable).

    The SECOND half — unpacking each tarball into the matching cluster disk
    (PersistentVolumeClaim) — is done inside the cluster by
    k8s/obs/history-copy/restore-job.yaml, which re-verifies the fingerprint
    again before extracting (so corruption that happens after this script is
    still caught).

    THIS IS A GO-LIVE-ONLY STEP. Run it exactly ONCE, at the real cutover, AFTER
    the live application has stopped writing to these volumes. Do NOT run it
    during a rehearsal — a rehearsal starts the cluster monitoring on empty disks
    on purpose.

    The mirror of the repo's WiFi-resilience rule (checksum-verify + retry every
    transfer to a node) lives in docs/network/wifi-resilience-baseline.md and the
    reference implementation is tools/preflight/cluster_lib.sh
    (transfer_with_checksum_retry). This script follows that same spirit.

.PARAMETER StagingTarget
    Where to copy the tarballs so the cluster can read them. Two forms:
      - A filesystem/UNC path that is already mounted on this machine, e.g. a
        mapped drive to the Mint NFS export:  \\10.10.10.91\cluster\obs-history-staging
        or  M:\obs-history-staging
      - An scp destination of the form  user@host:/abs/path , e.g.
        mint@192.168.0.91:/srv/nfs/cluster/obs-history-staging
    No credentials are ever hardcoded. For the scp form, rely on your existing
    SSH key / agent (the same "mint-wifi" style access the preflight scripts use).
    Default points at the Mint NFS staging folder over the wired backbone via a
    UNC path; override it to match how this machine actually reaches Mint.

.PARAMETER StageDir
    Local scratch folder where tarballs are built before they are copied out.
    Default: a folder under the system temp directory. It is reused between runs
    so a re-run can skip volumes that are already staged.

.PARAMETER MaxRetries
    How many times to retry a single volume's copy when the remote fingerprint
    does not match. Default 3.

.PARAMETER Volumes
    Override the list of Docker volume names to migrate. Default is the five
    file-backed monitoring volumes (see the table below). The pyroscope volume
    is included but NOTE: it normally lives on the Mint helper, not MSI — see the
    "NOTES" section. Pass a subset to migrate only some volumes.

.EXAMPLE
    # Dry-run-style listing first (Docker must be running, volumes present):
    docker volume ls

    # Real go-live copy to a mapped Mint NFS drive:
    pwsh -File scripts/obs-history-copy.ps1 -StagingTarget 'M:\obs-history-staging'

.EXAMPLE
    # Real go-live copy over scp using your existing SSH key:
    pwsh -File scripts/obs-history-copy.ps1 `
        -StagingTarget 'mint@192.168.0.91:/srv/nfs/cluster/obs-history-staging'

.NOTES
    SLICE-21 source-volume -> cluster PVC map (namespace xf-obs):
      vmsingle_data  -> PVC vmsingle-data  (mount /storage)
      loki_data      -> PVC loki-data      (mount /loki)
      tempo_data     -> PVC tempo-data     (mount /var/tempo)
      grafana_data   -> PVC grafana-data   (mount /var/lib/grafana)
      pyroscope_data -> PVC pyroscope-data (mount /data)
                        ^ NOTE: pyroscope_data currently lives on the MINT helper,
                          not on this MSI host. If you run this script on MSI it
                          will report pyroscope_data as "not found" and FAIL that
                          one volume. Either run the pyroscope export step on Mint,
                          or drop it from -Volumes here and stage it separately.

      alloy_data is intentionally SKIPPED: in the cluster alloy uses emptyDir, and
      its write-ahead log / scrape "positions" are reconstructable, so there is no
      durable history worth copying.

      GlitchTip has NO file volume to copy. Its data lives in the Postgres
      "glitchtip" database and rides the SLICE-13 live-database move (a
      pg_dump / pg_restore), NOT a volume tar copy. Do not look for a
      glitchtip_data volume here — there isn't one.
#>

[CmdletBinding()]
param(
    [string]$StagingTarget = '\\10.10.10.91\cluster\obs-history-staging',
    [string]$StageDir = (Join-Path $env:TEMP 'xf-obs-history-stage'),
    [int]$MaxRetries = 3,
    [string[]]$Volumes = @(
        'vmsingle_data',
        'loki_data',
        'tempo_data',
        'grafana_data',
        'pyroscope_data'
    )
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

# --- helpers ---------------------------------------------------------------

# True when StagingTarget is an scp destination (user@host:/path) rather than a
# local/UNC filesystem path. A bare Windows drive like "M:\..." is NOT scp.
function Test-ScpTarget {
    param([Parameter(Mandatory)] [string]$Target)
    # Matches host:/path or user@host:/path, but not a single-letter drive (C:\).
    return ($Target -match '^[^\\/]+@[^:]+:.+$') -or
           ($Target -match '^[A-Za-z0-9._-]{2,}:/.+$')
}

# Does the named Docker volume exist on this host?
function Test-DockerVolume {
    param([Parameter(Mandatory)] [string]$Name)
    docker volume inspect $Name *> $null
    return ($LASTEXITCODE -eq 0)
}

# Pack one Docker volume into a gzip tarball at $OutTar using a throwaway alpine
# container. Read-only mount of the source so the live data is never altered.
function Export-VolumeTarball {
    param(
        [Parameter(Mandatory)] [string]$Volume,
        [Parameter(Mandatory)] [string]$StageDir,
        [Parameter(Mandatory)] [string]$OutTar
    )
    $tarName = Split-Path $OutTar -Leaf
    docker run --rm `
        -v "${Volume}:/src:ro" `
        -v "${StageDir}:/out" `
        alpine sh -c "tar czf /out/$tarName -C /src ."
    if ($LASTEXITCODE -ne 0) {
        throw "tar of volume '$Volume' failed (docker exit $LASTEXITCODE)"
    }
    if (-not (Test-Path -LiteralPath $OutTar)) {
        throw "tarball '$OutTar' was not produced"
    }
}

# Compute the lowercase SHA-256 hex of a file (matches `sha256sum` output text).
function Get-Sha256Hex {
    param([Parameter(Mandatory)] [string]$Path)
    return (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash.ToLower()
}

# Read the remote fingerprint that was copied alongside the tarball. Returns the
# hex string, or $null if it cannot be read. Works for both local/UNC and scp.
function Get-RemoteSha256 {
    param(
        [Parameter(Mandatory)] [string]$Target,
        [Parameter(Mandatory)] [string]$ShaFileName
    )
    if (Test-ScpTarget $Target) {
        $parts = $Target -split ':', 2
        $host_ = $parts[0]; $path = $parts[1].TrimEnd('/')
        $remote = & ssh -o BatchMode=yes $host_ "cat '$path/$ShaFileName' 2>/dev/null"
        if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($remote)) { return $null }
        return ($remote -split '\s+')[0].Trim().ToLower()
    }
    $remotePath = Join-Path $Target $ShaFileName
    if (-not (Test-Path -LiteralPath $remotePath)) { return $null }
    return ((Get-Content -LiteralPath $remotePath -Raw) -split '\s+')[0].Trim().ToLower()
}

# Copy the tarball + its .sha256 sidecar to the staging target (local/UNC or scp).
function Copy-PairToTarget {
    param(
        [Parameter(Mandatory)] [string]$Target,
        [Parameter(Mandatory)] [string]$TarPath,
        [Parameter(Mandatory)] [string]$ShaPath
    )
    if (Test-ScpTarget $Target) {
        $dest = $Target.TrimEnd('/') + '/'
        & scp -q -o BatchMode=yes $TarPath $ShaPath $dest
        if ($LASTEXITCODE -ne 0) { throw "scp to '$Target' failed (exit $LASTEXITCODE)" }
        return
    }
    if (-not (Test-Path -LiteralPath $Target)) {
        New-Item -ItemType Directory -Path $Target -Force | Out-Null
    }
    Copy-Item -LiteralPath $TarPath -Destination $Target -Force
    Copy-Item -LiteralPath $ShaPath -Destination $Target -Force
}

# Migrate exactly one volume end to end. Returns $true on a verified copy,
# $false on a final failure (after retries). Never throws on a copy mismatch —
# it records the failure and the caller decides the exit code.
function Invoke-VolumeMigration {
    param(
        [Parameter(Mandatory)] [string]$Volume,
        [Parameter(Mandatory)] [string]$StageDir,
        [Parameter(Mandatory)] [string]$Target,
        [Parameter(Mandatory)] [int]$MaxRetries
    )
    if (-not (Test-DockerVolume $Volume)) {
        Write-Warning "[$Volume] volume not found on this host — skipping (FAIL)."
        return $false
    }

    $tar = Join-Path $StageDir "$Volume.tar.gz"
    $sha = "$tar.sha256"
    $shaName = Split-Path $sha -Leaf

    Write-Host "[$Volume] packing tarball..."
    Export-VolumeTarball -Volume $Volume -StageDir $StageDir -OutTar $tar
    $want = Get-Sha256Hex -Path $tar
    "$want  $Volume.tar.gz" | Set-Content -LiteralPath $sha -Encoding ascii -NoNewline
    Write-Host "[$Volume] sha256=$want"

    # Resumable: if the staged copy already matches, do not re-copy.
    if ((Get-RemoteSha256 -Target $Target -ShaFileName $shaName) -eq $want) {
        Write-Host "[$Volume] already staged with matching fingerprint — skipping copy."
        return $true
    }

    for ($attempt = 1; $attempt -le $MaxRetries; $attempt++) {
        Write-Host "[$Volume] copy attempt $attempt of $MaxRetries -> $Target"
        try {
            Copy-PairToTarget -Target $Target -TarPath $tar -ShaPath $sha
        } catch {
            Write-Warning "[$Volume] copy attempt $attempt errored: $($_.Exception.Message)"
            continue
        }
        if ((Get-RemoteSha256 -Target $Target -ShaFileName $shaName) -eq $want) {
            Write-Host "[$Volume] VERIFIED: staged fingerprint matches the source."
            return $true
        }
        Write-Warning "[$Volume] staged fingerprint did NOT match after attempt $attempt."
    }

    Write-Warning "[$Volume] FAILED after $MaxRetries attempts — staged copy never matched the source. Nothing was marked done."
    return $false
}

# --- main ------------------------------------------------------------------

Write-Host '=== SLICE-21 GO-LIVE: monitoring history copy (Windows -> Mint staging) ==='
Write-Host "Staging target : $StagingTarget"
Write-Host "Local stage dir: $StageDir"
Write-Host "Volumes        : $($Volumes -join ', ')"
Write-Host '(GO-LIVE ONLY. Do NOT run during a rehearsal.)'
Write-Host ''

# Docker must be reachable, or every volume export would fail the same way.
docker version *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Warning 'Docker is not reachable. Start Docker Desktop and retry.'
    exit 2
}

if (-not (Test-Path -LiteralPath $StageDir)) {
    New-Item -ItemType Directory -Path $StageDir -Force | Out-Null
}

$results = [ordered]@{}
foreach ($vol in $Volumes) {
    $results[$vol] = Invoke-VolumeMigration -Volume $vol -StageDir $StageDir `
        -Target $StagingTarget -MaxRetries $MaxRetries
}

Write-Host ''
Write-Host '=== PER-VOLUME SUMMARY ==='
$failed = 0
foreach ($vol in $results.Keys) {
    if ($results[$vol]) {
        Write-Host ("  PASS  {0}" -f $vol)
    } else {
        Write-Host ("  FAIL  {0}" -f $vol)
        $failed++
    }
}

if ($failed -gt 0) {
    Write-Warning "$failed volume(s) FAILED. Fix the cause and re-run (it resumes the good ones)."
    exit 1
}

Write-Host ''
Write-Host 'ALL VOLUMES STAGED AND VERIFIED.'
Write-Host 'Next: run the cluster restore Job per volume — see k8s/obs/history-copy/restore-job.yaml.'
exit 0
