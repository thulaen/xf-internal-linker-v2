"""Celery tasks for FR-016 telemetry sync."""

from __future__ import annotations

from datetime import timedelta

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


@shared_task(bind=True, name="analytics.sync_matomo_telemetry", time_limit=600, soft_time_limit=540)
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


@shared_task(bind=True, name="analytics.sync_ga4_telemetry", time_limit=600, soft_time_limit=540)
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


@shared_task(bind=True, name="analytics.sync_gsc_performance", time_limit=600, soft_time_limit=540)
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


@shared_task(name="analytics.recompute_all_search_impact", time_limit=1800, soft_time_limit=1740)
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


@shared_task(name="analytics.detect_traffic_spikes", time_limit=600, soft_time_limit=540)
def detect_traffic_spikes() -> dict[str, int]:
    """
    FR-023 Part 3: Momentum-based spike detection.
    Alerts the dashboard if a page's daily traffic is >300% above its 7-day trailing average.
    """
    from django.db.models import Avg, Sum
    from apps.notifications.services import emit_operator_alert
    from apps.notifications.models import OperatorAlert
    from apps.content.models import ContentItem
    from .models import SearchMetric

    # 1. Find the latest date we have GSC data for
    latest_metric = SearchMetric.objects.filter(source="gsc").order_by("-date").first()
    if not latest_metric:
        return {"alerts_emitted": 0}

    target_date = latest_metric.date
    seven_days_ago = target_date - timedelta(days=7)
    one_day_ago = target_date - timedelta(days=1)

    # 2. Identify candidates (pages with at least some traffic on the target date)
    # We only care about pages with > 10 clicks to avoid noise from 1 click vs 0.
    candidates = SearchMetric.objects.filter(
        date=target_date, 
        source="gsc", 
        clicks__gt=10
    ).values_list("content_item_id", flat=True)

    alerts_count = 0
    for item_id in candidates:
        stats = SearchMetric.objects.filter(
            content_item_id=item_id,
            source="gsc",
            date__range=[seven_days_ago, one_day_ago]
        ).aggregate(avg_clicks=Avg("clicks"))
        
        avg_clicks = stats["avg_clicks"] or 0
        latest_clicks = SearchMetric.objects.filter(
            content_item_id=item_id,
            source="gsc",
            date=target_date
        ).aggregate(total=Sum("clicks"))["total"] or 0

        # Threshold: 300% above average (i.e., 4x the average)
        if avg_clicks > 0 and latest_clicks > (avg_clicks * 4):
            item = ContentItem.objects.get(pk=item_id)
            emit_operator_alert(
                event_type="traffic_spike",
                severity=OperatorAlert.SEVERITY_INFO,
                title=f"Traffic Spike: {item.title[:40]}...",
                message=(
                    f"Page '{item.title}' saw {latest_clicks} clicks on {target_date}, "
                    f"which is {((latest_clicks/avg_clicks)-1)*100:.0f}% above its 7-day average ({avg_clicks:.1f})."
                ),
                source_area=OperatorAlert.AREA_PIPELINE,
                dedupe_key=f"traffic-spike-{item_id}-{target_date}",
                related_object_type="content_item",
                related_object_id=str(item_id),
                payload={
                    "item_id": item_id,
                    "date": str(target_date),
                    "latest_clicks": latest_clicks,
                    "avg_clicks": float(avg_clicks),
                }
            )
            alerts_count += 1

    return {"alerts_emitted": alerts_count}
