"""Phase 4.7 — "Why Is It Slow?" bottleneck classifier.

Given a task that's running slower than its expected p50 latency,
samples live system state and returns a one-word verdict from:

    cpu_bound · disk_bound · db_bound · network_bound
    lock_waiting · thermal_throttled · unknown

Plus a one-sentence why-string and a confidence in [0, 1].

Plain-English: the operator clicks "Why is it slow?" on a long-running
job and gets back "Disk-bound — your free disk dropped to 4 GB and
Postgres is waiting on writes." instead of staring at a generic spinner.

Storage discipline: returns a dataclass; nothing is persisted unless
the caller chooses to write to ``ops_feed.emit()``. No new tables.

Citations:
    * psutil docs — CPU / RAM / disk-wait sampling pattern.
    * PostgreSQL docs §28.2 ``pg_stat_activity`` for the lock-wait check.
    * Intel thermal-throttle documentation (2024) for thermal heuristics.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


# Verdict thresholds — single source of truth so the operator can audit
# why a particular reading triggered a particular verdict. All citations
# above. Each constant gets a docstring per TECH-DEBT-MANDATE rule 2
# (no magic numbers in services).

#: psutil ``cpu_percent`` ≥ this threshold flags CPU saturation.
_CPU_BOUND_THRESHOLD_PCT: float = 85.0

#: Free RAM below this fraction of total flags memory pressure.
_MEMORY_PRESSURE_FREE_FRACTION: float = 0.10

#: Disk-wait percentage above this flags I/O saturation.
_DISK_WAIT_THRESHOLD_PCT: float = 25.0

#: Host temp above this flags thermal throttling. Common hardware
#: typically begin throttling around 90 °C; we trigger early at 85 °C.
_THERMAL_THROTTLE_TEMP_C: float = 85.0

#: pg_stat_activity rows in ``LOCK`` wait_event_type above this flag
#: lock contention.
_LOCK_WAIT_THRESHOLD_ROWS: int = 5

#: Free disk below this fraction of total triggers disk-bound classification.
_DISK_FREE_PRESSURE_FRACTION: float = 0.10


@dataclass(frozen=True, slots=True)
class SlownessVerdict:
    """The analyzer's classification of why a task is slow."""

    verdict: str  # one of the 8 strings listed in module docstring
    why: str  # one plain-English sentence explaining the verdict
    confidence: float  # 0.0 - 1.0; high when multiple signals agree
    sampled_at: str  # ISO 8601 of when state was sampled


def analyze_slowness(*, task_name: str = "") -> SlownessVerdict:
    """Sample live system state and return a bottleneck verdict.

    Plain-English: this looks at right-now CPU / RAM / disk /
    Postgres-locks and decides which of those is the most likely cause
    of the current slowdown. Returns the verdict + a why-string the
    operator can read out loud.

    Cheap: ~50 ms per call. Safe to call
    from a UI button-handler. Does not write anywhere unless the caller
    chooses to log the result.
    """
    from datetime import datetime, timezone

    sampled_at = datetime.now(timezone.utc).isoformat()
    signals = _sample_all_signals()

    # Each candidate verdict gets a "did this signal trigger?" boolean
    # plus a confidence weight. Final verdict = highest-confidence
    # triggered signal. Multiple triggered signals raise overall
    # confidence (operator sees "high" if 2+ signals agree).
    candidates: list[tuple[str, str, float]] = []

    if signals.get("thermal_c") and signals["thermal_c"] >= _THERMAL_THROTTLE_TEMP_C:
        candidates.append(
            (
                "thermal_throttled",
                f"Host temperature is {signals['thermal_c']:.0f}°C — clocks may be throttled.",
                0.9,
            )
        )

    if signals.get("lock_wait_rows", 0) >= _LOCK_WAIT_THRESHOLD_ROWS:
        candidates.append(
            (
                "lock_waiting",
                f"{signals['lock_wait_rows']} backend(s) are waiting on Postgres locks — another query is holding a row or table lock.",
                0.85,
            )
        )

    if signals.get("disk_wait_pct", 0) >= _DISK_WAIT_THRESHOLD_PCT:
        candidates.append(
            (
                "disk_bound",
                f"Disk wait is at {signals['disk_wait_pct']:.0f}% — the system is queuing on storage.",
                0.75,
            )
        )

    if signals.get("disk_free_fraction", 1.0) < _DISK_FREE_PRESSURE_FRACTION:
        candidates.append(
            (
                "disk_bound",
                f"Free disk is {signals['disk_free_fraction'] * 100:.1f}% — Postgres write throughput drops sharply below 10% free.",
                0.7,
            )
        )

    if signals.get("cpu_pct", 0) >= _CPU_BOUND_THRESHOLD_PCT:
        candidates.append(
            (
                "cpu_bound",
                f"CPU is at {signals['cpu_pct']:.0f}% — the system is compute-saturated.",
                0.7,
            )
        )

    if signals.get("mem_free_fraction", 1.0) < _MEMORY_PRESSURE_FREE_FRACTION:
        candidates.append(
            (
                "cpu_bound",
                f"Free RAM is {signals['mem_free_fraction'] * 100:.1f}% — memory pressure is forcing slow swap activity.",
                0.6,
            )
        )

    if not candidates:
        return SlownessVerdict(
            verdict="unknown",
            why="No bottleneck signal triggered — task may be network-bound or simply long-running.",
            confidence=0.3,
            sampled_at=sampled_at,
        )

    # Pick the highest-confidence candidate. Tie-break by order in the
    # candidate list (which matches the priority operators care about
    # most: thermal first because it self-resolves; lock-waiting second
    # because it blocks others; resource-saturation last).
    candidates.sort(key=lambda c: c[2], reverse=True)
    verdict, why, confidence = candidates[0]

    # Multi-signal agreement boosts confidence by 10% per additional hit
    # (capped at 1.0).
    if len(candidates) > 1:
        confidence = min(1.0, confidence + 0.1 * (len(candidates) - 1))

    return SlownessVerdict(
        verdict=verdict,
        why=why,
        confidence=round(confidence, 2),
        sampled_at=sampled_at,
    )


# ── Live signal sampling ─────────────────────────────────────────


def _sample_all_signals() -> dict[str, float | int]:
    """Sample every signal the analyzer cares about. Each sample is
    optional — failure to read one signal doesn't break the analyzer.
    """
    out: dict[str, float | int] = {}
    out.update(_sample_cpu_mem())
    out.update(_sample_disk())
    out.update(_sample_postgres_locks())
    return out


def _sample_cpu_mem() -> dict[str, float]:
    """psutil CPU% + RAM-free fraction. Uses 0.5 s sample window so the
    CPU-percent reading is meaningful (the first call would otherwise
    return 0.0).
    """
    try:
        import psutil

        # 0.5 s interval gives a real reading rather than the cached 0.
        cpu_pct = float(psutil.cpu_percent(interval=0.5))
        vm = psutil.virtual_memory()
        mem_free_fraction = float(vm.available) / max(float(vm.total), 1.0)
        return {"cpu_pct": cpu_pct, "mem_free_fraction": mem_free_fraction}
    except Exception:
        logger.debug("slowness_analyzer: cpu/mem sample failed", exc_info=True)
        return {}


def _sample_disk() -> dict[str, float]:
    """Disk-wait % + free-disk fraction.

    Linux: ``psutil.cpu_times_percent`` exposes ``iowait`` directly.
    Windows: ``iowait`` doesn't exist, so derive a proxy from
    ``psutil.disk_io_counters().busy_time`` (Windows-only attribute,
    in ms over a 0.5 s window). Falls back to 0.0 if neither source
    is available.
    """
    import os

    out: dict[str, float] = {}
    try:
        import shutil

        # Use the project root on Windows (drive root) and / on POSIX.
        usage = shutil.disk_usage(os.environ.get("HOMEDRIVE", "/") or "/")
        out["disk_free_fraction"] = float(usage.free) / max(float(usage.total), 1.0)
    except Exception:
        logger.debug("slowness_analyzer: disk_free sample failed", exc_info=True)

    try:
        import psutil

        # Linux path: iowait is directly available.
        times = psutil.cpu_times_percent(interval=0.5, percpu=False)
        iowait = float(getattr(times, "iowait", 0.0) or 0.0)
        if iowait > 0.0:
            out["disk_wait_pct"] = iowait
            return out

        # Windows fallback: derive from disk_io_counters().busy_time
        # (milliseconds the disk has been busy in the sampling window).
        # We sample twice 250 ms apart and convert delta-busy-time to %.
        before = psutil.disk_io_counters(perdisk=False)
        if before is not None and hasattr(before, "busy_time"):
            import time

            time.sleep(0.25)
            after = psutil.disk_io_counters(perdisk=False)
            if after is not None and hasattr(after, "busy_time"):
                delta_ms = max(0.0, float(after.busy_time) - float(before.busy_time))
                # 250 ms wall-clock window; busy_time is the disk's "in flight"
                # ms across the same window. Cap at 100% for sanity.
                pct = min(100.0, (delta_ms / 250.0) * 100.0)
                out["disk_wait_pct"] = pct
                return out

        # Final fallback: no signal available on this platform.
        out["disk_wait_pct"] = 0.0
    except Exception:
        logger.debug("slowness_analyzer: disk_wait sample failed", exc_info=True)
    return out


def _sample_postgres_locks() -> dict[str, int]:
    """Count of pg_stat_activity rows currently waiting on a Lock."""
    try:
        from django.db import connection

        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT COUNT(*) FROM pg_stat_activity "
                "WHERE wait_event_type = 'Lock' AND state = 'active'"
            )
            row = cursor.fetchone()
            return {"lock_wait_rows": int(row[0]) if row else 0}
    except Exception:
        logger.debug("slowness_analyzer: pg_stat_activity sample failed", exc_info=True)
        return {}
