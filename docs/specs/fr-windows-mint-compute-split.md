# FR: Windows / Mint Compute Split

[SPEC FRESHNESS: reviewed_at=2026-06-02 next_review=2026-09-02]

## Summary

Windows is the 65% CPU compute worker for eligible quality shards.
Mint is the 35% compute worker and the sole durable artifact store.
Runtime containers use `xf-linker-backend-runtime:latest`.
Quality containers use `xf-linker-backend-quality:latest` (Docker Compose `quality` profile).
Durable shard outputs go to Mint via a SHA-256 content-addressed blob store at `/srv/xf/artifacts/`.
Windows temp shard outputs live in `C:\xf\temp-runs\` and are deleted after confirmed upload.

## Compute Split

| Node    | Share | Method     |
|---------|-------|------------|
| Windows | 65%   | Hamilton largest-remainder |
| Mint    | 35%   | Hamilton largest-remainder |

The `distribute_shards(n_shards, weights)` function in `scripts/shard_manifest.py`
implements the Hamilton (largest-remainder) apportionment method so the returned
integers always sum exactly to `n_shards`.

Reference: Balinski & Young 1982, *Fair Representation* (ISBN 978-0815710103).

### Compute Profiles

```
2m           — Windows 65%, Mint 35%
3m_one_strong — strong 58%, weak1 31%, weak2 31%
3m_two_strong — strong1 49%, strong2 49%, weak 22%
```

Storage placement: always `mint`, regardless of which node ran the shard.

## Backend Image Split

The `backend/Dockerfile` has three named targets:

| Target    | Base               | Purpose |
|-----------|--------------------|---------|
| go-tools  | golang:1.25-bookworm | Builds go-mutesting binary — no runtime output |
| runtime   | python:3.12-slim    | Production runtime; used by backend, celery workers, celery-beat |
| quality   | FROM runtime        | Extends runtime with all quality tools — never used in production |

Quality-only packages absent from runtime:
`mutmut`, `ruff`, `bandit`, `pip-audit`, `safety`, `pylint`, `coverage`,
`pytest`, `hypothesis`, Go toolchain, go-mutesting binary, luarocks, busted,
luacheck, luacov, luacov-cobertura, lua-quickcheck.

Reference: Docker multi-stage builds — https://docs.docker.com/build/building/multi-stage/

## Docker Compose Services

| Service              | Image                             | Profile  |
|----------------------|-----------------------------------|----------|
| backend              | xf-linker-backend-runtime:latest  | (default)|
| celery-worker-default| xf-linker-backend-runtime:latest  | (default)|
| celery-worker-pipeline| xf-linker-backend-runtime:latest | (default)|
| celery-beat          | xf-linker-backend-runtime:latest  | (default)|
| backend-quality      | xf-linker-backend-quality:latest  | quality  |

The `backend-quality` service is only started with `docker compose --profile quality`.
It is never started by a plain `docker compose up`.

## Mint Canonical Root and Layout

Mint artifact root: `/srv/xf/`

```
/srv/xf/
  bazel-cache/                         Bazel remote cache (Bazel-managed)
  bazel-cas/                           Bazel remote-execution CAS (Bazel-managed)
  artifacts/
    blob-store/sha256/<first2>/<sha256>  One file per unique artifact (content-addressed)
    runs/<run_id>/manifest.json          Per-run manifest (JSONL format — one entry per line)
    runs/<run_id>/merged/                Final merged outputs (also referenced via blobs)
  reports/                             Human-facing summaries
  backups/postgres/                    Postgres backups from Windows pg_dump
  temp-upload/                         Staging area; files renamed atomically into blob-store
```

Reference: Bazel remote cache — https://bazel.build/remote/rbe

## Blob Store Upload Protocol

Implemented in `scripts/mint_blob_store.py`.

1. Compute SHA-256 of the local artifact.
2. SSH: `test -f /srv/xf/artifacts/blob-store/sha256/<first2>/<sha256>` (check existence).
3. If blob exists → skip upload (deduplication: identical bytes stored once).
4. If blob is new → SCP to `/srv/xf/temp-upload/<sha256>.tmp`, then SSH `mv` to blob-store path (atomic rename).
5. Append JSONL manifest entry to `/srv/xf/artifacts/runs/<run_id>/manifest.json`.
6. Return confirmed manifest entry dict.
7. If SCP or rename fails → raise `RuntimeError`; caller fails the shard clearly.

Manifest entry fields (10 required):

```json
{
  "run_id":           "<run_id>",
  "worker":           "windows",
  "shard_id":         "<shard_id>",
  "tool":             "mutmut",
  "logical_path":     "mutation/backend/apps/audit/results.json",
  "sha256":           "<full_sha256_hex>",
  "size_bytes":       12345,
  "media_type":       "application/json",
  "created_at":       "2026-05-27T14:00:00Z",
  "required_for_merge": true
}
```

Reference: SHA-256 content addressing — RFC 6234
(https://datatracker.ietf.org/doc/html/rfc6234)

## Blob Store Deduplication

Two uploads of identical bytes create one blob and two manifest entries.
The blob is stored once at `/srv/xf/artifacts/blob-store/sha256/<first2>/<sha256>`.
Both runs' manifests reference the same sha256 — no duplicate bytes on disk.

## Blob Garbage Collection

Implemented in `scripts/mint_gc.py`.

1. Enumerate all blobs in the blob-store tree.
2. Enumerate all SHA-256 values referenced by manifests inside the 14-day test/cache retention window.
3. Blobs older than the grace period that are NOT referenced → eligible for deletion.
4. **Invariant: a blob referenced by any retained manifest is NEVER deleted.**
5. Bazel cache/CAS are managed by Bazel's own eviction — `mint_gc.py` never touches those.

Mint test and quality caches use a 14-day retention policy. Duplicate cache
and artifact bytes are stored once in the SHA-256 blob store; multiple run
manifests may point at the same blob, but the blob itself is not copied.

## Windows Storage Roots and Caps

| Root                      | Cap   | Contents |
|---------------------------|-------|----------|
| `C:\xf\pgdata\`           | 20 GB | PostgreSQL data directory |
| `C:\xf\frontend-runtime\` |  5 GB | Compiled Angular bundles |
| `C:\xf\bazel-output-base\`|  5 GB | Bazel output base |
| `C:\xf\temp-runs\`        |  2 GB | Per-shard temp artifacts (deleted after upload) |
| `C:\xf\tool-cache\`       | 15 GB | Python 2 GB + Go 3 GB + Rust 8 GB + npm 2 GB |

Caps are checked by `scripts/check-windows-storage.ps1` (warning only, not hard fail).

## Windows Artifact Lifecycle

1. Shard runs a quality tool on the Windows-assigned files.
2. Tool output written to `C:\xf\temp-runs\<run_id>\<tool>\`.
3. `scripts/upload-artifacts-to-mint.ps1` calls `scripts/mint_blob_store.py` to upload.
4. After confirmed upload, `Remove-Item` deletes the local temp.
5. `validate_safe_delete_path()` in `scripts/windows_storage.py` refuses deletion
   of any path outside `C:\xf\` or `%TEMP%`.

## What Windows Must NOT Retain Long-Term

- Long-term logs
- Coverage reports
- Mutation reports
- Screenshots, browser traces
- Static scanner report files
- Bazel remote cache (lives on Mint)
- Durable build artifacts
- Merged final reports
- Old shard outputs (deleted after confirmed upload to Mint)

Mint keeps uploaded test/cache artifacts for 14 days and dedupes them by
SHA-256, so repeated identical test output consumes one blob plus lightweight
manifest references.

## Windows Host Tools (Clean-Native)

Installed by `scripts/install-windows-host-tools.ps1` (idempotent):

| Tool          | Install Method          |
|---------------|-------------------------|
| Go            | winget GoLang.Go        |
| Rustup        | winget Rustlang.Rustup  |
| CMake         | winget Kitware.CMake    |
| Ninja         | winget Ninja-build.Ninja|
| Cppcheck      | winget Cppcheck.Cppcheck|
| golangci-lint | GitHub release ZIP      |
| protoc        | GitHub release ZIP      |
| Buf           | go install              |
| go-mutesting  | go install              |
| cargo-mutants | cargo install           |

**Not installed on Windows:** Infer, Mull, Haskell/GHC/Cabal.
**Remain on Mint/Docker:** C++ Mull, Infer, Haskell checks, compiled-tools final pass.

## Mint-Only Tools

- Mull (C++ mutation)
- Infer (Java/C++ static analysis)
- Haskell/GHC/Cabal checks
- compiled-tools final reproducible pass
- GlitchTip, Pyroscope, VictoriaMetrics, Grafana (observability stack on Mint)

## Preparation for Kubernetes and Bazel

The shard manifest format (`scripts/shard_manifest.py`) mirrors the K8s Job → remote-cache pattern:
- `distribute_shards()` produces a deterministic integer allocation
- Each shard writes to `C:\xf\temp-runs\<run_id>\` then uploads to the Mint blob store
- The Mint blob store content-addresses artifacts the same way Bazel CAS does

Reference: Kubernetes Jobs — https://kubernetes.io/docs/concepts/workloads/controllers/job/

## Plain-English Operator Summary

Windows is allowed to keep working cache but never durable generated outputs.
Mint stores durable outputs, and Mint storage is content-addressed by SHA-256 hash
so it never becomes a duplicate pile of identical bytes.

Every shard artifact that Windows produces is:
1. Written to a temp folder under `C:\xf\temp-runs\`.
2. Uploaded to Mint.
3. Deleted from Windows after the upload is confirmed.

The upload script refuses to delete any file outside `C:\xf\` or the system temp folder,
so it cannot accidentally delete source code.

## Failed-Shard AutoIssue Integration

When a distributed shard fails, the failure is filed as an AutoIssue in the Windows Postgres
database so it appears in the standard issue queue alongside GlitchTip errors, Pyroscope
hotspots, and mutation survivors.

### AutoIssue Fields

| Field | Value |
|---|---|
| `source` | `test_failure` |
| `category.key` | `failed_test` |
| `external_id` | `failed_test::<tool>::<test_target>::<test_file>::<test_name>::<fingerprint>` |
| `artifact_refs` | List of `{sha256, blob_path, tool, run_id, shard_id, media_type}` dicts |
| `severity` | `high` for infra/timeout; `medium` for deterministic failure; `low` for flaky |

The `external_id` deduplicates failures: the same test failing across two runs creates one
AutoIssue with `occurrence_count` incremented, not two separate rows.  A resolved AutoIssue
is reopened automatically when the same `external_id` reappears.

The `failure_fingerprint` inside `external_id` is a 16-character SHA-1 prefix of the
normalised failure summary (UUIDs, timestamps, temp paths, and digit runs stripped out),
matching the approach already used by the GlitchTip and CI-failure pickers.

### Evidence Storage

Heavy evidence (JUnit XML, coverage reports, mutation output, traces, logs, crash dumps,
SARIF) goes to the Mint blob store under `/srv/xf/artifacts/`.  Only the SHA-256 reference
and blob path are stored in `artifact_refs` on the AutoIssue row — no large content in
Postgres.

### Merge Gate

The final merge step (`scripts/merge_shard_outputs.py::check_failed_shards()`) refuses to
proceed if any manifest entry has `failed=True` and `required_for_merge=True` without an
`autoissue_id`.  This ensures every failed required shard is visible in the issue tracker
before results are merged.

### Management Command

```
python manage.py file_test_failure \
    --tool mutmut --test-target backend.apps.audit \
    --test-file apps/audit/tasks.py --test-name test_mutation_line_42 \
    --failure-summary "Mutant survived: replace + with -" \
    --severity medium --run-id run-001 --shard-id shard-0 \
    [--artifact-ref sha256=abc... blob_path=/srv/xf/...]
```

Prints `[TEST FAILURE AUTOISSUE: #<id> action=created|updated|reopened]`.

## Citations

- Docker multi-stage builds: https://docs.docker.com/build/building/multi-stage/
- Hamilton apportionment (largest-remainder method): Balinski & Young 1982, ISBN 978-0815710103
- Bazel remote cache: https://bazel.build/remote/rbe
- Kubernetes Jobs: https://kubernetes.io/docs/concepts/workloads/controllers/job/
- SHA-256 content addressing: RFC 6234 (https://datatracker.ietf.org/doc/html/rfc6234)

[SPEC CITED: feature=fr-windows-mint-compute-split kind=technical_doc id=https://docs.docker.com/build/building/multi-stage/ verified_at=2026-06-02]
