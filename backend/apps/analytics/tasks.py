"""Celery tasks for FR-016 telemetry sync."""

from __future__ import annotations

from datetime import timedelta

from celery import shared_task
from django.utils import timezone

from apps.api.query_params import coerce_int
from apps.core.helpers import HelperConstraint
from django.db import connection

from .external_errors import is_google_api_client_error
from .models import AnalyticsSyncRun
from .sync import run_ga4_sync, run_matomo_sync, run_gsc_sync


def _load_sync_run(sync_run_id: int) -> AnalyticsSyncRun:
    return AnalyticsSyncRun.objects.get(pk=sync_run_id)


def _queue_scheduled_sync(
    *, source: str, lookback_days: int, task_fn
) -> dict[str, int | str]:
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


def _mark_sync_failed(sync_run: AnalyticsSyncRun, exc: Exception) -> None:
    sync_run.status = "failed"
    sync_run.error_message = str(exc)
    sync_run.completed_at = timezone.now()
    sync_run.save(
        update_fields=["status", "error_message", "completed_at"]
    )


def _failed_sync_result(sync_run_id: int, exc: Exception) -> dict[str, int | str]:
    return {"sync_run_id": sync_run_id, "status": "failed", "error": str(exc)}


@shared_task(
    bind=True,
    name="analytics.sync_matomo_telemetry",
    time_limit=600,
    soft_time_limit=540,
)
@HelperConstraint(
    cpu_intensive=True,
    gpu_required=False,
    storage_writes_to="postgres_main",
    ram_peak_mb=512,
    expected_seconds_p50=300,
)
def sync_matomo_telemetry(self, sync_run_id: int) -> dict[str, int | str]:
    # Mandatory Prevention Sweep (#86): close stale connections before task logic.
    if not connection.in_atomic_block:
        connection.close()

    sync_run = _load_sync_run(sync_run_id)
    sync_run.status = "running"
    sync_run.error_message = ""
    sync_run.save(update_fields=["status", "error_message"])

    try:
        stats = run_matomo_sync(sync_run)
    except Exception as exc:
        _mark_sync_failed(sync_run, exc)
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
        ]
    )
    return {"sync_run_id": sync_run_id, **stats}


@shared_task(
    bind=True, name="analytics.sync_ga4_telemetry", time_limit=600, soft_time_limit=540
)
@HelperConstraint(
    cpu_intensive=True,
    gpu_required=False,
    storage_writes_to="postgres_main",
    ram_peak_mb=512,
    expected_seconds_p50=300,
)
def sync_ga4_telemetry(self, sync_run_id: int) -> dict[str, int | str]:
    # Mandatory Prevention Sweep (#86): close stale connections before task logic.
    if not connection.in_atomic_block:
        connection.close()

    sync_run = _load_sync_run(sync_run_id)
    sync_run.status = "running"
    sync_run.error_message = ""
    sync_run.save(update_fields=["status", "error_message"])

    try:
        stats = run_ga4_sync(sync_run)
    except Exception as exc:
        _mark_sync_failed(sync_run, exc)
        if is_google_api_client_error(exc):
            return _failed_sync_result(sync_run_id, exc)
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
        ]
    )
    return {"sync_run_id": sync_run_id, **stats}


@shared_task(
    bind=True,
    name="analytics.sync_gsc_performance",
    time_limit=600,
    soft_time_limit=540,
)
@HelperConstraint(
    cpu_intensive=True,
    gpu_required=False,
    storage_writes_to="postgres_main",
    ram_peak_mb=512,
    expected_seconds_p50=300,
)
def sync_gsc_performance(self, sync_run_id: int) -> dict[str, int | str]:
    # Mandatory Prevention Sweep (#86): close stale connections before task logic.
    if not connection.in_atomic_block:
        connection.close()

    sync_run = _load_sync_run(sync_run_id)
    sync_run.status = "running"
    sync_run.error_message = ""
    sync_run.save(update_fields=["status", "error_message"])

    try:
        stats = run_gsc_sync(sync_run)
    except Exception as exc:
        _mark_sync_failed(sync_run, exc)
        if is_google_api_client_error(exc):
            return _failed_sync_result(sync_run_id, exc)
        raise

    sync_run.status = "completed"
    sync_run.completed_at = timezone.now()
    # Bug fix 2026-05-04: bare int() crashed if a sync backend
    # returned a non-numeric stats value (e.g. "N/A" instead of 0).
    # coerce_int treats bad input as 0 so the sync run still saves
    # cleanly; the operator can investigate the bad backend later.
    sync_run.rows_read = coerce_int(stats.get("rows_read"), default=0, min_value=0)
    sync_run.rows_written = coerce_int(
        stats.get("rows_written"), default=0, min_value=0
    )
    sync_run.rows_updated = coerce_int(
        stats.get("rows_updated"), default=0, min_value=0
    )
    sync_run.save(
        update_fields=[
            "status",
            "completed_at",
            "rows_read",
            "rows_written",
            "rows_updated",
        ]
    )
    return {"sync_run_id": sync_run_id, **stats}


@shared_task(name="analytics.schedule_ga4_telemetry_hourly")
@HelperConstraint(
    cpu_intensive=False,
    gpu_required=False,
    storage_writes_to="postgres_main",
    ram_peak_mb=256,
)
def schedule_ga4_telemetry_hourly() -> dict[str, int | str]:
    # Mandatory Prevention Sweep (#86): close stale connections before task logic.
    if not connection.in_atomic_block:
        connection.close()

    return _queue_scheduled_sync(
        source="ga4",
        lookback_days=2,
        task_fn=sync_ga4_telemetry,
    )


@shared_task(name="analytics.schedule_ga4_telemetry_daily")
@HelperConstraint(
    cpu_intensive=False,
    gpu_required=False,
    storage_writes_to="postgres_main",
    ram_peak_mb=256,
)
def schedule_ga4_telemetry_daily() -> dict[str, int | str]:
    # Mandatory Prevention Sweep (#86): close stale connections before task logic.
    if not connection.in_atomic_block:
        connection.close()

    return _queue_scheduled_sync(
        source="ga4",
        lookback_days=7,
        task_fn=sync_ga4_telemetry,
    )


@shared_task(name="analytics.schedule_matomo_telemetry_hourly")
@HelperConstraint(
    cpu_intensive=False,
    gpu_required=False,
    storage_writes_to="postgres_main",
    ram_peak_mb=256,
)
def schedule_matomo_telemetry_hourly() -> dict[str, int | str]:
    # Mandatory Prevention Sweep (#86): close stale connections before task logic.
    if not connection.in_atomic_block:
        connection.close()

    return _queue_scheduled_sync(
        source="matomo",
        lookback_days=1,
        task_fn=sync_matomo_telemetry,
    )


@shared_task(name="analytics.schedule_matomo_telemetry_daily")
@HelperConstraint(
    cpu_intensive=False,
    gpu_required=False,
    storage_writes_to="postgres_main",
    ram_peak_mb=256,
)
def schedule_matomo_telemetry_daily() -> dict[str, int | str]:
    # Mandatory Prevention Sweep (#86): close stale connections before task logic.
    if not connection.in_atomic_block:
        connection.close()

    return _queue_scheduled_sync(
        source="matomo",
        lookback_days=7,
        task_fn=sync_matomo_telemetry,
    )


@shared_task(name="analytics.schedule_gsc_performance_daily")
@HelperConstraint(
    cpu_intensive=False,
    gpu_required=False,
    storage_writes_to="postgres_main",
    ram_peak_mb=256,
)
def schedule_gsc_performance_daily() -> dict[str, int | str]:
    # Mandatory Prevention Sweep (#86): close stale connections before task logic.
    if not connection.in_atomic_block:
        connection.close()

    from .views import get_gsc_settings

    settings = get_gsc_settings()
    # Bug fix 2026-05-04: bare int() crashed if operator-supplied
    # sync_lookback_days was non-numeric (e.g. "fortnight"). Now
    # falls back to 14 + clamps to a sensible range so an over-large
    # value can't trigger an unbounded GSC pull.
    lookback = coerce_int(
        settings.get("sync_lookback_days"),
        default=14,
        min_value=1,
        max_value=365,
    )
    return _queue_scheduled_sync(
        source="gsc",
        lookback_days=lookback,
        task_fn=sync_gsc_performance,
    )


@shared_task(
    bind=True,
    name="analytics.refresh_gsc_query_tfidf",
    time_limit=1800,
    soft_time_limit=1740,
)
@HelperConstraint(
    cpu_intensive=True,
    gpu_required=False,
    storage_writes_to="postgres_main",
    ram_peak_mb=512,
    expected_seconds_p50=600,
)
def refresh_gsc_query_tfidf(self, lookback_days: int = 90) -> dict[str, int]:
    """FR-105 RSQVA — recompute per-page GSC query TF-IDF vectors."""
    # Mandatory Prevention Sweep (#86): close stale connections before task logic.
    if not connection.in_atomic_block:
        connection.close()

    from .gsc_query_vocab import refresh_gsc_query_tfidf as _impl

    return _impl(lookback_days=lookback_days)


@shared_task(
    name="analytics.recompute_all_search_impact", time_limit=1800, soft_time_limit=1740
)
@HelperConstraint(
    cpu_intensive=True,
    gpu_required=False,
    storage_writes_to="postgres_main",
    ram_peak_mb=512,
    expected_seconds_p50=600,
)
def recompute_all_search_impact() -> dict[str, int]:
    """Recompute search impact for all applied suggestions."""
    # Mandatory Prevention Sweep (#86): close stale connections before task logic.
    if not connection.in_atomic_block:
        connection.close()

    from apps.suggestions.models import Suggestion
    from .impact_engine import compute_search_impact

    applied = Suggestion.objects.filter(status="applied")
    count = 0
    for sug in applied:
        compute_search_impact(sug)
        count += 1

    return {"processed_suggestions": count}


_SPIKE_RATIO = 4  # alert when latest clicks exceed 4x the trailing average
_SPIKE_NOISE_FLOOR_CLICKS = 10  # ignore pages below this on the target day


def _snapshot_gsc_clicks(start_date, end_date) -> "Path | None":
    """Export the GSC click window to a Parquet snapshot; None when empty.

    A fixed filename is reused (atomic replace) so snapshots never pile up.
    """
    import tempfile
    from pathlib import Path

    import polars as pl

    from apps.pipeline.services._parquet_io import write_parquet_atomic
    from .models import SearchMetric

    rows = list(
        SearchMetric.objects.filter(
            source="gsc", date__range=[start_date, end_date]
        ).values_list("content_item_id", "date", "clicks")
    )
    if not rows:
        return None
    item_ids, dates, clicks = zip(*rows)
    df = pl.DataFrame(
        {
            "content_item_id": list(item_ids),
            "date": list(dates),
            "clicks": list(clicks),
        }
    )
    path = (
        Path(tempfile.gettempdir())
        / "xf-analytics-snapshots"
        / "gsc_clicks_window.parquet"
    )
    write_parquet_atomic(df, path)
    return path


def _query_spikes(
    snapshot_path, target_date, window_start, window_end
) -> list[tuple[int, int, float]]:
    """One DataFusion SQL pass: noise floor, both windows, and the 4x rule."""
    from apps.pipeline.services.datafusion_engine import DataFusionEngine

    engine = DataFusionEngine()
    engine.register_parquet_file("gsc_clicks", snapshot_path)
    query_template = """
        WITH latest AS (
            SELECT content_item_id, SUM(clicks) AS latest_clicks
            FROM gsc_clicks
            WHERE "date" = DATE '{t}'
            GROUP BY content_item_id
            HAVING SUM(clicks) > {floor}
        ),
        trailing AS (
            SELECT content_item_id, AVG(clicks) AS avg_clicks
            FROM gsc_clicks
            WHERE "date" BETWEEN DATE '{ws}' AND DATE '{we}'
            GROUP BY content_item_id
        )
        SELECT latest.content_item_id, latest.latest_clicks, trailing.avg_clicks
        FROM latest
        JOIN trailing ON latest.content_item_id = trailing.content_item_id
        WHERE trailing.avg_clicks > 0
          AND latest.latest_clicks > trailing.avg_clicks * {r}
    """
    query = query_template.replace('{t}', str(target_date)).replace('{floor}', str(_SPIKE_NOISE_FLOOR_CLICKS)).replace('{ws}', str(window_start)).replace('{we}', str(window_end)).replace('{r}', str(_SPIKE_RATIO))  # nosec B608
    table = engine.execute_sql(query)
    return [
        (int(item_id), int(latest), float(avg))
        for item_id, latest, avg in zip(
            table.column("content_item_id").to_pylist(),
            table.column("latest_clicks").to_pylist(),
            table.column("avg_clicks").to_pylist(),
        )
    ]


@shared_task(
    name="analytics.detect_traffic_spikes", time_limit=600, soft_time_limit=540
)
@HelperConstraint(
    cpu_intensive=False,
    gpu_required=False,
    storage_writes_to="postgres_main",
    ram_peak_mb=256,
)
def detect_traffic_spikes() -> dict[str, int]:
    """
    FR-023 Part 3: Momentum-based spike detection.
    Alerts the dashboard when a page's daily traffic exceeds 4x its 7-day trailing average.

    DataFusion rewire 2026-06-10: the click window is snapshotted to a local
    Parquet file and a single analytical SQL pass computes the noise floor,
    both window aggregates, and the spike rule — replacing two ORM GROUP BY
    queries plus a Python filter loop, and keeping the heavy scan off the
    transactional Postgres connection.
    """
    # Mandatory Prevention Sweep (#86): close stale connections before task logic.
    if not connection.in_atomic_block:
        connection.close()

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

    # 2. Snapshot the full window once, then one SQL pass finds the spikes.
    snapshot_path = _snapshot_gsc_clicks(seven_days_ago, target_date)
    if snapshot_path is None:
        return {"alerts_emitted": 0}

    spiking = _query_spikes(snapshot_path, target_date, seven_days_ago, one_day_ago)
    if not spiking:
        return {"alerts_emitted": 0}

    # Bulk fetch titles in one round trip. Use a dict keyed on PK so a
    # dangling SearchMetric.content_item_id (item deleted between the
    # filter and this loop) just yields a None title — bug fix: the
    # previous code did `ContentItem.objects.get(pk=item_id)` which
    # raised DoesNotExist and killed the whole task on the first orphan.
    spiking_ids = [item_id for item_id, _, _ in spiking]
    titles_by_id: dict[int, str] = dict(
        ContentItem.objects.filter(pk__in=spiking_ids).values_list("pk", "title")
    )

    alerts_count = 0
    for item_id, latest_clicks, avg_clicks in spiking:
        title = titles_by_id.get(item_id) or f"(deleted item #{item_id})"
        # Defensive: title could legitimately be empty for newly-imported
        # rows; guard the slice + the format so the f-string can't crash.
        title_short = (title or "")[:40] or f"item #{item_id}"
        emit_operator_alert(
            event_type="traffic_spike",
            severity=OperatorAlert.SEVERITY_INFO,
            title=f"Traffic Spike: {title_short}...",
            message=(
                f"Page '{title}' saw {latest_clicks} clicks on {target_date}, "
                f"which is {((latest_clicks / avg_clicks) - 1) * 100:.0f}% above its 7-day average ({avg_clicks:.1f})."
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
            },
        )
        alerts_count += 1

    return {"alerts_emitted": alerts_count}
