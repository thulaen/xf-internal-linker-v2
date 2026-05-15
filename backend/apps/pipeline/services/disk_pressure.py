"""Disk-pressure circuit breaker — pre-flight guard for large writes.

Implements the contract described in `DISK-PRESSURE-RULES.md`. Until 2026-05-09
this module was *referenced* by callers (`_parquet_io.py`, `archive.py`) but
never shipped — so the pre-flight guards silently no-op'd. A full disk could
corrupt in-flight Parquet writes without an error path. This module fills
that gap.

Public surface
--------------
- ``DiskPressureError`` — raised by ``require_free_disk()`` when the requested
  write would push free disk below the safety margin. Caller should catch it
  and report via the standard ErrorLog ingest path; the resource-aware retry
  helper at ``apps.core.helpers.resource_aware_retry`` already classifies the
  exception name and defers the task by an hour.
- ``require_free_disk(estimated_bytes, *, safety_margin_gb=5)`` — the
  pre-flight guard called by every multi-GB writer. Hardware-aware: the
  default ``safety_margin_gb`` scales with the host tier (low-tier 2 GB,
  high-tier 5 GB) while the global watermarks protect a 48 GB reserve.
- ``current_state()`` — returns ``"GREEN" | "YELLOW" | "RED" | "CRITICAL"``
  read from the Django cache. Refreshed every 60 s by the
  ``refresh_disk_pressure_state`` Celery beat task.
- ``refresh_disk_pressure_state()`` — recomputes the state from
  ``shutil.disk_usage()``, caches it, and emits an OperatorAlert on the
  first transition into YELLOW / RED / CRITICAL. Idempotent: re-runs at the
  same state are silent (we don't double-alert).

Why a single module
-------------------
The contract is small enough to fit one file (KISS — `THINK-BEFORE-YOU-CODE.md`).
Splitting into "guard.py", "monitor.py", "state.py" would scatter the watermark
constants and force four imports for every caller. One module, three public
functions, ≤200 lines.
"""

from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass
from pathlib import Path

from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

# Cache key + TTL. The Celery beat task refreshes every 60 s; we set a 5 min
# TTL so a single missed beat tick doesn't blank the value.
_CACHE_KEY = "disk_pressure_state"
_CACHE_TTL_SECONDS = 300

# Last-alert cache key (used to suppress duplicate OperatorAlerts inside the
# 5-minute alert window per `DISK-PRESSURE-RULES.md` deduplication rule).
_LAST_ALERT_KEY = "disk_pressure_last_alerted_state"
_ALERT_DEDUP_TTL_SECONDS = 300

# Watermarks from `DISK-PRESSURE-RULES.md` § "The Watermarks". Free GB.
_GREEN_FLOOR_GB = 64.0
_YELLOW_FLOOR_GB = 48.0
_CRITICAL_FLOOR_GB = 1.0

# Per-tier safety margin defaults. Low-tier hosts have less headroom so we
# accept a smaller margin; high-tier hosts get the full 5 GB margin from
# the rule book.
_TIER_SAFETY_MARGIN_GB: dict[str, int] = {
    "low": 2,
    "medium": 3,
    "high": 5,
    "workstation": 5,
}

State = str  # one of GREEN / YELLOW / RED / CRITICAL


class DiskPressureError(Exception):
    """Raised when a write would push free disk below the safety margin.

    The exception name is canonical — `apps.core.helpers.resource_aware_retry`
    matches on the literal class name to classify the failure as
    ``disk_pressure`` and apply the 1-hour defer policy. Do not rename.
    """

    def __init__(self, *, estimated_bytes: int, free_gb: float, safety_margin_gb: int):
        self.estimated_bytes = estimated_bytes
        self.free_gb = free_gb
        self.safety_margin_gb = safety_margin_gb
        msg = (
            f"DiskPressureError: free disk {free_gb:.1f} GB < "
            f"projected_total {((estimated_bytes / (1024 ** 3)) + safety_margin_gb):.1f} GB "
            f"(write {estimated_bytes / (1024 ** 3):.1f} GB + margin {safety_margin_gb} GB). "
            f"Run `powershell -ExecutionPolicy Bypass -File docker_compact_vhd.ps1` to free disk."
        )
        super().__init__(msg)


@dataclass(frozen=True, slots=True)
class _DiskUsage:
    free_gb: float
    total_gb: float
    used_gb: float


def _measure(path: Path | None = None) -> _DiskUsage:
    target = path or Path(getattr(settings, "BASE_DIR", "."))
    usage = shutil.disk_usage(str(target))
    gb = 1024 ** 3
    return _DiskUsage(
        free_gb=usage.free / gb,
        total_gb=usage.total / gb,
        used_gb=usage.used / gb,
    )


def _classify(free_gb: float) -> State:
    if free_gb < _CRITICAL_FLOOR_GB:
        return "CRITICAL"
    if free_gb < _YELLOW_FLOOR_GB:
        return "RED"
    if free_gb < _GREEN_FLOOR_GB:
        return "YELLOW"
    return "GREEN"


def _default_safety_margin_gb() -> int:
    """Hardware-aware safety margin per DISK-PRESSURE-RULES.md."""
    try:
        from apps.pipeline.services.hardware_profile import detect_profile

        return _TIER_SAFETY_MARGIN_GB.get(detect_profile().tier, 5)
    except Exception:  # noqa: BLE001 — hardware profile is best-effort; fall back to 5 GB.
        return 5


def require_free_disk(
    *,
    estimated_bytes: int,
    safety_margin_gb: int | None = None,
    path: Path | None = None,
) -> None:
    """Pre-flight guard. Raises DiskPressureError if the write won't fit safely.

    Used by every multi-GB writer (Parquet snapshots, model downloads, batch
    embedding flushes). The check is intentionally cheap — one ``shutil`` call
    and one comparison — so callers can sprinkle it liberally.

    Args:
        estimated_bytes: Expected write size in bytes. Over-estimate is fine
            (we'd rather defer a write that would have fit).
        safety_margin_gb: Headroom to leave free after the write. Defaults to
            the hardware-tier-aware value (low: 2, medium: 3, high/workstation: 5).
        path: Filesystem path to measure free space against. Defaults to
            ``settings.BASE_DIR`` (where Postgres + media live in our compose).

    Raises:
        DiskPressureError: When ``free_gb < (estimated_bytes_gb + safety_margin_gb)``.
    """
    margin = safety_margin_gb if safety_margin_gb is not None else _default_safety_margin_gb()
    usage = _measure(path)
    write_gb = estimated_bytes / (1024 ** 3)
    if usage.free_gb < write_gb + margin:
        raise DiskPressureError(
            estimated_bytes=estimated_bytes,
            free_gb=usage.free_gb,
            safety_margin_gb=margin,
        )


def current_state() -> State:
    """Return the latest cached pressure state (GREEN/YELLOW/RED/CRITICAL).

    Reads from the Django cache. If no entry exists (cold start), measure now
    and cache the result so repeated callers within the same TTL window are
    cheap.
    """
    cached = cache.get(_CACHE_KEY)
    if cached in ("GREEN", "YELLOW", "RED", "CRITICAL"):
        return cached
    state = _classify(_measure().free_gb)
    cache.set(_CACHE_KEY, state, _CACHE_TTL_SECONDS)
    return state


def refresh_disk_pressure_state(*, path: Path | None = None) -> State:
    """Re-measure, cache, alert on first transition to YELLOW+.

    Called by the Celery beat task ``refresh_disk_pressure_state`` every 60 s
    (the cadence quoted in DISK-PRESSURE-RULES.md). On a state change INTO
    YELLOW / RED / CRITICAL, emits an OperatorAlert. Same state on repeat ticks
    is silent — the `_LAST_ALERT_KEY` cache entry deduplicates within a 5-min
    window so we never double-alert the operator.

    Returns the new state for callers that want to chain on it.
    """
    usage = _measure(path)
    state = _classify(usage.free_gb)
    cache.set(_CACHE_KEY, state, _CACHE_TTL_SECONDS)

    last_alerted = cache.get(_LAST_ALERT_KEY)
    if state in ("YELLOW", "RED", "CRITICAL") and last_alerted != state:
        _emit_alert(state, free_gb=usage.free_gb)
        cache.set(_LAST_ALERT_KEY, state, _ALERT_DEDUP_TTL_SECONDS)
    elif state == "GREEN" and last_alerted is not None:
        # Recovered — clear the dedup key so the next pressure event re-alerts.
        cache.delete(_LAST_ALERT_KEY)
    return state


def _emit_alert(state: State, *, free_gb: float) -> None:
    """Persist an OperatorAlert + ErrorLog row. Best-effort — never raises.

    Why both surfaces: OperatorAlert powers the in-app bell + toast
    (`apps.notifications`). ErrorLog powers the `/error-log` page so the
    operator sees the same warning even when notifications are dismissed.
    """
    severity_alert = {
        "YELLOW": "warning",
        "RED": "error",
        "CRITICAL": "urgent",
    }[state]
    severity_log = "warning" if state == "YELLOW" else "error"
    msg = (
        f"Disk pressure {state} — {free_gb:.1f} GB free. "
        f"Run docker_compact_vhd.ps1 to recover space."
    )
    try:
        from apps.notifications.models import OperatorAlert

        OperatorAlert.objects.create(
            severity=severity_alert,
            title=f"Disk pressure {state}",
            body=msg,
            dedupe_key=f"disk_pressure:{state}",
        )
    except Exception:  # noqa: BLE001 — alert is best-effort; never block the beat task.
        logger.warning("disk_pressure: OperatorAlert insert failed", exc_info=True)
    try:
        from apps.audit.error_ingest import ingest_error

        ingest_error(
            job_type="disk_pressure_monitor",
            step=state,
            error_message=msg,
            severity=severity_log,
            why=(
                "Free disk fell below the watermark threshold from "
                "DISK-PRESSURE-RULES.md. Large writes are at risk of "
                "corrupting in-flight Parquet files or OOMing the host."
            ),
        )
    except Exception:  # noqa: BLE001 — same defensive pattern.
        logger.warning("disk_pressure: ErrorLog ingest failed", exc_info=True)


__all__ = [
    "DiskPressureError",
    "current_state",
    "refresh_disk_pressure_state",
    "require_free_disk",
]
