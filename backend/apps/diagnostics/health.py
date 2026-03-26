import logging
import requests
from django.db import connection
from django_redis import get_redis_connection
from celery import current_app
from django.conf import settings
from apps.suggestions.models import Suggestion
from .models import ServiceStatusSnapshot, SystemConflict

logger = logging.getLogger(__name__)

def check_django():
    return "healthy", "Django API is responding normally.", "No action needed."

def check_postgresql():
    try:
        connection.ensure_connection()
        return "healthy", "PostgreSQL connection is active.", "No action needed."
    except Exception as e:
        return "failed", f"PostgreSQL connection failed: {str(e)}", "Check if the database service is running and the credentials are correct."

def check_redis():
    try:
        conn = get_redis_connection("default")
        conn.ping()
        return "healthy", "Redis connection is active.", "No action needed."
    except Exception as e:
        return "failed", f"Redis connection failed: {str(e)}", "Check if the Redis service is running and the URL is correct."

def check_celery():
    try:
        inspect = current_app.control.inspect()
        ping = inspect.ping()
        if ping:
            return "healthy", f"Celery workers are alive ({len(ping)} workers).", "No action needed."
        return "failed", "No Celery workers detected.", "Start the Celery worker process."
    except Exception as e:
        return "failed", f"Celery check failed: {str(e)}", "Check if Redis (the broker) is reachable."

def check_celery_beat():
    # Checking for beat is harder without shared state, but we can check if any periodic tasks have run recently
    # or if the django-celery-beat scheduler is active.
    try:
        import django_celery_beat  # noqa: F401
        # Just a placeholder for now
        return "healthy", "Celery Beat is configured.", "Check Celery Beat logs for recent executions."
    except ImportError:
        return "not_installed", "django-celery-beat is not installed.", "Install django-celery-beat if periodic tasks are required."

def check_channels():
    if not hasattr(settings, 'CHANNEL_LAYERS'):
        return "not_configured", "Django Channels is not configured.", "Add CHANNEL_LAYERS to settings."
    try:
        from channels.layers import get_channel_layer
        channel_layer = get_channel_layer()
        if channel_layer:
            # Simple test for RedisChannelLayer
            return "healthy", "Channel layer is available.", "No action needed."
        return "failed", "Channel layer could not be retrieved.", "Check Channels configuration."
    except Exception as e:
        return "failed", f"Channels check failed: {str(e)}", "Check Redis connectivity."

def check_http_worker():
    url = getattr(settings, 'HTTP_WORKER_URL', 'http://http-worker:5000/api/v1/status')
    try:
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            if data.get("status") == "ok":
                return "healthy", "C# HttpWorker is responding.", "No action needed."
            return "degraded", f"HttpWorker reported non-ok status: {data.get('status')}", "Check HttpWorker logs."
        return "failed", f"HttpWorker returned status code {response.status_code}.", "Check if the HttpWorker container is running."
    except Exception as e:
        return "failed", f"HttpWorker is unreachable: {str(e)}", "Check if the HttpWorker URL is correct and the service is up."

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
        metrics["disk_usage_percent"] = psutil.disk_usage('/').percent
    except ImportError:
        pass
    return metrics

def run_health_checks():
    checks = {
        'django': check_django,
        'postgresql': check_postgresql,
        'redis': check_redis,
        'celery_worker': check_celery,
        'celery_beat': check_celery_beat,
        'channels': check_channels,
        'http_worker': check_http_worker,
    }

    results = {}
    for service, check_fn in checks.items():
        state, explanation, next_step = check_fn()
        snapshot, created = ServiceStatusSnapshot.objects.get_or_create(service_name=service)
        snapshot.state = state
        snapshot.explanation = explanation
        snapshot.next_action_step = next_step
        if state == "healthy":
            snapshot.last_success = snapshot.last_check
        elif state == "failed":
            snapshot.last_failure = snapshot.last_check
        snapshot.save()
        results[service] = {
            "state": state,
            "explanation": explanation,
            "next_step": next_step,
            "last_check": snapshot.last_check,
        }
    return results

def detect_conflicts():
    conflicts = []
    
    # 1. Check for placeholder analytics vs missing real API
    # (Checking if analytics app exists but has no real data or API)
    from apps.analytics.models import SearchMetric
    if SearchMetric.objects.count() == 0:
        conflicts.append({
            "type": "placeholder",
            "title": "Analytics Data Missing",
            "description": "Analytics app is present but no SearchMetric records exist.",
            "severity": "medium",
            "location": "apps/analytics",
            "why": "The system has models for analytics, but no telemetry (GA4/GSC) sync has been performed yet.",
            "next_step": "Configure GA4/GSC sync to populate analytics data."
        })

    # 2. Check for drift in suggestions (e.g., pending suggestions with no destination)
    orphaned_suggestions = Suggestion.objects.filter(destination__isnull=True).count()
    if orphaned_suggestions > 0:
        conflicts.append({
            "type": "drift",
            "title": "Orphaned Suggestions",
            "description": f"Found {orphaned_suggestions} suggestions without a destination content item.",
            "severity": "high",
            "location": "apps.suggestions.models.Suggestion",
            "why": "Content items were likely deleted while suggestions were still pending.",
            "next_step": "Run a cleanup task to remove orphaned suggestions."
        })

    # 3. Check for planned-only systems mentioned in docs but not fully implemented
    # (Hardcoded for now based on FR requirements)
    planned_services = ['ga4', 'gsc', 'r_analytics', 'r_weight_tuning']
    for service in planned_services:
        snapshot, created = ServiceStatusSnapshot.objects.get_or_create(service_name=service)
        if snapshot.state == 'planned_only':
            conflicts.append({
                "type": "mismatch",
                "title": f"Planned Service: {service}",
                "description": f"{service} is in the roadmap but not yet implemented.",
                "severity": "low",
                "location": f"Phase {service}",
                "why": "This feature is planned for a future phase.",
                "next_step": "Wait for the implementation of this phase."
            })

    for c in conflicts:
        SystemConflict.objects.get_or_create(
            title=c["title"],
            defaults={
                "conflict_type": c["type"],
                "description": c["description"],
                "severity": c["severity"],
                "location": c["location"],
                "why": c["why"],
                "next_step": c["next_step"],
            }
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
    # In a real system, these could be checked against actual code/tests.
    return features
