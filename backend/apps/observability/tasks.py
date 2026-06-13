from __future__ import annotations

from celery import shared_task
from django.db import connection

from apps.core.helpers import HelperConstraint


@shared_task(name="observability.detect_gaps")
@HelperConstraint(
    cpu_intensive=False,
    gpu_required=False,
    storage_writes_to="postgres_main",
    ram_peak_mb=128,
)
def detect_observability_gaps() -> int:
    if not connection.in_atomic_block:
        connection.close()
    from apps.observability.services.gap_detector import detect_observability_gaps as _run

    return _run()


@shared_task(name="observability.collect_system_metrics")
@HelperConstraint(
    cpu_intensive=False,
    gpu_required=False,
    storage_writes_to="postgres_main",
    ram_peak_mb=128,
)
def collect_system_metrics() -> dict:
    if not connection.in_atomic_block:
        connection.close()
    return refresh_live_gauges()


def refresh_live_gauges() -> dict:
    """Emit live values for the data-backed gauge/histogram reserved metrics.

    Called by the Celery task above AND — so the values land in the scraped
    (web) process rather than only in a Celery worker — by MetricsView on every
    /metrics scrape. The prometheus_client registry is per-process and
    multiprocess mode is not configured, so refreshing here is what makes these
    gauges visible to vmagent. Each source is best-effort: one failing (e.g.
    Redis briefly unreachable) must not stop the others or break the scrape.
    The *_total counter metrics are emitted at their event sites, not here.
    """
    collected: dict[str, object] = {}
    for label, emit in (
        ("system", _emit_system_gauges),
        ("db_latency_s", _emit_db_latency),
        ("queues", _emit_queue_depth),
    ):
        try:
            collected[label] = emit()
        except Exception as exc:  # noqa: BLE001 - best-effort; record and continue.
            collected[label] = f"error: {type(exc).__name__}"
    return {"collected": collected}


def _emit_system_gauges() -> dict:
    """xf_system_memory_rss_bytes + xf_system_disk_{usage,capacity}_bytes."""
    import psutil

    from apps.observability.api import get_metric
    from apps.observability.instruments import safe_set

    rss = float(psutil.Process().memory_info().rss)
    safe_set(get_metric("xf_system_memory_rss_bytes"), rss, service="backend")
    disk = psutil.disk_usage("/")
    safe_set(get_metric("xf_system_disk_usage_bytes"), float(disk.used), mount="/")
    safe_set(get_metric("xf_system_disk_capacity_bytes"), float(disk.total), mount="/")
    return {"memory_rss_bytes": rss, "disk_used_bytes": float(disk.used)}


def _emit_db_latency() -> float:
    """xf_db_latency_seconds — time a trivial round-trip to Postgres."""
    import time

    from apps.observability.api import get_metric
    from apps.observability.instruments import safe_observe

    start = time.perf_counter()
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
        cursor.fetchone()
    elapsed = time.perf_counter() - start
    safe_observe(get_metric("xf_db_latency_seconds"), elapsed, operation="select", status="ok")
    return elapsed


def _emit_queue_depth() -> dict:
    """xf_queue_depth{queue} — Redis list length of each Celery queue."""
    import redis
    from django.conf import settings

    from apps.observability.api import get_metric
    from apps.observability.instruments import safe_set

    client = redis.Redis.from_url(settings.REDIS_URL, socket_connect_timeout=2)
    depths: dict[str, float] = {}
    for queue in ("default", "pipeline", "embeddings"):
        depth = float(client.llen(queue))
        safe_set(get_metric("xf_queue_depth"), depth, queue=queue)
        depths[queue] = depth
    return depths
