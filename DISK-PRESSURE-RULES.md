# DISK-PRESSURE-RULES.md - Free-Space Watermarks And Pre-Flight Guards

**Status:** PARAMOUNT for any change that creates new artefact rows, downloads model weights, or writes to media or `backups/`.

## Why This File Exists

The user wants at least 48 GB free disk kept available for app data, embeddings, backups, and database growth. Docker stale build cache can use 20 GB or more if it is not pruned. Embedding comparisons and provider switches can write multi-GB temporary files. Without watermarks, a large batch can fill the disk and make the database fail.

## The Watermarks

| Free disk | State | Action |
|---|---|---|
| 64 GB or more | GREEN | All writes proceed normally |
| 48-64 GB | YELLOW | Start safe cleanup of Docker build cache, stopped containers, quality temp folders, old coverage folders, and old mutation folders |
| 1-48 GB | RED | Project-wide write circuit breaker starts; new bulky artefact rows and quality runs wait until cleanup restores space |
| Less than 1 GB | CRITICAL | Backups stop, Postgres goes read-only, embed pipeline pauses |

## Tool Cache Prune Policy

Tool caches are disposable. App data, embeddings, database volumes, uploaded media, and backups are not disposable.

- Normal rule: keep deduped tool-cache entries for 3 days.
- Pressure rule: when free disk falls below 64 GB, prune stale disposable tool-cache entries older than 2 days.
- Reserve rule: when free disk falls below 48 GB, stop bulky verification work until cleanup restores the reserve.
- Shared-volume rule: tool caches must live in shared Docker volumes listed in `config/protected-data-stores.json`, not in separate per-container copies.
- Safety rule: cleanup may delete disposable cache contents, but must not delete Docker volumes or protected app data stores.

Current deduped tool-cache volumes:

- `compiled_tool_cache`
- `frontend_tool_cache`
- `go_tool_mod_cache`

## The Pre-Flight Guard

Every Celery task that estimates a multi-GB write must call:

```python
from apps.pipeline.services.disk_pressure import require_free_disk

require_free_disk(estimated_bytes=expected_write_size, safety_margin_gb=48)
```

Raises `DiskPressureError` if the projected write plus safety margin exceeds free disk. The caller catches and reports this to `/error-log` with a link to the cleanup and Docker reclaim scripts.

## The Circuit Breaker

A `DiskPressureMonitor` Celery beat task runs every 60 seconds, checks `shutil.disk_usage()`, and writes the current state to `cache.set("disk_pressure_state", state)`.

Writers consult the state via `apps.pipeline.services.disk_pressure.current_state()` before any large write. RED skips the write and queues the row in Redis for retry. A separate retry task runs every 30 seconds and drains the queue when the state returns to GREEN.

## Visibility

- Quick-Controls card on Dashboard shows current free GB and state chip.
- `/diagnostics` System Health card "Disk pressure" surfaces the live watermark.
- Each pressure-state transition logs to `/error-log` with severity `warning` for YELLOW and `critical` for RED.

## Operator Recovery Steps

When the operator sees a YELLOW, RED, or CRITICAL chip:

1. Run `powershell -ExecutionPolicy Bypass -File scripts/prune-verification-artifacts.ps1` to clear Docker build cache. This usually frees 5-20 GB inside Docker.
2. Run `powershell -ExecutionPolicy Bypass -File scripts/reclaim-docker-windows-space.ps1` for the no-downtime Windows reclaim path. This keeps the app running and never deletes Docker volumes.
3. If Windows still does not show the freed space, schedule downtime and run `powershell -ExecutionPolicy Bypass -File scripts/reclaim-docker-windows-space.ps1 -AllowDowntime`. Full virtual-disk compaction requires Docker or WSL to stop; do not run it while the app must stay online.
4. Optionally delete old `SupersededEmbedding` rows older than 7 days. The `nightly_data_retention` task does this automatically. Manual trigger: `nightly_data_retention.delay()`.

## Forbidden Patterns

- Do not tar or zip a multi-GB artefact to a `temp/` directory before processing. Stream instead.
- Do not persist intermediate state of a comparison run. Winner-only writes; loser data is discarded.
- Do not skip the pre-flight guard because a write looks small. Small writes still add up.
- Do not catch `DiskPressureError` and proceed anyway.
- Do not disable the circuit-breaker monitor for performance reasons.
