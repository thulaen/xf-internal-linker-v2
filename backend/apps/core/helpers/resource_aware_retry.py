"""Phase 4.10 — Resource-Aware Retry decorator.

Plain-English: when a Celery task fails because the system is out of
memory / out of disk / the GPU is hot / the GPU is OOM, blindly retrying
makes things worse. This decorator classifies the failure reason and
picks the right recovery: smaller batch size for OOM, defer-to-off-peak
for disk pressure, wait-for-cooldown for thermal, exponential-backoff
for transient errors.

Usage:

    from celery import shared_task
    from apps.core.helpers.resource_aware_retry import resource_aware_retry

    @shared_task(bind=True, name="embeddings.generate_batch")
    @resource_aware_retry(
        max_retries=5,
        oom_batch_shrink_ratio=0.5,
        thermal_wait_seconds=300,
        disk_pressure_defer_seconds=3600,
    )
    def generate_batch(self, batch_size, ...):
        ...

When the task raises one of the recognised resource-pressure exceptions,
the decorator:
    1. Classifies the failure (OOM / thermal / disk / transient / other)
    2. Picks the right next-attempt parameters (smaller batch for OOM)
    3. Logs to /error-log via ingest_error so the operator sees the
       resource-pressure pattern without it being silently retried away
    4. Re-raises self.retry(...) with the right countdown / kwargs

Storage discipline: per-task baseline batch size is remembered in a
single AppSetting row keyed by `resource_aware_retry.<task_name>.last_oom_batch`
so the next call starts at the smaller batch automatically (Phase 4.10
sub-gap 6: per-task baseline batch size memory).

Citations:
    * Celery autoretry docs §3.10 — wraps the standard pattern.
    * AWS exponential-backoff blog — backoff schedule.
    * Linux PSI papers (Andrei 2018) — pressure-class triage rationale.
"""

from __future__ import annotations

import functools
import logging
from typing import Any, Callable

logger = logging.getLogger(__name__)


# Per-class default backoff seconds. Operator may override at decorator
# call site; these are the safe baselines.
_DEFAULTS = {
    "oom_batch_shrink_ratio": 0.5,
    "thermal_wait_seconds": 300,
    "disk_pressure_defer_seconds": 3600,
    "transient_backoff_base_seconds": 30,
    "transient_backoff_max_seconds": 1800,
    "max_retries": 5,
}


# Map exception class names → failure category. We compare class names
# rather than using ``isinstance`` so the classifier doesn't import
# torch / heavy deps at module load.
_FAILURE_CLASSIFIERS = {
    # Generic OOM
    "MemoryError": "oom",
    # PyTorch CUDA OOM
    "OutOfMemoryError": "oom",
    "CudaOutOfMemoryError": "oom",
    # Transient network / DB
    "ConnectionError": "transient",
    "TimeoutError": "transient",
    "RequestException": "transient",
    "OperationalError": "transient",
    # Disk pressure (custom from DISK-PRESSURE-RULES)
    "DiskPressureError": "disk_pressure",
    # Thermal throttle (custom; raised by GPU thermal guard)
    "ThermalThrottleError": "thermal",
}


def classify_failure(exc: BaseException) -> str:
    """Map an exception instance to a failure-class string.

    Returns one of: ``oom`` / ``transient`` / ``disk_pressure`` /
    ``thermal`` / ``other``. The ``other`` class is treated as
    non-resource-pressure (let Celery's default autoretry handle it).
    """
    name = type(exc).__name__
    if name in _FAILURE_CLASSIFIERS:
        return _FAILURE_CLASSIFIERS[name]
    # Walk MRO so a subclass of MemoryError still classifies as oom.
    for parent in type(exc).__mro__:
        if parent.__name__ in _FAILURE_CLASSIFIERS:
            return _FAILURE_CLASSIFIERS[parent.__name__]
    # Heuristic fallback: search the exception message for OOM signatures.
    msg = str(exc).lower()
    if "out of memory" in msg or "oom" in msg or "cuda" in msg and "memory" in msg:
        return "oom"
    if "no space left" in msg or "disk full" in msg:
        return "disk_pressure"
    return "other"


def _read_last_oom_batch(task_name: str) -> int | None:
    """Per-task remembered batch size after a prior OOM. None if never."""
    try:
        from apps.core.models import AppSetting

        row = AppSetting.objects.filter(
            key=f"resource_aware_retry.{task_name}.last_oom_batch"
        ).first()
        if row and row.value and row.value.isdigit():
            return int(row.value)
    except Exception:  # noqa: BLE001 — AppSetting blip falls back to caller's default; no operator-visible impact.
        pass
    return None


def _persist_last_oom_batch(task_name: str, batch_size: int) -> None:
    """Stash the post-shrink batch size so the next call starts smaller."""
    try:
        from apps.core.models import AppSetting

        AppSetting.objects.update_or_create(
            key=f"resource_aware_retry.{task_name}.last_oom_batch",
            defaults={"value": str(max(1, int(batch_size)))},
        )
    except Exception:  # noqa: BLE001 — best-effort memory; failure to persist just costs us one extra OOM next run.
        logger.debug(
            "resource_aware_retry: could not persist last_oom_batch for %s",
            task_name,
            exc_info=True,
        )


def _emit_pressure_event(
    *, task_name: str, failure_class: str, exc: BaseException, action: str
) -> None:
    """Surface a resource-pressure event on /error-log (deduped)."""
    try:
        from apps.audit.error_ingest import ingest_error
        from apps.audit.models import ErrorLog

        severity = (
            ErrorLog.SEVERITY_HIGH
            if failure_class in {"oom", "disk_pressure"}
            else ErrorLog.SEVERITY_MEDIUM
        )
        ingest_error(
            job_type="resource_pressure",
            step=f"{task_name}:{failure_class}",
            error_message=f"{failure_class}: {exc}",
            raw_exception=repr(exc),
            why=f"Task {task_name} hit a resource-pressure failure; recovery action: {action}.",
            severity=severity,
        )
    except Exception:  # noqa: BLE001 — error-log itself failing must not break the retry path.
        logger.debug(
            "resource_aware_retry: ingest_error emit failed for %s",
            task_name,
            exc_info=True,
        )


def resource_aware_retry(
    *,
    max_retries: int | None = None,
    oom_batch_shrink_ratio: float | None = None,
    thermal_wait_seconds: int | None = None,
    disk_pressure_defer_seconds: int | None = None,
    transient_backoff_base_seconds: int | None = None,
    transient_backoff_max_seconds: int | None = None,
    batch_size_kwarg: str = "batch_size",
) -> Callable:
    """Decorator factory. Wraps a Celery bound task with resource-aware retry.

    The wrapped task MUST be ``@shared_task(bind=True, ...)`` so the
    decorator can call ``self.retry(...)`` from inside the catch block.

    Args:
        max_retries: cap on total retry attempts. Default 5.
        oom_batch_shrink_ratio: multiplier applied to ``batch_size``
            kwarg on OOM retry (e.g. 0.5 halves the batch). Default 0.5.
        thermal_wait_seconds: countdown when GPU thermal throttle is
            detected. Default 300 s (5 min).
        disk_pressure_defer_seconds: countdown when disk pressure is
            detected. Default 3600 s (1 h — defers to off-peak).
        transient_backoff_base_seconds: base for exponential backoff
            on transient (network/DB) failures. Default 30 s.
        transient_backoff_max_seconds: cap on transient backoff.
            Default 1800 s (30 min).
        batch_size_kwarg: kwarg name to shrink on OOM. Default "batch_size".
    """
    cfg = {
        "max_retries": max_retries or _DEFAULTS["max_retries"],
        "oom_batch_shrink_ratio": (
            oom_batch_shrink_ratio or _DEFAULTS["oom_batch_shrink_ratio"]
        ),
        "thermal_wait_seconds": (
            thermal_wait_seconds or _DEFAULTS["thermal_wait_seconds"]
        ),
        "disk_pressure_defer_seconds": (
            disk_pressure_defer_seconds or _DEFAULTS["disk_pressure_defer_seconds"]
        ),
        "transient_backoff_base_seconds": (
            transient_backoff_base_seconds
            or _DEFAULTS["transient_backoff_base_seconds"]
        ),
        "transient_backoff_max_seconds": (
            transient_backoff_max_seconds or _DEFAULTS["transient_backoff_max_seconds"]
        ),
        "batch_size_kwarg": batch_size_kwarg,
    }

    def _decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def _wrapper(self, *args: Any, **kwargs: Any) -> Any:
            # Pull the persisted last-OOM batch on the FIRST attempt
            # so a fresh task starts at the smaller size.
            attempt_no = (
                getattr(self.request, "retries", 0) if hasattr(self, "request") else 0
            )
            if attempt_no == 0:
                last_oom = _read_last_oom_batch(getattr(self, "name", func.__name__))
                if (
                    last_oom is not None
                    and cfg["batch_size_kwarg"] in kwargs
                    and isinstance(kwargs[cfg["batch_size_kwarg"]], int)
                    and last_oom < kwargs[cfg["batch_size_kwarg"]]
                ):
                    logger.info(
                        "resource_aware_retry: shrinking %s from %s to %s "
                        "(remembered post-OOM size)",
                        cfg["batch_size_kwarg"],
                        kwargs[cfg["batch_size_kwarg"]],
                        last_oom,
                    )
                    kwargs[cfg["batch_size_kwarg"]] = last_oom

            try:
                return func(self, *args, **kwargs)
            except Exception as exc:  # noqa: BLE001 — classifier handles every concrete exception.
                failure_class = classify_failure(exc)
                if failure_class == "other":
                    raise

                action, countdown, new_kwargs = _plan_recovery(
                    failure_class=failure_class,
                    cfg=cfg,
                    kwargs=kwargs,
                    task_name=getattr(self, "name", func.__name__),
                )
                _emit_pressure_event(
                    task_name=getattr(self, "name", func.__name__),
                    failure_class=failure_class,
                    exc=exc,
                    action=action,
                )
                raise self.retry(
                    exc=exc,
                    countdown=countdown,
                    max_retries=cfg["max_retries"],
                    kwargs=new_kwargs,
                )

        return _wrapper

    return _decorator


def _plan_recovery(
    *,
    failure_class: str,
    cfg: dict[str, Any],
    kwargs: dict[str, Any],
    task_name: str,
) -> tuple[str, int, dict[str, Any]]:
    """Pure function: pick countdown + new kwargs based on failure class.

    Returns ``(human_action, countdown_seconds, new_kwargs)``. ``new_kwargs``
    is the (possibly modified) kwargs dict the next attempt will receive.
    """
    new_kwargs = dict(kwargs)
    if failure_class == "oom":
        bs_key = cfg["batch_size_kwarg"]
        old_bs = new_kwargs.get(bs_key)
        if isinstance(old_bs, int) and old_bs > 1:
            new_bs = max(1, int(old_bs * cfg["oom_batch_shrink_ratio"]))
            new_kwargs[bs_key] = new_bs
            _persist_last_oom_batch(task_name, new_bs)
            return (
                f"halve {bs_key} from {old_bs} to {new_bs} and retry",
                30,
                new_kwargs,
            )
        return (
            "retry after 60 s with same kwargs (batch already at minimum)",
            60,
            new_kwargs,
        )

    if failure_class == "thermal":
        return (
            f"wait {cfg['thermal_wait_seconds']} s for thermal cooldown",
            cfg["thermal_wait_seconds"],
            new_kwargs,
        )

    if failure_class == "disk_pressure":
        return (
            f"defer {cfg['disk_pressure_defer_seconds']} s for disk pressure",
            cfg["disk_pressure_defer_seconds"],
            new_kwargs,
        )

    # transient
    return (
        f"exponential backoff up to {cfg['transient_backoff_max_seconds']} s",
        min(
            cfg["transient_backoff_base_seconds"] * 2,
            cfg["transient_backoff_max_seconds"],
        ),
        new_kwargs,
    )
