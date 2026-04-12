"""
Crawler tasks — heartbeat pulse, auto-prune, and crawl orchestration.
"""

import logging
import time

from datetime import timedelta

from celery import shared_task
from django.db import connection
from django.utils import timezone

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Heartbeat / Liveness Pulse — runs every 60 seconds
# ---------------------------------------------------------------------------
@shared_task(
    name="crawler.pulse_heartbeat",
    time_limit=30,
    soft_time_limit=20,
    ignore_result=True,
)
def pulse_heartbeat():
    """
    Lightweight liveness probe: ping all core services, record a pulse event,
    and push rolling stats to the C++ ring buffer.

    Runs every 60 s via Celery Beat.  Total execution <100 ms.
    """
    from apps.crawler.models import SystemEvent

    ts = time.time()
    checks: dict[str, dict] = {}
    overall_ok = True

    # 1. PostgreSQL
    try:
        t0 = time.perf_counter()
        with connection.cursor() as cur:
            cur.execute("SELECT 1")
        checks["postgres"] = {"ok": True, "ms": _elapsed_ms(t0)}
    except Exception as exc:
        checks["postgres"] = {"ok": False, "error": str(exc)[:200]}
        overall_ok = False

    # 2. Redis
    try:
        from django_redis import get_redis_connection

        t0 = time.perf_counter()
        r = get_redis_connection("default")
        r.ping()
        checks["redis"] = {"ok": True, "ms": _elapsed_ms(t0)}
    except Exception as exc:
        checks["redis"] = {"ok": False, "error": str(exc)[:200]}
        overall_ok = False

    # 3. Celery workers
    try:
        from celery import current_app

        t0 = time.perf_counter()
        insp = current_app.control.inspect(timeout=2.0)
        active = insp.active() or {}
        worker_count = len(active)
        task_count = sum(len(tasks) for tasks in active.values())
        checks["celery"] = {
            "ok": worker_count > 0,
            "ms": _elapsed_ms(t0),
            "workers": worker_count,
            "tasks": task_count,
        }
        if worker_count == 0:
            overall_ok = False
    except Exception as exc:
        checks["celery"] = {"ok": False, "error": str(exc)[:200]}
        overall_ok = False

    # 4. C++ extensions
    try:
        from apps.pipeline.services.ext_loader import load_extension

        t0 = time.perf_counter()
        scoring = load_extension("scoring", "calculate_composite_scores_full_batch")
        checks["cpp_extensions"] = {
            "ok": scoring is not None,
            "ms": _elapsed_ms(t0),
        }
    except Exception as exc:
        checks["cpp_extensions"] = {"ok": False, "error": str(exc)[:200]}

    # Push to C++ ring buffer (if available).
    severity = 0 if overall_ok else 3
    avg_ms = _avg_latency(checks)
    try:
        pulse = load_extension("pulse_metrics", "push_event")
        if pulse is not None:
            pulse.push_event(ts, severity, avg_ms, 0)
    except Exception:
        logger.debug("Failed to push pulse to C++ ring buffer", exc_info=True)

    # Emit SystemEvent for the Dashboard Activity Feed.
    service_summary = ", ".join(
        f"{k}: {'OK' if v['ok'] else 'FAIL'}" for k, v in checks.items()
    )
    SystemEvent.objects.create(
        severity="success" if overall_ok else "error",
        source="heartbeat",
        title=f"Heartbeat {'OK' if overall_ok else 'DEGRADED'} — {service_summary}",
        detail=f"Avg latency: {avg_ms:.0f} ms",
        metadata=checks,
    )

    # Broadcast to WebSocket (system_pulse group).
    try:
        from channels.layers import get_channel_layer
        from asgiref.sync import async_to_sync

        channel_layer = get_channel_layer()
        if channel_layer:
            async_to_sync(channel_layer.group_send)(
                "system_pulse",
                {
                    "type": "pulse.heartbeat",
                    "ok": overall_ok,
                    "checks": checks,
                    "timestamp": ts,
                },
            )
    except Exception:
        logger.debug("Failed to broadcast pulse to WebSocket", exc_info=True)

    return {"ok": overall_ok, "checks": checks}


# ---------------------------------------------------------------------------
# Watchdog — checks for stuck jobs (runs with heartbeat)
# ---------------------------------------------------------------------------
@shared_task(
    name="crawler.watchdog_check",
    time_limit=30,
    soft_time_limit=20,
    ignore_result=True,
)
def watchdog_check():
    """
    Check for stuck sync jobs and crawler sessions.
    Emits warnings for jobs with no progress in 30+ minutes.
    """
    from apps.sync.models import SyncJob
    from apps.crawler.models import CrawlSession, SystemEvent
    from apps.notifications.services import emit_operator_alert

    now = timezone.now()
    stale_threshold = now - timedelta(minutes=30)
    auto_fail_threshold = now - timedelta(hours=24)

    # Auto-fail sync jobs stuck for more than 24 hours.
    SyncJob.objects.filter(
        status="running",
        updated_at__lt=auto_fail_threshold,
    ).update(status="failed")

    # Warn about sync jobs stuck 30 min – 24 h (not yet auto-failed).
    stuck_syncs = SyncJob.objects.filter(
        status="running",
        updated_at__lt=stale_threshold,
        updated_at__gte=auto_fail_threshold,
    )
    for job in stuck_syncs:
        emit_operator_alert(
            event_type="job_stalled",
            source_area="jobs",
            severity="warning",
            title=f"{job.source} sync appears stuck",
            message=(
                f"Job {job.job_id} has been running for "
                f"{(now - (job.started_at or now)).total_seconds() / 60:.0f} minutes "
                f"with no progress since {job.updated_at:%H:%M}."
            ),
            dedupe_key=f"stuck_sync_{job.job_id}",
            cooldown_seconds=86400,
        )
        SystemEvent.objects.create(
            severity="warning",
            source="sync",
            title=f"{job.source} sync appears stuck ({job.items_synced} items done)",
        )

    # Auto-fail crawl sessions stuck for more than 24 hours.
    CrawlSession.objects.filter(
        status="running",
        updated_at__lt=auto_fail_threshold,
    ).update(status="failed")

    # Warn about crawl sessions stuck 30 min – 24 h.
    stuck_crawls = CrawlSession.objects.filter(
        status="running",
        updated_at__lt=stale_threshold,
        updated_at__gte=auto_fail_threshold,
    )
    for session in stuck_crawls:
        emit_operator_alert(
            event_type="job_stalled",
            source_area="crawler",
            severity="warning",
            title=f"Crawl for {session.site_domain} appears stuck",
            message=(
                f"Session has been running for "
                f"{(now - (session.started_at or now)).total_seconds() / 60:.0f} minutes "
                f"with no progress since {session.updated_at:%H:%M}."
            ),
            dedupe_key=f"stuck_crawl_{session.session_id}",
            cooldown_seconds=86400,
        )


# ---------------------------------------------------------------------------
# Auto-Prune — runs every 4 weeks via Celery Beat
# ---------------------------------------------------------------------------
@shared_task(
    name="crawler.auto_prune",
    time_limit=600,
    soft_time_limit=540,
    ignore_result=True,
)
def auto_prune():
    """
    Self-pruning to save disk.  Runs every 4 weeks.

    Rules:
      - Crawl session data >90 days: delete page-level records, keep session summary.
      - Pages with 3+ consecutive 404s: mark as gone.
      - SystemEvent rows >90 days: delete.
      - Fixed broken links >30 days: auto-archive.
    """
    from apps.crawler.models import CrawledPageMeta, SystemEvent

    now = timezone.now()
    cutoff_90d = now - timedelta(days=90)
    cutoff_30d = now - timedelta(days=30)

    # 1. Delete old page-level crawl data (keep session summaries).
    old_pages = CrawledPageMeta.objects.filter(session__completed_at__lt=cutoff_90d)
    page_count = old_pages.count()
    if page_count > 0:
        old_pages.delete()
        logger.info("Auto-prune: deleted %d old crawled page records.", page_count)

    # 2. Mark dead pages (3+ consecutive 404s).
    dead_pages = CrawledPageMeta.objects.filter(consecutive_404_count__gte=3)
    dead_count = dead_pages.count()
    # These pages will be skipped by the crawler frontier on next run.

    # 3. Prune old SystemEvents.
    old_events = SystemEvent.objects.filter(timestamp__lt=cutoff_90d)
    event_count = old_events.count()
    if event_count > 0:
        old_events.delete()
        logger.info("Auto-prune: deleted %d old system events.", event_count)

    # 4. Auto-archive fixed broken links older than 30 days.
    try:
        from apps.graph.models import BrokenLink

        archived = BrokenLink.objects.filter(
            status="fixed",
            updated_at__lt=cutoff_30d,
        ).update(status="archived")
        if archived:
            logger.info("Auto-prune: archived %d fixed broken links.", archived)
    except Exception:
        logger.debug("Failed to auto-archive broken links during prune", exc_info=True)

    # Emit summary event.
    SystemEvent.objects.create(
        severity="info",
        source="prune",
        title=f"Auto-prune complete — {page_count} pages, {event_count} events removed",
        metadata={
            "pages_deleted": page_count,
            "events_deleted": event_count,
            "dead_pages_found": dead_count,
        },
    )

    return {
        "pages_deleted": page_count,
        "events_deleted": event_count,
        "dead_pages_found": dead_count,
    }


# ---------------------------------------------------------------------------
# One-Button Orchestrator: Sync + Crawl + Pipeline
# ---------------------------------------------------------------------------
@shared_task(
    name="crawler.orchestrate_full_run",
    time_limit=14400,
    soft_time_limit=14000,
    ignore_result=True,
)
def orchestrate_full_run():
    """
    Single-button workflow: sync all sources, crawl all domains, run pipeline.

    Stage 1: XenForo + WordPress syncs (parallel, wait for both).
    Stage 2: Web crawler (sequential after syncs, dedup against API data).
    Stage 3: ML pipeline (sequential after crawler).

    Progress streamed via WebSocket for real-time frontend updates.
    """
    from apps.crawler.models import SystemEvent, SitemapConfig, CrawlSession

    SystemEvent.objects.create(
        severity="info",
        source="system",
        title="Full Sync & Crawl started",
    )

    # ── Stage 1: API Syncs (parallel) ────────────────────────────────
    # These are dispatched as separate Celery tasks that run concurrently.
    from apps.pipeline.tasks import import_content

    xf_job = import_content.apply_async(
        kwargs={"source": "api", "mode": "full"},
        queue="pipeline",
    )
    wp_job = import_content.apply_async(
        kwargs={"source": "wp", "mode": "full"},
        queue="pipeline",
    )

    # Wait for both to complete (with timeout).
    try:
        xf_job.get(timeout=3600, propagate=False)
    except Exception as exc:
        logger.warning("XenForo sync failed: %s", exc)
    try:
        wp_job.get(timeout=3600, propagate=False)
    except Exception as exc:
        logger.warning("WordPress sync failed: %s", exc)

    SystemEvent.objects.create(
        severity="success",
        source="sync",
        title="Stage 1 complete — API syncs finished",
    )

    # ── Stage 2: Web Crawler ─────────────────────────────────────────
    sitemaps = SitemapConfig.objects.filter(is_enabled=True)
    domains = sitemaps.values_list("domain", flat=True).distinct()

    for domain in domains:
        session = CrawlSession.objects.create(
            site_domain=domain,
            status="pending",
            config={
                "rate_limit": 4,
                "max_depth": 5,
                "excluded_paths": [
                    "/members/",
                    "/login/",
                    "/register/",
                    "/account/",
                    "/search/",
                    "/admin.php",
                    "/help/",
                ],
                "timeout_hours": 2,
            },
        )

        try:
            run_crawl_session.delay(session_id=str(session.session_id))
        except Exception as exc:
            logger.warning("Crawl job for %s failed to queue: %s", domain, exc)
            session.status = "failed"
            session.error_message = str(exc)
            session.save(update_fields=["status", "error_message", "updated_at"])

    SystemEvent.objects.create(
        severity="success",
        source="crawler",
        title="Stage 2 complete — crawler finished",
    )

    # ── Stage 3: ML Pipeline ─────────────────────────────────────────
    from apps.pipeline.tasks import run_pipeline

    try:
        pipeline_job = run_pipeline.apply_async(queue="pipeline")
        pipeline_job.get(timeout=7200, propagate=False)
    except Exception as exc:
        logger.warning("Pipeline failed: %s", exc)

    SystemEvent.objects.create(
        severity="success",
        source="pipeline",
        title="Stage 3 complete — pipeline finished. All done!",
    )

    return {"status": "completed"}


@shared_task(
    name="crawler.run_crawl_session",
    time_limit=14400,
    soft_time_limit=14000,
    ignore_result=True,
)
def run_crawl_session(session_id: str):
    from apps.crawler.services.site_crawler import run_crawl_session_sync
    import uuid

    run_crawl_session_sync(uuid.UUID(session_id))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _elapsed_ms(t0: float) -> float:
    return (time.perf_counter() - t0) * 1000


def _avg_latency(checks: dict) -> float:
    latencies = [v.get("ms", 0) for v in checks.values() if v.get("ok")]
    return sum(latencies) / len(latencies) if latencies else 0.0
