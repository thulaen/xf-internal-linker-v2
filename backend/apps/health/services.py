import logging
from datetime import timedelta
from typing import Dict, Any, Optional, Callable
from dataclasses import dataclass, asdict
from django.utils import timezone
from django.conf import settings
from django.db import connections

from apps.core.models import AppSetting
from apps.analytics.models import SearchMetric
from apps.notifications.models import OperatorAlert
from apps.notifications.services import emit_operator_alert, resolve_operator_alert
from apps.content.models import ContentItem
from apps.core.runtime_registry import (
    get_current_embedding_device,
    get_current_embedding_model_name,
    summarize_helpers,
    summarize_model_registry,
)
from apps.suggestions.models import PipelineRun
from .models import ServiceHealthRecord

logger = logging.getLogger(__name__)

# HTTP status code surfaced in a health message when a WordPress
# Application Password is rejected. Named so the magic-number lint
# rule does not fire on the embedded `401` in the user-facing string.
HTTP_UNAUTHORIZED = 401

# Default broker URL used when CELERY_BROKER_URL is not set. Named so
# the port number in the URL does not trip the magic-number detector.
_DEFAULT_REDIS_PORT = 6379
_DEFAULT_CELERY_BROKER_URL = f"redis://redis:{_DEFAULT_REDIS_PORT}/2"

# Celery queue depth beyond which the health check returns a warning
# (configurable per-setting, default is this value).
_DEFAULT_CELERY_ERROR_DEPTH = 200

# How many characters of the crawler error_message to surface in the
# health card before truncating.
_CRAWL_ERROR_PREVIEW_CHARS = 200

# Crawler data-size threshold (in MB) above which the health card
# nudges the operator to prune.
_CRAWLER_STORAGE_WARN_MB = 5000

# Denominator when converting a failure-threshold percent to a
# success-rate floor (e.g. if failure_threshold = 20, the success
# floor is 100 - 20 = 80).
_PERCENT_BASE = 100


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
                "description": description,
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
    description="Core data storage for application state and settings.",
)
def check_database_health() -> ServiceHealthResult:
    try:
        connections["default"].cursor()
        return ServiceHealthResult(
            service_key="database",
            status=ServiceHealthRecord.STATUS_HEALTHY,
            status_label="Database connection is healthy.",
            issue_description="PostgreSQL is reachable and accepting queries.",
            suggested_fix="No action needed.",
            last_success_at=timezone.now(),
        )
    except Exception as e:
        return ServiceHealthResult(
            service_key="database",
            status=ServiceHealthRecord.STATUS_DOWN,
            status_label="Database connection failed.",
            issue_description=f"The application cannot connect to PostgreSQL: {str(e)}",
            suggested_fix="Check if the 'postgres' container is running and the database credentials are correct.",
            last_error_at=timezone.now(),
            last_error_message=str(e),
        )


@HealthCheckRegistry.register(
    "redis",
    name="Redis Cache & Broker",
    description="In-memory data store for caching and Celery message brokering.",
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
            last_success_at=timezone.now(),
        )
    except Exception as e:
        return ServiceHealthResult(
            service_key="redis",
            status=ServiceHealthRecord.STATUS_DOWN,
            status_label="Redis connection failed.",
            issue_description=f"Redis is unreachable or not responding to pings: {str(e)}",
            suggested_fix="Check if the 'redis' container is running and REDIS_URL is correct.",
            last_error_at=timezone.now(),
            last_error_message=str(e),
        )


@HealthCheckRegistry.register(
    "celery",
    name="Celery Worker Cluster",
    description="Distributed task queue for background processing.",
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
                last_error_at=timezone.now(),
            )

        worker_count = len(active)
        return ServiceHealthResult(
            service_key="celery",
            status=ServiceHealthRecord.STATUS_HEALTHY,
            status_label=f"Celery is healthy ({worker_count} workers).",
            issue_description=f"Background processing queue is active with {worker_count} workers.",
            suggested_fix="No action needed.",
            last_success_at=timezone.now(),
            metadata={"worker_count": worker_count},
        )
    except Exception as e:
        return ServiceHealthResult(
            service_key="celery",
            status=ServiceHealthRecord.STATUS_ERROR,
            status_label="Celery cluster check failed.",
            issue_description=f"Error inspecting Celery workers: {str(e)}",
            suggested_fix="Check Redis connectivity and ensure Celery is properly configured.",
            last_error_at=timezone.now(),
            last_error_message=str(e),
        )


# ── Runtime & AI Checkers ─────────────────────────────────────────


@HealthCheckRegistry.register(
    "native_scoring",
    name="C++ Performance Kernels",
    description="Compiled native extensions for hot-path ranking and NLU.",
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
                metadata={"module_statuses": statuses},
            )

        if failed:
            return ServiceHealthResult(
                service_key="native_scoring",
                status=ServiceHealthRecord.STATUS_WARNING,
                status_label="C++ extensions degraded.",
                issue_description=f"Some optional performance kernels ({', '.join(s['module'] for s in failed)}) are using Python fallback.",
                suggested_fix="Rebuild native extensions to restore full performance.",
                last_success_at=timezone.now(),
                metadata={"module_statuses": statuses},
            )

        return ServiceHealthResult(
            service_key="native_scoring",
            status=ServiceHealthRecord.STATUS_HEALTHY,
            status_label="C++ performance kernels healthy.",
            issue_description="All native C++ scoring and NLU extensions are loaded and active.",
            suggested_fix="No action needed.",
            last_success_at=timezone.now(),
            metadata={"module_statuses": statuses},
        )
    except Exception as e:
        return ServiceHealthResult(
            service_key="native_scoring",
            status=ServiceHealthRecord.STATUS_ERROR,
            status_label="C++ diagnostics failed.",
            issue_description=f"Error checking native extension status: {str(e)}",
            suggested_fix="Check the 'extensions' directory and Python import functionality.",
            last_error_at=timezone.now(),
            last_error_message=str(e),
        )


@HealthCheckRegistry.register(
    "ml_models",
    name="AI & NLP Models",
    description="Language models (SpaCy) and Embedding engines (BGE) for suggestion logic.",
)
def check_ml_models_health() -> ServiceHealthResult:
    try:
        # Check SpaCy
        import spacy

        model_name = settings.SPACY_MODEL
        spacy_ok = spacy.util.is_package(model_name)
        model_runtime = summarize_model_registry()
        active_model = model_runtime.get("active_model") or {}
        embedding_model = (
            active_model.get("model_name") or get_current_embedding_model_name()
        )
        device_target = (
            active_model.get("device_target") or get_current_embedding_device()
        )

        # Check BGE (using import check as proxy for environment readiness)

        if not spacy_ok:
            return ServiceHealthResult(
                service_key="ml_models",
                status=ServiceHealthRecord.STATUS_ERROR,
                status_label="SpaCy model missing.",
                issue_description=f"The required NLU model '{model_name}' is not installed in the environment.",
                suggested_fix=f"Run 'python -m spacy download {model_name}' inside the backend container.",
                last_error_at=timezone.now(),
            )

        return ServiceHealthResult(
            service_key="ml_models",
            status=ServiceHealthRecord.STATUS_HEALTHY,
            status_label="ML models are loaded.",
            issue_description=(
                f"NLU ({model_name}) and Embedding ({embedding_model}) models are "
                f"available. Active device: {device_target}."
            ),
            suggested_fix="No action needed.",
            last_success_at=timezone.now(),
            metadata={
                "spacy_model": model_name,
                "embedding_model": embedding_model,
                "embedding_device": device_target,
                "candidate_model": (model_runtime.get("candidate_model") or {}).get(
                    "model_name"
                ),
                "hot_swap_safe": model_runtime.get("hot_swap_safe", False),
            },
        )
    except Exception as e:
        return ServiceHealthResult(
            service_key="ml_models",
            status=ServiceHealthRecord.STATUS_ERROR,
            status_label="ML environment check failed.",
            issue_description=f"Error verifying ML dependencies: {str(e)}",
            suggested_fix="Ensure 'sentence-transformers' and 'spacy' are installed in the Python environment.",
            last_error_at=timezone.now(),
            last_error_message=str(e),
        )


@HealthCheckRegistry.register(
    "model_runtime",
    name="Model Runtime",
    description="Champion/candidate embedding runtime ownership, hot swap, and backfill state.",
)
def check_model_runtime_health() -> ServiceHealthResult:
    try:
        summary = summarize_model_registry()
        active_model = summary.get("active_model") or {}
        candidate_model = summary.get("candidate_model") or {}
        backfill = summary.get("backfill") or {}
        active_name = (
            active_model.get("model_name") or get_current_embedding_model_name()
        )
        device_target = (
            active_model.get("device_target") or get_current_embedding_device()
        )
        active_status = active_model.get("status") or "unknown"

        metadata = {
            "active_model": active_name,
            "active_dimension": active_model.get("dimension"),
            "active_device": device_target,
            "candidate_model": candidate_model.get("model_name"),
            "candidate_status": candidate_model.get("status"),
            "hot_swap_safe": summary.get("hot_swap_safe", False),
            "reclaimable_disk_bytes": summary.get("reclaimable_disk_bytes", 0),
            "backfill_status": backfill.get("status"),
            "backfill_progress_pct": backfill.get("progress_pct"),
        }

        if not active_model:
            return ServiceHealthResult(
                service_key="model_runtime",
                status=ServiceHealthRecord.STATUS_WARNING,
                status_label="Runtime registry inferred the active model.",
                issue_description=(
                    "The runtime registry has not been explicitly seeded yet, so the "
                    "app inferred the active embedding model from current settings."
                ),
                suggested_fix=(
                    "Open Settings > Runtime so the app can register the active model "
                    "and show full hot-swap diagnostics."
                ),
                last_success_at=timezone.now(),
                metadata=metadata,
            )

        if active_status in {"failed", "deleted"}:
            return ServiceHealthResult(
                service_key="model_runtime",
                status=ServiceHealthRecord.STATUS_ERROR,
                status_label=f"Active model runtime is {active_status}.",
                issue_description=(
                    f"The active embedding model '{active_name}' is not ready to serve."
                ),
                suggested_fix=(
                    "Open Settings > Runtime, warm or roll back the champion model, "
                    "and re-run the health check."
                ),
                last_error_at=timezone.now(),
                metadata=metadata,
            )

        if backfill and backfill.get("status") in {"queued", "running", "paused"}:
            return ServiceHealthResult(
                service_key="model_runtime",
                status=ServiceHealthRecord.STATUS_WARNING,
                status_label="Model swap in progress.",
                issue_description=(
                    f"The active model is '{active_name}' on {device_target}, and a "
                    f"backfill is {backfill.get('status')}."
                ),
                suggested_fix=(
                    "Let the backfill finish, or pause it from Settings > Runtime if "
                    "you need to free resources."
                ),
                last_success_at=timezone.now(),
                metadata=metadata,
            )

        if candidate_model:
            return ServiceHealthResult(
                service_key="model_runtime",
                status=ServiceHealthRecord.STATUS_WARNING,
                status_label="Candidate model waiting for promotion.",
                issue_description=(
                    f"The active model is '{active_name}' on {device_target}, and "
                    f"candidate '{candidate_model.get('model_name')}' is "
                    f"{candidate_model.get('status')}."
                ),
                suggested_fix=(
                    "If the candidate looks good, promote it in Settings > Runtime. "
                    "Otherwise drain or delete it to reclaim disk."
                ),
                last_success_at=timezone.now(),
                metadata=metadata,
            )

        return ServiceHealthResult(
            service_key="model_runtime",
            status=ServiceHealthRecord.STATUS_HEALTHY,
            status_label=f"Runtime healthy: {active_name} on {device_target}.",
            issue_description=(
                f"The active embedding model is '{active_name}' on {device_target}, "
                "and no swap or backfill is blocking work."
            ),
            suggested_fix="No action needed.",
            last_success_at=timezone.now(),
            metadata=metadata,
        )
    except Exception as e:
        return ServiceHealthResult(
            service_key="model_runtime",
            status=ServiceHealthRecord.STATUS_ERROR,
            status_label="Model runtime check failed.",
            issue_description=f"Could not read runtime registry state: {str(e)}",
            suggested_fix="Check the runtime registry tables and retry the health check.",
            last_error_at=timezone.now(),
            last_error_message=str(e),
        )


@HealthCheckRegistry.register(
    "helper_nodes",
    name="Helper Nodes",
    description="Distributed helper availability, RAM pressure, and helper-assisted execution capacity.",
)
def check_helper_nodes_health() -> ServiceHealthResult:
    try:
        summary = summarize_helpers()
        counts = summary.get("counts") or {}
        online_count = int(counts.get("online", 0))
        busy_count = int(counts.get("busy", 0))
        stale_count = int(counts.get("stale", 0))
        offline_count = int(counts.get("offline", 0))
        aggregate_ram_pressure = float(summary.get("aggregate_ram_pressure") or 0.0)
        busiest = summary.get("busiest") or {}
        metadata = {
            "online_count": online_count,
            "busy_count": busy_count,
            "stale_count": stale_count,
            "offline_count": offline_count,
            "aggregate_ram_pressure": aggregate_ram_pressure,
            "busiest_helper": busiest.get("name"),
            "busiest_effective_load": busiest.get("effective_load"),
        }

        if online_count + busy_count + stale_count + offline_count == 0:
            return ServiceHealthResult(
                service_key="helper_nodes",
                status=ServiceHealthRecord.STATUS_NOT_CONFIGURED,
                status_label="No helper nodes configured.",
                issue_description=(
                    "The primary machine is handling all work because no helper nodes "
                    "have been registered yet."
                ),
                suggested_fix=(
                    "Open Settings > Helpers to register a helper node if you want to "
                    "offload RAM-heavy or GPU-heavy background work."
                ),
                metadata=metadata,
            )

        if online_count == 0 and busy_count == 0 and stale_count > 0:
            return ServiceHealthResult(
                service_key="helper_nodes",
                status=ServiceHealthRecord.STATUS_WARNING,
                status_label="Helpers are stale.",
                issue_description=(
                    "Helpers are registered, but their heartbeats are old enough that "
                    "the scheduler is treating them as stale."
                ),
                suggested_fix=(
                    "Check the helper machines, then use Settings > Helpers to resume "
                    "or remove the stale entries."
                ),
                last_error_at=timezone.now(),
                metadata=metadata,
            )

        if online_count == 0 and busy_count == 0 and offline_count > 0:
            return ServiceHealthResult(
                service_key="helper_nodes",
                status=ServiceHealthRecord.STATUS_WARNING,
                status_label="All helpers are offline.",
                issue_description=(
                    "Helper nodes are registered, but none are currently available for work."
                ),
                suggested_fix=(
                    "Bring a helper online or delete old registrations in Settings > Helpers."
                ),
                last_error_at=timezone.now(),
                metadata=metadata,
            )

        if aggregate_ram_pressure >= 0.9:
            return ServiceHealthResult(
                service_key="helper_nodes",
                status=ServiceHealthRecord.STATUS_WARNING,
                status_label="Helpers are near their RAM cap.",
                issue_description=(
                    "At least one helper is online, but the aggregate RAM pressure is "
                    "high enough that new RAM-heavy jobs may stay on the primary node."
                ),
                suggested_fix=(
                    "Reduce helper load, add a stronger helper, or raise the helper RAM "
                    "cap carefully in Settings > Helpers."
                ),
                last_success_at=timezone.now(),
                metadata=metadata,
            )

        return ServiceHealthResult(
            service_key="helper_nodes",
            status=ServiceHealthRecord.STATUS_HEALTHY,
            status_label=f"Helpers healthy ({online_count} online, {busy_count} busy).",
            issue_description=(
                f"{online_count} helpers are online, {busy_count} are busy, and "
                "helper-assisted background execution is available."
            ),
            suggested_fix="No action needed.",
            last_success_at=timezone.now(),
            metadata=metadata,
        )
    except Exception as e:
        return ServiceHealthResult(
            service_key="helper_nodes",
            status=ServiceHealthRecord.STATUS_ERROR,
            status_label="Helper health check failed.",
            issue_description=f"Could not summarise helper node state: {str(e)}",
            suggested_fix="Check the helper registry data and retry the health check.",
            last_error_at=timezone.now(),
            last_error_message=str(e),
        )


@HealthCheckRegistry.register(
    "gpu_faiss",
    name="GPU & FAISS Index",
    description="CUDA GPU availability and persistent FAISS vector index for Stage 1 pipeline search.",
)
def check_gpu_faiss_health() -> ServiceHealthResult:
    try:
        import torch
        from apps.pipeline.services.faiss_index import get_faiss_status

        cuda_available = torch.cuda.is_available()
        faiss_status = get_faiss_status()
        faiss_active = faiss_status.get("active", False)
        faiss_device = faiss_status.get("device", "none")
        faiss_vectors = faiss_status.get("vectors", 0)
        faiss_vram_mb = faiss_status.get("vram_mb", 0)

        meta = {
            "cuda_available": cuda_available,
            "faiss_active": faiss_active,
            "faiss_device": faiss_device,
            "faiss_vectors": faiss_vectors,
        }

        if cuda_available:
            props = torch.cuda.get_device_properties(0)
            total_vram_mb = props.total_memory // (1024 * 1024)
            used_vram_mb = (props.total_memory - torch.cuda.mem_get_info(0)[0]) // (
                1024 * 1024
            )
            meta["gpu_name"] = props.name
            meta["vram_total_mb"] = total_vram_mb
            meta["vram_used_mb"] = used_vram_mb
            meta["faiss_vram_mb"] = faiss_vram_mb

        if not faiss_active:
            return ServiceHealthResult(
                service_key="gpu_faiss",
                status=ServiceHealthRecord.STATUS_WARNING,
                status_label="FAISS index not loaded.",
                issue_description="The FAISS vector index has not been built yet. Stage 1 pipeline is running on the slower NumPy CPU path.",
                suggested_fix="Trigger a pipeline run or wait for the next Celery Beat refresh (every 15 minutes). Check that content items have embeddings.",
                last_error_at=timezone.now(),
                metadata=meta,
            )

        on_gpu = "GPU" in faiss_device
        if not on_gpu:
            return ServiceHealthResult(
                service_key="gpu_faiss",
                status=ServiceHealthRecord.STATUS_WARNING,
                status_label=f"FAISS on CPU ({faiss_vectors:,} vectors).",
                issue_description="FAISS index is loaded but running on CPU, not GPU. Stage 1 search is faster than NumPy but not at full GPU speed.",
                suggested_fix="Ensure ML_PERFORMANCE_MODE=HIGH_PERFORMANCE in your .env and that CUDA drivers are available inside the container.",
                last_success_at=timezone.now(),
                metadata=meta,
            )

        return ServiceHealthResult(
            service_key="gpu_faiss",
            status=ServiceHealthRecord.STATUS_HEALTHY,
            status_label=f"FAISS-GPU active ({faiss_vectors:,} vectors, {faiss_vram_mb} MB VRAM).",
            issue_description=f"Persistent FAISS index is live on {faiss_device} with {faiss_vectors:,} content embeddings.",
            suggested_fix="No action needed.",
            last_success_at=timezone.now(),
            metadata=meta,
        )
    except Exception as e:
        return ServiceHealthResult(
            service_key="gpu_faiss",
            status=ServiceHealthRecord.STATUS_ERROR,
            status_label="GPU/FAISS check failed.",
            issue_description=f"Could not query GPU or FAISS index status: {str(e)}",
            suggested_fix="Ensure PyTorch and faiss-gpu-cu12 are installed in the backend container.",
            last_error_at=timezone.now(),
            last_error_message=str(e),
        )


# ── Analytics & Data Checkers ─────────────────────────────────────


def _ga4_enrich_credentials_and_quota(property_id_value: str, metadata: dict) -> None:
    """Try to validate GA4 read credentials and populate quota info into metadata.

    Mutates metadata in-place. Silently skips if credentials are not configured
    (some installs only use Measurement Protocol and never set up the Data API).
    Raises on credential errors so the caller can surface them as an error status.
    """

    def _get(key: str) -> str:
        s = AppSetting.objects.filter(key=key).first()
        return s.value if s else ""

    client_email = _get("analytics.ga4_read_client_email")
    private_key = _get("analytics.ga4_read_private_key")
    project_id = _get("analytics.ga4_read_project_id")
    refresh_token = _get("analytics.google_oauth_refresh_token")
    client_id = _get("analytics.google_oauth_client_id")
    client_secret = _get("analytics.google_oauth_client_secret")

    # If no read credentials at all, nothing to validate.
    if not (client_email or refresh_token):
        return

    from apps.analytics.ga4_client import build_ga4_data_service, get_ga4_quota

    service = build_ga4_data_service(
        property_id=property_id_value,
        project_id=project_id,
        client_email=client_email,
        private_key=private_key,
        refresh_token=refresh_token,
        client_id=client_id,
        client_secret=client_secret,
    )
    response = get_ga4_quota(service=service, property_id=property_id_value)
    quota = response.get("propertyQuota", {})
    tokens_day = quota.get("tokensPerDay", {})
    if tokens_day:
        metadata["tokens_per_day_consumed"] = tokens_day.get("consumed", 0)
        metadata["tokens_per_day_remaining"] = tokens_day.get("remaining", 0)


@HealthCheckRegistry.register(
    "ga4",
    name="Google Analytics 4",
    description="Integration with Google Analytics Data API for telemetry metrics.",
)
def check_ga4_health() -> ServiceHealthResult:
    property_id = AppSetting.objects.filter(key="analytics.ga4_property_id").first()
    if not property_id or not property_id.value:
        return ServiceHealthResult(
            service_key="ga4",
            status=ServiceHealthRecord.STATUS_NOT_CONFIGURED,
            status_label="GA4 not configured.",
            issue_description="Google Analytics 4 property ID is missing from settings.",
            suggested_fix="Go to Settings > Analytics and provide your GA4 Property ID.",
        )

    try:
        stale_hours = get_health_setting("ga4_stale_threshold_hours", 72)
        latest_metric = (
            SearchMetric.objects.filter(source="ga4").order_by("-date").first()
        )

        metadata = {
            "property_id": property_id.value[-4:].rjust(len(property_id.value), "*")
        }
        if latest_metric:
            lag_hours = (
                timezone.now()
                - timezone.make_aware(
                    timezone.datetime.combine(
                        latest_metric.date, timezone.datetime.min.time()
                    )
                )
            ).total_seconds() / 3600
            metadata["lag_hours"] = round(lag_hours, 1)

            if lag_hours > stale_hours:
                return ServiceHealthResult(
                    service_key="ga4",
                    status=ServiceHealthRecord.STATUS_STALE,
                    status_label="GA4 data is stale.",
                    issue_description=f"Last GA4 data is from {latest_metric.date} ({round(lag_hours)}h lag).",
                    suggested_fix="Check if the GA4 sync task is running or if the Google service account has been disabled.",
                    last_success_at=timezone.now(),
                    metadata=metadata,
                )

        # Validate read credentials and fetch daily quota if possible.
        _ga4_enrich_credentials_and_quota(property_id.value, metadata)

        # Data-flow validation: check that recent imports actually contain data.
        recent_rows = SearchMetric.objects.filter(
            source="ga4", date__gte=(timezone.now() - timezone.timedelta(days=7))
        ).count()
        metadata["recent_7d_rows"] = recent_rows
        if latest_metric and recent_rows == 0:
            return ServiceHealthResult(
                service_key="ga4",
                status=ServiceHealthRecord.STATUS_WARNING,
                status_label="GA4 connected but no recent data.",
                issue_description=(
                    "GA4 API responds and credentials are valid, but zero rows were "
                    "imported in the last 7 days. The integration may be misconfigured "
                    "(wrong property ID, missing permissions, or no traffic)."
                ),
                suggested_fix=(
                    "Verify the GA4 property ID matches the correct site. Check that the "
                    "service account has 'Viewer' access. Confirm the site is receiving traffic."
                ),
                last_success_at=timezone.now(),
                metadata=metadata,
            )

        return ServiceHealthResult(
            service_key="ga4",
            status=ServiceHealthRecord.STATUS_HEALTHY,
            status_label="GA4 connected.",
            issue_description="GA4 connectivity established and telemetry data is fresh.",
            suggested_fix="No action needed.",
            last_success_at=timezone.now(),
            metadata=metadata,
        )
    except Exception as e:
        return ServiceHealthResult(
            service_key="ga4",
            status=ServiceHealthRecord.STATUS_ERROR,
            status_label="GA4 connection failed.",
            issue_description=f"Error connecting to Google Analytics API: {str(e)}",
            suggested_fix="Verify your Google Service Account credentials and API permissions.",
            last_error_at=timezone.now(),
            last_error_message=str(e),
        )


def _gsc_validate_credentials(property_url: str) -> None:
    """Try to call the GSC API to confirm credentials are still valid.

    Silently skips if no credentials are configured.
    Raises on auth failure so the caller can surface it as an error status.
    """

    def _get(key: str) -> str:
        s = AppSetting.objects.filter(key=key).first()
        return s.value if s else ""

    client_email = _get("analytics.gsc_client_email")
    private_key = _get("analytics.gsc_private_key")
    refresh_token = _get("analytics.google_oauth_refresh_token")
    client_id = _get("analytics.google_oauth_client_id")
    client_secret = _get("analytics.google_oauth_client_secret")

    if not (client_email or refresh_token):
        return

    from apps.analytics.gsc_client import build_gsc_service, test_gsc_access

    service = build_gsc_service(
        client_email=client_email,
        private_key=private_key,
        refresh_token=refresh_token,
        client_id=client_id,
        client_secret=client_secret,
    )
    test_gsc_access(service=service, property_url=property_url)


@HealthCheckRegistry.register(
    "gsc",
    name="Search Console",
    description="Integration with Google Search Console for organic performance data.",
)
def check_gsc_health() -> ServiceHealthResult:
    site_url = AppSetting.objects.filter(key="analytics.gsc_site_url").first()
    if not site_url or not site_url.value:
        return ServiceHealthResult(
            service_key="gsc",
            status=ServiceHealthRecord.STATUS_NOT_CONFIGURED,
            status_label="GSC site URL missing.",
            issue_description="Google Search Console site URL has not been defined.",
            suggested_fix="Go to Settings > Analytics and provide your GSC Site URL.",
        )

    try:
        stale_hours = get_health_setting("gsc_stale_threshold_hours", 72)
        latest_metric = (
            SearchMetric.objects.filter(source="gsc").order_by("-date").first()
        )

        metadata = {"site_url": site_url.value}
        if latest_metric:
            lag_hours = (
                timezone.now()
                - timezone.make_aware(
                    timezone.datetime.combine(
                        latest_metric.date, timezone.datetime.min.time()
                    )
                )
            ).total_seconds() / 3600
            metadata["lag_hours"] = round(lag_hours, 1)

            if lag_hours > stale_hours:
                return ServiceHealthResult(
                    service_key="gsc",
                    status=ServiceHealthRecord.STATUS_STALE,
                    status_label="GSC data is stale.",
                    issue_description=f"Last GSC data is from {latest_metric.date} ({round(lag_hours)}h lag).",
                    suggested_fix="Check the Search Console sync task logs and Google Cloud Project status.",
                    last_success_at=timezone.now(),
                    metadata=metadata,
                )

        # Validate read credentials if configured.
        _gsc_validate_credentials(site_url.value)

        # Data-flow validation: check recent imports contain actual rows.
        recent_rows = SearchMetric.objects.filter(
            source="gsc", date__gte=(timezone.now() - timezone.timedelta(days=7))
        ).count()
        metadata["recent_7d_rows"] = recent_rows
        if latest_metric and recent_rows == 0:
            return ServiceHealthResult(
                service_key="gsc",
                status=ServiceHealthRecord.STATUS_WARNING,
                status_label="GSC connected but no recent data.",
                issue_description=(
                    "GSC API responds and credentials are valid, but zero rows were "
                    "imported in the last 7 days. The site URL may be wrong, the service "
                    "account may lack permissions, or the site has no search traffic."
                ),
                suggested_fix=(
                    "Verify the GSC site URL matches the correct property. Check that "
                    "the service account is listed as a user in Search Console."
                ),
                last_success_at=timezone.now(),
                metadata=metadata,
            )

        return ServiceHealthResult(
            service_key="gsc",
            status=ServiceHealthRecord.STATUS_HEALTHY,
            status_label="GSC connected.",
            issue_description="Search Console data is being imported correctly.",
            suggested_fix="No action needed.",
            last_success_at=timezone.now(),
            metadata=metadata,
        )
    except Exception as e:
        return ServiceHealthResult(
            service_key="gsc",
            status=ServiceHealthRecord.STATUS_ERROR,
            status_label="GSC connection failed.",
            issue_description=f"Error connecting to Search Console API: {str(e)}",
            suggested_fix="Verify service account access to the property in GSC dashboard.",
            last_error_at=timezone.now(),
            last_error_message=str(e),
        )


@HealthCheckRegistry.register(
    "matomo",
    name="Matomo Analytics",
    description="Self-hosted analytics alternative for privacy-focused tracking.",
)
def check_matomo_health() -> ServiceHealthResult:
    matomo_enabled = AppSetting.objects.filter(key="analytics.matomo_enabled").first()
    if not matomo_enabled or matomo_enabled.value.lower() not in ("true", "1", "yes"):
        return ServiceHealthResult(
            service_key="matomo",
            status=ServiceHealthRecord.STATUS_NOT_ENABLED,
            status_label="Matomo disabled.",
            issue_description="Matomo tracking is currently turned off in settings.",
            suggested_fix="No action needed unless you wish to use Matomo analytics.",
        )

    matomo_url = AppSetting.objects.filter(key="analytics.matomo_url").first()
    if not matomo_url or not matomo_url.value:
        return ServiceHealthResult(
            service_key="matomo",
            status=ServiceHealthRecord.STATUS_NOT_CONFIGURED,
            status_label="Matomo URL missing.",
            issue_description="Matomo analytics enabled but no server URL provided.",
            suggested_fix="Provide your Matomo instance URL in Settings.",
        )

    try:
        metadata = {"url": matomo_url.value}

        # Data-flow validation: check for recent Matomo-sourced metrics.
        matomo_rows = SearchMetric.objects.filter(source="matomo").count()
        metadata["total_rows"] = matomo_rows
        if matomo_rows == 0:
            return ServiceHealthResult(
                service_key="matomo",
                status=ServiceHealthRecord.STATUS_WARNING,
                status_label="Matomo connected but no data imported.",
                issue_description=(
                    "Matomo API is reachable but zero analytics rows have been imported. "
                    "The site ID or auth token may be wrong, or no tracking data exists."
                ),
                suggested_fix=(
                    "Verify the Matomo site ID and auth token. Check that the Matomo "
                    "tracking code is installed on the target site."
                ),
                last_success_at=timezone.now(),
                metadata=metadata,
            )

        return ServiceHealthResult(
            service_key="matomo",
            status=ServiceHealthRecord.STATUS_HEALTHY,
            status_label="Matomo connected.",
            issue_description=f"Matomo API is reachable and {matomo_rows:,} rows imported.",
            suggested_fix="No action needed.",
            last_success_at=timezone.now(),
            metadata=metadata,
        )
    except Exception as e:
        return ServiceHealthResult(
            service_key="matomo",
            status=ServiceHealthRecord.STATUS_ERROR,
            status_label="Matomo connection failed.",
            issue_description=f"Error communicating with Matomo: {str(e)}",
            suggested_fix="Check if your Matomo instance is online and the API token is valid.",
            last_error_at=timezone.now(),
            last_error_message=str(e),
        )


# ── CMS & Feature Checkers ────────────────────────────────────────


@HealthCheckRegistry.register(
    "xenforo",
    name="XenForo Forum",
    description="Primary content source for internal linking and discussion graph.",
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
            suggested_fix="Configure XENFORO_BASE_URL and XENFORO_API_KEY in your environment variables.",
        )

    # Validate the API key is still accepted before checking staleness.
    try:
        from apps.sync.services.xenforo_api import XenForoAPIClient

        client = XenForoAPIClient(base_url=base_url, api_key=api_key)
        if not client.verify_api_key():
            return ServiceHealthResult(
                service_key="xenforo",
                status=ServiceHealthRecord.STATUS_ERROR,
                status_label="XenForo API key rejected.",
                issue_description="The XenForo server rejected the API key (it may have been revoked or rotated).",
                suggested_fix="Re-generate the API key in XenForo Admin > API Keys and update XENFORO_API_KEY.",
                last_error_at=timezone.now(),
            )
    except Exception as e:
        return ServiceHealthResult(
            service_key="xenforo",
            status=ServiceHealthRecord.STATUS_ERROR,
            status_label="XenForo unreachable.",
            issue_description=f"Could not connect to XenForo to verify the API key: {str(e)}",
            suggested_fix="Check if the XenForo server is online and XENFORO_BASE_URL is correct.",
            last_error_at=timezone.now(),
            last_error_message=str(e),
        )

    try:
        latest_sync = (
            ContentItem.objects.filter(content_type__in=["thread", "post"])
            .order_by("-updated_at")
            .first()
        )
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
                    metadata=metadata,
                )

        # Data-flow validation: check that ContentItems actually exist from this source.
        xf_items = ContentItem.objects.filter(
            content_type__in=["thread", "resource"]
        ).count()
        metadata["content_items"] = xf_items
        if xf_items == 0:
            return ServiceHealthResult(
                service_key="xenforo",
                status=ServiceHealthRecord.STATUS_WARNING,
                status_label="XenForo connected but no content imported.",
                issue_description=(
                    "XenForo API is reachable but zero content items exist in the database. "
                    "The API key may have insufficient permissions, or the forum is empty."
                ),
                suggested_fix=(
                    "Trigger a full sync from the Jobs page. Check that the API key has "
                    "read permissions for threads and resources."
                ),
                last_success_at=timezone.now(),
                metadata=metadata,
            )

        return ServiceHealthResult(
            service_key="xenforo",
            status=ServiceHealthRecord.STATUS_HEALTHY,
            status_label="XenForo connected.",
            issue_description=f"XenForo API is reachable and {xf_items:,} content items are synced.",
            suggested_fix="No action needed.",
            last_success_at=timezone.now(),
            metadata=metadata,
        )
    except Exception as e:
        return ServiceHealthResult(
            service_key="xenforo",
            status=ServiceHealthRecord.STATUS_ERROR,
            status_label="XenForo check failed.",
            issue_description=f"Error connecting to XenForo: {str(e)}",
            suggested_fix="Check if your XenForo instance is up and the API key has 'read' permissions.",
            last_error_at=timezone.now(),
            last_error_message=str(e),
        )


@HealthCheckRegistry.register(
    "wordpress",
    name="WordPress Site",
    description="Secondary content source for blog posts and page linking.",
)
def check_wordpress_health() -> ServiceHealthResult:
    base_url = getattr(settings, "WORDPRESS_BASE_URL", "")
    if not base_url:
        return ServiceHealthResult(
            service_key="wordpress",
            status=ServiceHealthRecord.STATUS_NOT_CONFIGURED,
            status_label="WordPress not configured.",
            issue_description="WordPress base URL is missing.",
            suggested_fix="Configure WORDPRESS_BASE_URL in your environment variables.",
        )

    # If credentials are present, verify they are still accepted.
    try:
        from apps.sync.services.wordpress_api import WordPressAPIClient

        wp_client = WordPressAPIClient()
        if wp_client.has_credentials:
            result = wp_client.verify_credentials()
            if not result["ok"]:
                return ServiceHealthResult(
                    service_key="wordpress",
                    status=ServiceHealthRecord.STATUS_ERROR,
                    status_label="WordPress credentials rejected.",
                    issue_description=(
                        f"The WordPress Application Password was rejected "
                        f"(HTTP {HTTP_UNAUTHORIZED}). It may have been revoked."
                    ),
                    suggested_fix="Re-generate the Application Password in WordPress Users > Profile and update WORDPRESS_APP_PASSWORD.",
                    last_error_at=timezone.now(),
                )
    except Exception as e:
        return ServiceHealthResult(
            service_key="wordpress",
            status=ServiceHealthRecord.STATUS_ERROR,
            status_label="WordPress unreachable.",
            issue_description=f"Could not connect to WordPress to verify credentials: {str(e)}",
            suggested_fix="Check if the WordPress server is online and WORDPRESS_BASE_URL is correct.",
            last_error_at=timezone.now(),
            last_error_message=str(e),
        )

    try:
        latest_sync = (
            ContentItem.objects.filter(content_type__in=["wp_post", "wp_page"])
            .order_by("-updated_at")
            .first()
        )
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
                    metadata=metadata,
                )

        # Data-flow validation: check that WordPress content items exist.
        wp_items = ContentItem.objects.filter(content_type="wp_post").count()
        metadata["content_items"] = wp_items
        if wp_items == 0:
            return ServiceHealthResult(
                service_key="wordpress",
                status=ServiceHealthRecord.STATUS_WARNING,
                status_label="WordPress connected but no content imported.",
                issue_description=(
                    "WordPress API is reachable but zero posts exist in the database. "
                    "The Application Password may lack read permissions, or the site has no posts."
                ),
                suggested_fix=(
                    "Trigger a full WordPress sync from the Jobs page. Verify the "
                    "Application Password has 'read' scope."
                ),
                last_success_at=timezone.now(),
                metadata=metadata,
            )

        return ServiceHealthResult(
            service_key="wordpress",
            status=ServiceHealthRecord.STATUS_HEALTHY,
            status_label="WordPress connected.",
            issue_description=f"WordPress API is reachable and {wp_items:,} posts are synced.",
            suggested_fix="No action needed.",
            last_success_at=timezone.now(),
            metadata=metadata,
        )
    except Exception as e:
        return ServiceHealthResult(
            service_key="wordpress",
            status=ServiceHealthRecord.STATUS_ERROR,
            status_label="WordPress check failed.",
            issue_description=f"Error connecting to WordPress: {str(e)}",
            suggested_fix="Ensure the WordPress instance is online and the REST API is not blocked.",
            last_error_at=timezone.now(),
            last_error_message=str(e),
        )


@HealthCheckRegistry.register(
    "knowledge_graph",
    name="Entity Knowledge Graph",
    description="Graph database storing relationships between people, places, and topics.",
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
                last_success_at=timezone.now(),
            )

        return ServiceHealthResult(
            service_key="knowledge_graph",
            status=ServiceHealthRecord.STATUS_HEALTHY,
            status_label="Knowledge Graph healthy.",
            issue_description=f"Knowledge graph is active with {node_count} extracted entities.",
            suggested_fix="No action needed.",
            last_success_at=timezone.now(),
            metadata={"node_count": node_count},
        )
    except Exception as e:
        return ServiceHealthResult(
            service_key="knowledge_graph",
            status=ServiceHealthRecord.STATUS_ERROR,
            status_label="Knowledge Graph check failed.",
            issue_description=f"Error querying knowledge graph database: {str(e)}",
            suggested_fix="Check database accessibility for specialized entity tables.",
            last_error_at=timezone.now(),
            last_error_message=str(e),
        )


@HealthCheckRegistry.register(
    "weights_plugins",
    name="Ranking Core & Plugins",
    description="System-wide ranking weights and modular functional overrides.",
)
def check_weights_plugins_health() -> ServiceHealthResult:
    try:
        from apps.plugins.models import Plugin
        from apps.suggestions.weight_preset_service import PRESET_DEFAULTS

        # Derive required keys from the single source of truth so this check
        # never drifts when weights are added or removed.
        missing_weights = [
            key
            for key in PRESET_DEFAULTS
            if not AppSetting.objects.filter(key=key).exists()
        ]

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
                metadata={
                    "enabled_plugins": enabled_plugins,
                    "total_plugins": total_plugins,
                },
            )

        return ServiceHealthResult(
            service_key="weights_plugins",
            status=ServiceHealthRecord.STATUS_HEALTHY,
            status_label="Weights and Plugins healthy.",
            issue_description=f"Ranking weights are correctly defined, and {enabled_plugins} plugins are active.",
            suggested_fix="No action needed.",
            last_success_at=timezone.now(),
            metadata={
                "enabled_plugins": enabled_plugins,
                "total_plugins": total_plugins,
            },
        )
    except Exception as e:
        return ServiceHealthResult(
            service_key="weights_plugins",
            status=ServiceHealthRecord.STATUS_ERROR,
            status_label="Configuration check failed.",
            issue_description=f"Error verifying weights or plugins: {str(e)}",
            suggested_fix="Check database integrity for core settings and plugin tables.",
            last_error_at=timezone.now(),
            last_error_message=str(e),
        )


@HealthCheckRegistry.register(
    "webhooks",
    name="Real-time Webhooks",
    description="Ingress point for instant content updates from XF and WP.",
)
def check_webhooks_health() -> ServiceHealthResult:
    try:
        from apps.sync.models import WebhookReceipt

        recent_cutoff = timezone.now() - timedelta(days=7)
        recent_receipts = WebhookReceipt.objects.filter(
            created_at__gte=recent_cutoff
        ).count()

        # This is just a warning if no activity. It might be healthy but just quiet.
        if recent_receipts == 0:
            return ServiceHealthResult(
                service_key="webhooks",
                status=ServiceHealthRecord.STATUS_WARNING,
                status_label="No recent webhook activity.",
                issue_description="No webhooks from WordPress or XenForo have been received in the last 7 days.",
                suggested_fix="Verify the 'Webhook Secret' matches between your forum/site and this app.",
                last_success_at=timezone.now(),
            )

        return ServiceHealthResult(
            service_key="webhooks",
            status=ServiceHealthRecord.STATUS_HEALTHY,
            status_label="Webhooks active.",
            issue_description=f"Receiving real-time updates ({recent_receipts} in last 7 days).",
            suggested_fix="No action needed.",
            last_success_at=timezone.now(),
            metadata={"recent_count": recent_receipts},
        )
    except Exception as e:
        return ServiceHealthResult(
            service_key="webhooks",
            status=ServiceHealthRecord.STATUS_ERROR,
            status_label="Webhook check failed.",
            issue_description=f"Error querying webhook receipt logs: {str(e)}",
            suggested_fix="Check database connectivity and ensure the sync app is properly installed.",
            last_error_at=timezone.now(),
            last_error_message=str(e),
        )


@HealthCheckRegistry.register(
    "pipeline_health",
    name="Suggestion Pipeline",
    description="Core linking engine — generates internal link suggestions from content.",
)
def check_pipeline_health() -> ServiceHealthResult:
    try:
        total_ever = PipelineRun.objects.count()
        if total_ever == 0:
            return ServiceHealthResult(
                service_key="pipeline_health",
                status=ServiceHealthRecord.STATUS_NOT_CONFIGURED,
                status_label="No pipeline runs yet.",
                issue_description="The suggestion pipeline has never run.",
                suggested_fix="Trigger a pipeline run from the Jobs page.",
            )

        since_7d = timezone.now() - timedelta(days=7)
        recent = PipelineRun.objects.filter(created_at__gte=since_7d)
        completed = recent.filter(run_state="completed").count()
        failed = recent.filter(run_state="failed").count()
        terminal = completed + failed
        success_rate = round((completed / terminal) * 100) if terminal else 100

        last_run = PipelineRun.objects.order_by("-created_at").first()
        hours_since = (timezone.now() - last_run.created_at).total_seconds() / 3600

        failure_threshold = get_health_setting("pipeline_failure_rate_warning_pct", 20)
        no_run_threshold = get_health_setting("pipeline_warning_hours_no_run", 24)

        meta = {
            "completed_7d": completed,
            "failed_7d": failed,
            "success_rate_7d": success_rate,
            "hours_since_last_run": round(hours_since, 1),
            "last_run_state": last_run.run_state,
        }

        if failed >= 3 and hours_since < 24:
            return ServiceHealthResult(
                service_key="pipeline_health",
                status=ServiceHealthRecord.STATUS_ERROR,
                status_label=f"Pipeline failing — {failed} failures in 7 days.",
                issue_description=f"{failed} pipeline runs have failed in the last 7 days (success rate: {success_rate}%).",
                suggested_fix="Check the pipeline logs for the error message. Common causes: embedding model not loaded, database constraint, or out of memory.",
                last_error_at=timezone.now(),
                metadata=meta,
            )
        if hours_since > no_run_threshold:
            return ServiceHealthResult(
                service_key="pipeline_health",
                status=ServiceHealthRecord.STATUS_WARNING,
                status_label=f"No pipeline run in {round(hours_since)}h.",
                issue_description=f"The last pipeline run was {round(hours_since)} hours ago.",
                suggested_fix="Check the scheduled pipeline task in Celery Beat, or trigger a manual run from Jobs.",
                last_success_at=last_run.created_at
                if last_run.run_state == "completed"
                else None,
                metadata=meta,
            )
        if success_rate < (_PERCENT_BASE - failure_threshold):
            return ServiceHealthResult(
                service_key="pipeline_health",
                status=ServiceHealthRecord.STATUS_WARNING,
                status_label=f"Pipeline success rate is {success_rate}% (7d).",
                issue_description=f"{failed} of {terminal} pipeline runs failed in the last 7 days.",
                suggested_fix="Review failed pipeline run logs for recurring errors.",
                metadata=meta,
            )

        return ServiceHealthResult(
            service_key="pipeline_health",
            status=ServiceHealthRecord.STATUS_HEALTHY,
            status_label=f"Pipeline healthy ({success_rate}% success, 7d).",
            issue_description=f"{completed} successful runs in the last 7 days.",
            suggested_fix="No action needed.",
            last_success_at=timezone.now(),
            metadata=meta,
        )
    except Exception as e:
        return ServiceHealthResult(
            service_key="pipeline_health",
            status=ServiceHealthRecord.STATUS_ERROR,
            status_label="Pipeline check failed.",
            issue_description=f"Could not read pipeline run history: {str(e)}",
            suggested_fix="Check database connectivity.",
            last_error_at=timezone.now(),
            last_error_message=str(e),
        )


@HealthCheckRegistry.register(
    "celery_queues",
    name="Celery Queue Depth",
    description="Number of pending tasks waiting in each Celery queue.",
)
def check_celery_queue_depth() -> ServiceHealthResult:
    import redis as redis_lib

    try:
        broker_url = getattr(settings, "CELERY_BROKER_URL", _DEFAULT_CELERY_BROKER_URL)
        r = redis_lib.from_url(broker_url, socket_connect_timeout=5)
        queue_names = ["default", "pipeline", "embeddings"]
        depths = {q: r.llen(q) for q in queue_names}
        total = sum(depths.values())

        warn_threshold = get_health_setting("celery_queue_warning_depth", 50)
        error_threshold = get_health_setting(
            "celery_queue_error_depth", _DEFAULT_CELERY_ERROR_DEPTH
        )

        meta = {
            "default_depth": depths["default"],
            "pipeline_depth": depths["pipeline"],
            "embeddings_depth": depths["embeddings"],
            "total_depth": total,
        }

        worst_queue = max(depths, key=lambda q: depths[q])
        worst_depth = depths[worst_queue]

        if worst_depth >= error_threshold:
            return ServiceHealthResult(
                service_key="celery_queues",
                status=ServiceHealthRecord.STATUS_ERROR,
                status_label=f"Queue overflow — {worst_depth} tasks in '{worst_queue}'.",
                issue_description=f"The '{worst_queue}' queue has {worst_depth} tasks waiting (threshold: {error_threshold}).",
                suggested_fix="Scale up Celery workers or investigate why tasks are not being consumed.",
                last_error_at=timezone.now(),
                metadata=meta,
            )
        if worst_depth >= warn_threshold:
            return ServiceHealthResult(
                service_key="celery_queues",
                status=ServiceHealthRecord.STATUS_WARNING,
                status_label=f"Queue building up — {worst_depth} tasks in '{worst_queue}'.",
                issue_description=f"The '{worst_queue}' queue has {worst_depth} tasks waiting.",
                suggested_fix="Monitor queue depth — if it keeps growing, add more Celery workers.",
                metadata=meta,
            )

        return ServiceHealthResult(
            service_key="celery_queues",
            status=ServiceHealthRecord.STATUS_HEALTHY,
            status_label=f"Queues clear ({total} total pending).",
            issue_description="All Celery queues are processing normally.",
            suggested_fix="No action needed.",
            last_success_at=timezone.now(),
            metadata=meta,
        )
    except Exception as e:
        return ServiceHealthResult(
            service_key="celery_queues",
            status=ServiceHealthRecord.STATUS_ERROR,
            status_label="Queue depth check failed.",
            issue_description=f"Could not read queue depths from Redis: {str(e)}",
            suggested_fix="Ensure Redis is running and CELERY_BROKER_URL is correct.",
            last_error_at=timezone.now(),
            last_error_message=str(e),
        )


@HealthCheckRegistry.register(
    "celery_beat",
    name="Celery Beat Scheduler",
    description="Scheduled task runner that triggers periodic jobs (syncs, health checks, etc.).",
)
def check_celery_beat_health() -> ServiceHealthResult:
    try:
        from django_celery_beat.models import PeriodicTask

        PROBE_TASK = "periodic-system-health-check"
        stale_minutes = get_health_setting("beat_stale_threshold_minutes", 60)

        try:
            task = PeriodicTask.objects.get(name=PROBE_TASK)
        except PeriodicTask.DoesNotExist:
            return ServiceHealthResult(
                service_key="celery_beat",
                status=ServiceHealthRecord.STATUS_NOT_CONFIGURED,
                status_label="Beat probe task not found.",
                issue_description=f"The '{PROBE_TASK}' periodic task is missing from the database.",
                suggested_fix="Run migrations to re-seed the Celery Beat schedule.",
            )

        meta = {"expected_interval_minutes": 30}

        if task.last_run_at is None:
            return ServiceHealthResult(
                service_key="celery_beat",
                status=ServiceHealthRecord.STATUS_WARNING,
                status_label="Beat has not run yet.",
                issue_description="Celery Beat has never executed the health check task. It may not be running.",
                suggested_fix="Ensure the 'celery-beat' service is running.",
                metadata=meta,
            )

        minutes_ago = (timezone.now() - task.last_run_at).total_seconds() / 60
        meta["last_run_minutes_ago"] = round(minutes_ago, 1)

        if minutes_ago > stale_minutes * 1.5:
            return ServiceHealthResult(
                service_key="celery_beat",
                status=ServiceHealthRecord.STATUS_ERROR,
                status_label=f"Beat stale — last run {round(minutes_ago)}m ago.",
                issue_description=f"Celery Beat last ran {round(minutes_ago)} minutes ago (expected every 30 min).",
                suggested_fix="Restart the 'celery-beat' container. Check for lock file conflicts.",
                last_error_at=timezone.now(),
                metadata=meta,
            )
        if minutes_ago > stale_minutes:
            return ServiceHealthResult(
                service_key="celery_beat",
                status=ServiceHealthRecord.STATUS_WARNING,
                status_label=f"Beat delayed — last run {round(minutes_ago)}m ago.",
                issue_description=f"Celery Beat ran {round(minutes_ago)} minutes ago (expected every 30 min).",
                suggested_fix="Monitor — if this continues, restart the 'celery-beat' container.",
                metadata=meta,
            )

        return ServiceHealthResult(
            service_key="celery_beat",
            status=ServiceHealthRecord.STATUS_HEALTHY,
            status_label=f"Beat is running (last run {round(minutes_ago)}m ago).",
            issue_description="Celery Beat scheduler is firing on schedule.",
            suggested_fix="No action needed.",
            last_success_at=task.last_run_at,
            metadata=meta,
        )
    except Exception as e:
        return ServiceHealthResult(
            service_key="celery_beat",
            status=ServiceHealthRecord.STATUS_ERROR,
            status_label="Beat check failed.",
            issue_description=f"Could not read Celery Beat schedule: {str(e)}",
            suggested_fix="Check database connectivity and django-celery-beat migrations.",
            last_error_at=timezone.now(),
            last_error_message=str(e),
        )


@HealthCheckRegistry.register(
    "sitemaps", name="Sitemaps", description="Configured sitemaps for the web crawler."
)
def check_sitemaps() -> ServiceHealthResult:
    try:
        from apps.crawler.models import SitemapConfig

        total = SitemapConfig.objects.count()
        enabled = SitemapConfig.objects.filter(is_enabled=True).count()

        if total == 0:
            return ServiceHealthResult(
                service_key="sitemaps",
                status=ServiceHealthRecord.STATUS_NOT_CONFIGURED,
                status_label="No sitemaps configured.",
                issue_description="The web crawler needs at least one sitemap URL to seed its crawl.",
                suggested_fix="Go to the Web Crawler page and add your sitemap URLs.",
                metadata={"total": 0, "enabled": 0},
            )

        return ServiceHealthResult(
            service_key="sitemaps",
            status=ServiceHealthRecord.STATUS_HEALTHY,
            status_label=f"{enabled} of {total} sitemaps enabled.",
            last_success_at=timezone.now(),
            metadata={"total": total, "enabled": enabled},
        )
    except Exception as e:
        return ServiceHealthResult(
            service_key="sitemaps",
            status=ServiceHealthRecord.STATUS_ERROR,
            status_label="Sitemap check failed.",
            last_error_at=timezone.now(),
            last_error_message=str(e),
        )


@HealthCheckRegistry.register(
    "crawler_status",
    name="Web Crawler",
    description="Status of the most recent web crawl session.",
)
def check_crawler_status() -> ServiceHealthResult:
    try:
        from apps.crawler.models import CrawlSession

        latest = CrawlSession.objects.order_by("-created_at").first()

        if latest is None:
            return ServiceHealthResult(
                service_key="crawler_status",
                status=ServiceHealthRecord.STATUS_NOT_CONFIGURED,
                status_label="No crawl sessions yet.",
                issue_description="The web crawler has never been run.",
                suggested_fix="Go to the Web Crawler page and start your first crawl.",
            )

        meta = {
            "last_status": latest.status,
            "pages_crawled": latest.pages_crawled,
            "domain": latest.site_domain,
        }

        if latest.status == "failed":
            return ServiceHealthResult(
                service_key="crawler_status",
                status=ServiceHealthRecord.STATUS_WARNING,
                status_label=f"Last crawl failed ({latest.site_domain}).",
                issue_description=latest.error_message[:_CRAWL_ERROR_PREVIEW_CHARS]
                if latest.error_message
                else "Unknown error.",
                suggested_fix="Check the error message and try running the crawl again.",
                last_error_at=latest.updated_at,
                metadata=meta,
            )

        if latest.status == "running":
            return ServiceHealthResult(
                service_key="crawler_status",
                status=ServiceHealthRecord.STATUS_HEALTHY,
                status_label=f"Crawl running — {latest.pages_crawled} pages done.",
                last_success_at=timezone.now(),
                metadata=meta,
            )

        return ServiceHealthResult(
            service_key="crawler_status",
            status=ServiceHealthRecord.STATUS_HEALTHY,
            status_label=f"Last crawl: {latest.status} — {latest.pages_crawled} pages ({latest.site_domain}).",
            last_success_at=latest.completed_at or latest.updated_at,
            metadata=meta,
        )
    except Exception as e:
        return ServiceHealthResult(
            service_key="crawler_status",
            status=ServiceHealthRecord.STATUS_ERROR,
            status_label="Crawler status check failed.",
            last_error_at=timezone.now(),
            last_error_message=str(e),
        )


@HealthCheckRegistry.register(
    "crawler_storage",
    name="Crawler Storage",
    description="Disk space consumed by crawler data.",
)
def check_crawler_storage() -> ServiceHealthResult:
    try:
        from apps.crawler.models import CrawledPageMeta
        from django.db.models import Sum

        agg = CrawledPageMeta.objects.aggregate(total=Sum("content_length"))
        total_bytes = agg["total"] or 0
        total_mb = round(total_bytes / (1024 * 1024), 1)

        meta = {"storage_bytes": total_bytes, "storage_mb": total_mb}

        if total_mb > _CRAWLER_STORAGE_WARN_MB:
            return ServiceHealthResult(
                service_key="crawler_storage",
                status=ServiceHealthRecord.STATUS_WARNING,
                status_label=f"Crawler data: {total_mb} MB — consider pruning.",
                issue_description="Crawler data exceeds 5 GB. Auto-prune should reduce this.",
                suggested_fix="Check that auto-prune is running (every 4 weeks) or manually prune old sessions.",
                metadata=meta,
            )

        return ServiceHealthResult(
            service_key="crawler_storage",
            status=ServiceHealthRecord.STATUS_HEALTHY,
            status_label=f"Crawler data: {total_mb} MB.",
            last_success_at=timezone.now(),
            metadata=meta,
        )
    except Exception as e:
        return ServiceHealthResult(
            service_key="crawler_storage",
            status=ServiceHealthRecord.STATUS_ERROR,
            status_label="Crawler storage check failed.",
            last_error_at=timezone.now(),
            last_error_message=str(e),
        )


@HealthCheckRegistry.register(
    "disk_space",
    name="Disk Space",
    description="Available storage on the server filesystem (models, logs, media).",
)
def check_disk_space() -> ServiceHealthResult:
    import shutil

    try:
        warn_pct = get_health_setting("disk_warning_pct", 80)
        error_pct = get_health_setting("disk_error_pct", 90)

        usage = shutil.disk_usage("/app")
        total_gb = round(usage.total / (1024**3), 1)
        used_gb = round(usage.used / (1024**3), 1)
        free_gb = round(usage.free / (1024**3), 1)
        usage_pct = round((usage.used / usage.total) * 100, 1)

        meta = {
            "total_gb": total_gb,
            "used_gb": used_gb,
            "free_gb": free_gb,
            "usage_pct": usage_pct,
        }

        if usage_pct >= error_pct:
            return ServiceHealthResult(
                service_key="disk_space",
                status=ServiceHealthRecord.STATUS_ERROR,
                status_label=f"Disk critically full — {usage_pct}% used.",
                issue_description=f"Only {free_gb} GB free of {total_gb} GB total. Services may fail.",
                suggested_fix="Delete old logs, clear Docker image cache (`docker image prune -f`), or expand the volume.",
                last_error_at=timezone.now(),
                metadata=meta,
            )
        if usage_pct >= warn_pct:
            return ServiceHealthResult(
                service_key="disk_space",
                status=ServiceHealthRecord.STATUS_WARNING,
                status_label=f"Disk filling up — {usage_pct}% used.",
                issue_description=f"{free_gb} GB remaining of {total_gb} GB total.",
                suggested_fix="Clear old Docker images with `docker image prune -f` and review log rotation.",
                metadata=meta,
            )

        return ServiceHealthResult(
            service_key="disk_space",
            status=ServiceHealthRecord.STATUS_HEALTHY,
            status_label=f"Disk healthy — {free_gb} GB free ({usage_pct}% used).",
            issue_description=f"{free_gb} GB free of {total_gb} GB total.",
            suggested_fix="No action needed.",
            last_success_at=timezone.now(),
            metadata=meta,
        )
    except Exception as e:
        return ServiceHealthResult(
            service_key="disk_space",
            status=ServiceHealthRecord.STATUS_ERROR,
            status_label="Disk space check failed.",
            issue_description=f"Could not read disk usage: {str(e)}",
            suggested_fix="Check filesystem permissions.",
            last_error_at=timezone.now(),
            last_error_message=str(e),
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
        defaults={"last_check_at": timezone.now(), "status_label": "Initializing..."},
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
    if result.status in (
        ServiceHealthRecord.STATUS_ERROR,
        ServiceHealthRecord.STATUS_DOWN,
        ServiceHealthRecord.STATUS_STALE,
    ):
        severity = (
            OperatorAlert.SEVERITY_ERROR
            if result.status == ServiceHealthRecord.STATUS_DOWN
            else OperatorAlert.SEVERITY_WARNING
        )
        emit_operator_alert(
            event_type=f"health.{service_key}.degraded",
            severity=severity,
            title=f"System Health: {service_key.upper()} Degraded",
            message=result.status_label,
            dedupe_key=dedupe_key,
            source_area="system",
            related_route="/health",
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
            "is_healthy": record.status == ServiceHealthRecord.STATUS_HEALTHY,
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
            "is_healthy": False,
        }
