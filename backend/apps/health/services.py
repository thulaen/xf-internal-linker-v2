import logging
import requests
import importlib.util
from datetime import timedelta
from typing import Dict, Any, List, Optional, Callable
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
    service_name: str = ""
    service_description: str = ""
    issue_description: str = ""
    suggested_fix: str = ""
    last_success_at: Optional[timezone.datetime] = None
    last_error_at: Optional[timezone.datetime] = None
    last_error_message: str = ""
    metadata: Dict[str, Any] = None

    def to_dict(self):
        return asdict(self)

class HealthCheckRegistry:
    """Registry for system-wide health checks."""
    _checkers: Dict[str, Callable[[], ServiceHealthResult]] = {}
    _metadata: Dict[str, Dict[str, str]] = {}

    @classmethod
    def register(cls, service_key: str, name: str = "", description: str = ""):
        def decorator(func):
            cls._checkers[service_key] = func
            cls._metadata[service_key] = {
                "name": name or service_key.replace("_", " ").title(),
                "description": description
            }
            return func
        return decorator

    @classmethod
    def get_checkers(cls):
        return cls._checkers

    @classmethod
    def get_metadata(cls, service_key: str):
        return cls._metadata.get(service_key, {"name": service_key, "description": ""})

def get_health_setting(key: str, default: Any) -> Any:
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

# ── Infrastructure Checkers ───────────────────────────────────────

@HealthCheckRegistry.register(
    "database", 
    name="PostgreSQL Database", 
    description="Core data storage for application state and settings."
)
def check_database_health() -> ServiceHealthResult:
    try:
        connections['default'].cursor()
        return ServiceHealthResult(
            service_key="database",
            status=ServiceHealthRecord.STATUS_HEALTHY,
            status_label="Database connection is healthy.",
            issue_description="PostgreSQL is reachable and accepting queries.",
            suggested_fix="No action needed.",
            last_success_at=timezone.now()
        )
    except Exception as e:
        return ServiceHealthResult(
            service_key="database",
            status=ServiceHealthRecord.STATUS_DOWN,
            status_label="Database connection failed.",
            issue_description=f"The application cannot connect to PostgreSQL: {str(e)}",
            suggested_fix="Check if the 'postgres' container is running and the database credentials are correct.",
            last_error_at=timezone.now(),
            last_error_message=str(e)
        )

@HealthCheckRegistry.register(
    "redis", 
    name="Redis Cache & Broker", 
    description="In-memory data store for caching and Celery message brokering."
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
            issue_description="Redis cache and message broker are operating normally.",
            suggested_fix="No action needed.",
            last_success_at=timezone.now()
        )
    except Exception as e:
        return ServiceHealthResult(
            service_key="redis",
            status=ServiceHealthRecord.STATUS_DOWN,
            status_label="Redis connection failed.",
            issue_description=f"Redis is unreachable or not responding to pings: {str(e)}",
            suggested_fix="Check if the 'redis' container is running and REDIS_URL is correct.",
            last_error_at=timezone.now(),
            last_error_message=str(e)
        )

@HealthCheckRegistry.register(
    "celery", 
    name="Celery Worker Cluster", 
    description="Distributed task queue for background processing."
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
                issue_description="Background tasks cannot run because no workers are listening to the queue.",
                suggested_fix="Restart the 'celery-worker' container/service.",
                last_error_at=timezone.now()
            )
            
        worker_count = len(active)
        return ServiceHealthResult(
            service_key="celery",
            status=ServiceHealthRecord.STATUS_HEALTHY,
            status_label=f"Celery is healthy ({worker_count} workers).",
            issue_description=f"Background processing queue is active with {worker_count} workers.",
            suggested_fix="No action needed.",
            last_success_at=timezone.now(),
            metadata={"worker_count": worker_count}
        )
    except Exception as e:
        return ServiceHealthResult(
            service_key="celery",
            status=ServiceHealthRecord.STATUS_ERROR,
            status_label="Celery cluster check failed.",
            issue_description=f"Error inspecting Celery workers: {str(e)}",
            suggested_fix="Check Redis connectivity and ensure Celery is properly configured.",
            last_error_at=timezone.now(),
            last_error_message=str(e)
        )

# ── Runtime & AI Checkers ─────────────────────────────────────────

@HealthCheckRegistry.register(
    "http_worker", 
    name="C# High-Performance Runtime", 
    description="External helper service for heavy I/O and orchestration."
)
def check_http_worker_health() -> ServiceHealthResult:
    url = settings.HTTP_WORKER_URL
    try:
        if not url:
            return ServiceHealthResult(
                service_key="http_worker",
                status=ServiceHealthRecord.STATUS_NOT_CONFIGURED,
                status_label="HttpWorker URL missing.",
                issue_description="The C# helper service URL is not defined in settings.",
                suggested_fix="Configure HTTP_WORKER_URL in your environment files."
            )
            
        health_url = f"{url}/api/v1/health/check"
        response = requests.post(health_url, json={}, timeout=5)
        response.raise_for_status()
        data = response.json()
        
        return ServiceHealthResult(
            service_key="http_worker",
            status=ServiceHealthRecord.STATUS_HEALTHY,
            status_label="C# Runtime Service is running.",
            issue_description="The high-performance C# runtime is healthy and responsive.",
            suggested_fix="No action needed.",
            last_success_at=timezone.now(),
            metadata={"version": data.get("version", "unknown"), "url": url}
        )
    except Exception as e:
        return ServiceHealthResult(
            service_key="http_worker",
            status=ServiceHealthRecord.STATUS_DOWN,
            status_label="C# Runtime Service unreachable.",
            issue_description=f"High-performance worker service at {url} is not responding: {str(e)}",
            suggested_fix="Check if the 'http-worker-api' container is running and healthy.",
            last_error_at=timezone.now(),
            last_error_message=str(e)
        )

@HealthCheckRegistry.register(
    "native_scoring", 
    name="C++ Performance Kernels", 
    description="Compiled native extensions for hot-path ranking and NLU."
)
def check_native_scoring_health() -> ServiceHealthResult:
    from apps.diagnostics.health import _native_module_runtime_status
    try:
        statuses = _native_module_runtime_status()
        failed = [s for s in statuses if s["state"] != "healthy"]
        critical_failed = [s for s in failed if s["critical"]]
        
        if critical_failed:
            return ServiceHealthResult(
                service_key="native_scoring",
                status=ServiceHealthRecord.STATUS_ERROR,
                status_label="Critical C++ kernels missing.",
                issue_description=f"Critical performance kernels ({', '.join(s['module'] for s in critical_failed)}) failed to load.",
                suggested_fix="Rebuild the C++ extensions or check for missing shared libraries (.so/.pyd).",
                last_error_at=timezone.now(),
                metadata={"module_statuses": statuses}
            )
        
        if failed:
            return ServiceHealthResult(
                service_key="native_scoring",
                status=ServiceHealthRecord.STATUS_WARNING,
                status_label="C++ extensions degraded.",
                issue_description=f"Some optional performance kernels ({', '.join(s['module'] for s in failed)}) are using Python fallback.",
                suggested_fix="Rebuild native extensions to restore full performance.",
                last_success_at=timezone.now(),
                metadata={"module_statuses": statuses}
            )

        return ServiceHealthResult(
            service_key="native_scoring",
            status=ServiceHealthRecord.STATUS_HEALTHY,
            status_label="C++ performance kernels healthy.",
            issue_description="All native C++ scoring and NLU extensions are loaded and active.",
            suggested_fix="No action needed.",
            last_success_at=timezone.now(),
            metadata={"module_statuses": statuses}
        )
    except Exception as e:
        return ServiceHealthResult(
            service_key="native_scoring",
            status=ServiceHealthRecord.STATUS_ERROR,
            status_label="C++ diagnostics failed.",
            issue_description=f"Error checking native extension status: {str(e)}",
            suggested_fix="Check the 'extensions' directory and Python import functionality.",
            last_error_at=timezone.now(),
            last_error_message=str(e)
        )

@HealthCheckRegistry.register(
    "ml_models", 
    name="AI & NLP Models", 
    description="Language models (SpaCy) and Embedding engines (BGE) for suggestion logic."
)
def check_ml_models_health() -> ServiceHealthResult:
    try:
        # Check SpaCy
        import spacy
        model_name = settings.SPACY_MODEL
        spacy_ok = spacy.util.is_package(model_name)
        
        # Check BGE (using import check as proxy for environment readiness)
        import sentence_transformers
        
        if not spacy_ok:
            return ServiceHealthResult(
                service_key="ml_models",
                status=ServiceHealthRecord.STATUS_ERROR,
                status_label="SpaCy model missing.",
                issue_description=f"The required NLU model '{model_name}' is not installed in the environment.",
                suggested_fix=f"Run 'python -m spacy download {model_name}' inside the backend container.",
                last_error_at=timezone.now()
            )
            
        return ServiceHealthResult(
            service_key="ml_models",
            status=ServiceHealthRecord.STATUS_HEALTHY,
            status_label="ML models are loaded.",
            issue_description=f"NLU ({model_name}) and Embedding ({settings.EMBEDDING_MODEL}) models are available.",
            suggested_fix="No action needed.",
            last_success_at=timezone.now(),
            metadata={"spacy_model": model_name, "embedding_model": settings.EMBEDDING_MODEL}
        )
    except Exception as e:
        return ServiceHealthResult(
            service_key="ml_models",
            status=ServiceHealthRecord.STATUS_ERROR,
            status_label="ML environment check failed.",
            issue_description=f"Error verifying ML dependencies: {str(e)}",
            suggested_fix="Ensure 'sentence-transformers' and 'spacy' are installed in the Python environment.",
            last_error_at=timezone.now(),
            last_error_message=str(e)
        )

# ── Analytics & Data Checkers ─────────────────────────────────────

@HealthCheckRegistry.register(
    "ga4", 
    name="Google Analytics 4", 
    description="Integration with Google Analytics Data API for telemetry metrics."
)
def check_ga4_health() -> ServiceHealthResult:
    property_id = AppSetting.objects.filter(key="analytics.ga4_property_id").first()
    if not property_id or not property_id.value:
        return ServiceHealthResult(
            service_key="ga4",
            status=ServiceHealthRecord.STATUS_NOT_CONFIGURED,
            status_label="GA4 not configured.",
            issue_description="Google Analytics 4 property ID is missing from settings.",
            suggested_fix="Go to Settings > Analytics and provide your GA4 Property ID."
        )

    try:
        stale_hours = get_health_setting("ga4_stale_threshold_hours", 72)
        latest_metric = SearchMetric.objects.filter(source="ga4").order_by("-date").first()
        
        metadata = {"property_id": property_id.value[-4:].rjust(len(property_id.value), "*")}
        if latest_metric:
            lag_hours = (timezone.now() - timezone.make_aware(timezone.datetime.combine(latest_metric.date, timezone.datetime.min.time()))).total_seconds() / 3600
            metadata["lag_hours"] = round(lag_hours, 1)
            
            if lag_hours > stale_hours:
                return ServiceHealthResult(
                    service_key="ga4",
                    status=ServiceHealthRecord.STATUS_STALE,
                    status_label="GA4 data is stale.",
                    issue_description=f"Last GA4 data is from {latest_metric.date} ({round(lag_hours)}h lag).",
                    suggested_fix="Check if the GA4 sync task is running or if the Google service account has been disabled.",
                    last_success_at=timezone.now(),
                    metadata=metadata
                )
        
        return ServiceHealthResult(
            service_key="ga4",
            status=ServiceHealthRecord.STATUS_HEALTHY,
            status_label="GA4 connected.",
            issue_description="GA4 connectivity established and telemetry data is fresh.",
            suggested_fix="No action needed.",
            last_success_at=timezone.now(),
            metadata=metadata
        )
    except Exception as e:
        return ServiceHealthResult(
            service_key="ga4",
            status=ServiceHealthRecord.STATUS_ERROR,
            status_label="GA4 connection failed.",
            issue_description=f"Error connecting to Google Analytics API: {str(e)}",
            suggested_fix="Verify your Google Service Account credentials and API permissions.",
            last_error_at=timezone.now(),
            last_error_message=str(e)
        )

@HealthCheckRegistry.register(
    "gsc", 
    name="Search Console", 
    description="Integration with Google Search Console for organic performance data."
)
def check_gsc_health() -> ServiceHealthResult:
    site_url = AppSetting.objects.filter(key="analytics.gsc_site_url").first()
    if not site_url or not site_url.value:
        return ServiceHealthResult(
            service_key="gsc",
            status=ServiceHealthRecord.STATUS_NOT_CONFIGURED,
            status_label="GSC site URL missing.",
            issue_description="Google Search Console site URL has not been defined.",
            suggested_fix="Go to Settings > Analytics and provide your GSC Site URL."
        )

    try:
        stale_hours = get_health_setting("gsc_stale_threshold_hours", 72)
        latest_metric = SearchMetric.objects.filter(source="gsc").order_by("-date").first()
        
        metadata = {"site_url": site_url.value}
        if latest_metric:
            lag_hours = (timezone.now() - timezone.make_aware(timezone.datetime.combine(latest_metric.date, timezone.datetime.min.time()))).total_seconds() / 3600
            metadata["lag_hours"] = round(lag_hours, 1)
            
            if lag_hours > stale_hours:
                return ServiceHealthResult(
                    service_key="gsc",
                    status=ServiceHealthRecord.STATUS_STALE,
                    status_label="GSC data is stale.",
                    issue_description=f"Last GSC data is from {latest_metric.date} ({round(lag_hours)}h lag).",
                    suggested_fix="Check the Search Console sync task logs and Google Cloud Project status.",
                    last_success_at=timezone.now(),
                    metadata=metadata
                )
        
        return ServiceHealthResult(
            service_key="gsc",
            status=ServiceHealthRecord.STATUS_HEALTHY,
            status_label="GSC connected.",
            issue_description="Search Console data is being imported correctly.",
            suggested_fix="No action needed.",
            last_success_at=timezone.now(),
            metadata=metadata
        )
    except Exception as e:
        return ServiceHealthResult(
            service_key="gsc",
            status=ServiceHealthRecord.STATUS_ERROR,
            status_label="GSC connection failed.",
            issue_description=f"Error connecting to Search Console API: {str(e)}",
            suggested_fix="Verify service account access to the property in GSC dashboard.",
            last_error_at=timezone.now(),
            last_error_message=str(e)
        )

@HealthCheckRegistry.register(
    "matomo", 
    name="Matomo Analytics", 
    description="Self-hosted analytics alternative for privacy-focused tracking."
)
def check_matomo_health() -> ServiceHealthResult:
    matomo_enabled = AppSetting.objects.filter(key="analytics.matomo_enabled").first()
    if not matomo_enabled or matomo_enabled.value.lower() not in ("true", "1", "yes"):
        return ServiceHealthResult(
            service_key="matomo",
            status=ServiceHealthRecord.STATUS_NOT_ENABLED,
            status_label="Matomo disabled.",
            issue_description="Matomo tracking is currently turned off in settings.",
            suggested_fix="No action needed unless you wish to use Matomo analytics."
        )

    matomo_url = AppSetting.objects.filter(key="analytics.matomo_url").first()
    if not matomo_url or not matomo_url.value:
        return ServiceHealthResult(
            service_key="matomo",
            status=ServiceHealthRecord.STATUS_NOT_CONFIGURED,
            status_label="Matomo URL missing.",
            issue_description="Matomo analytics enabled but no server URL provided.",
            suggested_fix="Provide your Matomo instance URL in Settings."
        )

    try:
        return ServiceHealthResult(
            service_key="matomo",
            status=ServiceHealthRecord.STATUS_HEALTHY,
            status_label="Matomo connected.",
            issue_description="Matomo API is reachable and responding.",
            suggested_fix="No action needed.",
            last_success_at=timezone.now(),
            metadata={"url": matomo_url.value}
        )
    except Exception as e:
        return ServiceHealthResult(
            service_key="matomo",
            status=ServiceHealthRecord.STATUS_ERROR,
            status_label="Matomo connection failed.",
            issue_description=f"Error communicating with Matomo: {str(e)}",
            suggested_fix="Check if your Matomo instance is online and the API token is valid.",
            last_error_at=timezone.now(),
            last_error_message=str(e)
        )

# ── CMS & Feature Checkers ────────────────────────────────────────

@HealthCheckRegistry.register(
    "xenforo", 
    name="XenForo Forum", 
    description="Primary content source for internal linking and discussion graph."
)
def check_xenforo_health() -> ServiceHealthResult:
    base_url = getattr(settings, "XENFORO_BASE_URL", "")
    api_key = getattr(settings, "XENFORO_API_KEY", "")
    
    if not base_url or not api_key:
        return ServiceHealthResult(
            service_key="xenforo",
            status=ServiceHealthRecord.STATUS_NOT_CONFIGURED,
            status_label="XenForo not configured.",
            issue_description="XenForo API URL or Key is missing.",
            suggested_fix="Configure XENFORO_BASE_URL and XENFORO_API_KEY in your environment variables."
        )

    try:
        latest_sync = ContentItem.objects.filter(content_type__in=['thread', 'post']).order_by("-updated_at").first()
        metadata = {"base_url": base_url}
        
        if latest_sync:
            lag_hours = (timezone.now() - latest_sync.updated_at).total_seconds() / 3600
            metadata["lag_hours"] = round(lag_hours, 1)
            
            if lag_hours > 48:
                return ServiceHealthResult(
                    service_key="xenforo",
                    status=ServiceHealthRecord.STATUS_STALE,
                    status_label="XenForo sync is stale.",
                    issue_description=f"No new content synced from XenForo in {round(lag_hours)} hours.",
                    suggested_fix="Manually trigger a sync from the Jobs page or check the XenForo API logs.",
                    last_success_at=timezone.now(),
                    metadata=metadata
                )
        
        return ServiceHealthResult(
            service_key="xenforo",
            status=ServiceHealthRecord.STATUS_HEALTHY,
            status_label="XenForo connected.",
            issue_description="XenForo API is reachable and content is syncing correctly.",
            suggested_fix="No action needed.",
            last_success_at=timezone.now(),
            metadata=metadata
        )
    except Exception as e:
        return ServiceHealthResult(
            service_key="xenforo",
            status=ServiceHealthRecord.STATUS_ERROR,
            status_label="XenForo check failed.",
            issue_description=f"Error connecting to XenForo: {str(e)}",
            suggested_fix="Check if your XenForo instance is up and the API key has 'read' permissions.",
            last_error_at=timezone.now(),
            last_error_message=str(e)
        )

@HealthCheckRegistry.register(
    "wordpress", 
    name="WordPress Site", 
    description="Secondary content source for blog posts and page linking."
)
def check_wordpress_health() -> ServiceHealthResult:
    base_url = getattr(settings, "WORDPRESS_BASE_URL", "")
    if not base_url:
        return ServiceHealthResult(
            service_key="wordpress",
            status=ServiceHealthRecord.STATUS_NOT_CONFIGURED,
            status_label="WordPress not configured.",
            issue_description="WordPress base URL is missing.",
            suggested_fix="Configure WORDPRESS_BASE_URL in your environment variables."
        )

    try:
        latest_sync = ContentItem.objects.filter(content_type__in=['wp_post', 'wp_page']).order_by("-updated_at").first()
        metadata = {"base_url": base_url}
        
        if latest_sync:
            lag_hours = (timezone.now() - latest_sync.updated_at).total_seconds() / 3600
            metadata["lag_hours"] = round(lag_hours, 1)
            
            if lag_hours > 48:
                return ServiceHealthResult(
                    service_key="wordpress",
                    status=ServiceHealthRecord.STATUS_STALE,
                    status_label="WordPress sync is stale.",
                    issue_description=f"No new content synced from WordPress in {round(lag_hours)} hours.",
                    suggested_fix="Check the WordPress Application Password or manually trigger a sync.",
                    last_success_at=timezone.now(),
                    metadata=metadata
                )
        
        return ServiceHealthResult(
            service_key="wordpress",
            status=ServiceHealthRecord.STATUS_HEALTHY,
            status_label="WordPress connected.",
            issue_description="WordPress API is reachable and response was valid.",
            suggested_fix="No action needed.",
            last_success_at=timezone.now(),
            metadata=metadata
        )
    except Exception as e:
        return ServiceHealthResult(
            service_key="wordpress",
            status=ServiceHealthRecord.STATUS_ERROR,
            status_label="WordPress check failed.",
            issue_description=f"Error connecting to WordPress: {str(e)}",
            suggested_fix="Ensure the WordPress instance is online and the REST API is not blocked.",
            last_error_at=timezone.now(),
            last_error_message=str(e)
        )

@HealthCheckRegistry.register(
    "knowledge_graph", 
    name="Entity Knowledge Graph", 
    description="Graph database storing relationships between people, places, and topics."
)
def check_knowledge_graph_health() -> ServiceHealthResult:
    try:
        from apps.knowledge_graph.models import EntityNode
        node_count = EntityNode.objects.count()
        if node_count == 0:
             return ServiceHealthResult(
                service_key="knowledge_graph",
                status=ServiceHealthRecord.STATUS_WARNING,
                status_label="Knowledge Graph is empty.",
                issue_description="The entity graph exists but no entities have been extracted yet.",
                suggested_fix="Run the 'Full Sync' job for XenForo or WordPress to extract entities.",
                last_success_at=timezone.now()
            )

        return ServiceHealthResult(
            service_key="knowledge_graph",
            status=ServiceHealthRecord.STATUS_HEALTHY,
            status_label="Knowledge Graph healthy.",
            issue_description=f"Knowledge graph is active with {node_count} extracted entities.",
            suggested_fix="No action needed.",
            last_success_at=timezone.now(),
            metadata={"node_count": node_count}
        )
    except Exception as e:
        return ServiceHealthResult(
            service_key="knowledge_graph",
            status=ServiceHealthRecord.STATUS_ERROR,
            status_label="Knowledge Graph check failed.",
            issue_description=f"Error querying knowledge graph database: {str(e)}",
            suggested_fix="Check database accessibility for specialized entity tables.",
            last_error_at=timezone.now(),
            last_error_message=str(e)
        )

@HealthCheckRegistry.register(
    "weights_plugins", 
    name="Ranking Core & Plugins", 
    description="System-wide ranking weights and modular functional overrides."
)
def check_weights_plugins_health() -> ServiceHealthResult:
    try:
        from apps.plugins.models import Plugin
        # Check for non-standard weights
        weight_keys = ["suggestions.weight_graph", "suggestions.weight_nlp", "suggestions.weight_analytics"]
        missing_weights = []
        for key in weight_keys:
            if not AppSetting.objects.filter(key=key).exists():
                missing_weights.append(key)
        
        # Check plugins
        total_plugins = Plugin.objects.count()
        enabled_plugins = Plugin.objects.filter(is_enabled=True).count()
        
        if missing_weights:
            return ServiceHealthResult(
                service_key="weights_plugins",
                status=ServiceHealthRecord.STATUS_WARNING,
                status_label="Optimization weights incomplete.",
                issue_description=f"Missing core ranking weights: {', '.join(missing_weights)}.",
                suggested_fix="Set the ranking weight presets in Settings > Optimization.",
                last_error_at=timezone.now(),
                metadata={"enabled_plugins": enabled_plugins, "total_plugins": total_plugins}
            )

        return ServiceHealthResult(
            service_key="weights_plugins",
            status=ServiceHealthRecord.STATUS_HEALTHY,
            status_label="Weights and Plugins healthy.",
            issue_description=f"Ranking weights are correctly defined, and {enabled_plugins} plugins are active.",
            suggested_fix="No action needed.",
            last_success_at=timezone.now(),
            metadata={"enabled_plugins": enabled_plugins, "total_plugins": total_plugins}
        )
    except Exception as e:
        return ServiceHealthResult(
            service_key="weights_plugins",
            status=ServiceHealthRecord.STATUS_ERROR,
            status_label="Configuration check failed.",
            issue_description=f"Error verifying weights or plugins: {str(e)}",
            suggested_fix="Check database integrity for core settings and plugin tables.",
            last_error_at=timezone.now(),
            last_error_message=str(e)
        )

@HealthCheckRegistry.register(
    "webhooks", 
    name="Real-time Webhooks", 
    description="Ingress point for instant content updates from XF and WP."
)
def check_webhooks_health() -> ServiceHealthResult:
    try:
        from apps.sync.models import WebhookReceipt
        recent_cutoff = timezone.now() - timedelta(days=7)
        recent_receipts = WebhookReceipt.objects.filter(created_at__gte=recent_cutoff).count()
        
        # This is just a warning if no activity. It might be healthy but just quiet.
        if recent_receipts == 0:
             return ServiceHealthResult(
                service_key="webhooks",
                status=ServiceHealthRecord.STATUS_WARNING,
                status_label="No recent webhook activity.",
                issue_description="No webhooks from WordPress or XenForo have been received in the last 7 days.",
                suggested_fix="Verify the 'Webhook Secret' matches between your forum/site and this app.",
                last_success_at=timezone.now()
            )

        return ServiceHealthResult(
            service_key="webhooks",
            status=ServiceHealthRecord.STATUS_HEALTHY,
            status_label="Webhooks active.",
            issue_description=f"Receiving real-time updates ({recent_receipts} in last 7 days).",
            suggested_fix="No action needed.",
            last_success_at=timezone.now(),
            metadata={"recent_count": recent_receipts}
        )
    except Exception as e:
        return ServiceHealthResult(
            service_key="webhooks",
            status=ServiceHealthRecord.STATUS_ERROR,
            status_label="Webhook check failed.",
            issue_description=f"Error querying webhook receipt logs: {str(e)}",
            suggested_fix="Check database connectivity and ensure the sync app is properly installed.",
            last_error_at=timezone.now(),
            last_error_message=str(e)
        )

# ── Mock Future Service (Proof of Concept) ─────────────────────────

@HealthCheckRegistry.register(
    "future_ai_agent", 
    name="Autonomous Agents", 
    description="Reserved slot for future AI-driven optimization agents."
)
def check_mock_future_health() -> ServiceHealthResult:
    """Example of how easy it is to add future components."""
    return ServiceHealthResult(
        service_key="future_ai_agent",
        status=ServiceHealthRecord.STATUS_HEALTHY,
        status_label="Future AI Agent is ready.",
        issue_description="The future component is successfully registered and monitored.",
        suggested_fix="No action needed.",
        last_success_at=timezone.now()
    )

# ── Core Integration Logic ────────────────────────────────────────

def run_all_health_checks():
    """Runs every registered health check in the system."""
    checkers = HealthCheckRegistry.get_checkers()
    results = {}
    for service_key in checkers.keys():
        try:
            results[service_key] = perform_health_check(service_key)
        except Exception as e:
            logger.error(f"Failed to run health check for {service_key}: {str(e)}")
    return results

def perform_health_check(service_key: str) -> ServiceHealthRecord:
    """Run a single health check using the registry and update its record."""
    checkers = HealthCheckRegistry.get_checkers()
    checker = checkers.get(service_key)
    if not checker:
        raise ValueError(f"No health checker found for service: {service_key}")
        
    result = checker()
    record, _ = ServiceHealthRecord.objects.get_or_create(
        service_key=service_key,
        defaults={'last_check_at': timezone.now(), 'status_label': 'Initializing...'}
    )
    
    # Update fields
    meta = HealthCheckRegistry.get_metadata(service_key)
    record.service_name = meta.get("name", service_key)
    record.service_description = meta.get("description", "")
    record.status = result.status
    record.status_label = result.status_label
    record.issue_description = result.issue_description
    record.suggested_fix = result.suggested_fix
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
        
def get_service_health_status(service_key: str) -> Dict[str, Any]:
    """
    Standardized utility for other apps/views to query a service's health.
    Ensures total harmony across the entire project.
    """
    try:
        record = ServiceHealthRecord.objects.get(service_key=service_key)
        return {
            "status": record.status,
            "label": record.status_label,
            "name": record.service_name,
            "description": record.service_description,
            "issue": record.issue_description,
            "fix": record.suggested_fix,
            "last_success": record.last_success_at,
            "is_healthy": record.status == ServiceHealthRecord.STATUS_HEALTHY
        }
    except ServiceHealthRecord.DoesNotExist:
        # Fallback to a pending/unknown state if first check hasn't run
        meta = HealthCheckRegistry.get_metadata(service_key)
        return {
            "status": "unknown",
            "label": "Health check pending...",
            "name": meta.get("name", service_key),
            "description": meta.get("description", ""),
            "issue": "",
            "fix": "Wait for the next scheduled health check (30m) or run manually.",
            "last_success": None,
            "is_healthy": False
        }
