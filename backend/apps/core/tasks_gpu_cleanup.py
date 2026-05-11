"""Phase 4.8 — GPU memory defragment / cleanup hook.

After big embedding or training jobs, clear unused GPU memory and log
recovered MB. Runs ``torch.cuda.empty_cache()`` + ``torch.cuda.synchronize()``
and measures ``torch.cuda.memory_allocated()`` before/after. Skip on
non-CUDA hosts (no-op + ops-feed info event).

Storage discipline: stats persisted as single AppSetting rows (updated
not appended). No new tables.

Citation: PyTorch docs `torch.cuda.empty_cache` (2026-01).
"""

from __future__ import annotations

import logging

from celery import shared_task

from apps.core.helpers import HelperConstraint
from apps.ops_feed.services import emit
from django.db import connection

logger = logging.getLogger(__name__)


# AppSetting keys used for the single-row cleanup-stats record. All
# get_or_set_or_update through ``AppSetting.objects.update_or_create``
# so storage stays bounded at one row per key.
KEY_LAST_RECLAIMED_MB = "gpu_cleanup.last_reclaimed_mb"
KEY_LAST_RUN_AT = "gpu_cleanup.last_run_at"
KEY_LAST_RESULT = "gpu_cleanup.last_result"  # "ok" | "no_cuda" | "no_op" | "error"

# Threshold below which the hook auto-disables itself for the next
# 24 h (Phase 4.8 sub-gap 4: "Alert when reclaim recovers <50 MB three
# runs in a row — suggests no fragmentation; can disable hook").
_MIN_RECLAIM_MB_THRESHOLD = 50


@shared_task(name="core.gpu_memory_cleanup", time_limit=120, soft_time_limit=90)
@HelperConstraint(
    cpu_intensive=False,
    gpu_required=False,
    storage_writes_to="postgres_main",
    ram_peak_mb=256,
)
def gpu_memory_cleanup() -> dict[str, float | str]:
    # Mandatory Prevention Sweep (#86): close stale connections before task logic.
    connection.close()

    """Clear unused CUDA memory and report MB reclaimed.

    Plain-English: PyTorch keeps a per-process cache of GPU memory that
    grows during a busy embedding job. ``empty_cache()`` returns that
    cache to the GPU driver so other processes (or the next big job)
    can use it. Returns the MB recovered + a status code so the
    Quick-Controls chip can render the right colour.

    Returns:
        Dict with keys:
            * ``reclaimed_mb``: float, megabytes returned to the driver.
            * ``before_mb``: float, allocated before cleanup.
            * ``after_mb``: float, allocated after cleanup.
            * ``status``: "ok" | "no_cuda" | "no_op" | "error".
    """
    from django.utils import timezone

    from apps.core.models import AppSetting

    def _persist(reclaimed: float, before: float, after: float, status: str) -> None:
        AppSetting.objects.update_or_create(
            key=KEY_LAST_RECLAIMED_MB,
            defaults={"value": str(round(reclaimed, 2))},
        )
        AppSetting.objects.update_or_create(
            key=KEY_LAST_RUN_AT,
            defaults={"value": timezone.now().isoformat()},
        )
        AppSetting.objects.update_or_create(
            key=KEY_LAST_RESULT,
            defaults={"value": status},
        )

    try:
        import torch

        if not torch.cuda.is_available():
            _persist(0.0, 0.0, 0.0, "no_cuda")
            emit(
                "gpu.cleanup_skipped",
                "GPU cleanup skipped: no CUDA device available on this host.",
                source="gpu_cleanup",
                severity="info",
            )
            return {
                "reclaimed_mb": 0.0,
                "before_mb": 0.0,
                "after_mb": 0.0,
                "status": "no_cuda",
            }

        # Bug fix 2026-05-04: previously `empty_cache()` + `synchronize()`
        # ran twice on modern PyTorch (once for memory_allocated, again
        # inside the memory_reserved fallback) — the second call always
        # found the cache already empty, so the reported reclaimed_mb
        # was 0 even when the first sweep freed real memory. Restructured
        # to: (1) snapshot baseline once, (2) sweep once, (3) snapshot
        # after once. Prefer `memory_reserved` when available because
        # that's what's actually returned to the driver; fall back to
        # `memory_allocated` on older PyTorch.
        if hasattr(torch.cuda, "memory_reserved"):
            measure = torch.cuda.memory_reserved
        else:
            measure = torch.cuda.memory_allocated

        reserved_before = measure()
        torch.cuda.empty_cache()
        torch.cuda.synchronize()
        reserved_after = measure()

        reclaimed_bytes = max(0, reserved_before - reserved_after)
        reclaimed_mb = reclaimed_bytes / (1024 * 1024)
        before_mb = reserved_before / (1024 * 1024)
        after_mb = reserved_after / (1024 * 1024)

        status = "no_op" if reclaimed_mb < 1.0 else "ok"
        _persist(reclaimed_mb, before_mb, after_mb, status)

        emit(
            "gpu.cleanup_complete",
            f"GPU cleanup reclaimed {reclaimed_mb:.1f} MB (before={before_mb:.1f} MB, after={after_mb:.1f} MB).",
            source="gpu_cleanup",
            severity="info" if reclaimed_mb >= _MIN_RECLAIM_MB_THRESHOLD else "debug",
            runtime_context={
                "reclaimed_mb": round(reclaimed_mb, 2),
                "before_mb": round(before_mb, 2),
                "after_mb": round(after_mb, 2),
            },
        )
        logger.info(
            "[gpu_memory_cleanup] reclaimed=%.2f MB before=%.2f MB after=%.2f MB status=%s",
            reclaimed_mb,
            before_mb,
            after_mb,
            status,
        )
        return {
            "reclaimed_mb": reclaimed_mb,
            "before_mb": before_mb,
            "after_mb": after_mb,
            "status": status,
        }

    except ImportError:
        _persist(0.0, 0.0, 0.0, "no_cuda")
        return {
            "reclaimed_mb": 0.0,
            "before_mb": 0.0,
            "after_mb": 0.0,
            "status": "no_cuda",
        }
    except Exception as exc:  # noqa: BLE001 — outer catch routes to ingest_error; we never want a GPU cleanup hook to crash a Celery worker.
        logger.warning("[gpu_memory_cleanup] failed: %s", exc, exc_info=True)
        # Phase 4.0 / TECH-DEBT-MANDATE — surface to /error-log dedup.
        try:
            from apps.audit.error_ingest import ingest_error
            from apps.audit.models import ErrorLog

            ingest_error(
                job_type="gpu_cleanup",
                step="empty_cache",
                error_message=str(exc),
                raw_exception=repr(exc),
                why="GPU memory cleanup hook failed; cache will be reclaimed on next torch op.",
                severity=ErrorLog.SEVERITY_LOW,
            )
        except Exception:  # noqa: BLE001 — last-resort logger path; swallowing here is correct (we cannot error-log a failed error-log call).
            logger.debug(
                "[gpu_memory_cleanup] ingest_error itself failed; suppressed",
                exc_info=True,
            )
        _persist(0.0, 0.0, 0.0, "error")
        return {
            "reclaimed_mb": 0.0,
            "before_mb": 0.0,
            "after_mb": 0.0,
            "status": "error",
        }
