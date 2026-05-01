# DISK-PRESSURE-RULES.md — Free-Space Watermarks And Pre-Flight Guards

**Status:** PARAMOUNT for any change that creates new artefact rows, downloads model weights, or writes to media/`backups/`.

## Why This File Exists

The user has 59 GB free disk on a 150 GB Windows VHDX. Docker's stale build cache routinely eats 20+ GB if not pruned (which is why the session-end prune script exists). Embedding comparisons + provider switches can write multi-GB temp files. Without watermarks, a runaway batch silently fills the disk and the database OOMs the laptop.

## The Watermarks

| Free disk | State | Action |
|---|---|---|
| ≥ 10 GB | GREEN | All writes proceed normally |
| 5–10 GB | YELLOW | Operator chip on Quick-Controls; new comparison runs deferred; existing runs continue |
| < 5 GB | RED | Project-wide write circuit-breaker engages; new artefact rows queued in Redis; operator alerted |
| < 1 GB | CRITICAL | Backups stop, Postgres goes read-only, embed pipeline pauses |

## The Pre-Flight Guard

Every Celery task that estimates a multi-GB write must call:

```python
from apps.pipeline.services.disk_pressure import require_free_disk

require_free_disk(estimated_bytes=expected_write_size, safety_margin_gb=5)
```

Raises `DiskPressureError` if the projected write + safety margin exceeds free disk. Caller catches and reports to `/error-log` with a link to the existing `docker_compact_vhd.ps1` script.

## The Circuit Breaker

A `DiskPressureMonitor` Celery beat task runs every 60 seconds, checks `shutil.disk_usage()`, and writes the current state to `cache.set("disk_pressure_state", state)`.

Writers consult the state via `apps.pipeline.services.disk_pressure.current_state()` before any large write. RED skips the write and queues the row in Redis for retry. A separate retry task runs every 30 seconds and drains the queue when the state returns to GREEN.

## Visibility

- Quick-Controls card on Dashboard shows current free GB + state chip.
- `/diagnostics` System Health card "Disk pressure" surfaces the live watermark.
- Each pressure-state transition logs to `/error-log` (severity=warning for YELLOW, severity=critical for RED).

## Operator Recovery Steps (Plain-English)

When the operator sees a RED chip:
1. Run `powershell -ExecutionPolicy Bypass -File scripts/prune-verification-artifacts.ps1` to clear Docker build cache (typically frees 5–20 GB).
2. Run `powershell -ExecutionPolicy Bypass -File docker_compact_vhd.ps1` to compact the Windows VHDX so freed space returns to Windows.
3. Optionally delete old `SupersededEmbedding` rows older than 7 days (the `nightly_data_retention` task does this automatically; manual trigger via Django shell `nightly_data_retention.delay()`).

## Forbidden Patterns

- ❌ Tar / zip a multi-GB artefact to a `temp/` directory before processing — stream instead
- ❌ Persist intermediate state of a comparison run (winner-only writes; loser is discarded)
- ❌ Skip the pre-flight guard "because it's only 100 MB" — small writes still hit the ceiling cumulatively
- ❌ Catch `DiskPressureError` and proceed anyway
- ❌ Disable the circuit-breaker monitor for "performance" reasons
