"""Celery tasks for FR-016 telemetry sync."""

from __future__ import annotations

from celery import shared_task
from django.utils import timezone

from .models import AnalyticsSyncRun
from .sync import run_ga4_sync, run_matomo_sync, run_gsc_sync


def _load_sync_run(sync_run_id: int) -> AnalyticsSyncRun:
    return AnalyticsSyncRun.objects.get(pk=sync_run_id)


def _queue_scheduled_sync(*, source: str, lookback_days: int, task_fn) -> dict[str, int | str]:
    sync_run = AnalyticsSyncRun.objects.create(
        source=source,
        status="pending",
        lookback_days=lookback_days,
    )
    task = task_fn.delay(sync_run.pk)
    return {
        "sync_run_id": sync_run.pk,
        "task_id": task.id,
        "source": source,
        "lookback_days": lookback_days,
    }


@shared_task(bind=True, name="analytics.sync_matomo_telemetry")
def sync_matomo_telemetry(self, sync_run_id: int) -> dict[str, int | str]:
    sync_run = _load_sync_run(sync_run_id)
    sync_run.status = "running"
    sync_run.error_message = ""
    sync_run.save(update_fields=["status", "error_message", "updated_at"])

    try:
        stats = run_matomo_sync(sync_run)
    except Exception as exc:
        sync_run.status = "failed"
        sync_run.error_message = str(exc)
        sync_run.completed_at = timezone.now()
        sync_run.save(
            update_fields=["status", "error_message", "completed_at", "updated_at"]
        )
        raise

    sync_run.status = "completed"
    sync_run.completed_at = timezone.now()
    sync_run.rows_read = int(stats["rows_read"])
    sync_run.rows_written = int(stats["rows_written"])
    sync_run.rows_updated = int(stats["rows_updated"])
    sync_run.save(
        update_fields=[
            "status",
            "completed_at",
            "rows_read",
            "rows_written",
            "rows_updated",
            "updated_at",
        ]
    )
    return {"sync_run_id": sync_run_id, **stats}


@shared_task(bind=True, name="analytics.sync_ga4_telemetry")
def sync_ga4_telemetry(self, sync_run_id: int) -> dict[str, int | str]:
    sync_run = _load_sync_run(sync_run_id)
    sync_run.status = "running"
    sync_run.error_message = ""
    sync_run.save(update_fields=["status", "error_message", "updated_at"])

    try:
        stats = run_ga4_sync(sync_run)
    except Exception as exc:
        sync_run.status = "failed"
        sync_run.error_message = str(exc)
        sync_run.completed_at = timezone.now()
        sync_run.save(
            update_fields=["status", "error_message", "completed_at", "updated_at"]
        )
        raise

    sync_run.status = "completed"
    sync_run.completed_at = timezone.now()
    sync_run.rows_read = int(stats["rows_read"])
    sync_run.rows_written = int(stats["rows_written"])
    sync_run.rows_updated = int(stats["rows_updated"])
    sync_run.save(
        update_fields=[
            "status",
            "completed_at",
            "rows_read",
            "rows_written",
            "rows_updated",
            "updated_at",
        ]
    )
    return {"sync_run_id": sync_run_id, **stats}


@shared_task(bind=True, name="analytics.sync_gsc_performance")
def sync_gsc_performance(self, sync_run_id: int) -> dict[str, int | str]:
    sync_run = _load_sync_run(sync_run_id)
    sync_run.status = "running"
    sync_run.error_message = ""
    sync_run.save(update_fields=["status", "error_message", "updated_at"])

    try:
        stats = run_gsc_sync(sync_run)
    except Exception as exc:
        sync_run.status = "failed"
        sync_run.error_message = str(exc)
        sync_run.completed_at = timezone.now()
        sync_run.save(
            update_fields=["status", "error_message", "completed_at", "updated_at"]
        )
        raise

    sync_run.status = "completed"
    sync_run.completed_at = timezone.now()
    sync_run.rows_read = int(stats.get("rows_read", 0))
    sync_run.rows_written = int(stats.get("rows_written", 0))
    sync_run.rows_updated = int(stats.get("rows_updated", 0))
    sync_run.save(
        update_fields=[
            "status",
            "completed_at",
            "rows_read",
            "rows_written",
            "rows_updated",
            "updated_at",
        ]
    )
    return {"sync_run_id": sync_run_id, **stats}


@shared_task(name="analytics.schedule_ga4_telemetry_hourly")
def schedule_ga4_telemetry_hourly() -> dict[str, int | str]:
    return _queue_scheduled_sync(
        source="ga4",
        lookback_days=2,
        task_fn=sync_ga4_telemetry,
    )


@shared_task(name="analytics.schedule_ga4_telemetry_daily")
def schedule_ga4_telemetry_daily() -> dict[str, int | str]:
    return _queue_scheduled_sync(
        source="ga4",
        lookback_days=7,
        task_fn=sync_ga4_telemetry,
    )


@shared_task(name="analytics.schedule_matomo_telemetry_hourly")
def schedule_matomo_telemetry_hourly() -> dict[str, int | str]:
    return _queue_scheduled_sync(
        source="matomo",
        lookback_days=1,
        task_fn=sync_matomo_telemetry,
    )


@shared_task(name="analytics.schedule_matomo_telemetry_daily")
def schedule_matomo_telemetry_daily() -> dict[str, int | str]:
    return _queue_scheduled_sync(
        source="matomo",
        lookback_days=7,
        task_fn=sync_matomo_telemetry,
    )


@shared_task(name="analytics.schedule_gsc_performance_daily")
def schedule_gsc_performance_daily() -> dict[str, int | str]:
    from .views import get_gsc_settings
    settings = get_gsc_settings()
    return _queue_scheduled_sync(
        source="gsc",
        lookback_days=int(settings.get("sync_lookback_days") or 14),
        task_fn=sync_gsc_performance,
    )


@shared_task(name="analytics.recompute_all_search_impact")
def recompute_all_search_impact() -> dict[str, int]:
    """Recompute search impact for all applied suggestions."""
    from apps.suggestions.models import Suggestion
    from .impact_engine import compute_search_impact

    applied = Suggestion.objects.filter(status="applied")
    count = 0
    for sug in applied:
        compute_search_impact(sug)
        count += 1

    return {"processed_suggestions": count}
