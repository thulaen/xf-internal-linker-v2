import logging
import requests
from datetime import timedelta
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, asdict
from django.utils import timezone
from django.conf import settings
from django.db import connections
from django.db.utils import OperationalError

from apps.core.models import AppSetting
from apps.analytics.models import SearchMetric
from apps.notifications.models import OperatorAlert
from apps.notifications.services import emit_operator_alert, resolve_operator_alert
from apps.content.models import ContentItem
from apps.suggestions.models import PipelineRun, Suggestion
from .models import ServiceHealthRecord

logger = logging.getLogger(__name__)

@dataclass
class ServiceHealthResult:
    service_key: str
    status: str
    status_label: str
    last_success_at: Optional[timezone.datetime] = None
    last_error_at: Optional[timezone.datetime] = None
    last_error_message: str = ""
    metadata: Dict[str, Any] = None

    def to_dict(self):
        return asdict(self)

def get_health_setting(key: str, default: Any) -> Any:
    """Helper to fetch health thresholds from AppSetting."""
    try:
        setting = AppSetting.objects.get(key=f"health.{key}")
        if setting.value_type == "int":
            return int(setting.value)
        if setting.value_type == "float":
            return float(setting.value)
        if setting.value_type == "bool":
            return setting.value.lower() in ("true", "1", "yes")
        return setting.value
    except AppSetting.DoesNotExist:
        return default

def check_ga4_health() -> ServiceHealthResult:
    from apps.analytics.ga4_client import build_ga4_data_service, test_ga4_data_api_access
    
    # 1. Check if configured
    property_id = AppSetting.objects.filter(key="analytics.ga4_property_id").first()
    if not property_id or not property_id.value:
        return ServiceHealthResult(
            service_key="ga4",
            status=ServiceHealthRecord.STATUS_NOT_CONFIGURED,
            status_label="GA4 property ID is missing."
        )

    # 2. Test Connection
    try:
        # Fetch credentials from settings
        project_id = AppSetting.objects.filter(key="analytics.google_cloud_project_id").first()
        client_email = AppSetting.objects.filter(key="analytics.google_service_account_email").first()
        private_key = AppSetting.objects.filter(key="analytics.google_service_account_private_key").first()
        
        service = build_ga4_data_service(
            property_id=property_id.value,
            project_id=project_id.value if project_id else "",
            client_email=client_email.value if client_email else "",
            private_key=private_key.value if private_key else ""
        )
        test_ga4_data_api_access(service=service, property_id=property_id.value)
        
        # 3. Check Freshness
        stale_hours = get_health_setting("ga4_stale_threshold_hours", 72)
        latest_metric = SearchMetric.objects.filter(source="ga4").order_by("-date").first()
        
        metadata = {"property_id": property_id.value[-4:].rjust(len(property_id.value), "*")}
        if latest_metric:
            lag_hours = (timezone.now() - timezone.make_aware(timezone.datetime.combine(latest_metric.date, timezone.datetime.min.time()))).total_seconds() / 3600
            metadata["last_data_date"] = latest_metric.date.isoformat()
            metadata["lag_hours"] = round(lag_hours, 1)
            
            if lag_hours > stale_hours:
                return ServiceHealthResult(
                    service_key="ga4",
                    status=ServiceHealthRecord.STATUS_STALE,
                    status_label=f"GA4 data is stale ({round(lag_hours)}h lag).",
                    last_success_at=timezone.now(),
                    metadata=metadata
                )
        
        return ServiceHealthResult(
            service_key="ga4",
            status=ServiceHealthRecord.STATUS_HEALTHY,
            status_label="GA4 is connected and fresh.",
            last_success_at=timezone.now(),
            metadata=metadata
        )
    except Exception as e:
        return ServiceHealthResult(
            service_key="ga4",
            status=ServiceHealthRecord.STATUS_ERROR,
            status_label=f"GA4 connection failed: {str(e)}",
            last_error_at=timezone.now(),
            last_error_message=str(e)
        )

def check_gsc_health() -> ServiceHealthResult:
    from apps.analytics.gsc_client import build_gsc_service, test_gsc_access
    
    # 1. Check if configured
    site_url = AppSetting.objects.filter(key="analytics.gsc_site_url").first()
    if not site_url or not site_url.value:
        return ServiceHealthResult(
            service_key="gsc",
            status=ServiceHealthRecord.STATUS_NOT_CONFIGURED,
            status_label="GSC site URL is missing."
        )

    # 2. Test Connection
    try:
        client_email = AppSetting.objects.filter(key="analytics.google_service_account_email").first()
        private_key = AppSetting.objects.filter(key="analytics.google_service_account_private_key").first()
        
        service = build_gsc_service(
            client_email=client_email.value if client_email else "",
            private_key=private_key.value if private_key else ""
        )
        test_gsc_access(service, site_url.value)
        
        # 3. Check Freshness
        stale_hours = get_health_setting("gsc_stale_threshold_hours", 72)
        latest_metric = SearchMetric.objects.filter(source="gsc").order_by("-date").first()
        
        metadata = {"site_url": site_url.value}
        if latest_metric:
            lag_hours = (timezone.now() - timezone.make_aware(timezone.datetime.combine(latest_metric.date, timezone.datetime.min.time()))).total_seconds() / 3600
            metadata["last_data_date"] = latest_metric.date.isoformat()
            metadata["lag_hours"] = round(lag_hours, 1)
            
            if lag_hours > stale_hours:
                return ServiceHealthResult(
                    service_key="gsc",
                    status=ServiceHealthRecord.STATUS_STALE,
                    status_label=f"GSC data is stale ({round(lag_hours)}h lag).",
                    last_success_at=timezone.now(),
                    metadata=metadata
                )
        
        return ServiceHealthResult(
            service_key="gsc",
            status=ServiceHealthRecord.STATUS_HEALTHY,
            status_label="GSC is connected and fresh.",
            last_success_at=timezone.now(),
            metadata=metadata
        )
    except Exception as e:
        return ServiceHealthResult(
            service_key="gsc",
            status=ServiceHealthRecord.STATUS_ERROR,
            status_label=f"GSC connection failed: {str(e)}",
            last_error_at=timezone.now(),
            last_error_message=str(e)
        )

def check_xenforo_health() -> ServiceHealthResult:
    from apps.sync.services.xenforo_api import XenForoAPIClient
    
    try:
        base_url = getattr(settings, "XENFORO_BASE_URL", "")
        api_key = getattr(settings, "XENFORO_API_KEY", "")
        
        if not base_url or not api_key:
            return ServiceHealthResult(
                service_key="xenforo",
                status=ServiceHealthRecord.STATUS_NOT_CONFIGURED,
                status_label="XenForo API credentials missing."
            )
            
        client = XenForoAPIClient()
        if client.verify_api_key():
            # Check staleness
            stale_hours = get_health_setting("xenforo_stale_threshold_hours", 48)
            latest_sync = ContentItem.objects.filter(content_type__in=['thread', 'post']).order_by("-updated_at").first()
            
            metadata = {"base_url": base_url}
            if latest_sync:
                lag_hours = (timezone.now() - latest_sync.updated_at).total_seconds() / 3600
                metadata["last_sync"] = latest_sync.updated_at.isoformat()
                metadata["lag_hours"] = round(lag_hours, 1)
                
                if lag_hours > stale_hours:
                    return ServiceHealthResult(
                        service_key="xenforo",
                        status=ServiceHealthRecord.STATUS_STALE,
                        status_label=f"XenForo sync is stale ({round(lag_hours)}h lag).",
                        last_success_at=timezone.now(),
                        metadata=metadata
                    )
            
            return ServiceHealthResult(
                service_key="xenforo",
                status=ServiceHealthRecord.STATUS_HEALTHY,
                status_label="XenForo API connected and syncing.",
                last_success_at=timezone.now(),
                metadata=metadata
            )
        else:
            return ServiceHealthResult(
                service_key="xenforo",
                status=ServiceHealthRecord.STATUS_ERROR,
                status_label="XenForo API key verification failed.",
                last_error_at=timezone.now()
            )
    except Exception as e:
        return ServiceHealthResult(
            service_key="xenforo",
            status=ServiceHealthRecord.STATUS_ERROR,
            status_label=f"XenForo check failed: {str(e)}",
            last_error_at=timezone.now(),
            last_error_message=str(e)
        )

def check_wordpress_health() -> ServiceHealthResult:
    from apps.sync.services.wordpress_api import WordPressAPIClient
    
    try:
        base_url = getattr(settings, "WORDPRESS_BASE_URL", "")
        if not base_url:
            return ServiceHealthResult(
                service_key="wordpress",
                status=ServiceHealthRecord.STATUS_NOT_CONFIGURED,
                status_label="WordPress URL missing."
            )
            
        client = WordPressAPIClient()
        # WordPress doesn't have a simple verify. Try fetching 1 post.
        client.get_posts(page=1)
        
        # Check staleness
        stale_hours = get_health_setting("wordpress_stale_threshold_hours", 48)
        latest_sync = ContentItem.objects.filter(content_type__in=['wp_post', 'wp_page']).order_by("-updated_at").first()
        
        metadata = {"base_url": base_url}
        if latest_sync:
            lag_hours = (timezone.now() - latest_sync.updated_at).total_seconds() / 3600
            metadata["last_sync"] = latest_sync.updated_at.isoformat()
            metadata["lag_hours"] = round(lag_hours, 1)
            
            if lag_hours > stale_hours:
                return ServiceHealthResult(
                    service_key="wordpress",
                    status=ServiceHealthRecord.STATUS_STALE,
                    status_label=f"WordPress sync is stale ({round(lag_hours)}h lag).",
                    last_success_at=timezone.now(),
                    metadata=metadata
                )
        
        return ServiceHealthResult(
            service_key="wordpress",
            status=ServiceHealthRecord.STATUS_HEALTHY,
            status_label="WordPress API connected and syncing.",
            last_success_at=timezone.now(),
            metadata=metadata
        )
    except Exception as e:
        return ServiceHealthResult(
            service_key="wordpress",
            status=ServiceHealthRecord.STATUS_ERROR,
            status_label=f"WordPress check failed: {str(e)}",
            last_error_at=timezone.now(),
            last_error_message=str(e)
        )

def check_http_worker_health() -> ServiceHealthResult:
    try:
        url = settings.HTTP_WORKER_URL
        if not url:
            return ServiceHealthResult(
                service_key="http_worker",
                status=ServiceHealthRecord.STATUS_NOT_CONFIGURED,
                status_label="HttpWorker URL is not configured."
            )
            
        health_url = f"{url}/api/v1/health/check"
        response = requests.post(health_url, json={}, timeout=5)
        response.raise_for_status()
        data = response.json()
        
        return ServiceHealthResult(
            service_key="http_worker",
            status=ServiceHealthRecord.STATUS_HEALTHY,
            status_label="HttpWorker Service is running.",
            last_success_at=timezone.now(),
            metadata={"version": data.get("version", "unknown"), "url": url}
        )
    except Exception as e:
        return ServiceHealthResult(
            service_key="http_worker",
            status=ServiceHealthRecord.STATUS_DOWN,
            status_label=f"HttpWorker Service is unreachable: {str(e)}",
            last_error_at=timezone.now(),
            last_error_message=str(e)
        )

def check_celery_health() -> ServiceHealthResult:
    from config.celery import app as celery_app
    try:
        insp = celery_app.control.inspect()
        active = insp.active()
        if active is None or not active:
            return ServiceHealthResult(
                service_key="celery",
                status=ServiceHealthRecord.STATUS_DOWN,
                status_label="No active Celery workers found.",
                last_error_at=timezone.now()
            )
            
        worker_count = len(active)
        # Check queue depth (requires redis client access directly usually, or just assume ok if workers active)
        # For simplicity, we'll just check worker count here.
        
        return ServiceHealthResult(
            service_key="celery",
            status=ServiceHealthRecord.STATUS_HEALTHY,
            status_label=f"Celery is running with {worker_count} active workers.",
            last_success_at=timezone.now(),
            metadata={"worker_count": worker_count}
        )
    except Exception as e:
        return ServiceHealthResult(
            service_key="celery",
            status=ServiceHealthRecord.STATUS_ERROR,
            status_label=f"Celery check failed: {str(e)}",
            last_error_at=timezone.now(),
            last_error_message=str(e)
        )

def check_database_health() -> ServiceHealthResult:
    try:
        connections['default'].cursor()
        return ServiceHealthResult(
            service_key="database",
            status=ServiceHealthRecord.STATUS_HEALTHY,
            status_label="Database connection is healthy.",
            last_success_at=timezone.now()
        )
    except OperationalError as e:
        return ServiceHealthResult(
            service_key="database",
            status=ServiceHealthRecord.STATUS_DOWN,
            status_label=f"Database connection failed: {str(e)}",
            last_error_at=timezone.now(),
            last_error_message=str(e)
        )

def check_redis_health() -> ServiceHealthResult:
    try:
        import redis
        r = redis.from_url(settings.REDIS_URL)
        r.ping()
        return ServiceHealthResult(
            service_key="redis",
            status=ServiceHealthRecord.STATUS_HEALTHY,
            status_label="Redis is reachable.",
            last_success_at=timezone.now()
        )
    except Exception as e:
        return ServiceHealthResult(
            service_key="redis",
            status=ServiceHealthRecord.STATUS_DOWN,
            status_label=f"Redis connection failed: {str(e)}",
            last_error_at=timezone.now(),
            last_error_message=str(e)
        )

def check_pipeline_health() -> ServiceHealthResult:
    try:
        latest_run = PipelineRun.objects.order_by("-created_at").first()
        if not latest_run:
            return ServiceHealthResult(
                service_key="pipeline",
                status=ServiceHealthRecord.STATUS_NOT_CONFIGURED,
                status_label="No pipeline runs recorded yet."
            )
            
        if latest_run.status == "failed":
            return ServiceHealthResult(
                service_key="pipeline",
                status=ServiceHealthRecord.STATUS_ERROR,
                status_label=f"Last pipeline run failed: {latest_run.error_message[:100]}",
                last_error_at=latest_run.created_at,
                last_error_message=latest_run.error_message
            )
            
        # Check for sudden drop in suggestions
        drop_threshold = get_health_setting("pipeline_suggestion_drop_threshold_pct", 30)
        previous_runs = PipelineRun.objects.filter(status="completed").order_by("-created_at")[1:6]
        if previous_runs:
            avg_count = sum(r.suggestion_count for r in previous_runs) / len(previous_runs)
            if avg_count > 0:
                drop_pct = (avg_count - latest_run.suggestion_count) / avg_count * 100
                if drop_pct > drop_threshold:
                    return ServiceHealthResult(
                        service_key="pipeline",
                        status=ServiceHealthRecord.STATUS_WARNING,
                        status_label=f"Pipeline suggestion count dropped by {round(drop_pct)}% vs average.",
                        last_success_at=latest_run.created_at,
                        metadata={"current_count": latest_run.suggestion_count, "avg_count": round(avg_count)}
                    )
                    
        return ServiceHealthResult(
            service_key="pipeline",
            status=ServiceHealthRecord.STATUS_HEALTHY,
            status_label="Algorithm pipeline is healthy.",
            last_success_at=latest_run.created_at,
            metadata={"last_run_count": latest_run.suggestion_count}
        )
    except Exception as e:
        return ServiceHealthResult(
            service_key="pipeline",
            status=ServiceHealthRecord.STATUS_ERROR,
            status_label=f"Pipeline health check failed: {str(e)}",
            last_error_at=timezone.now(),
            last_error_message=str(e)
        )

def check_matomo_health() -> ServiceHealthResult:
    # 1. Check if configured
    matomo_enabled = AppSetting.objects.filter(key="analytics.matomo_enabled").first()
    if not matomo_enabled or matomo_enabled.value.lower() not in ("true", "1", "yes"):
        return ServiceHealthResult(
            service_key="matomo",
            status=ServiceHealthRecord.STATUS_NOT_ENABLED,
            status_label="Matomo tracking is disabled."
        )

    matomo_url = AppSetting.objects.filter(key="analytics.matomo_url").first()
    matomo_token = AppSetting.objects.filter(key="analytics.matomo_api_token").first()
    
    if not matomo_url or not matomo_url.value:
        return ServiceHealthResult(
            service_key="matomo",
            status=ServiceHealthRecord.STATUS_NOT_CONFIGURED,
            status_label="Matomo URL is missing."
        )

    try:
        # Test connection (simple API call to get site info)
        site_id = AppSetting.objects.filter(key="analytics.matomo_site_id").first()
        site_id_val = site_id.value if site_id else "1"
        ping_url = f"{matomo_url.value.rstrip('/')}/index.php?module=API&method=SitesManager.getSiteFromId&idSite={site_id_val}&format=JSON&token_auth={matomo_token.value if matomo_token else ''}"
        
        response = requests.get(ping_url, timeout=5)
        response.raise_for_status()
        
        # Check for data staleness (if possible via telemetry models, but let's stick to connectivity for now)
        return ServiceHealthResult(
            service_key="matomo",
            status=ServiceHealthRecord.STATUS_HEALTHY,
            status_label="Matomo is connected.",
            last_success_at=timezone.now(),
            metadata={"url": matomo_url.value}
        )
    except Exception as e:
        return ServiceHealthResult(
            service_key="matomo",
            status=ServiceHealthRecord.STATUS_ERROR,
            status_label=f"Matomo connection failed: {str(e)}",
            last_error_at=timezone.now(),
            last_error_message=str(e)
        )

# Mapping of service keys to checker functions
CHECKERS = {
    "ga4": check_ga4_health,
    "gsc": check_gsc_health,
    "xenforo": check_xenforo_health,
    "wordpress": check_wordpress_health,
    "http_worker": check_http_worker_health,
    "celery": check_celery_health,
    "database": check_database_health,
    "redis": check_redis_health,
    "pipeline": check_pipeline_health,
    "matomo": check_matomo_health,
}

def perform_health_check(service_key: str) -> ServiceHealthRecord:
    """Run a single health check and update its record."""
    checker = CHECKERS.get(service_key)
    if not checker:
        raise ValueError(f"No health checker found for service: {service_key}")
        
    result = checker()
    record, _ = ServiceHealthRecord.objects.get_or_create(
        service_key=service_key,
        defaults={'last_check_at': timezone.now()}
    )
    
    # Update fields
    record.status = result.status
    record.status_label = result.status_label
    record.last_check_at = timezone.now()
    if result.last_success_at:
        record.last_success_at = result.last_success_at
    if result.last_error_at:
        record.last_error_at = result.last_error_at
    if result.last_error_message:
        record.last_error_message = result.last_error_message
    if result.metadata:
        record.metadata = result.metadata
        
    record.save()
    
    # Alert management
    dedupe_key = f"health.{service_key}"
    if result.status in (ServiceHealthRecord.STATUS_ERROR, ServiceHealthRecord.STATUS_DOWN, ServiceHealthRecord.STATUS_STALE):
        severity = OperatorAlert.SEVERITY_ERROR if result.status == ServiceHealthRecord.STATUS_DOWN else OperatorAlert.SEVERITY_WARNING
        emit_operator_alert(
            event_type=f"health.{service_key}.degraded",
            severity=severity,
            title=f"System Health: {service_key.upper()} Degraded",
            message=result.status_label,
            dedupe_key=dedupe_key,
            source_area="system",
            related_route="/health"
        )
    elif result.status == ServiceHealthRecord.STATUS_HEALTHY:
        resolve_operator_alert(dedupe_key)
        
    return record
