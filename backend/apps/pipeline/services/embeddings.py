"""Embedding generation service.

V2 change from V1: eliminates .npy file artifacts entirely.
Embeddings are stored directly in pgvector VectorField columns on
ContentItem and Sentence models. The sentence-transformers model is
loaded once and cached in process.

Performance mode is controlled by the canonical performance-mode resolver:
  balanced (default) — CPU only, batch_size=32
  high               — GPU if CUDA available, batch_size starts at 128
                       and backs off automatically if memory pressure is hit
"""

from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timezone
from typing import Any

import numpy as np
from django.conf import settings

from apps.core.performance_mode import (
    PERFORMANCE_MODE_HIGH,
    get_requested_performance_mode,
)

try:
    from extensions import l2norm

    HAS_CPP_EXT = True
except ImportError:
    HAS_CPP_EXT = False

logger = logging.getLogger(__name__)

DEFAULT_MODEL_NAME = "BAAI/bge-m3"
EMBEDDING_DIM = 1024
STORAGE_VECTOR_MAX_DIM = 16_000

_model_cache: dict[str, Any] = {}
_CPU_THREAD_HEADROOM = 2
_GPU_RESUME_DELTA_C = 10
_GPU_TEMP_RESUME_FLOOR_C = 50
_PERCENT_TO_FRACTION = 100.0


# ---------------------------------------------------------------------------
# Model loading
# ---------------------------------------------------------------------------


def _resolve_device() -> str:
    """Return 'cuda' or 'cpu' based on the canonical performance mode.

    When CUDA is selected, applies mode-dependent VRAM fraction limits
    as documented in docs/PERFORMANCE.md §6 (GPU Self-Limiting) AND runs a
    tiny warmup op (plan item 15). A driver can report CUDA available but
    fail on the first real op (bad VRAM state, thermal throttle at boot,
    etc.); warmup catches those silent failures so we fall back to CPU
    with a loud alert instead of crashing mid-pipeline.

    If the user asked for High Performance but GPU is unavailable, emit the
    named operator-alert rule from notifications/alert_rules.py so they know
    the system silently dropped to CPU (plan item 10, rule d).
    """
    return _get_effective_runtime_resolution(
        apply_vram_cap=True,
        emit_alerts=True,
    )["device"]


def _cuda_warmup_ok() -> bool:
    """Run a tiny GPU op to confirm CUDA actually works, not just reports-available.

    Returns True if a 1x1 tensor allocation + multiplication succeeds.  Any
    exception (OOM, driver fault, thermal pause) returns False and the caller
    falls back to CPU.  Logged at warning level so the failure is visible in
    container logs.
    """
    try:
        import torch

        t = torch.ones(1, device="cuda")
        _ = (t * 2).sum().item()
        torch.cuda.synchronize()
        return True
    except Exception as exc:  # broad on purpose — any CUDA failure must fall back
        logger.warning("CUDA warmup failed: %s", exc)
        return False


def _emit_gpu_fallback_alert(reason: str) -> None:
    """Best-effort alert emit. Never raises — embeddings must keep working."""
    try:
        from apps.notifications.alert_rules import alert_gpu_fallback_to_cpu

        alert_gpu_fallback_to_cpu(reason=reason)
    except Exception:
        logger.debug("Failed to emit gpu-fallback alert", exc_info=True)


def _read_performance_setting(key: str) -> str | None:
    try:
        from apps.core.models import AppSetting

        return (
            AppSetting.objects.filter(key=key).values_list("value", flat=True).first()
        )
    except Exception:
        logger.debug("AppSetting unavailable for %s", key, exc_info=True)
        return None


def _read_performance_int(
    key: str,
    default: int,
    *,
    minimum: int | None = None,
    maximum: int | None = None,
) -> int:
    value = _read_performance_setting(key)
    if value in (None, ""):
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    if minimum is not None and parsed < minimum:
        return default
    if maximum is not None and parsed > maximum:
        return default
    return parsed


def _read_performance_bool(key: str, default: bool) -> bool:
    value = _read_performance_setting(key)
    if value is None:
        return default
    lowered = str(value).strip().lower()
    if lowered in {"1", "true", "yes", "on"}:
        return True
    if lowered in {"0", "false", "no", "off"}:
        return False
    return default


def _get_performance_mode() -> str:
    return get_requested_performance_mode()


def _get_effective_runtime_resolution(
    *,
    apply_vram_cap: bool = False,
    emit_alerts: bool = False,
) -> dict[str, str]:
    """Resolve the actual runtime that embeddings would use right now."""
    mode = _get_performance_mode()
    resolution = {
        "performance_mode": mode,
        "effective_runtime_mode": "cpu",
        "device": "cpu",
        "reason": "High mode not requested",
    }

    if mode != PERFORMANCE_MODE_HIGH:
        return resolution

    try:
        import torch
    except ImportError:
        logger.debug("torch not installed, falling back to CPU")
        if emit_alerts:
            _emit_gpu_fallback_alert("torch not installed")
        resolution["reason"] = "torch not installed"
        return resolution

    if not torch.cuda.is_available():
        if emit_alerts:
            _emit_gpu_fallback_alert("CUDA unavailable")
        resolution["reason"] = "CUDA unavailable"
        return resolution

    if not _cuda_warmup_ok():
        if emit_alerts:
            _emit_gpu_fallback_alert("CUDA warmup failed")
        resolution["reason"] = "CUDA warmup failed"
        return resolution

    if apply_vram_cap:
        _apply_vram_fraction()

    resolution.update(
        {
            "effective_runtime_mode": "gpu",
            "device": "cuda",
            "reason": "",
        }
    )
    return resolution


def get_effective_runtime_resolution() -> dict[str, str]:
    """Public read-only view of the current embedding runtime choice."""
    return _get_effective_runtime_resolution(
        apply_vram_cap=False,
        emit_alerts=False,
    )


def _get_cpu_thread_cap() -> int:
    logical_processors = os.cpu_count() or 4
    return max(1, logical_processors - _CPU_THREAD_HEADROOM)


def _get_cpu_encode_threads() -> int:
    return _read_performance_int(
        "system.cpu_encode_threads",
        default=min(4, _get_cpu_thread_cap()),
        minimum=1,
        maximum=_get_cpu_thread_cap(),
    )


def _get_gpu_memory_budget_fraction() -> float:
    raw_budget_pct = _read_performance_int(
        "system.gpu_memory_budget_pct",
        default=0,
        minimum=25,
        maximum=80,
    )
    if raw_budget_pct:
        return raw_budget_pct / _PERCENT_TO_FRACTION
    if _get_performance_mode() == PERFORMANCE_MODE_HIGH:
        return getattr(settings, "CUDA_MEMORY_FRACTION_HIGH", 0.60)
    return getattr(settings, "CUDA_MEMORY_FRACTION_SAFE", 0.25)


def _get_gpu_temp_pause_c() -> int:
    return _read_performance_int(
        "system.gpu_temp_pause_c",
        default=getattr(settings, "GPU_TEMP_CEILING_C", 90),
        minimum=75,
        maximum=95,
    )


def _get_gpu_temp_resume_c() -> int:
    configured_pause = _read_performance_int(
        "system.gpu_temp_pause_c",
        default=0,
        minimum=75,
        maximum=95,
    )
    if not configured_pause:
        return getattr(settings, "GPU_TEMP_RESUME_C", 80)
    return max(_GPU_TEMP_RESUME_FLOOR_C, configured_pause - _GPU_RESUME_DELTA_C)


def _aggressive_oom_backoff_enabled() -> bool:
    return _read_performance_bool("system.aggressive_oom_backoff", True)


def _apply_vram_fraction() -> None:
    """Set per-process VRAM cap based on current performance mode.

    Safe/Balanced = 25% (1.5 GB on RTX 3050 6 GB).
    High Performance = 80% (4.8 GB on RTX 3050 6 GB).

    These percentages are relative to detected VRAM — they scale
    automatically with GPU upgrades.  See docs/PERFORMANCE.md §6.
    """
    try:
        import torch

        perf_mode = _get_performance_mode()
        fraction = _get_gpu_memory_budget_fraction()

        torch.cuda.set_per_process_memory_fraction(fraction)
        logger.info(
            "GPU VRAM fraction set to %.0f%% (mode=%s)", fraction * 100, perf_mode
        )
    except Exception:
        logger.warning("Failed to set VRAM fraction", exc_info=True)


def _check_gpu_temperature() -> bool:
    """Check GPU temperature against the hard ceiling.

    Returns True if safe to proceed, False if too hot.
    Temperature ceiling is configurable via GPU_TEMP_CEILING_C
    (default 90°C).  See docs/PERFORMANCE.md §6.
    """
    try:
        import pynvml

        pynvml.nvmlInit()
        handle = pynvml.nvmlDeviceGetHandleByIndex(0)
        temp = pynvml.nvmlDeviceGetTemperature(handle, pynvml.NVML_TEMPERATURE_GPU)
        pynvml.nvmlShutdown()

        ceiling = _get_gpu_temp_pause_c()

        if temp >= ceiling:
            logger.warning(
                "GPU temperature %d°C >= %d°C ceiling — pausing GPU work",
                temp,
                ceiling,
            )
            return False
        return True
    except Exception:
        # If pynvml is not available, assume safe (CPU fallback handles it).
        return True


def _thermal_guard_before_gpu_batch() -> None:
    """Pause GPU work if the chip is at or above the temperature ceiling.

    No-op on CPU-only environments (pynvml ImportError is swallowed
    by ``_check_gpu_temperature``). Extracted so the encode loops stay
    under the McCabe complexity cap (see ``lint-all.ps1`` check 16).
    """
    if not _check_gpu_temperature():
        _wait_for_gpu_cooldown()


def _flush_embeddings_slice(
    model_class: type,
    pks_slice: list[int],
    raw_vectors_list: list,
    *,
    embedding_signature: str | None = None,
) -> None:
    """L2-normalise accumulated vectors and bulk_update the given PK slice.

    Clears ``raw_vectors_list`` in place. No-op if the buffer is empty,
    so call sites don't need their own ``if raw_vectors_list:`` guard.
    Shared between the ContentItem and Sentence embedding paths.
    """
    if not raw_vectors_list:
        return
    normalised = _l2_normalize(np.vstack(raw_vectors_list))
    fields = ["embedding"]
    supports_model_version = False
    try:
        model_class._meta.get_field("embedding_model_version")
        supports_model_version = True
    except Exception:
        supports_model_version = False

    # Quality gate (plan Part 9, FR-236) — decides per-item REPLACE / REJECT /
    # NOOP / ACCEPT_NEW before we archive + overwrite. Filters pks_slice + the
    # normalised matrix to only the rows the gate approves. If the gate is
    # disabled (AppSetting embedding.gate_enabled = false), behaviour matches
    # the pre-gate pipeline exactly.
    gate_kept_indices, gate_pks_kept = _run_quality_gate(
        model_class=model_class,
        pks_slice=pks_slice,
        normalised=normalised,
        embedding_signature=embedding_signature,
    )
    if gate_kept_indices is not None:
        # Gate active and produced a filtered set. If nothing kept, bail early.
        if not gate_kept_indices:
            raw_vectors_list.clear()
            return
        if len(gate_kept_indices) < len(pks_slice):
            normalised = normalised[gate_kept_indices]
            pks_slice = gate_pks_kept

    # Archive existing embeddings before overwrite (plan Part 2). Scope: ContentItem
    # only — SupersededEmbedding.content_item is a FK to ContentItem, not Sentence.
    # Skips rows that are empty or already at the target signature (nothing to preserve).
    # Best-effort: archive failure never blocks the bulk_update.
    if getattr(model_class, "__name__", "") == "ContentItem" and pks_slice:
        try:
            from apps.content.models import SupersededEmbedding

            archive_qs = model_class.objects.filter(
                pk__in=pks_slice, embedding__isnull=False
            )
            if supports_model_version and embedding_signature:
                archive_qs = archive_qs.exclude(
                    embedding_model_version=embedding_signature
                )
            archive_rows = [
                SupersededEmbedding(
                    content_item=row,
                    embedding=row.embedding,
                    embedding_model_version=getattr(row, "embedding_model_version", "")
                    or "",
                    content_hash=getattr(row, "content_hash", "") or "",
                    content_version=getattr(row, "content_version", 1) or 1,
                )
                for row in archive_qs.iterator(chunk_size=500)
            ]
            if archive_rows:
                SupersededEmbedding.objects.bulk_create(
                    archive_rows, batch_size=500, ignore_conflicts=True
                )
        except Exception:
            logger.warning(
                "SupersededEmbedding archive batch failed; bulk_update will proceed",
                exc_info=True,
            )

    model_class.objects.bulk_update(
        [
            model_class(
                **(
                    {
                        "pk": pk,
                        "embedding": vec.tolist(),
                        **(
                            {"embedding_model_version": embedding_signature}
                            if supports_model_version and embedding_signature
                            else {}
                        ),
                    }
                )
            )
            for pk, vec in zip(pks_slice, normalised, strict=True)
        ],
        fields=fields
        + (
            ["embedding_model_version"]
            if supports_model_version and embedding_signature
            else []
        ),
        batch_size=500,
    )
    raw_vectors_list.clear()


def _wait_for_gpu_cooldown() -> None:
    """Block until GPU temperature drops below the resume threshold.

    Resume threshold: 80°C (configurable via GPU_TEMP_RESUME_C).
    """
    import time

    resume_temp = _get_gpu_temp_resume_c()
    max_wait = 300  # 5 minutes max wait

    for _ in range(max_wait // 5):
        try:
            import pynvml

            pynvml.nvmlInit()
            handle = pynvml.nvmlDeviceGetHandleByIndex(0)
            temp = pynvml.nvmlDeviceGetTemperature(handle, pynvml.NVML_TEMPERATURE_GPU)
            pynvml.nvmlShutdown()

            if temp <= resume_temp:
                logger.info("GPU cooled to %d°C — resuming", temp)
                return
        except Exception:
            return  # pynvml unavailable — skip waiting

        time.sleep(5)

    logger.warning("GPU did not cool below %d°C within %ds", resume_temp, max_wait)


def _emit_model_alert(
    event_type: str, severity: str, title: str, message: str, model_name: str
) -> None:
    """Emit a model state alert. Never raises."""
    try:
        from apps.notifications.models import OperatorAlert
        from apps.notifications.services import emit_operator_alert

        emit_operator_alert(
            event_type=event_type,
            severity=severity,
            title=title,
            message=message,
            source_area=OperatorAlert.AREA_MODELS,
            dedupe_key=f"{event_type}:{model_name}",
            related_route="/jobs",
            payload={"model_name": model_name},
        )
    except Exception:
        logger.warning(
            "_emit_model_alert: failed to emit alert for model %s",
            model_name,
            exc_info=True,
        )


def _get_model_cache_key(model_name: str, device: str) -> str:
    """Keep separate cached model instances for CPU and CUDA loads."""
    return f"{model_name}::{device}"


def _load_model(model_name: str = DEFAULT_MODEL_NAME) -> Any:
    """Load and cache a sentence-transformers model."""
    device = _resolve_device()
    cache_key = _get_model_cache_key(model_name, device)
    if cache_key in _model_cache:
        return _model_cache[cache_key]

    from sentence_transformers import SentenceTransformer

    logger.info("Loading embedding model '%s' on device='%s'...", model_name, device)
    _emit_model_alert(
        "model.warming",
        "info",
        "Embedding model is loading",
        f"The app is loading the embedding model '{model_name}' into memory. The first run may be slower than normal.",
        model_name,
    )
    start = time.monotonic()
    try:
        model = SentenceTransformer(model_name, device=device, trust_remote_code=True)
        profile = _assert_model_dimension_supported(model_name, model)
    except Exception as exc:
        _emit_model_alert(
            "model.load_failed",
            "error",
            "Embedding model failed to load",
            f"The app could not load the embedding model '{model_name}': {exc}. Open Jobs or Error Log for details.",
            model_name,
        )
        raise
    elapsed = time.monotonic() - start
    logger.info("Model loaded in %.2fs.", elapsed)
    if device == "cuda":
        try:
            model.half()
            logger.info("fp16 inference enabled for model '%s'.", model_name)
        except Exception:
            logger.debug(
                "fp16 conversion not supported for model '%s', using fp32", model_name
            )
    if profile["recommended_batch_size"] < profile["configured_batch_size"]:
        logger.info(
            "Model '%s' recommends batch size %d instead of configured %d because it reports %d dimensions.",
            model_name,
            profile["recommended_batch_size"],
            profile["configured_batch_size"],
            profile["embedding_dim"],
        )
    _model_cache[cache_key] = model
    _emit_model_alert(
        "model.ready",
        "success",
        "Embedding model ready",
        f"Model '{model_name}' loaded successfully in {elapsed:.1f}s on {device}.",
        model_name,
    )
    if device == "cpu":
        try:
            import torch

            torch.set_num_threads(_get_cpu_encode_threads())
        except Exception:
            logger.debug("torch not available, skipping CPU thread limit")
    return model


def _get_model_name() -> str:
    """Read the configured embedding model name from AppSetting."""
    try:
        from apps.core.models import AppSetting

        setting = AppSetting.objects.filter(key="embedding_model").first()
        if setting:
            return str(setting.value)
    except Exception:
        logger.debug(
            "AppSetting table not available, using default embedding model name"
        )
    return DEFAULT_MODEL_NAME


# Bounds for the user-tunable batch size (mirrored in RuntimeConfigView).
# Anything below the floor is too small to benefit from vectorisation;
# anything above the ceiling risks GPU OOM on the RTX 3050 baseline.
_BATCH_SIZE_MIN = 8
_BATCH_SIZE_MAX = 128
_BATCH_SIZE_HIGH = _BATCH_SIZE_MAX
_BATCH_SIZE_DEFAULT = 32
_OOM_ERROR_MARKERS = (
    "out of memory",
    "cuda out of memory",
    "cublas_status_alloc_failed",
    "mps backend out of memory",
    "can't allocate memory",
    "std::bad_alloc",
)


def _get_model_embedding_dimension(model: Any | None) -> int | None:
    """Read the embedding dimension reported by the loaded model when available."""
    if model is None:
        return None
    get_dimension = getattr(model, "get_sentence_embedding_dimension", None)
    if not callable(get_dimension):
        return None
    try:
        value = get_dimension()
    except Exception:
        logger.debug("Model did not expose embedding dimension cleanly", exc_info=True)
        return None
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _get_runtime_registry_dimension(model_name: str | None = None) -> int | None:
    """Return the last known registered dimension for the active embedding runtime."""
    try:
        from apps.core.runtime_models import RuntimeModelRegistry

        query = RuntimeModelRegistry.objects.filter(task_type="embedding")
        if model_name:
            query = query.filter(model_name=model_name)
        registry_row = (
            query.exclude(dimension__isnull=True)
            .exclude(status="deleted")
            .order_by("-promoted_at", "-id")
            .first()
        )
        if registry_row and registry_row.dimension:
            return int(registry_row.dimension)
    except Exception:
        logger.debug("Runtime registry dimension lookup unavailable", exc_info=True)
    return None


def get_current_embedding_dimension(
    *, model: Any | None = None, model_name: str | None = None
) -> int:
    """Return the active embedding dimension for loaders, status, and sizing."""
    resolved_model_name = model_name or _get_model_name()
    return (
        _get_model_embedding_dimension(model)
        or _get_runtime_registry_dimension(resolved_model_name)
        or EMBEDDING_DIM
    )


def get_current_embedding_signature(
    *, model: Any | None = None, model_name: str | None = None
) -> str:
    """Return the active model signature stored alongside embeddings."""
    resolved_model_name = model_name or _get_model_name()
    dimension = get_current_embedding_dimension(
        model=model,
        model_name=resolved_model_name,
    )
    return f"{resolved_model_name}:{dimension}"


def get_current_embedding_filter(
    *, prefix: str = "", model: Any | None = None, model_name: str | None = None
) -> dict[str, str]:
    """Return ORM filters that scope queries to the active embedding signature."""
    return {
        f"{prefix}embedding_model_version": get_current_embedding_signature(
            model=model,
            model_name=model_name,
        )
    }


def _describe_model_runtime(
    *,
    model_name: str,
    configured_batch_size: int,
    model: Any | None = None,
) -> dict[str, Any]:
    """Summarize the runtime assumptions for the configured embedding model."""
    embedding_dim = get_current_embedding_dimension(
        model=model,
        model_name=model_name,
    )
    dimension_compatible = 0 < embedding_dim <= STORAGE_VECTOR_MAX_DIM
    recommended_batch_size = configured_batch_size
    if embedding_dim > EMBEDDING_DIM:
        scaled = int(configured_batch_size * EMBEDDING_DIM / max(embedding_dim, 1))
        recommended_batch_size = max(
            _BATCH_SIZE_MIN, min(configured_batch_size, scaled)
        )
    return {
        "model_name": model_name,
        "embedding_dim": embedding_dim,
        "active_signature": get_current_embedding_signature(
            model=model,
            model_name=model_name,
        ),
        "storage_dimension_cap": STORAGE_VECTOR_MAX_DIM,
        "dimension_compatible": dimension_compatible,
        "configured_batch_size": configured_batch_size,
        "recommended_batch_size": recommended_batch_size,
    }


def _assert_model_dimension_supported(model_name: str, model: Any) -> dict[str, Any]:
    """Fail fast when the configured model exceeds generic-vector storage limits."""
    profile = _describe_model_runtime(
        model_name=model_name,
        configured_batch_size=_get_configured_batch_size(),
        model=model,
    )
    if profile["dimension_compatible"]:
        return profile

    raise ValueError(
        f"Embedding model '{model_name}' outputs {profile['embedding_dim']} dimensions, "
        f"which exceeds the storage cap of {profile['storage_dimension_cap']} dimensions. "
        "Choose a smaller model or raise the storage contract before promoting it."
    )


def _get_configured_batch_size() -> int:
    """Resolve the configured embedding batch size before model-aware tuning.

    Priority: AppSetting override (key=system.embedding_batch_size, set by the
    noob-friendly slider in Settings > Performance) → performance mode default.
    Read on every pipeline run so the user does not need a restart.
    """
    try:
        from apps.core.models import AppSetting

        raw = (
            AppSetting.objects.filter(key="system.embedding_batch_size")
            .values_list("value", flat=True)
            .first()
        )
        if raw is not None:
            val = int(raw)
            if _BATCH_SIZE_MIN <= val <= _BATCH_SIZE_MAX:
                return val
    except Exception:
        logger.debug("AppSetting unavailable; falling back to mode-based batch size")

    # Hardware-aware auto-tuning (plan Part 8a, FR-233): if the operator has
    # not set an explicit override, let the hardware profile pick a batch size
    # scaled to RAM / VRAM / current provider dimension. Falls back to the
    # mode-based default on any failure so this path is always safe.
    try:
        from apps.pipeline.services.hardware_profile import (
            detect_profile,
            recommended_batch_size,
        )

        prof = detect_profile()
        # Resolve the current provider's output dimension if the abstraction
        # is installed; otherwise fall back to the local BGE dim.
        dimension = EMBEDDING_DIM
        try:
            from apps.pipeline.services.embedding_providers import get_provider

            provider = get_provider()
            dimension = int(getattr(provider, "dimension", EMBEDDING_DIM)) or EMBEDDING_DIM
        except Exception:
            pass
        auto_batch = recommended_batch_size(dimension=dimension, profile=prof)
        if _BATCH_SIZE_MIN <= auto_batch <= _BATCH_SIZE_MAX:
            return auto_batch
    except Exception:
        logger.debug(
            "Hardware-aware batch sizing unavailable; using mode-based default",
            exc_info=True,
        )

    return (
        _BATCH_SIZE_HIGH
        if _get_performance_mode() == PERFORMANCE_MODE_HIGH
        else _BATCH_SIZE_DEFAULT
    )


def _get_batch_size(model: Any | None = None) -> int:
    """Resolve the effective embedding batch size for the current model."""
    configured_batch_size = _get_configured_batch_size()
    if model is None:
        return configured_batch_size
    profile = _describe_model_runtime(
        model_name=_get_model_name(),
        configured_batch_size=configured_batch_size,
        model=model,
    )
    return int(profile["recommended_batch_size"])


def _is_embedding_oom_error(exc: Exception) -> bool:
    """Detect OOM-style failures from either CUDA or CPU allocators."""
    message = str(exc).lower()
    return any(marker in message for marker in _OOM_ERROR_MARKERS)


def _clear_embedding_runtime_memory() -> None:
    """Best-effort memory cleanup after an OOM before retrying."""
    try:
        import torch

        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            try:
                torch.cuda.ipc_collect()
            except Exception:
                logger.debug("torch.cuda.ipc_collect unavailable", exc_info=True)
    except Exception:
        logger.debug("Runtime memory cleanup skipped", exc_info=True)


def _get_retry_batch_size_after_oom(
    *,
    job_id: str | None,
    model_name: str,
    failed_batch_size: int,
    exc: Exception,
) -> int | None:
    retry_batch_size = _next_retry_batch_size(failed_batch_size)
    _clear_embedding_runtime_memory()
    if not _aggressive_oom_backoff_enabled() or retry_batch_size >= failed_batch_size:
        return None
    _record_embedding_backoff(
        job_id=job_id,
        model_name=model_name,
        failed_batch_size=failed_batch_size,
        retry_batch_size=retry_batch_size,
        exc=exc,
    )
    return retry_batch_size


def _next_retry_batch_size(current_batch_size: int) -> int:
    """Return the next smaller retry size without dropping below the floor."""
    if current_batch_size <= _BATCH_SIZE_MIN:
        return current_batch_size
    reduced = max(_BATCH_SIZE_MIN, current_batch_size // 2)
    if reduced == current_batch_size and current_batch_size > _BATCH_SIZE_MIN:
        reduced = current_batch_size - 1
    return max(_BATCH_SIZE_MIN, reduced)


def _get_embedding_pause_reason(job_id: str | None) -> str | None:
    """Read the current pause contract without raising so callers can checkpoint first."""
    if not job_id:
        return None
    from apps.core.pause_contract import should_pause_now

    should_pause, reason = should_pause_now(job_type="embeddings", job_id=job_id)
    if should_pause:
        return reason
    return None


def _mark_embedding_job_paused(job_id: str | None, reason: str) -> None:
    """Persist a pause state after the caller flushed any pending checkpoints."""
    if not job_id:
        return
    from apps.sync.models import SyncJob

    SyncJob.objects.filter(job_id=job_id).update(
        status="paused",
        is_resumable=True,
        checkpoint_stage="embed",
        message=f"Paused at embedding checkpoint: {reason}",
    )


def _record_embedding_backoff(
    *,
    job_id: str | None,
    model_name: str,
    failed_batch_size: int,
    retry_batch_size: int,
    exc: Exception,
) -> None:
    """Record an OOM backoff event in logs, alerts, and the SyncJob row."""
    message = (
        f"Embedding batch hit memory pressure at batch size {failed_batch_size}; "
        f"retrying with {retry_batch_size} for model '{model_name}'."
    )
    logger.warning("%s Error: %s", message, exc)
    _emit_model_alert(
        "model.oom_backoff",
        "warning",
        "Embedding batch size reduced after memory pressure",
        message,
        model_name,
    )
    if not job_id:
        return

    from apps.sync.models import SyncJob

    SyncJob.objects.filter(job_id=job_id).update(
        is_resumable=True,
        checkpoint_stage="embed",
        message=message,
    )


# ---------------------------------------------------------------------------
# L2 normalization
# ---------------------------------------------------------------------------


def _l2_normalize(arr: np.ndarray) -> np.ndarray:
    """Row-wise L2 normalization. Zero-row arrays pass through unchanged."""
    if arr.shape[0] == 0:
        return arr

    if HAS_CPP_EXT:
        # In-place C++ normalization (fast)
        l2norm.normalize_l2_batch(arr)
        return arr.astype(np.float32)
    else:
        # Numpy fallback
        norms = np.linalg.norm(arr, axis=1, keepdims=True)
        norms = np.maximum(norms, 1e-12)
        return (arr / norms).astype(np.float32)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Provider-aware encode helper (plan Part 1)
# ---------------------------------------------------------------------------


def _encode_batch_via_provider(
    *,
    batch_texts: list[str],
    model: Any,
    batch_size: int,
    job_id: str | None,
) -> np.ndarray:
    """Encode a batch through the active provider abstraction.

    Fast path: if the active provider is ``local``, delegates straight to the
    already-loaded ``model.encode()`` — preserves the existing GPU/CPU path,
    OOM-retry behaviour, and thermal guard surrounding calls. Zero overhead.

    API path: when the user has flipped ``AppSetting("embedding.provider")`` to
    ``openai`` or ``gemini``, calls ``provider.embed()`` and records token +
    cost usage in ``EmbeddingCostLedger`` via upsert (unique on (job_id,
    provider) so resume never duplicates). Provider-side pause checks and
    retries are handled inside the provider class.
    """
    try:
        from apps.pipeline.services.embedding_providers import (
            BudgetExceededError,
            ProviderError,
            get_provider,
        )
    except ImportError:
        # Provider module not present → legacy local path.
        return model.encode(
            batch_texts,
            batch_size=batch_size,
            show_progress_bar=False,
            convert_to_numpy=True,
        )

    try:
        provider = get_provider()
    except Exception:
        logger.exception("get_provider failed; falling back to local encode")
        return model.encode(
            batch_texts,
            batch_size=batch_size,
            show_progress_bar=False,
            convert_to_numpy=True,
        )

    if getattr(provider, "name", "local") == "local":
        # Existing fast path — nothing gained by routing through the wrapper,
        # and we preserve all surrounding OOM / thermal behaviour.
        return model.encode(
            batch_texts,
            batch_size=batch_size,
            show_progress_bar=False,
            convert_to_numpy=True,
        )

    # API-provider path with graceful fallback (plan Part 8b, FR-234):
    # if the provider raises BudgetExceededError / AuthenticationError /
    # RateLimitError, switch to the configured fallback provider (default
    # ``local``) and retry the batch once. On double failure, re-raise.
    try:
        result = provider.embed(batch_texts, batch_size=batch_size, job_id=job_id)
    except BudgetExceededError as exc:
        fallback = _attempt_graceful_fallback(
            failing_provider_name=getattr(provider, "name", "unknown"),
            reason=str(exc),
            reason_code="budget",
        )
        if fallback is None:
            raise
        provider = fallback
        result = provider.embed(batch_texts, batch_size=batch_size, job_id=job_id)
    except ProviderError as exc:
        reason_code = getattr(exc, "reason", "provider_error")
        if reason_code not in ("auth", "rate_limit", "budget", "transient"):
            raise
        fallback = _attempt_graceful_fallback(
            failing_provider_name=getattr(provider, "name", "unknown"),
            reason=str(exc),
            reason_code=reason_code,
        )
        if fallback is None:
            raise
        provider = fallback
        result = provider.embed(batch_texts, batch_size=batch_size, job_id=job_id)

    if job_id:
        _record_provider_usage(
            job_id=job_id,
            provider_name=getattr(provider, "name", "unknown"),
            signature=getattr(provider, "signature", ""),
            items=len(batch_texts),
            tokens=getattr(result, "tokens_input", 0),
            cost_usd=getattr(result, "cost_usd", 0.0),
        )
    return result.vectors


def _attempt_graceful_fallback(
    *,
    failing_provider_name: str,
    reason: str,
    reason_code: str,
) -> Any | None:
    """Switch ``embedding.provider`` to the configured fallback and return the new provider.

    Called from ``_encode_batch_via_provider`` when the primary provider raises
    a recoverable error (auth / rate-limit / budget / transient). Operations:
      1. Read ``AppSetting("embedding.fallback_provider")``; default ``local``.
      2. If fallback equals the failing provider, do nothing (avoid infinite loop).
      3. Update ``AppSetting("embedding.provider")`` in place so subsequent
         batches resolve to the new provider immediately.
      4. Clear the provider cache so ``get_provider()`` re-instantiates.
      5. Emit an operator alert so the Embeddings page surfaces the switch.
      6. Return the new provider.

    On any internal failure, returns ``None`` — the caller re-raises the original
    error so the operator is not silently stuck.
    """
    try:
        from apps.core.models import AppSetting

        fallback_row = AppSetting.objects.filter(key="embedding.fallback_provider").first()
        fallback_name = (str(fallback_row.value).strip().lower() if fallback_row else "local") or "local"
        if fallback_name == failing_provider_name:
            logger.warning(
                "Fallback provider equals failing provider (%s); cannot recover",
                failing_provider_name,
            )
            return None

        AppSetting.objects.update_or_create(
            key="embedding.provider",
            defaults={"value": fallback_name},
        )

        from apps.pipeline.services.embedding_providers import clear_cache, get_provider

        clear_cache()
        new_provider = get_provider()

        logger.warning(
            "Embedding provider fallback: %s → %s (reason=%s: %s)",
            failing_provider_name,
            fallback_name,
            reason_code,
            reason,
        )

        _emit_fallback_alert(
            failing=failing_provider_name,
            fallback=fallback_name,
            reason_code=reason_code,
            reason_message=reason,
        )
        return new_provider
    except Exception:
        logger.exception("Graceful fallback failed for provider=%s", failing_provider_name)
        return None


def _emit_fallback_alert(
    *,
    failing: str,
    fallback: str,
    reason_code: str,
    reason_message: str,
) -> None:
    """Best-effort operator alert for the Embeddings page and system alerts UI."""
    try:
        from apps.diagnostics.alerts import emit_operator_alert

        emit_operator_alert(
            event_type="embedding.provider_fallback",
            severity="warning",
            payload={
                "failing_provider": failing,
                "fallback_provider": fallback,
                "reason_code": reason_code,
                "reason_message": reason_message[:500],
            },
        )
    except Exception:
        # Alert system optional; never block fallback.
        logger.debug("emit_operator_alert unavailable", exc_info=True)


def _run_quality_gate(
    *,
    model_class: type,
    pks_slice: list[int],
    normalised: np.ndarray,
    embedding_signature: str | None,
) -> tuple[list[int] | None, list[int]]:
    """Apply the measure-twice gate to this flush batch.

    Returns a ``(kept_indices, kept_pks)`` tuple:
        kept_indices: Row indices into ``normalised`` the gate approved, or
                      ``None`` if the gate is disabled (caller should act as
                      pre-feature).
        kept_pks: ``pks_slice`` filtered to the same set.

    Only ContentItem currently goes through the gate (Sentence embeddings have
    no archive table and no provider-aware signature yet).
    """
    try:
        from apps.pipeline.services.embedding_quality_gate import (
            QualityGate,
            is_gate_enabled,
            load_gate_thresholds,
            load_provider_ranking,
            persist_decisions,
        )
    except ImportError:
        return None, pks_slice

    if not is_gate_enabled():
        return None, pks_slice
    if getattr(model_class, "__name__", "") != "ContentItem" or not pks_slice:
        return None, pks_slice
    if embedding_signature is None:
        return None, pks_slice

    # Fetch existing rows once: (pk, embedding, embedding_model_version, text).
    try:
        has_signature_field = True
        try:
            model_class._meta.get_field("embedding_model_version")
        except Exception:
            has_signature_field = False

        values_fields = ["pk", "embedding", "title", "distilled_text"]
        if has_signature_field:
            values_fields.append("embedding_model_version")
        existing = {
            row["pk"]: row
            for row in model_class.objects.filter(pk__in=pks_slice).values(
                *values_fields
            )
        }
    except Exception:
        logger.warning("Gate: existing-row fetch failed; skipping gate", exc_info=True)
        return None, pks_slice

    thresholds = load_gate_thresholds()
    ranking = load_provider_ranking()
    try:
        from apps.pipeline.services.embedding_providers import get_provider
        provider = get_provider()
    except Exception:
        provider = None

    gate = QualityGate(
        provider_ranking=ranking,
        provider=provider,
        quality_delta_threshold=thresholds[0],
        noop_cosine_threshold=thresholds[1],
        stability_threshold=thresholds[2],
    )

    decisions_to_log: list = []
    kept_indices: list[int] = []
    kept_pks: list[int] = []
    for idx, pk in enumerate(pks_slice):
        row = existing.get(pk)
        new_vec = normalised[idx]
        old_vec = None
        old_sig = ""
        text = None
        if row is not None:
            raw_emb = row.get("embedding")
            if raw_emb is not None:
                try:
                    old_vec = np.asarray(raw_emb, dtype=np.float32)
                except Exception:
                    old_vec = None
            if has_signature_field:
                old_sig = row.get("embedding_model_version") or ""
            title = row.get("title") or ""
            distilled = row.get("distilled_text") or ""
            text = f"{title}\n\n{distilled}".strip()

        decision = gate.evaluate(
            text=text,
            old_vec=old_vec,
            old_sig=old_sig,
            new_vec=new_vec,
            new_sig=embedding_signature,
        )
        decisions_to_log.append((pk, "content_item", decision, old_sig, embedding_signature))
        if decision.action in ("REPLACE", "ACCEPT_NEW"):
            kept_indices.append(idx)
            kept_pks.append(pk)

    # Log all decisions (batched).
    persist_decisions(decisions_to_log)
    return kept_indices, kept_pks


def _record_provider_usage(
    *,
    job_id: str,
    provider_name: str,
    signature: str,
    items: int,
    tokens: int,
    cost_usd: float,
) -> None:
    """Upsert a row in ``EmbeddingCostLedger`` for this (job_id, provider)."""
    try:
        from apps.pipeline.models import EmbeddingCostLedger
        from django.db import transaction
        from django.db.models import F

        with transaction.atomic():
            row, created = EmbeddingCostLedger.objects.get_or_create(
                job_id=job_id,
                provider=provider_name,
                defaults={
                    "signature": signature,
                    "items": items,
                    "tokens_input": tokens,
                    "cost_usd": cost_usd,
                },
            )
            if not created:
                # Increment in place to avoid read-modify-write races.
                EmbeddingCostLedger.objects.filter(pk=row.pk).update(
                    signature=signature,
                    items=F("items") + items,
                    tokens_input=F("tokens_input") + tokens,
                    cost_usd=F("cost_usd") + cost_usd,
                )
    except Exception:
        # Ledger write failures must never break the embed flow.
        logger.warning("EmbeddingCostLedger write failed", exc_info=True)


def generate_content_item_embeddings(
    content_item_ids: list[int] | None = None,
    job_id: str | None = None,
    force_reembed: bool = False,
) -> dict[str, int]:
    """Generate and store embeddings for ContentItem.embedding (destination embeddings).

    Each ContentItem's embedding = L2-normalized encoding of:
        '{title}\\n\\n{distilled_text}'.strip()

    Args:
        content_item_ids: List of ContentItem PKs to embed.
                          None = all items with is_deleted=False.

    Returns:
        Dict with 'embedded' and 'skipped' counts.
    """
    from apps.content.models import ContentItem

    model_name = _get_model_name()
    model = _load_model(model_name)
    embedding_signature = get_current_embedding_signature(
        model=model,
        model_name=model_name,
    )
    batch_size = _get_batch_size(model)

    qs = ContentItem.objects.filter(is_deleted=False)
    if content_item_ids is not None:
        qs = qs.filter(pk__in=content_item_ids)

    if not force_reembed:
        qs = qs.exclude(
            embedding__isnull=False,
            embedding_model_version=embedding_signature,
        )

    qs = qs.values_list("pk", "title", "distilled_text")

    items = list(qs)
    if not items:
        return {"embedded": 0, "skipped": 0}

    pks: list[int] = []
    texts: list[str] = []
    for pk, title, distilled in items:
        title_clean = (title or "").strip()
        distilled_clean = (distilled or "").strip()
        if distilled_clean:
            text = f"{title_clean}\n\n{distilled_clean}".strip()
        else:
            text = title_clean
        if not text:
            continue
        pks.append(pk)
        texts.append(text)

    if not texts:
        return {"embedded": 0, "skipped": len(items)}

    logger.info("Embedding %d content items...", len(texts))
    start = time.monotonic()

    # Process in batches to report progress
    raw_vectors_list = []
    total_items = len(texts)

    if job_id:
        from apps.sync.models import SyncJob
        from apps.pipeline.tasks import _publish_progress

        job = SyncJob.objects.filter(job_id=job_id).first()
    else:
        job = None

    batch_num = 0
    flushed_count = 0  # how many items already persisted to DB
    cursor = 0
    while cursor < total_items:
        pause_reason = _get_embedding_pause_reason(job_id)
        if pause_reason:
            _flush_embeddings_slice(
                ContentItem,
                pks[flushed_count:cursor],
                raw_vectors_list,
                embedding_signature=embedding_signature,
            )
            flushed_count = cursor
            _mark_embedding_job_paused(job_id, pause_reason)
            from apps.core.pause_contract import JobPaused

            raise JobPaused(pause_reason)

        batch_texts = texts[cursor : cursor + batch_size]
        _thermal_guard_before_gpu_batch()
        try:
            batch_vectors = _encode_batch_via_provider(
                batch_texts=list(batch_texts),
                model=model,
                batch_size=batch_size,
                job_id=job_id,
            )
        except Exception as exc:
            if not _is_embedding_oom_error(exc):
                raise
            retry_batch_size = _get_retry_batch_size_after_oom(
                job_id=job_id,
                model_name=model_name,
                failed_batch_size=batch_size,
                exc=exc,
            )
            if retry_batch_size is None:
                raise
            batch_size = retry_batch_size
            continue

        raw_vectors_list.append(batch_vectors)
        batch_num += 1
        cursor += len(batch_texts)
        processed = cursor

        # Report progress
        if job_id:
            pct = processed / total_items

            if job:
                job.embedding_items_completed = processed
                # Throttle DB writes — saving every batch issues O(N/batch_size) UPDATEs;
                # every 5th batch cuts that by 5x with negligible progress-reporting lag.
                if batch_num % 5 == 0:
                    job.save(update_fields=["embedding_items_completed", "updated_at"])

            _publish_progress(
                job_id,
                "running",
                0.8 + (pct * 0.1),
                f"Content embeddings: {processed}/{total_items}...",
                embedding_progress=pct
                * 0.5,  # Content items are first half of embedding phase
                ml_progress=0.7 + (pct * 0.15),
            )

        # Checkpoint flush every 5 batches — same cadence as the progress save above.
        # If the worker dies mid-run, items already flushed have embeddings persisted
        # and the resume run skips them once their embedding_model_version matches.
        if batch_num % 5 == 0:
            _flush_embeddings_slice(
                ContentItem,
                pks[flushed_count:processed],
                raw_vectors_list,
                embedding_signature=embedding_signature,
            )
            flushed_count = processed

    # Persist final count regardless of whether the last batch fell on a multiple-of-5 boundary.
    if job_id and job:
        job.save(update_fields=["embedding_items_completed", "updated_at"])

    # Tail flush — any batches since the last checkpoint flush. Helper no-ops
    # if the buffer is empty, so no call-site guard needed.
    _flush_embeddings_slice(
        ContentItem,
        pks[flushed_count:],
        raw_vectors_list,
        embedding_signature=embedding_signature,
    )

    elapsed = time.monotonic() - start
    logger.info("Encoded %d items in %.2fs.", len(texts), elapsed)

    return {"embedded": len(pks), "skipped": len(items) - len(pks)}


def generate_sentence_embeddings(
    content_item_ids: list[int] | None = None,
    job_id: str | None = None,
    force_reembed: bool = False,
) -> dict[str, int]:
    """Generate and store embeddings for Sentence.embedding (host sentence embeddings).

    Only sentences within the HOST_SCAN_WORD_LIMIT window are embedded,
    matching the ML guardrail.

    Args:
        content_item_ids: Limit to sentences belonging to these ContentItem PKs.
                          None = all sentences for non-deleted content items.

    Returns:
        Dict with 'embedded' and 'skipped' counts.
    """
    from apps.content.models import Sentence

    model_name = _get_model_name()
    model = _load_model(model_name)
    embedding_signature = get_current_embedding_signature(
        model=model,
        model_name=model_name,
    )
    batch_size = _get_batch_size(model)

    qs = Sentence.objects.filter(
        content_item__is_deleted=False,
    )
    if content_item_ids is not None:
        qs = qs.filter(content_item__pk__in=content_item_ids)

    if not force_reembed:
        qs = qs.exclude(
            embedding__isnull=False,
            embedding_model_version=embedding_signature,
        )

    # Only embed sentences within the HOST_SCAN_WORD_LIMIT window
    qs = qs.filter(word_position__lte=settings.HOST_SCAN_WORD_LIMIT).values_list(
        "pk", "text"
    )

    sentences = list(qs)
    if not sentences:
        return {"embedded": 0, "skipped": 0}

    pks: list[int] = []
    texts: list[str] = []
    for pk, text in sentences:
        if text and text.strip():
            pks.append(pk)
            texts.append(text.strip())

    if not texts:
        return {"embedded": 0, "skipped": len(sentences)}

    logger.info("Embedding %d sentences...", len(texts))
    start = time.monotonic()

    # Process in batches to report progress
    raw_vectors_list = []
    total_sentences = len(texts)

    from apps.content.models import Sentence as SentenceModel

    batch_num = 0
    flushed_count = 0  # how many sentences already persisted to DB
    cursor = 0
    while cursor < total_sentences:
        pause_reason = _get_embedding_pause_reason(job_id)
        if pause_reason:
            _flush_embeddings_slice(
                SentenceModel,
                pks[flushed_count:cursor],
                raw_vectors_list,
                embedding_signature=embedding_signature,
            )
            flushed_count = cursor
            _mark_embedding_job_paused(job_id, pause_reason)
            from apps.core.pause_contract import JobPaused

            raise JobPaused(pause_reason)

        batch_texts = texts[cursor : cursor + batch_size]
        _thermal_guard_before_gpu_batch()
        try:
            batch_vectors = _encode_batch_via_provider(
                batch_texts=list(batch_texts),
                model=model,
                batch_size=batch_size,
                job_id=job_id,
            )
        except Exception as exc:
            if not _is_embedding_oom_error(exc):
                raise
            retry_batch_size = _get_retry_batch_size_after_oom(
                job_id=job_id,
                model_name=model_name,
                failed_batch_size=batch_size,
                exc=exc,
            )
            if retry_batch_size is None:
                raise
            batch_size = retry_batch_size
            continue

        raw_vectors_list.append(batch_vectors)
        batch_num += 1
        cursor += len(batch_texts)
        processed = cursor

        # Report progress
        if job_id:
            from apps.pipeline.tasks import _publish_progress

            pct = processed / total_sentences

            _publish_progress(
                job_id,
                "running",
                0.9 + (pct * 0.09),
                f"Sentence embeddings: {processed}/{total_sentences}...",
                embedding_progress=0.5 + (pct * 0.5),  # Sentences are second half
                ml_progress=0.85 + (pct * 0.14),
            )

        # Checkpoint flush every 5 batches — if the worker dies mid-run, items
        # already flushed have embeddings persisted and the resume run skips them
        # once their embedding_model_version matches the active signature.
        if batch_num % 5 == 0:
            _flush_embeddings_slice(
                SentenceModel,
                pks[flushed_count:processed],
                raw_vectors_list,
                embedding_signature=embedding_signature,
            )
            flushed_count = processed

    # Tail flush — helper no-ops on empty buffer.
    _flush_embeddings_slice(
        SentenceModel,
        pks[flushed_count:],
        raw_vectors_list,
        embedding_signature=embedding_signature,
    )

    elapsed = time.monotonic() - start
    logger.info("Encoded %d sentences in %.2fs.", len(texts), elapsed)

    return {"embedded": len(pks), "skipped": len(sentences) - len(pks)}


def generate_all_embeddings(
    content_item_ids: list[int] | None = None,
    job_id: str | None = None,
    force_reembed: bool = False,
) -> dict[str, int]:
    """Generate both ContentItem and Sentence embeddings in one call.

    Returns combined stats dict.
    """
    ci_stats = generate_content_item_embeddings(
        content_item_ids, job_id=job_id, force_reembed=force_reembed
    )
    sent_stats = generate_sentence_embeddings(
        content_item_ids, job_id=job_id, force_reembed=force_reembed
    )
    return {
        "content_items_embedded": ci_stats["embedded"],
        "content_items_skipped": ci_stats["skipped"],
        "sentences_embedded": sent_stats["embedded"],
        "sentences_skipped": sent_stats["skipped"],
    }


def get_model_status() -> dict[str, Any]:
    """Return a status dict about the currently cached model."""
    model_name = _get_model_name()
    runtime_resolution = get_effective_runtime_resolution()
    device = runtime_resolution["device"]
    cache_key = _get_model_cache_key(model_name, device)
    loaded = cache_key in _model_cache
    model = _model_cache.get(cache_key)
    profile = _describe_model_runtime(
        model_name=model_name,
        configured_batch_size=_get_configured_batch_size(),
        model=model,
    )
    return {
        "model_name": model_name,
        "loaded": loaded,
        "device": device,
        "fp16": runtime_resolution["effective_runtime_mode"] == "gpu",
        "mode": runtime_resolution["performance_mode"],
        "effective_runtime_mode": runtime_resolution["effective_runtime_mode"],
        "effective_runtime_reason": runtime_resolution["reason"],
        "batch_size": _get_batch_size(model),
        "configured_batch_size": profile["configured_batch_size"],
        "embedding_dim": profile["embedding_dim"],
        "active_signature": profile["active_signature"],
        "storage_dimension_cap": profile["storage_dimension_cap"],
        "dimension_compatible": profile["dimension_compatible"],
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }
