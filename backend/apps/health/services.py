"""System-wide health checks for the operator-visible /diagnostics page.

Every ``check_*_health`` function returns a ``ServiceHealthResult``
dataclass that the frontend renders as a status card. The shared builders
``_make_health_result`` + ``_make_check_failed_result`` centralise the
ServiceHealthResult construction so each check only supplies the
per-domain (status, label, issue, fix) wording. The 11 ``_classify_*_state``
helpers extract per-check decision trees as pure functions for easy testing.
"""

import logging
from datetime import timedelta
from typing import Any, Callable, Dict, Optional
from dataclasses import asdict, dataclass
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
        logger.exception("health check raised; surfacing as ServiceHealthResult")
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
        logger.exception("health check raised; surfacing as ServiceHealthResult")
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
                suggested_fix="Restart the 'celery-worker-default' and 'celery-worker-pipeline' containers/services.",
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
        logger.exception("health check raised; surfacing as ServiceHealthResult")
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
        logger.exception("health check raised; surfacing as ServiceHealthResult")
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

        if not spacy_ok:
            return _make_health_result(
                "ml_models",
                status=ServiceHealthRecord.STATUS_ERROR,
                label="SpaCy model missing.",
                issue=f"The required NLU model '{model_name}' is not installed in the environment.",
                fix=f"Run 'python -m spacy download {model_name}' inside the backend container.",
                success=False,
            )
        return _make_health_result(
            "ml_models",
            status=ServiceHealthRecord.STATUS_HEALTHY,
            label="ML models are loaded.",
            issue=(
                f"NLU ({model_name}) and Embedding ({embedding_model}) models are "
                f"available. Active device: {device_target}."
            ),
            fix="No action needed.",
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
        logger.exception("health check raised; surfacing via _make_check_failed_result")
        return _make_check_failed_result(
            "ml_models",
            e,
            label="ML environment check failed.",
            fix="Ensure 'sentence-transformers' and 'spacy' are installed in the Python environment.",
        )


def _build_model_runtime_metadata(
    summary: dict,
    active_model: dict,
    candidate_model: dict,
    backfill: dict,
    active_name: str,
    device_target: str,
) -> dict:
    """Pure function — flatten the model-registry summary into a metadata dict."""
    return {
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


def _model_runtime_result(
    metadata: dict,
    *,
    status: str,
    label: str,
    issue: str,
    fix: str,
    success: bool = True,
) -> ServiceHealthResult:
    """Builder — one ServiceHealthResult per model-runtime branch."""
    return _make_health_result(
        "model_runtime",
        metadata=metadata,
        status=status,
        label=label,
        issue=issue,
        fix=fix,
        success=success,
    )


def _make_health_result(  # noqa: forbidden-pattern too-many-args  # justification: keyword-only API used by 30+ callsites; dataclass would add 30+ object allocations per health-page render with no behavioural win.
    service_key: str,
    *,
    status: str,
    label: str,
    issue: str,
    fix: str,
    success: bool = True,
    metadata: dict | None = None,
    error_message: str = "",
) -> ServiceHealthResult:
    """Generic ServiceHealthResult builder — shared by every ``check_*_health`` function.

    Centralises the timestamp + (success_at OR error_at) routing so each check
    only supplies the per-branch fields. Pass ``success=False`` for any
    DOWN/ERROR/WARNING status that represents a probe failure (so
    ``last_error_at`` is set instead of ``last_success_at``).
    """
    now = timezone.now()
    return ServiceHealthResult(
        service_key=service_key,
        status=status,
        status_label=label,
        issue_description=issue,
        suggested_fix=fix,
        last_success_at=now if success else None,
        last_error_at=None if success else now,
        last_error_message=error_message,
        metadata=metadata,
    )


def _make_check_failed_result(
    service_key: str,
    error: Exception,
    *,
    label: str,
    fix: str,
) -> ServiceHealthResult:
    """Standard "the health check itself crashed" result.

    Replaces the ``except Exception as e: return ServiceHealthResult(...)``
    block at the bottom of every long check with a 1-line call.
    """
    return _make_health_result(
        service_key,
        status=ServiceHealthRecord.STATUS_ERROR,
        label=label,
        issue=f"Could not run health check: {error}",
        fix=fix,
        success=False,
        error_message=str(error),
    )


# Model-runtime state templates. Each entry: (key, status, label_tmpl, issue_tmpl, fix_tmpl, success).
# Keeps the per-state wording co-located + a constant rather than buried in an
# 80-line if-elif chain. Templates use .format(name=, device=, candidate_name=,
# candidate_status=, backfill_status=, active_status=).
_MODEL_RUNTIME_STATES: tuple[tuple[str, str, str, str, str, bool], ...] = (
    (
        "no_active",
        ServiceHealthRecord.STATUS_WARNING,
        "Runtime registry inferred the active model.",
        "The runtime registry has not been explicitly seeded yet, so the app "
        "inferred the active embedding model from current settings.",
        "Open Settings > Runtime so the app can register the active model and "
        "show full hot-swap diagnostics.",
        True,
    ),
    (
        "failed_or_deleted",
        ServiceHealthRecord.STATUS_ERROR,
        "Active model runtime is {active_status}.",
        "The active embedding model '{name}' is not ready to serve.",
        "Open Settings > Runtime, warm or roll back the champion model, and "
        "re-run the health check.",
        False,
    ),
    (
        "swap_in_progress",
        ServiceHealthRecord.STATUS_WARNING,
        "Model swap in progress.",
        "The active model is '{name}' on {device}, and a backfill is {backfill_status}.",
        "Let the backfill finish, or pause it from Settings > Runtime if you "
        "need to free resources.",
        True,
    ),
    (
        "candidate_waiting",
        ServiceHealthRecord.STATUS_WARNING,
        "Candidate model waiting for promotion.",
        "The active model is '{name}' on {device}, and candidate "
        "'{candidate_name}' is {candidate_status}.",
        "If the candidate looks good, promote it in Settings > Runtime. "
        "Otherwise drain or delete it to reclaim disk.",
        True,
    ),
    (
        "healthy",
        ServiceHealthRecord.STATUS_HEALTHY,
        "Runtime healthy: {name} on {device}.",
        "The active embedding model is '{name}' on {device}, and no swap or "
        "backfill is blocking work.",
        "No action needed.",
        True,
    ),
)


def _pick_model_runtime_state_key(
    active_model: dict,
    candidate_model: dict,
    backfill: dict,
    active_status: str,
) -> str:
    """Pick which row of ``_MODEL_RUNTIME_STATES`` matches the current state."""
    if not active_model:
        return "no_active"
    if active_status in {"failed", "deleted"}:
        return "failed_or_deleted"
    if backfill and backfill.get("status") in {"queued", "running", "paused"}:
        return "swap_in_progress"
    if candidate_model:
        return "candidate_waiting"
    return "healthy"


def _classify_model_runtime_state(
    active_model: dict,
    candidate_model: dict,
    backfill: dict,
    active_name: str,
    device_target: str,
    active_status: str,
) -> dict:
    """Return the kwargs dict for ``_model_runtime_result`` matching current state."""
    fmt = {
        "name": active_name,
        "device": device_target,
        "candidate_name": candidate_model.get("model_name", ""),
        "candidate_status": candidate_model.get("status", ""),
        "backfill_status": backfill.get("status", ""),
        "active_status": active_status,
    }
    state_key = _pick_model_runtime_state_key(
        active_model,
        candidate_model,
        backfill,
        active_status,
    )
    for key, status, label, issue, fix, success in _MODEL_RUNTIME_STATES:
        if key == state_key:
            return {
                "status": status,
                "label": label.format(**fmt),
                "issue": issue.format(**fmt),
                "fix": fix.format(**fmt),
                "success": success,
            }
    raise ValueError(
        f"Unknown model-runtime state key: {state_key}"
    )  # pragma: no cover


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
        metadata = _build_model_runtime_metadata(
            summary,
            active_model,
            candidate_model,
            backfill,
            active_name,
            device_target,
        )
        decision = _classify_model_runtime_state(
            active_model,
            candidate_model,
            backfill,
            active_name,
            device_target,
            active_status,
        )
        return _model_runtime_result(metadata, **decision)
    except Exception as e:
        logger.exception("health check raised; surfacing as ServiceHealthResult")
        return ServiceHealthResult(
            service_key="model_runtime",
            status=ServiceHealthRecord.STATUS_ERROR,
            status_label="Model runtime check failed.",
            issue_description=f"Could not read runtime registry state: {str(e)}",
            suggested_fix="Check the runtime registry tables and retry the health check.",
            last_error_at=timezone.now(),
            last_error_message=str(e),
        )


_HELPER_RAM_PRESSURE_WARN = 0.9
# Helper-state copy. Pulled out so _classify_helper_nodes_state stays small.
_HELPER_STATES: dict[str, dict[str, object]] = {
    "no_helpers": {
        "status": ServiceHealthRecord.STATUS_NOT_CONFIGURED,
        "label": "No helper nodes configured.",
        "issue": (
            "The primary machine is handling all work because no helper "
            "nodes have been registered yet."
        ),
        "fix": (
            "Open Settings > Helpers to register a helper node if you want "
            "to offload RAM-heavy or GPU-heavy background work."
        ),
        "success": True,
    },
    "all_stale": {
        "status": ServiceHealthRecord.STATUS_WARNING,
        "label": "Helpers are stale.",
        "issue": (
            "Helpers are registered, but their heartbeats are old enough that "
            "the scheduler is treating them as stale."
        ),
        "fix": (
            "Check the helper machines, then use Settings > Helpers to resume "
            "or remove the stale entries."
        ),
        "success": False,
    },
    "all_offline": {
        "status": ServiceHealthRecord.STATUS_WARNING,
        "label": "All helpers are offline.",
        "issue": (
            "Helper nodes are registered, but none are currently available for work."
        ),
        "fix": (
            "Bring a helper online or delete old registrations in Settings > Helpers."
        ),
        "success": False,
    },
    "ram_cap": {
        "status": ServiceHealthRecord.STATUS_WARNING,
        "label": "Helpers are near their RAM cap.",
        "issue": (
            "At least one helper is online, but the aggregate RAM pressure is "
            "high enough that new RAM-heavy jobs may stay on the primary node."
        ),
        "fix": (
            "Reduce helper load, add a stronger helper, or raise the helper RAM "
            "cap carefully in Settings > Helpers."
        ),
        "success": True,
    },
}


def _classify_helper_nodes_state(
    online_count: int,
    busy_count: int,
    stale_count: int,
    offline_count: int,
    aggregate_ram_pressure: float,
) -> dict:
    """Pure function — pick the matching state from ``_HELPER_STATES`` (or build healthy)."""
    if online_count + busy_count + stale_count + offline_count == 0:
        return dict(_HELPER_STATES["no_helpers"])
    if online_count == 0 and busy_count == 0 and stale_count > 0:
        return dict(_HELPER_STATES["all_stale"])
    if online_count == 0 and busy_count == 0 and offline_count > 0:
        return dict(_HELPER_STATES["all_offline"])
    if aggregate_ram_pressure >= _HELPER_RAM_PRESSURE_WARN:
        return dict(_HELPER_STATES["ram_cap"])
    return {
        "status": ServiceHealthRecord.STATUS_HEALTHY,
        "label": f"Helpers healthy ({online_count} online, {busy_count} busy).",
        "issue": (
            f"{online_count} helpers are online, {busy_count} are busy, and "
            "helper-assisted background execution is available."
        ),
        "fix": "No action needed.",
        "success": True,
    }


@HealthCheckRegistry.register(
    "helper_nodes",
    name="Helper Nodes",
    description="Distributed helper availability, RAM pressure, and helper-assisted execution capacity.",
)
def check_helper_nodes_health() -> ServiceHealthResult:
    try:
        from apps.core.runtime_registry import helper_status_counts

        summary = summarize_helpers()
        # Refactor 2026-05-04: shared helper_status_counts (also used by
        # diagnostics/views._helper_nodes_tile) — single source of truth
        # for the (online, busy, stale, offline) 4-tuple parsing.
        online_count, busy_count, stale_count, offline_count = helper_status_counts(
            summary
        )
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
        decision = _classify_helper_nodes_state(
            online_count,
            busy_count,
            stale_count,
            offline_count,
            aggregate_ram_pressure,
        )
        return _make_health_result("helper_nodes", metadata=metadata, **decision)
    except Exception as e:
        logger.exception("health check raised; surfacing via _make_check_failed_result")
        return _make_check_failed_result(
            "helper_nodes",
            e,
            label="Helper health check failed.",
            fix="Check the helper registry data and retry the health check.",
        )


@HealthCheckRegistry.register(
    "gpu_faiss",
    name="GPU & FAISS Index",
    description="CUDA GPU availability and persistent FAISS vector index for Stage 1 pipeline search.",
)
def _enrich_gpu_faiss_metadata_with_cuda(meta: dict, faiss_vram_mb: int) -> None:
    """Mutate ``meta`` with CUDA GPU properties + VRAM usage."""
    import torch

    bytes_per_mb = 1024 * 1024
    props = torch.cuda.get_device_properties(0)
    total_vram_mb = props.total_memory // bytes_per_mb
    used_vram_mb = (props.total_memory - torch.cuda.mem_get_info(0)[0]) // bytes_per_mb
    meta["gpu_name"] = props.name
    meta["vram_total_mb"] = total_vram_mb
    meta["vram_used_mb"] = used_vram_mb
    meta["faiss_vram_mb"] = faiss_vram_mb


def _classify_faiss_cpu_fallback(
    requested_mode: str,
    runtime_resolution: dict,
    faiss_vectors: int,
) -> dict:
    """Pick wording for the FAISS-on-CPU branch (with vs without High-mode mismatch)."""
    fallback_reason = runtime_resolution.get("reason") or "GPU path not active"
    if (
        requested_mode == "high"
        and runtime_resolution.get("effective_runtime_mode") == "cpu"
    ):
        issue = (
            "FAISS index is loaded but still running on CPU. High mode is "
            f"requested, but the live embedding runtime is still on CPU because {fallback_reason}."
        )
        fix = (
            "Open Settings > Performance and keep High Performance selected. "
            f"Then check the backend runtime for the CPU fallback reason: {fallback_reason}."
        )
    else:
        issue = (
            "FAISS index is loaded but running on CPU, not GPU. Stage 1 "
            "search is faster than NumPy but not at full GPU speed."
        )
        fix = (
            "Open Settings > Performance and switch to High Performance if "
            "you want GPU acceleration for embeddings and FAISS."
        )
    return {
        "status": ServiceHealthRecord.STATUS_WARNING,
        "label": f"FAISS on CPU ({faiss_vectors:,} vectors).",
        "issue": issue,
        "fix": fix,
        "success": True,
    }


def _build_gpu_faiss_metadata(
    cuda_available: bool,
    faiss_status: dict,
    requested_mode: str,
    runtime_resolution: dict,
) -> dict:
    """Pure function — flatten the GPU + FAISS state into a metadata dict."""
    meta = {
        "cuda_available": cuda_available,
        "faiss_active": faiss_status.get("active", False),
        "faiss_device": faiss_status.get("device", "none"),
        "faiss_vectors": faiss_status.get("vectors", 0),
        "performance_mode": requested_mode,
        "effective_runtime_mode": runtime_resolution.get("effective_runtime_mode"),
        "effective_runtime_reason": runtime_resolution.get("reason", ""),
    }
    if cuda_available:
        _enrich_gpu_faiss_metadata_with_cuda(meta, faiss_status.get("vram_mb", 0))
    return meta


def _classify_gpu_faiss_state(
    meta: dict,
    requested_mode: str,
    runtime_resolution: dict,
) -> dict:
    """Pure function — pick wording for FAISS not-loaded / on-CPU / GPU-active."""
    faiss_vectors = meta["faiss_vectors"]
    faiss_vram_mb = meta.get("faiss_vram_mb", 0)
    faiss_device = meta["faiss_device"]
    if not meta["faiss_active"]:
        return {
            "status": ServiceHealthRecord.STATUS_WARNING,
            "label": "FAISS index not loaded.",
            "issue": (
                "The FAISS vector index has not been built yet. Stage 1 pipeline "
                "is running on the slower NumPy CPU path."
            ),
            "fix": (
                "Trigger a pipeline run or wait for the next Celery Beat refresh "
                "(every 15 minutes). Check that content items have embeddings."
            ),
            "success": False,
        }
    if "GPU" not in faiss_device:
        return _classify_faiss_cpu_fallback(
            requested_mode, runtime_resolution, faiss_vectors
        )
    return {
        "status": ServiceHealthRecord.STATUS_HEALTHY,
        "label": f"FAISS-GPU active ({faiss_vectors:,} vectors, {faiss_vram_mb} MB VRAM).",
        "issue": (
            f"Persistent FAISS index is live on {faiss_device} with "
            f"{faiss_vectors:,} content embeddings."
        ),
        "fix": "No action needed.",
        "success": True,
    }


def check_gpu_faiss_health() -> ServiceHealthResult:
    try:
        import torch
        from apps.core.performance_mode import get_requested_performance_mode
        from apps.pipeline.services.embeddings import get_effective_runtime_resolution
        from apps.pipeline.services.faiss_index import get_faiss_status

        requested_mode = get_requested_performance_mode()
        runtime_resolution = get_effective_runtime_resolution()
        meta = _build_gpu_faiss_metadata(
            torch.cuda.is_available(),
            get_faiss_status(),
            requested_mode,
            runtime_resolution,
        )
        decision = _classify_gpu_faiss_state(meta, requested_mode, runtime_resolution)
        return _make_health_result("gpu_faiss", metadata=meta, **decision)
    except Exception as e:
        logger.exception("health check raised; surfacing via _make_check_failed_result")
        return _make_check_failed_result(
            "gpu_faiss",
            e,
            label="GPU/FAISS check failed.",
            fix="Ensure PyTorch and faiss-gpu-cu12 are installed in the backend container.",
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


_RECENT_DATA_WINDOW_DAYS = 7


def _compute_metric_lag_hours(latest_metric) -> float:
    """Hours between now and the latest SearchMetric.date (date, not datetime)."""
    return (
        timezone.now()
        - timezone.make_aware(
            timezone.datetime.combine(
                latest_metric.date,
                timezone.datetime.min.time(),
            )
        )
    ).total_seconds() / 3600


@dataclass
class _SearchMetricCheckConfig:
    """Bundle of strings + filters that drive ``_check_google_analytics_source_health``.

    Pulling the 18 ex-kwargs into a dataclass keeps the function body tiny
    AND lets the GA4 / GSC callers configure the check inline as a literal
    rather than via positional or keyword soup.
    """

    service_key: str
    setting_key: str
    source: str
    not_configured_label: str
    not_configured_issue: str
    not_configured_fix: str
    stale_threshold_setting: str
    stale_label: str
    stale_issue_template: str
    stale_fix: str
    empty_label: str
    empty_issue: str
    empty_fix: str
    healthy_label: str
    healthy_issue: str
    error_label: str
    error_fix: str
    enrich_metadata: Optional[Callable[[str, dict], None]] = None
    extra_metadata_provider: Optional[Callable[[str], dict]] = None


def _check_metric_freshness(
    cfg: _SearchMetricCheckConfig,
    latest_metric,
    metadata: dict,
) -> ServiceHealthResult | None:
    """Return STALE result if the latest metric is too old; mutates metadata."""
    if not latest_metric:
        return None
    lag_hours = _compute_metric_lag_hours(latest_metric)
    metadata["lag_hours"] = round(lag_hours, 1)
    stale_hours = get_health_setting(cfg.stale_threshold_setting, 72)
    if lag_hours <= stale_hours:
        return None
    return _make_health_result(
        cfg.service_key,
        metadata=metadata,
        status=ServiceHealthRecord.STATUS_STALE,
        label=cfg.stale_label,
        issue=cfg.stale_issue_template.format(
            date=latest_metric.date,
            lag_hours=round(lag_hours),
        ),
        fix=cfg.stale_fix,
    )


def _check_metric_recent_volume(
    cfg: _SearchMetricCheckConfig,
    latest_metric,
    metadata: dict,
) -> ServiceHealthResult:
    """Return WARNING (no recent data) or HEALTHY result based on 7-day row count."""
    recent_rows = SearchMetric.objects.filter(
        source=cfg.source,
        date__gte=(timezone.now() - timezone.timedelta(days=_RECENT_DATA_WINDOW_DAYS)),
    ).count()
    metadata["recent_7d_rows"] = recent_rows
    if latest_metric and recent_rows == 0:
        return _make_health_result(
            cfg.service_key,
            metadata=metadata,
            status=ServiceHealthRecord.STATUS_WARNING,
            label=cfg.empty_label,
            issue=cfg.empty_issue,
            fix=cfg.empty_fix,
        )
    return _make_health_result(
        cfg.service_key,
        metadata=metadata,
        status=ServiceHealthRecord.STATUS_HEALTHY,
        label=cfg.healthy_label,
        issue=cfg.healthy_issue,
        fix="No action needed.",
    )


def _check_google_analytics_source_health(
    cfg: _SearchMetricCheckConfig,
) -> ServiceHealthResult:
    """Shared body of GA4 + GSC health checks. Both follow the same shape:
    setting present? → fresh? → credentials valid? → recent data? → healthy."""
    setting_row = AppSetting.objects.filter(key=cfg.setting_key).first()
    if not setting_row or not setting_row.value:
        return _make_health_result(
            cfg.service_key,
            status=ServiceHealthRecord.STATUS_NOT_CONFIGURED,
            label=cfg.not_configured_label,
            issue=cfg.not_configured_issue,
            fix=cfg.not_configured_fix,
        )
    try:
        latest_metric = (
            SearchMetric.objects.filter(source=cfg.source).order_by("-date").first()
        )
        metadata = (
            cfg.extra_metadata_provider(setting_row.value)
            if cfg.extra_metadata_provider
            else {}
        )
        stale = _check_metric_freshness(cfg, latest_metric, metadata)
        if stale:
            return stale
        if cfg.enrich_metadata:
            cfg.enrich_metadata(setting_row.value, metadata)
        return _check_metric_recent_volume(cfg, latest_metric, metadata)
    except Exception as e:
        logger.exception("health check raised; surfacing via _make_check_failed_result")
        return _make_check_failed_result(
            cfg.service_key,
            e,
            label=cfg.error_label,
            fix=cfg.error_fix,
        )


@HealthCheckRegistry.register(
    "ga4",
    name="Google Analytics 4",
    description="Integration with Google Analytics Data API for telemetry metrics.",
)
def check_ga4_health() -> ServiceHealthResult:
    return _check_google_analytics_source_health(
        _SearchMetricCheckConfig(
            service_key="ga4",
            setting_key="analytics.ga4_property_id",
            source="ga4",
            not_configured_label="GA4 not configured.",
            not_configured_issue="Google Analytics 4 property ID is missing from settings.",
            not_configured_fix="Go to Settings > Analytics and provide your GA4 Property ID.",
            stale_threshold_setting="ga4_stale_threshold_hours",
            stale_label="GA4 data is stale.",
            stale_issue_template="Last GA4 data is from {date} ({lag_hours}h lag).",
            stale_fix="Check if the GA4 sync task is running or if the Google service account has been disabled.",
            empty_label="GA4 connected but no recent data.",
            empty_issue=(
                "GA4 API responds and credentials are valid, but zero rows were "
                "imported in the last 7 days. The integration may be misconfigured "
                "(wrong property ID, missing permissions, or no traffic)."
            ),
            empty_fix=(
                "Verify the GA4 property ID matches the correct site. Check that the "
                "service account has 'Viewer' access. Confirm the site is receiving traffic."
            ),
            healthy_label="GA4 connected.",
            healthy_issue="GA4 connectivity established and telemetry data is fresh.",
            error_label="GA4 connection failed.",
            error_fix="Verify your Google Service Account credentials and API permissions.",
            enrich_metadata=_ga4_enrich_credentials_and_quota,
            extra_metadata_provider=lambda value: {
                "property_id": value[-4:].rjust(len(value), "*"),
            },
        )
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
    def _enrich(site_url_value: str, _metadata: dict) -> None:
        _gsc_validate_credentials(site_url_value)

    return _check_google_analytics_source_health(
        _SearchMetricCheckConfig(
            service_key="gsc",
            setting_key="analytics.gsc_site_url",
            source="gsc",
            not_configured_label="GSC site URL missing.",
            not_configured_issue="Google Search Console site URL has not been defined.",
            not_configured_fix="Go to Settings > Analytics and provide your GSC Site URL.",
            stale_threshold_setting="gsc_stale_threshold_hours",
            stale_label="GSC data is stale.",
            stale_issue_template="Last GSC data is from {date} ({lag_hours}h lag).",
            stale_fix="Check the Search Console sync task logs and Google Cloud Project status.",
            empty_label="GSC connected but no recent data.",
            empty_issue=(
                "GSC API responds and credentials are valid, but zero rows were "
                "imported in the last 7 days. The site URL may be wrong, the service "
                "account may lack permissions, or the site has no search traffic."
            ),
            empty_fix=(
                "Verify the GSC site URL matches the correct property. Check that "
                "the service account is listed as a user in Search Console."
            ),
            healthy_label="GSC connected.",
            healthy_issue="Search Console data is being imported correctly.",
            error_label="GSC connection failed.",
            error_fix="Verify service account access to the property in GSC dashboard.",
            enrich_metadata=_enrich,
            extra_metadata_provider=lambda value: {"site_url": value},
        )
    )


def _check_matomo_preflight() -> ServiceHealthResult | None:
    """Verify Matomo is enabled + has a URL set. Short-circuit on failure."""
    matomo_enabled = AppSetting.objects.filter(key="analytics.matomo_enabled").first()
    if not matomo_enabled or matomo_enabled.value.lower() not in ("true", "1", "yes"):
        return _make_health_result(
            "matomo",
            status=ServiceHealthRecord.STATUS_NOT_ENABLED,
            label="Matomo disabled.",
            issue="Matomo tracking is currently turned off in settings.",
            fix="No action needed unless you wish to use Matomo analytics.",
        )
    matomo_url = AppSetting.objects.filter(key="analytics.matomo_url").first()
    if not matomo_url or not matomo_url.value:
        return _make_health_result(
            "matomo",
            status=ServiceHealthRecord.STATUS_NOT_CONFIGURED,
            label="Matomo URL missing.",
            issue="Matomo analytics enabled but no server URL provided.",
            fix="Provide your Matomo instance URL in Settings.",
        )
    return None


@HealthCheckRegistry.register(
    "matomo",
    name="Matomo Analytics",
    description="Self-hosted analytics alternative for privacy-focused tracking.",
)
def check_matomo_health() -> ServiceHealthResult:
    short_circuit = _check_matomo_preflight()
    if short_circuit:
        return short_circuit
    matomo_url = AppSetting.objects.filter(key="analytics.matomo_url").first()
    try:
        matomo_rows = SearchMetric.objects.filter(source="matomo").count()
        metadata = {"url": matomo_url.value, "total_rows": matomo_rows}
        if matomo_rows == 0:
            return _make_health_result(
                "matomo",
                metadata=metadata,
                status=ServiceHealthRecord.STATUS_WARNING,
                label="Matomo connected but no data imported.",
                issue=(
                    "Matomo API is reachable but zero analytics rows have been imported. "
                    "The site ID or auth token may be wrong, or no tracking data exists."
                ),
                fix=(
                    "Verify the Matomo site ID and auth token. Check that the Matomo "
                    "tracking code is installed on the target site."
                ),
            )
        return _make_health_result(
            "matomo",
            metadata=metadata,
            status=ServiceHealthRecord.STATUS_HEALTHY,
            label="Matomo connected.",
            issue=f"Matomo API is reachable and {matomo_rows:,} rows imported.",
            fix="No action needed.",
        )
    except Exception as e:
        logger.exception("health check raised; surfacing via _make_check_failed_result")
        return _make_check_failed_result(
            "matomo",
            e,
            label="Matomo connection failed.",
            fix="Check if your Matomo instance is online and the API token is valid.",
        )


# ── CMS & Feature Checkers ────────────────────────────────────────


_SYNC_LAG_STALE_HOURS = 48


def _check_sync_lag_or_none(
    service_key: str,
    metadata: dict,
    sync_filter: dict[str, list[str]],
    *,
    stale_label: str,
    stale_fix: str,
    stale_issue_template: str,
) -> ServiceHealthResult | None:
    """Shared helper — return a STALE result if the latest sync is older than
    ``_SYNC_LAG_STALE_HOURS``, else None. Mutates ``metadata['lag_hours']``."""
    latest_sync = (
        ContentItem.objects.filter(**sync_filter).order_by("-updated_at").first()
    )
    if latest_sync is None:
        return None
    lag_hours = (timezone.now() - latest_sync.updated_at).total_seconds() / 3600
    metadata["lag_hours"] = round(lag_hours, 1)
    if lag_hours <= _SYNC_LAG_STALE_HOURS:
        return None
    return _make_health_result(
        service_key,
        metadata=metadata,
        status=ServiceHealthRecord.STATUS_STALE,
        label=stale_label,
        issue=stale_issue_template.format(lag_hours=round(lag_hours)),
        fix=stale_fix,
    )


def _check_content_count_or_none(  # noqa: forbidden-pattern too-many-args  # justification: shared by XF + WP + Matomo content-count checks; bundling kwargs would double the call count.
    service_key: str,
    metadata: dict,
    count_filter: dict,
    *,
    item_label: str,
    empty_label: str,
    empty_issue: str,
    empty_fix: str,
    healthy_label: str,
    healthy_issue_template: str,
) -> ServiceHealthResult:
    """Shared helper — return WARNING (no content) or HEALTHY (n content items)."""
    item_count = ContentItem.objects.filter(**count_filter).count()
    metadata["content_items"] = item_count
    if item_count == 0:
        return _make_health_result(
            service_key,
            metadata=metadata,
            status=ServiceHealthRecord.STATUS_WARNING,
            label=empty_label,
            issue=empty_issue,
            fix=empty_fix,
        )
    return _make_health_result(
        service_key,
        metadata=metadata,
        status=ServiceHealthRecord.STATUS_HEALTHY,
        label=healthy_label,
        issue=healthy_issue_template.format(
            item_count=item_count, item_label=item_label
        ),
        fix="No action needed.",
    )


def _xf_check_credentials() -> ServiceHealthResult | None:
    """Verify XenForo API key. Return short-circuit result on failure, else None."""
    base_url = getattr(settings, "XENFORO_BASE_URL", "")
    api_key = getattr(settings, "XENFORO_API_KEY", "")
    if not base_url or not api_key:
        return _make_health_result(
            "xenforo",
            status=ServiceHealthRecord.STATUS_NOT_CONFIGURED,
            label="XenForo not configured.",
            issue="XenForo API URL or Key is missing.",
            fix="Configure XENFORO_BASE_URL and XENFORO_API_KEY in your environment variables.",
        )
    try:
        from apps.sync.services.xenforo_api import XenForoAPIClient

        client = XenForoAPIClient(base_url=base_url, api_key=api_key)
        if not client.verify_api_key():
            return _make_health_result(
                "xenforo",
                status=ServiceHealthRecord.STATUS_ERROR,
                label="XenForo API key rejected.",
                issue=(
                    "The XenForo server rejected the API key "
                    "(it may have been revoked or rotated)."
                ),
                fix="Re-generate the API key in XenForo Admin > API Keys and update XENFORO_API_KEY.",
                success=False,
            )
    except Exception as e:
        logger.exception("credential check raised; surfacing as ServiceHealthResult")
        return _make_health_result(
            "xenforo",
            status=ServiceHealthRecord.STATUS_ERROR,
            label="XenForo unreachable.",
            issue=f"Could not connect to XenForo to verify the API key: {e}",
            fix="Check if the XenForo server is online and XENFORO_BASE_URL is correct.",
            success=False,
            error_message=str(e),
        )
    return None


@HealthCheckRegistry.register(
    "xenforo",
    name="XenForo Forum",
    description="Primary content source for internal linking and discussion graph.",
)
def check_xenforo_health() -> ServiceHealthResult:
    short_circuit = _xf_check_credentials()
    if short_circuit:
        return short_circuit
    try:
        metadata = {"base_url": getattr(settings, "XENFORO_BASE_URL", "")}
        stale = _check_sync_lag_or_none(
            "xenforo",
            metadata,
            {"content_type__in": ["thread", "post"]},
            stale_label="XenForo sync is stale.",
            stale_issue_template="No new content synced from XenForo in {lag_hours} hours.",
            stale_fix="Manually trigger a sync from the Jobs page or check the XenForo API logs.",
        )
        if stale:
            return stale
        return _check_content_count_or_none(
            "xenforo",
            metadata,
            {"content_type__in": ["thread", "resource"]},
            item_label="content items",
            empty_label="XenForo connected but no content imported.",
            empty_issue=(
                "XenForo API is reachable but zero content items exist in the database. "
                "The API key may have insufficient permissions, or the forum is empty."
            ),
            empty_fix=(
                "Trigger a full sync from the Jobs page. Check that the API key has "
                "read permissions for threads and resources."
            ),
            healthy_label="XenForo connected.",
            healthy_issue_template="XenForo API is reachable and {item_count:,} {item_label} are synced.",
        )
    except Exception as e:
        logger.exception("health check raised; surfacing via _make_check_failed_result")
        return _make_check_failed_result(
            "xenforo",
            e,
            label="XenForo check failed.",
            fix="Check if your XenForo instance is up and the API key has 'read' permissions.",
        )


@HealthCheckRegistry.register(
    "wordpress",
    name="WordPress Site",
    description="Secondary content source for blog posts and page linking.",
)
def _wp_check_credentials() -> ServiceHealthResult | None:
    """Verify WordPress base URL + Application Password. Short-circuit on failure."""
    base_url = getattr(settings, "WORDPRESS_BASE_URL", "")
    if not base_url:
        return _make_health_result(
            "wordpress",
            status=ServiceHealthRecord.STATUS_NOT_CONFIGURED,
            label="WordPress not configured.",
            issue="WordPress base URL is missing.",
            fix="Configure WORDPRESS_BASE_URL in your environment variables.",
        )
    try:
        from apps.sync.services.wordpress_api import WordPressAPIClient

        wp_client = WordPressAPIClient()
        if wp_client.has_credentials:
            result = wp_client.verify_credentials()
            if not result["ok"]:
                return _make_health_result(
                    "wordpress",
                    status=ServiceHealthRecord.STATUS_ERROR,
                    label="WordPress credentials rejected.",
                    issue=(
                        f"The WordPress Application Password was rejected "
                        f"(HTTP {HTTP_UNAUTHORIZED}). It may have been revoked."
                    ),
                    fix=(
                        "Re-generate the Application Password in WordPress Users "
                        "> Profile and update WORDPRESS_APP_PASSWORD."
                    ),
                    success=False,
                )
    except Exception as e:
        logger.exception("credential check raised; surfacing as ServiceHealthResult")
        return _make_health_result(
            "wordpress",
            status=ServiceHealthRecord.STATUS_ERROR,
            label="WordPress unreachable.",
            issue=f"Could not connect to WordPress to verify credentials: {e}",
            fix="Check if the WordPress server is online and WORDPRESS_BASE_URL is correct.",
            success=False,
            error_message=str(e),
        )
    return None


def check_wordpress_health() -> ServiceHealthResult:
    short_circuit = _wp_check_credentials()
    if short_circuit:
        return short_circuit
    try:
        metadata = {"base_url": getattr(settings, "WORDPRESS_BASE_URL", "")}
        stale = _check_sync_lag_or_none(
            "wordpress",
            metadata,
            {"content_type__in": ["wp_post", "wp_page"]},
            stale_label="WordPress sync is stale.",
            stale_issue_template="No new content synced from WordPress in {lag_hours} hours.",
            stale_fix="Check the WordPress Application Password or manually trigger a sync.",
        )
        if stale:
            return stale
        return _check_content_count_or_none(
            "wordpress",
            metadata,
            {"content_type": "wp_post"},
            item_label="posts",
            empty_label="WordPress connected but no content imported.",
            empty_issue=(
                "WordPress API is reachable but zero posts exist in the database. "
                "The Application Password may lack read permissions, or the site has no posts."
            ),
            empty_fix=(
                "Trigger a full WordPress sync from the Jobs page. Verify the "
                "Application Password has 'read' scope."
            ),
            healthy_label="WordPress connected.",
            healthy_issue_template="WordPress API is reachable and {item_count:,} {item_label} are synced.",
        )
    except Exception as e:
        logger.exception("health check raised; surfacing via _make_check_failed_result")
        return _make_check_failed_result(
            "wordpress",
            e,
            label="WordPress check failed.",
            fix="Ensure the WordPress instance is online and the REST API is not blocked.",
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
        logger.exception("health check raised; surfacing as ServiceHealthResult")
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

        # Single bulk query (DRY + perf) replaces the per-key .exists() loop.
        existing_keys = set(
            AppSetting.objects.filter(key__in=PRESET_DEFAULTS).values_list(
                "key", flat=True
            )
        )
        missing_weights = [k for k in PRESET_DEFAULTS if k not in existing_keys]
        total_plugins = Plugin.objects.count()
        enabled_plugins = Plugin.objects.filter(is_enabled=True).count()
        meta = {"enabled_plugins": enabled_plugins, "total_plugins": total_plugins}

        if missing_weights:
            return _make_health_result(
                "weights_plugins",
                metadata=meta,
                status=ServiceHealthRecord.STATUS_WARNING,
                label="Optimization weights incomplete.",
                issue=f"Missing core ranking weights: {', '.join(missing_weights)}.",
                fix="Set the ranking weight presets in Settings > Optimization.",
                success=False,
            )
        return _make_health_result(
            "weights_plugins",
            metadata=meta,
            status=ServiceHealthRecord.STATUS_HEALTHY,
            label="Weights and Plugins healthy.",
            issue=(
                f"Ranking weights are correctly defined, and {enabled_plugins} plugins are active."
            ),
            fix="No action needed.",
        )
    except Exception as e:
        logger.exception("health check raised; surfacing via _make_check_failed_result")
        return _make_check_failed_result(
            "weights_plugins",
            e,
            label="Configuration check failed.",
            fix="Check database integrity for core settings and plugin tables.",
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
        logger.exception("health check raised; surfacing as ServiceHealthResult")
        return ServiceHealthResult(
            service_key="webhooks",
            status=ServiceHealthRecord.STATUS_ERROR,
            status_label="Webhook check failed.",
            issue_description=f"Error querying webhook receipt logs: {str(e)}",
            suggested_fix="Check database connectivity and ensure the sync app is properly installed.",
            last_error_at=timezone.now(),
            last_error_message=str(e),
        )


_PIPELINE_FAILURE_BURST_COUNT = 3
_PIPELINE_FAILURE_BURST_HOURS = 24


def _classify_pipeline_state(  # noqa: forbidden-pattern too-many-args  # justification: pipeline state has 8 orthogonal axes; a dataclass adds friction without simplifying the decision tree.
    failed: int,
    completed: int,
    terminal: int,
    success_rate: int,
    hours_since: float,
    no_run_threshold: float,
    failure_threshold: float,
    last_run,
) -> dict | None:
    """Pure function — pick the matching kwargs dict for the pipeline check, or
    None to signal HEALTHY (caller builds the healthy result)."""
    if (
        failed >= _PIPELINE_FAILURE_BURST_COUNT
        and hours_since < _PIPELINE_FAILURE_BURST_HOURS
    ):
        return {
            "status": ServiceHealthRecord.STATUS_ERROR,
            "label": f"Pipeline failing — {failed} failures in 7 days.",
            "issue": (
                f"{failed} pipeline runs have failed in the last 7 days "
                f"(success rate: {success_rate}%)."
            ),
            "fix": (
                "Check the pipeline logs for the error message. Common causes: "
                "embedding model not loaded, database constraint, or out of memory."
            ),
            "success": False,
        }
    if hours_since > no_run_threshold:
        return {
            "status": ServiceHealthRecord.STATUS_WARNING,
            "label": f"No pipeline run in {round(hours_since)}h.",
            "issue": f"The last pipeline run was {round(hours_since)} hours ago.",
            "fix": "Check the scheduled pipeline task in Celery Beat, or trigger a manual run from Jobs.",
            "success": last_run.run_state == "completed",
        }
    if success_rate < (_PERCENT_BASE - failure_threshold):
        return {
            "status": ServiceHealthRecord.STATUS_WARNING,
            "label": f"Pipeline success rate is {success_rate}% (7d).",
            "issue": f"{failed} of {terminal} pipeline runs failed in the last 7 days.",
            "fix": "Review failed pipeline run logs for recurring errors.",
            "success": True,
        }
    return None


@HealthCheckRegistry.register(
    "pipeline_health",
    name="Suggestion Pipeline",
    description="Core linking engine — generates internal link suggestions from content.",
)
def check_pipeline_health() -> ServiceHealthResult:
    try:
        if PipelineRun.objects.count() == 0:
            return _make_health_result(
                "pipeline_health",
                status=ServiceHealthRecord.STATUS_NOT_CONFIGURED,
                label="No pipeline runs yet.",
                issue="The suggestion pipeline has never run.",
                fix="Trigger a pipeline run from the Jobs page.",
            )
        since_7d = timezone.now() - timedelta(days=7)
        recent = PipelineRun.objects.filter(created_at__gte=since_7d)
        completed = recent.filter(run_state="completed").count()
        failed = recent.filter(run_state="failed").count()
        terminal = completed + failed
        success_rate = (
            round((completed / terminal) * _PERCENT_BASE) if terminal else _PERCENT_BASE
        )
        last_run = PipelineRun.objects.order_by("-created_at").first()
        hours_since = (timezone.now() - last_run.created_at).total_seconds() / 3600
        meta = {
            "completed_7d": completed,
            "failed_7d": failed,
            "success_rate_7d": success_rate,
            "hours_since_last_run": round(hours_since, 1),
            "last_run_state": last_run.run_state,
        }
        decision = _classify_pipeline_state(
            failed,
            completed,
            terminal,
            success_rate,
            hours_since,
            get_health_setting("pipeline_warning_hours_no_run", 24),
            get_health_setting("pipeline_failure_rate_warning_pct", 20),
            last_run,
        )
        if decision is not None:
            return _make_health_result("pipeline_health", metadata=meta, **decision)
        return _make_health_result(
            "pipeline_health",
            metadata=meta,
            status=ServiceHealthRecord.STATUS_HEALTHY,
            label=f"Pipeline healthy ({success_rate}% success, 7d).",
            issue=f"{completed} successful runs in the last 7 days.",
            fix="No action needed.",
        )
    except Exception as e:
        logger.exception("health check raised; surfacing via _make_check_failed_result")
        return _make_check_failed_result(
            "pipeline_health",
            e,
            label="Pipeline check failed.",
            fix="Check database connectivity.",
        )


_CELERY_QUEUE_NAMES = ("default", "pipeline", "embeddings")


def _classify_celery_queue_depth(
    worst_queue: str,
    worst_depth: int,
    total: int,
    warn_threshold: int,
    error_threshold: int,
) -> dict:
    """Pick the matching kwargs for celery-queue-depth check."""
    if worst_depth >= error_threshold:
        return {
            "status": ServiceHealthRecord.STATUS_ERROR,
            "label": f"Queue overflow — {worst_depth} tasks in '{worst_queue}'.",
            "issue": (
                f"The '{worst_queue}' queue has {worst_depth} tasks waiting "
                f"(threshold: {error_threshold})."
            ),
            "fix": "Scale up Celery workers or investigate why tasks are not being consumed.",
            "success": False,
        }
    if worst_depth >= warn_threshold:
        return {
            "status": ServiceHealthRecord.STATUS_WARNING,
            "label": f"Queue building up — {worst_depth} tasks in '{worst_queue}'.",
            "issue": f"The '{worst_queue}' queue has {worst_depth} tasks waiting.",
            "fix": "Monitor queue depth — if it keeps growing, add more Celery workers.",
            "success": True,
        }
    return {
        "status": ServiceHealthRecord.STATUS_HEALTHY,
        "label": f"Queues clear ({total} total pending).",
        "issue": "All Celery queues are processing normally.",
        "fix": "No action needed.",
        "success": True,
    }


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
        depths = {q: r.llen(q) for q in _CELERY_QUEUE_NAMES}
        total = sum(depths.values())
        meta = {f"{q}_depth": depths[q] for q in _CELERY_QUEUE_NAMES}
        meta["total_depth"] = total
        worst_queue = max(depths, key=lambda q: depths[q])
        decision = _classify_celery_queue_depth(
            worst_queue,
            depths[worst_queue],
            total,
            get_health_setting("celery_queue_warning_depth", 50),
            get_health_setting("celery_queue_error_depth", _DEFAULT_CELERY_ERROR_DEPTH),
        )
        return _make_health_result("celery_queues", metadata=meta, **decision)
    except Exception as e:
        logger.exception("health check raised; surfacing via _make_check_failed_result")
        return _make_check_failed_result(
            "celery_queues",
            e,
            label="Queue depth check failed.",
            fix="Ensure Redis is running and CELERY_BROKER_URL is correct.",
        )


_BEAT_PROBE_TASK_NAME = "periodic-system-health-check"
_BEAT_EXPECTED_INTERVAL_MIN = 30
_BEAT_STALE_MULTIPLIER = 1.5


def _classify_celery_beat_state(
    minutes_ago: float,
    stale_minutes: float,
) -> dict:
    """Pick the matching kwargs for celery-beat freshness check."""
    if minutes_ago > stale_minutes * _BEAT_STALE_MULTIPLIER:
        return {
            "status": ServiceHealthRecord.STATUS_ERROR,
            "label": f"Beat stale — last run {round(minutes_ago)}m ago.",
            "issue": (
                f"Celery Beat last ran {round(minutes_ago)} minutes ago "
                f"(expected every {_BEAT_EXPECTED_INTERVAL_MIN} min)."
            ),
            "fix": "Restart the 'celery-beat' container. Check for lock file conflicts.",
            "success": False,
        }
    if minutes_ago > stale_minutes:
        return {
            "status": ServiceHealthRecord.STATUS_WARNING,
            "label": f"Beat delayed — last run {round(minutes_ago)}m ago.",
            "issue": (
                f"Celery Beat ran {round(minutes_ago)} minutes ago "
                f"(expected every {_BEAT_EXPECTED_INTERVAL_MIN} min)."
            ),
            "fix": "Monitor — if this continues, restart the 'celery-beat' container.",
            "success": True,
        }
    return {
        "status": ServiceHealthRecord.STATUS_HEALTHY,
        "label": f"Beat is running (last run {round(minutes_ago)}m ago).",
        "issue": "Celery Beat scheduler is firing on schedule.",
        "fix": "No action needed.",
        "success": True,
    }


@HealthCheckRegistry.register(
    "celery_beat",
    name="Celery Beat Scheduler",
    description="Scheduled task runner that triggers periodic jobs (syncs, health checks, etc.).",
)
def check_celery_beat_health() -> ServiceHealthResult:
    try:
        from django_celery_beat.models import PeriodicTask

        try:
            task = PeriodicTask.objects.get(name=_BEAT_PROBE_TASK_NAME)
        except PeriodicTask.DoesNotExist:
            return _make_health_result(
                "celery_beat",
                status=ServiceHealthRecord.STATUS_NOT_CONFIGURED,
                label="Beat probe task not found.",
                issue=f"The '{_BEAT_PROBE_TASK_NAME}' periodic task is missing from the database.",
                fix="Run migrations to re-seed the Celery Beat schedule.",
            )
        meta = {"expected_interval_minutes": _BEAT_EXPECTED_INTERVAL_MIN}
        if task.last_run_at is None:
            return _make_health_result(
                "celery_beat",
                metadata=meta,
                status=ServiceHealthRecord.STATUS_WARNING,
                label="Beat has not run yet.",
                issue="Celery Beat has never executed the health check task. It may not be running.",
                fix="Ensure the 'celery-beat' service is running.",
            )
        minutes_ago = (timezone.now() - task.last_run_at).total_seconds() / 60
        meta["last_run_minutes_ago"] = round(minutes_ago, 1)
        decision = _classify_celery_beat_state(
            minutes_ago,
            get_health_setting("beat_stale_threshold_minutes", 60),
        )
        return _make_health_result("celery_beat", metadata=meta, **decision)
    except Exception as e:
        logger.exception("health check raised; surfacing via _make_check_failed_result")
        return _make_check_failed_result(
            "celery_beat",
            e,
            label="Beat check failed.",
            fix="Check database connectivity and django-celery-beat migrations.",
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
        logger.exception("health check raised; surfacing as ServiceHealthResult")
        return ServiceHealthResult(
            service_key="sitemaps",
            status=ServiceHealthRecord.STATUS_ERROR,
            status_label="Sitemap check failed.",
            last_error_at=timezone.now(),
            last_error_message=str(e),
        )


def _classify_crawler_session_state(latest) -> dict:
    """Pick wording for a single CrawlSession's status."""
    if latest.status == "failed":
        return {
            "status": ServiceHealthRecord.STATUS_WARNING,
            "label": f"Last crawl failed ({latest.site_domain}).",
            "issue": (
                latest.error_message[:_CRAWL_ERROR_PREVIEW_CHARS]
                if latest.error_message
                else "Unknown error."
            ),
            "fix": "Check the error message and try running the crawl again.",
            "success": False,
        }
    if latest.status == "running":
        return {
            "status": ServiceHealthRecord.STATUS_HEALTHY,
            "label": f"Crawl running — {latest.pages_crawled} pages done.",
            "issue": "",
            "fix": "",
            "success": True,
        }
    return {
        "status": ServiceHealthRecord.STATUS_HEALTHY,
        "label": (
            f"Last crawl: {latest.status} — {latest.pages_crawled} "
            f"pages ({latest.site_domain})."
        ),
        "issue": "",
        "fix": "",
        "success": True,
    }


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
            return _make_health_result(
                "crawler_status",
                status=ServiceHealthRecord.STATUS_NOT_CONFIGURED,
                label="No crawl sessions yet.",
                issue="The web crawler has never been run.",
                fix="Go to the Web Crawler page and start your first crawl.",
            )
        meta = {
            "last_status": latest.status,
            "pages_crawled": latest.pages_crawled,
            "domain": latest.site_domain,
        }
        return _make_health_result(
            "crawler_status",
            metadata=meta,
            **_classify_crawler_session_state(latest),
        )
    except Exception as e:
        logger.exception("health check raised; surfacing via _make_check_failed_result")
        return _make_check_failed_result(
            "crawler_status",
            e,
            label="Crawler status check failed.",
            fix="Check the crawler models and database connectivity.",
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
        logger.exception("health check raised; surfacing as ServiceHealthResult")
        return ServiceHealthResult(
            service_key="crawler_storage",
            status=ServiceHealthRecord.STATUS_ERROR,
            status_label="Crawler storage check failed.",
            last_error_at=timezone.now(),
            last_error_message=str(e),
        )


_BYTES_PER_GIGABYTE = 1024**3


def _classify_disk_space(
    free_gb: float,
    total_gb: float,
    usage_pct: float,
    warn_pct: float,
    error_pct: float,
) -> dict:
    """Pick wording for a disk-usage percentage."""
    if usage_pct >= error_pct:
        return {
            "status": ServiceHealthRecord.STATUS_ERROR,
            "label": f"Disk critically full — {usage_pct}% used.",
            "issue": f"Only {free_gb} GB free of {total_gb} GB total. Services may fail.",
            "fix": "Delete old logs, clear Docker image cache (`docker image prune -f`), or expand the volume.",
            "success": False,
        }
    if usage_pct >= warn_pct:
        return {
            "status": ServiceHealthRecord.STATUS_WARNING,
            "label": f"Disk filling up — {usage_pct}% used.",
            "issue": f"{free_gb} GB remaining of {total_gb} GB total.",
            "fix": "Clear old Docker images with `docker image prune -f` and review log rotation.",
            "success": True,
        }
    return {
        "status": ServiceHealthRecord.STATUS_HEALTHY,
        "label": f"Disk healthy — {free_gb} GB free ({usage_pct}% used).",
        "issue": f"{free_gb} GB free of {total_gb} GB total.",
        "fix": "No action needed.",
        "success": True,
    }


@HealthCheckRegistry.register(
    "disk_space",
    name="Disk Space",
    description="Available storage on the server filesystem (models, logs, media).",
)
def check_disk_space() -> ServiceHealthResult:
    import shutil

    try:
        usage = shutil.disk_usage("/app")
        total_gb = round(usage.total / _BYTES_PER_GIGABYTE, 1)
        used_gb = round(usage.used / _BYTES_PER_GIGABYTE, 1)
        free_gb = round(usage.free / _BYTES_PER_GIGABYTE, 1)
        usage_pct = round((usage.used / usage.total) * _PERCENT_BASE, 1)
        meta = {
            "total_gb": total_gb,
            "used_gb": used_gb,
            "free_gb": free_gb,
            "usage_pct": usage_pct,
        }
        decision = _classify_disk_space(
            free_gb,
            total_gb,
            usage_pct,
            get_health_setting("disk_warning_pct", 80),
            get_health_setting("disk_error_pct", 90),
        )
        return _make_health_result("disk_space", metadata=meta, **decision)
    except Exception as e:
        logger.exception("health check raised; surfacing via _make_check_failed_result")
        return _make_check_failed_result(
            "disk_space",
            e,
            label="Disk space check failed.",
            fix="Check filesystem permissions.",
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
    record = _persist_health_record(service_key, result)
    _emit_or_resolve_health_alert(service_key, result)
    return record


_DEGRADED_STATUSES = (
    ServiceHealthRecord.STATUS_ERROR,
    ServiceHealthRecord.STATUS_DOWN,
    ServiceHealthRecord.STATUS_STALE,
)


def _persist_health_record(
    service_key: str, result: ServiceHealthResult
) -> ServiceHealthRecord:
    """Create-or-update the ``ServiceHealthRecord`` row for ``service_key``."""
    record, _ = ServiceHealthRecord.objects.get_or_create(
        service_key=service_key,
        defaults={"last_check_at": timezone.now(), "status_label": "Initializing..."},
    )
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
    return record


def _emit_or_resolve_health_alert(
    service_key: str, result: ServiceHealthResult
) -> None:
    """Emit an OperatorAlert on degraded statuses, resolve it on healthy."""
    dedupe_key = f"health.{service_key}"
    if result.status in _DEGRADED_STATUSES:
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
