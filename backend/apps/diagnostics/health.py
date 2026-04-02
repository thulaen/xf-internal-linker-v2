import logging
import os
from datetime import timedelta

import requests
from asgiref.sync import async_to_sync
from celery import current_app
from django.conf import settings
from django.db import connection
from django.utils import timezone
from django_redis import get_redis_connection

from apps.suggestions.models import Suggestion

from .models import ServiceStatusSnapshot, SystemConflict

logger = logging.getLogger(__name__)


def _result(
    state: str,
    explanation: str,
    next_step: str,
    metadata: dict | None = None,
):
    return state, explanation, next_step, metadata or {}


def _http_worker_status_url() -> str:
    base_url = str(getattr(settings, "HTTP_WORKER_URL", "http://http-worker-api:8080")).rstrip("/")
    if base_url.endswith("/api/v1/status"):
        return base_url
    return f"{base_url}/api/v1/status"


def _http_worker_metadata(status_url: str, data: dict) -> dict:
    worker = data.get("worker") or {}
    scheduler = data.get("scheduler") or {}
    performance = data.get("performance") or {}
    last_completed = worker.get("last_completed") or {}
    last_failed = worker.get("last_failed") or {}
    redis_connected = bool(data.get("redis_connected"))
    database_connected = bool(data.get("database_connected"))
    worker_online = bool(data.get("worker_online"))
    queue_depth = data.get("queue_depth", 0)

    return {
        "url": status_url,
        "schema_version": data.get("schema_version"),
        "build_version": data.get("build_version"),
        "redis_connected": redis_connected,
        "database_connected": database_connected,
        "worker_online": worker_online,
        "queue_depth": queue_depth,
        "worker_heartbeat_age_seconds": data.get("worker_heartbeat_age_seconds"),
        "worker_instance_id": worker.get("instance_id"),
        "dead_letter_count": worker.get("dead_letter_count"),
        "retry_count_total": worker.get("retry_count_total"),
        "latency_p50_ms": performance.get("latency_p50_ms"),
        "latency_p95_ms": performance.get("latency_p95_ms"),
        "latency_p99_ms": performance.get("latency_p99_ms"),
        "drain_rate_per_minute": performance.get("drain_rate_per_minute"),
        "scheduler_status": scheduler.get("status"),
        "scheduler_mode": scheduler.get("ownership_mode"),
        "scheduler_enabled_tasks": scheduler.get("enabled_periodic_tasks"),
        "scheduler_heartbeat_age_seconds": data.get("scheduler_heartbeat_age_seconds"),
        "last_completed_job_type": last_completed.get("job_type"),
        "last_failed_job_type": last_failed.get("job_type"),
        "last_failed_error": last_failed.get("error"),
        "python_fallback_active": not (redis_connected and database_connected and worker_online),
    }


def check_django():
    return _result(
        "healthy",
        "Django answered this health check.",
        "No action needed.",
        {
            "settings_module": os.environ.get("DJANGO_SETTINGS_MODULE", ""),
        },
    )


def check_postgresql():
    try:
        connection.ensure_connection()
        return _result(
            "healthy",
            "PostgreSQL accepted a live connection.",
            "No action needed.",
            {
                "database": connection.settings_dict.get("NAME", ""),
                "host": connection.settings_dict.get("HOST", ""),
            },
        )
    except Exception as exc:
        return _result(
            "failed",
            f"PostgreSQL connection failed: {exc}",
            "Check whether PostgreSQL is running and whether the Django database settings are correct.",
        )


def check_redis():
    try:
        conn = get_redis_connection("default")
        conn.ping()
        return _result(
            "healthy",
            "Redis answered a live ping.",
            "No action needed.",
            {
                "redis_url": getattr(settings, "REDIS_URL", ""),
            },
        )
    except Exception as exc:
        return _result(
            "failed",
            f"Redis connection failed: {exc}",
            "Check whether Redis is running and whether REDIS_URL is correct.",
        )


def check_celery():
    try:
        inspect = current_app.control.inspect()
        ping = inspect.ping() or {}
        worker_count = len(ping)
        if worker_count > 0:
            return _result(
                "healthy",
                f"Celery workers replied to a ping ({worker_count} worker(s)).",
                "No action needed.",
                {
                    "worker_count": worker_count,
                },
            )
        return _result(
            "failed",
            "No Celery workers replied to a ping.",
            "Start the Celery worker process or check the broker connection.",
        )
    except Exception as exc:
        return _result(
            "failed",
            f"Celery check failed: {exc}",
            "Check Redis connectivity and the Celery worker logs.",
        )


def check_celery_beat():
    if not getattr(settings, "CELERY_BEAT_RUNTIME_ENABLED", True):
        return _result(
            "disabled",
            "Celery Beat is retired in this runtime shape, and the C# scheduler lane is expected to own live periodic execution.",
            "No action needed unless the C# scheduler lane loses heartbeat or stops dispatching due work.",
            {
                "runtime_enabled": False,
            },
        )

    try:
        from django_celery_beat.models import PeriodicTask

        enabled_tasks = PeriodicTask.objects.filter(enabled=True).count()
        if enabled_tasks == 0:
            return _result(
                "not_configured",
                "Celery Beat is installed, but there are no enabled periodic tasks.",
                "Add or enable a periodic task before relying on Celery Beat.",
                {
                    "enabled_periodic_tasks": 0,
                    "proof": "configuration_only",
                },
            )
        return _result(
            "degraded",
            f"Found {enabled_tasks} enabled periodic task(s), but this check does not have a live Beat heartbeat yet.",
            "Add a Beat heartbeat before treating Celery Beat as fully healthy.",
            {
                "enabled_periodic_tasks": enabled_tasks,
                "proof": "configuration_only",
            },
        )
    except ImportError:
        return _result(
            "not_installed",
            "django-celery-beat is not installed.",
            "Install django-celery-beat if scheduled tasks are required.",
        )
    except Exception as exc:
        return _result(
            "failed",
            f"Celery Beat check failed: {exc}",
            "Check the database and the Celery Beat configuration.",
        )


def check_channels():
    if not hasattr(settings, "CHANNEL_LAYERS"):
        return _result(
            "not_configured",
            "Django Channels is not configured.",
            "Add CHANNEL_LAYERS to the Django settings before relying on WebSocket progress updates.",
        )
    try:
        from channels.layers import get_channel_layer

        channel_layer = get_channel_layer()
        if channel_layer is None:
            return _result(
                "failed",
                "Channel layer could not be created.",
                "Check the Channels backend settings and Redis connection.",
            )
        async_to_sync(channel_layer.group_send)(
            "diagnostics_health_probe",
            {"type": "diagnostics.noop"},
        )
        return _result(
            "healthy",
            "Channel layer accepted a live send operation.",
            "No action needed.",
            {
                "backend": channel_layer.__class__.__name__,
            },
        )
    except Exception as exc:
        return _result(
            "failed",
            f"Channels check failed: {exc}",
            "Check the Channels backend and Redis connection.",
        )


def check_http_worker():
    status_url = _http_worker_status_url()
    if not getattr(settings, "HTTP_WORKER_ENABLED", False):
        return _result(
            "disabled",
            "C# HttpWorker is turned off, so Python still owns this helper path.",
            "Set HTTP_WORKER_ENABLED=true when you want Django to use the C# helper service.",
            {
                "url": status_url,
                "python_fallback_active": True,
            },
        )

    try:
        response = requests.get(status_url, timeout=5)
        if response.status_code != 200:
            return _result(
                "failed",
                f"C# HttpWorker returned status code {response.status_code}.",
                "Check whether the http-worker-api service is running and reachable.",
                {
                    "url": status_url,
                    "python_fallback_active": True,
                },
            )

        data = response.json()
        redis_connected = bool(data.get("redis_connected"))
        database_connected = bool(data.get("database_connected"))
        worker_online = bool(data.get("worker_online"))
        queue_depth = data.get("queue_depth", 0)
        metadata = _http_worker_metadata(status_url, data)

        if redis_connected and database_connected and worker_online:
            return _result(
                "healthy",
                f"C# HttpWorker API, Redis, and the queue worker are all alive. Queue depth is {queue_depth}.",
                "No action needed.",
                metadata,
            )

        if not redis_connected:
            return _result(
                "degraded",
                "C# HttpWorker answered, but its Redis queue is not healthy yet.",
                "Restore Redis first, then confirm the queue depth starts draining again.",
                metadata,
            )

        if not database_connected:
            return _result(
                "degraded",
                "C# HttpWorker answered, but its PostgreSQL lane is not healthy yet.",
                "Wire the real Postgres connection string into the C# runtime and restore database connectivity before trusting C# job ownership.",
                metadata,
            )

        return _result(
            "degraded",
            "C# HttpWorker API answered, but the queue-backed worker lane is offline. Direct helper endpoints may still work, but C# is not ready to own heavy jobs yet.",
            "Start the http-worker-queue service and wait for a fresh worker heartbeat before trusting this lane.",
            metadata,
        )
    except Exception as exc:
        return _result(
            "failed",
            f"C# HttpWorker is unreachable: {exc}",
            "Check whether HTTP_WORKER_URL points at the live http-worker-api service.",
            {
                "url": status_url,
                "python_fallback_active": True,
            },
        )


def check_runtime_lanes():
    owners = {
        "heavy_runtime_owner": getattr(settings, "HEAVY_RUNTIME_OWNER", "celery"),
        "broken_link_scan_owner": getattr(settings, "RUNTIME_OWNER_BROKEN_LINK_SCAN", "celery"),
        "graph_sync_owner": getattr(settings, "RUNTIME_OWNER_GRAPH_SYNC", "celery"),
        "import_owner": getattr(settings, "RUNTIME_OWNER_IMPORT", "celery"),
        "pipeline_owner": getattr(settings, "RUNTIME_OWNER_PIPELINE", "celery"),
    }
    csharp_owned = [lane for lane, owner in owners.items() if owner == "csharp" and lane != "heavy_runtime_owner"]
    celery_owned = [lane for lane, owner in owners.items() if owner == "celery" and lane != "heavy_runtime_owner"]
    metadata = {
        **owners,
        "csharp_owned_lane_count": len(csharp_owned),
        "celery_owned_lane_count": len(celery_owned),
    }

    if not celery_owned:
        return _result(
            "healthy",
            "C# owns every tracked heavy runtime lane.",
            "No action needed.",
            metadata,
        )

    explanation = (
        "Heavy runtime ownership is split right now. "
        f"C# owns {', '.join(csharp_owned) if csharp_owned else 'no tracked lanes yet'}, "
        f"while Celery still owns {', '.join(celery_owned)}."
    )
    if "graph_sync_owner" in celery_owned:
        next_step = "Move graph_sync next, then import and pipeline, so Celery stops owning the remaining heavy lanes."
    elif "import_owner" in celery_owned:
        next_step = "Move import next, then pipeline, so the C# scheduler is no longer dispatching Celery-owned heavy work."
    elif "pipeline_owner" in celery_owned:
        next_step = "Move pipeline next, then keep trimming the remaining Celery-owned support lanes."
    else:
        next_step = "Finish moving the remaining Celery-owned lanes before calling the heavy runtime cutover complete."
    return _result(
        "degraded",
        explanation,
        next_step,
        metadata,
    )


def check_scheduler_lane():
    state, _explanation, _next_step, metadata = check_http_worker()
    scheduler_status = str(metadata.get("scheduler_status") or "").strip().lower()
    scheduler_mode = str(metadata.get("scheduler_mode") or "").strip().lower()

    if not getattr(settings, "HTTP_WORKER_ENABLED", False):
        return _result(
            "disabled",
            "The C# scheduler lane is off because the HttpWorker runtime is disabled.",
            "Turn on the C# runtime before moving periodic work off Celery Beat.",
            {
                "scheduler_mode": scheduler_mode or "disabled",
            },
        )

    if state == "failed":
        return _result(
            "failed",
            "The C# scheduler lane cannot be trusted because the HttpWorker status endpoint is unreachable.",
            "Restore the C# runtime first, then re-check scheduler ownership.",
            metadata,
        )

    if scheduler_status == "active":
        return _result(
            "healthy",
            "The C# scheduler lane is active and reporting a fresh heartbeat.",
            "No action needed.",
            metadata,
        )

    if scheduler_status == "shadow":
        return _result(
            "degraded",
            "The C# scheduler lane is alive in shadow mode, but Celery Beat still owns live periodic execution.",
            "Keep validating parity, then flip schedule ownership to C# before retiring Beat.",
            metadata,
        )

    if scheduler_status == "disabled":
        return _result(
            "disabled",
            "The C# scheduler lane is installed but disabled.",
            "Enable the C# scheduler lane before moving periodic jobs off Celery Beat.",
            metadata,
        )

    return _result(
        "degraded",
        "The C# scheduler lane does not have a trustworthy heartbeat yet.",
        "Check the Postgres connection string and the scheduler worker logs.",
        metadata,
    )


def check_native_scoring():
    try:
        from extensions import scoring  # noqa: F401

        return _result(
            "healthy",
            "The native C++ scoring extension is importable, so the fast scoring kernel is available.",
            "No action needed.",
            {
                "native_scoring_active": True,
            },
        )
    except Exception as exc:
        return _result(
            "failed",
            f"The native C++ scoring extension could not be loaded: {exc}",
            "Rebuild the native extensions before trusting final weighted scoring.",
            {
                "native_scoring_active": False,
            },
        )


def check_embedding_specialist():
    return _result(
        "disabled",
        "No bounded Python embedding specialist lane is deployed yet, and embeddings are still tied to the older Python/Celery path.",
        "When embeddings are migrated, keep the Python specialist narrow and place C# in charge of orchestration around it.",
        {
            "embedding_specialist_active": False,
        },
    )


def check_ga4():
    from apps.analytics.models import SearchMetric

    latest_row = SearchMetric.objects.filter(source="ga4").order_by("-date").first()
    if latest_row is None:
        return _result(
            "not_configured",
            "GA4 has no synced telemetry rows yet.",
            "Configure GA4 sync and wait for fresh rows before trusting this signal.",
            {
                "ga4_connected": False,
            },
        )

    is_fresh = latest_row.date >= timezone.now().date() - timedelta(days=7)
    return _result(
        "healthy" if is_fresh else "degraded",
        "GA4 telemetry rows exist." if is_fresh else "GA4 telemetry rows exist, but they look stale.",
        "No action needed." if is_fresh else "Run the GA4 sync again before trusting this signal.",
        {
            "ga4_connected": True,
            "latest_ga4_date": latest_row.date.isoformat(),
        },
    )


def check_gsc():
    from apps.analytics.models import SearchMetric

    latest_row = SearchMetric.objects.filter(source="gsc").order_by("-date").first()
    if latest_row is None:
        return _result(
            "not_configured",
            "GSC has no synced telemetry rows yet.",
            "Configure GSC sync and wait for fresh rows before trusting this signal.",
            {
                "gsc_connected": False,
            },
        )

    is_fresh = latest_row.date >= timezone.now().date() - timedelta(days=7)
    return _result(
        "healthy" if is_fresh else "degraded",
        "GSC telemetry rows exist." if is_fresh else "GSC telemetry rows exist, but they look stale.",
        "No action needed." if is_fresh else "Run the GSC sync again before trusting this signal.",
        {
            "gsc_connected": True,
            "latest_gsc_date": latest_row.date.isoformat(),
        },
    )


def check_matomo():
    from apps.core.models import AppSetting

    setting_keys = {
        "analytics.matomo_enabled",
        "analytics.matomo_url",
        "analytics.matomo_site_id_xenforo",
        "analytics.matomo_token_auth",
    }
    configured_keys = set(
        AppSetting.objects.filter(
            key__in=setting_keys,
        ).exclude(value="").values_list("key", flat=True)
    )
    if configured_keys != setting_keys:
        return _result(
            "not_configured",
            "Matomo is not fully configured in the app settings yet.",
            "Fill in the Matomo settings before expecting telemetry from this dependency.",
            {
                "matomo_connected": False,
            },
        )

    return _result(
        "degraded",
        "Matomo settings exist, but there is no live sync proof in diagnostics yet.",
        "Add the Matomo sync lane and freshness proof before calling this dependency healthy.",
        {
            "matomo_connected": False,
        },
    )


def get_resource_usage():
    metrics = {
        "cpu_percent": "unavailable",
        "ram_usage_mb": "unavailable",
        "disk_usage_percent": "unavailable",
    }
    try:
        import psutil

        metrics["cpu_percent"] = psutil.cpu_percent()
        metrics["ram_usage_mb"] = psutil.virtual_memory().used / (1024 * 1024)
        metrics["disk_usage_percent"] = psutil.disk_usage("/").percent
    except ImportError:
        pass
    return metrics


def run_health_checks():
    checks = {
        "django": check_django,
        "postgresql": check_postgresql,
        "redis": check_redis,
        "celery_worker": check_celery,
        "celery_beat": check_celery_beat,
        "channels": check_channels,
        "http_worker": check_http_worker,
        "runtime_lanes": check_runtime_lanes,
        "scheduler_lane": check_scheduler_lane,
        "native_scoring": check_native_scoring,
        "embedding_specialist": check_embedding_specialist,
        "ga4": check_ga4,
        "gsc": check_gsc,
        "matomo": check_matomo,
    }

    results = {}
    checked_at = timezone.now()
    for service, check_fn in checks.items():
        state, explanation, next_step, metadata = check_fn()
        snapshot, _ = ServiceStatusSnapshot.objects.get_or_create(service_name=service)
        snapshot.state = state
        snapshot.explanation = explanation
        snapshot.next_action_step = next_step
        snapshot.metadata = metadata
        if state == "healthy":
            snapshot.last_success = checked_at
        elif state == "failed":
            snapshot.last_failure = checked_at
        snapshot.save()
        results[service] = {
            "state": state,
            "explanation": explanation,
            "next_step": next_step,
            "last_check": checked_at,
            "metadata": metadata,
        }
    return results


def detect_conflicts():
    conflicts = []

    from apps.analytics.models import SearchMetric

    if SearchMetric.objects.count() == 0:
        conflicts.append(
            {
                "type": "placeholder",
                "title": "Analytics Data Missing",
                "description": "Analytics models exist, but there are no SearchMetric rows yet.",
                "severity": "medium",
                "location": "apps/analytics",
                "why": "The code can read analytics data, but no sync has populated it yet.",
                "next_step": "Run the analytics sync before trusting traffic-based ranking signals.",
            }
        )

    orphaned_suggestions = Suggestion.objects.filter(destination__isnull=True).count()
    if orphaned_suggestions > 0:
        conflicts.append(
            {
                "type": "drift",
                "title": "Orphaned Suggestions",
                "description": f"Found {orphaned_suggestions} suggestion row(s) without a destination content item.",
                "severity": "high",
                "location": "apps.suggestions.models.Suggestion",
                "why": "Content was deleted while suggestions were still hanging around.",
                "next_step": "Clean up orphaned suggestions and check the delete flow.",
            }
        )

    if getattr(settings, "HTTP_WORKER_ENABLED", False) and "http-worker:5000" in _http_worker_status_url():
        conflicts.append(
            {
                "type": "mismatch",
                "title": "HttpWorker URL Drift",
                "description": "Diagnostics is still pointed at the old HttpWorker host or port.",
                "severity": "high",
                "location": "apps.diagnostics.health.check_http_worker",
                "why": "The compose service is named http-worker-api on port 8080, so the old URL will always lie.",
                "next_step": "Set HTTP_WORKER_URL to the live http-worker-api base URL.",
            }
        )

    settings_module = os.environ.get("DJANGO_SETTINGS_MODULE", "")
    if settings_module.endswith(".development"):
        conflicts.append(
            {
                "type": "drift",
                "title": "Development Runtime Active",
                "description": "The main Django process is running with development settings.",
                "severity": "medium",
                "location": settings_module,
                "why": "Development mode is fine for local work, but it is not a trustworthy runtime shape for a 16 GB production box.",
                "next_step": "Move the main compose runtime onto production settings before calling the stack production-ready.",
            }
        )

    planned_services = ["ga4", "gsc", "r_analytics", "r_weight_tuning"]
    for service in planned_services:
        snapshot, _ = ServiceStatusSnapshot.objects.get_or_create(service_name=service)
        if snapshot.state == "planned_only":
            conflicts.append(
                {
                    "type": "mismatch",
                    "title": f"Planned Service: {service}",
                    "description": f"{service} is on the roadmap but does not have a live runtime yet.",
                    "severity": "low",
                    "location": f"diagnostics:{service}",
                    "why": "This entry is roadmap tracking, not proof that the service exists.",
                    "next_step": "Do not treat this row as a live dependency until a real runtime is wired in.",
                }
            )

    for conflict in conflicts:
        SystemConflict.objects.get_or_create(
            title=conflict["title"],
            defaults={
                "conflict_type": conflict["type"],
                "description": conflict["description"],
                "severity": conflict["severity"],
                "location": conflict["location"],
                "why": conflict["why"],
                "next_step": conflict["next_step"],
            },
        )

    return conflicts


def get_feature_readinessMatrix():
    """
    Returns a list of features (FR-006 to FR-021) and their readiness state.
    """
    features = [
        {"id": "FR-006", "name": "XenForo import", "status": "verified"},
        {"id": "FR-007", "name": "WordPress import", "status": "implemented"},
        {"id": "FR-008", "name": "Phrase relevance", "status": "implemented"},
        {"id": "FR-009", "name": "Learned anchors", "status": "implemented"},
        {"id": "FR-010", "name": "Rare-term propagation", "status": "implemented"},
        {"id": "FR-011", "name": "Field-aware relevance", "status": "implemented"},
        {"id": "FR-012", "name": "Link freshness", "status": "implemented"},
        {"id": "FR-013", "name": "Node affinity", "status": "implemented"},
        {"id": "FR-014", "name": "Global ranking (PageRank)", "status": "implemented"},
        {"id": "FR-015", "name": "3-stage pipeline", "status": "verified"},
        {"id": "FR-016", "name": "GA4 telemetry", "status": "planned_only"},
        {"id": "FR-017", "name": "GSC attribution", "status": "planned_only"},
        {"id": "FR-018", "name": "Weight tuning", "status": "planned_only"},
        {"id": "FR-019", "name": "Alert delivery", "status": "planned_only"},
        {"id": "FR-020", "name": "Hot swap", "status": "planned_only"},
        {"id": "FR-021", "name": "System health", "status": "implementing"},
    ]
    return features
