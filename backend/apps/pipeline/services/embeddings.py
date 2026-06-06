"""Embedding generation service.

V2 change from V1: eliminates .npy file artifacts entirely.
Embeddings are stored directly in pgvector VectorField columns on
ContentItem and Sentence models. Embedding vectors are generated through the
active paid provider from ``apps.pipeline.services.embedding_providers``.
"""

from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timezone
from typing import Any

import numpy as np
from django.conf import settings

from apps.ops_feed.services import emit
from apps.core.performance_mode import get_requested_performance_mode

try:
    from extensions import l2norm

    HAS_CPP_EXT = True
except ImportError:
    HAS_CPP_EXT = False

logger = logging.getLogger(__name__)

DEFAULT_MODEL_NAME = "text-embedding-3-small"
EMBEDDING_DIM = 1024
STORAGE_VECTOR_MAX_DIM = 16_000
_model_cache: dict[str, Any] = {}

#: Hard cap on the character count we feed the paid provider per ContentItem
#: embedding. Bumped to 1,000,000 chars (~250,000 tokens) per LEDGER
#: L5 so massive forum threads aren't truncated. The cap only exists to
#: prevent extreme-edge-case memory and token-cost spikes (a 100 MB single
#: post would otherwise pull 100 MB through the tokenizer). For 99.9 %
#: of forum posts this is effectively "no truncation". Late-paragraph
#: recall on truly massive threads is handled by the FR-053 passage
#: retrieval pipeline (masterplan Group E).
_MAX_EMBED_CHARS: int = 1_000_000

_CPU_THREAD_HEADROOM = 2


def _compute_embed_text_hash(text: str) -> str:
    """Group D.2 — SHA-256 hex digest of the exact text we embed.

    Stored on ``ContentItem.embedding_text_hash`` so a future re-embed
    can skip rows whose text hasn't changed since the last embedding.
    Empty input returns "" so the caller can use the truthiness check
    (``if hash:``) without an extra None comparison.
    """
    import hashlib

    if not text:
        return ""
    return hashlib.sha256(text.encode("utf-8"), usedforsecurity=False).hexdigest()


def _truncate_at_sentence(text: str, max_chars: int) -> str:
    """Trim *text* to <= *max_chars* characters at a clean boundary.

    Tries the last newline, then the last full-stop, then a hard cut as
    a fallback. The point is to avoid splitting a word mid-letter when
    the soft cap kicks in — readers (and the model) prefer a clean
    sentence end over a jagged truncation.
    """
    if len(text) <= max_chars:
        return text
    window = text[:max_chars]
    # Prefer the last newline (paragraph boundary) inside the window.
    cut = window.rfind("\n")
    if cut < int(max_chars * 0.7):
        # Fall back to the last full-stop if the newline lands too early
        # (else we'd waste a lot of the budget).
        period_cut = window.rfind(". ")
        if period_cut > cut:
            cut = period_cut + 1  # keep the full stop
    if cut <= 0:
        # No paragraph or sentence boundary at all — hard-cut.
        return window.rstrip()
    return window[:cut].rstrip()


# ---------------------------------------------------------------------------
# Model loading
# ---------------------------------------------------------------------------


def _resolve_device() -> str:
    """Return the provider-backed runtime device label."""
    return "api"


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


def _get_effective_runtime_resolution() -> dict[str, str]:
    """Resolve the actual runtime that embeddings use right now."""
    mode = _get_performance_mode()
    return {
        "performance_mode": mode,
        "effective_runtime_mode": "api",
        "device": "api",
        "reason": "paid embedding provider",
    }


def get_effective_runtime_resolution() -> dict[str, str]:
    """Public read-only view of the current embedding runtime choice."""
    return _get_effective_runtime_resolution()


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


def _aggressive_oom_backoff_enabled() -> bool:
    return _read_performance_bool("system.aggressive_oom_backoff", True)


def _model_supports_field(model_class: type, field_name: str) -> bool:
    """True if the Django model has a Meta-registered field by that name."""
    try:
        model_class._meta.get_field(field_name)
    except Exception:  # noqa: BLE001 — Django raises FieldDoesNotExist; treat as missing.
        return False
    return True


def _archive_existing_content_item_embeddings(
    *,
    model_class: type,
    pks_slice: list[int],
    supports_model_version: bool,
    embedding_signature: str | None,
) -> None:
    """Best-effort archive of pre-existing ContentItem embeddings before overwrite.

    Scope: ContentItem only — ``SupersededEmbedding.content_item`` is a FK
    to ContentItem, not Sentence. Skips rows that are empty or already at
    the target signature. Archive failure NEVER blocks the bulk_update.
    """
    if getattr(model_class, "__name__", "") != "ContentItem" or not pks_slice:
        return
    try:
        from apps.content.models import SupersededEmbedding

        archive_qs = model_class.objects.filter(
            pk__in=pks_slice,
            embedding__isnull=False,
        )
        if supports_model_version and embedding_signature:
            archive_qs = archive_qs.exclude(
                embedding_model_version=embedding_signature,
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
                archive_rows,
                batch_size=500,
                ignore_conflicts=True,
            )
    except Exception:
        logger.warning(
            "SupersededEmbedding archive batch failed; bulk_update will proceed",
            exc_info=True,
        )


def _build_bulk_update_rows(
    model_class: type,
    pks_slice: list[int],
    normalised,
    *,
    supports_model_version: bool,
    embedding_signature: str | None,
    use_text_hashes: bool,
    text_hashes: list[str] | None,
) -> list:
    """Construct the per-row instances for bulk_update.

    Conditionally includes ``embedding_model_version`` and
    ``embedding_text_hash`` so each row sets only the fields the model
    actually supports.
    """
    hashes_iter = text_hashes if use_text_hashes else [""] * len(pks_slice)
    return [
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
                    **({"embedding_text_hash": text_hash} if use_text_hashes else {}),
                }
            )
        )
        for pk, vec, text_hash in zip(pks_slice, normalised, hashes_iter, strict=True)
    ]


def _apply_quality_gate_filter(
    *,
    model_class,
    pks_slice: list[int],
    normalised,
    embedding_signature: str | None,
    text_hashes: list[str] | None,
) -> tuple[list[int], object, list[str] | None] | None:
    """Run the embedding quality gate and filter the kept-indices.

    Returns ``None`` when the gate kept ZERO rows (caller should bail).
    Returns ``(pks_slice, normalised, text_hashes)`` filtered down to the
    kept-indices set. If the gate is disabled the inputs pass through.
    """
    gate_kept_indices, gate_pks_kept = _run_quality_gate(
        model_class=model_class,
        pks_slice=pks_slice,
        normalised=normalised,
        embedding_signature=embedding_signature,
    )
    if gate_kept_indices is None:
        return pks_slice, normalised, text_hashes
    if not gate_kept_indices:
        return None
    if len(gate_kept_indices) < len(pks_slice):
        normalised = normalised[gate_kept_indices]
        pks_slice = gate_pks_kept
        # Group D.2 bug-fix: also filter ``text_hashes`` so the length-match
        # check stays honest. Without this the gate-pruned set would have
        # ``len(text_hashes) > len(pks_slice)`` and the hash write would
        # silently disable. The signature filter then wouldn't be able to
        # short-circuit unchanged content on subsequent passes.
        if text_hashes is not None and len(text_hashes) > len(pks_slice):
            text_hashes = [text_hashes[i] for i in gate_kept_indices]
    return pks_slice, normalised, text_hashes


def _flush_embeddings_slice(
    model_class: type,
    pks_slice: list[int],
    raw_vectors_list: list,
    *,
    embedding_signature: str | None = None,
    text_hashes: list[str] | None = None,
) -> None:
    """L2-normalise accumulated vectors and bulk_update the given PK slice.

    No-op when ``raw_vectors_list`` is empty. Quality gate (FR-236)
    filters pks/vectors/hashes; archive runs only for ContentItem.
    """
    if not raw_vectors_list:
        return
    normalised = _l2_normalize(np.vstack(raw_vectors_list))
    supports_model_version = _model_supports_field(
        model_class, "embedding_model_version"
    )
    supports_text_hash = _model_supports_field(model_class, "embedding_text_hash")
    gate_result = _apply_quality_gate_filter(
        model_class=model_class,
        pks_slice=pks_slice,
        normalised=normalised,
        embedding_signature=embedding_signature,
        text_hashes=text_hashes,
    )
    if gate_result is None:
        raw_vectors_list.clear()
        return
    pks_slice, normalised, text_hashes = gate_result
    if not _l2_audit_passed(normalised):
        raw_vectors_list.clear()
        return
    _register_in_nrt_delta(  # FR-246 — see docs/specs/fr246-nrt-delta-faiss.md
        model_class=model_class,
        pks_slice=pks_slice,
        normalised=normalised,
    )
    use_text_hashes = (
        supports_text_hash
        and text_hashes is not None
        and len(text_hashes) == len(pks_slice)
    )
    _persist_flush_slice(
        model_class=model_class,
        pks_slice=pks_slice,
        normalised=normalised,
        supports_model_version=supports_model_version,
        embedding_signature=embedding_signature,
        use_text_hashes=use_text_hashes,
        text_hashes=text_hashes,
    )
    raw_vectors_list.clear()


def _persist_flush_slice(  # noqa: forbidden-pattern too-many-args  # justification: kwargs are the deliberate API; collapsing into a state object obscures the persistence boundary.
    *,
    model_class: type,
    pks_slice: list[int],
    normalised: np.ndarray,
    supports_model_version: bool,
    embedding_signature: str | None,
    use_text_hashes: bool,
    text_hashes: list[str] | None,
) -> None:
    """Archive prior ContentItem embeddings + bulk-update the new slice."""
    _archive_existing_content_item_embeddings(
        model_class=model_class,
        pks_slice=pks_slice,
        supports_model_version=supports_model_version,
        embedding_signature=embedding_signature,
    )
    _bulk_update_embeddings(
        model_class=model_class,
        pks_slice=pks_slice,
        normalised=normalised,
        supports_model_version=supports_model_version,
        embedding_signature=embedding_signature,
        use_text_hashes=use_text_hashes,
        text_hashes=text_hashes,
    )


def _bulk_update_embeddings(  # noqa: forbidden-pattern too-many-args  # justification: kwargs are the deliberate API; collapsing into a state object obscures which fields are being persisted at the bulk_update boundary.
    *,
    model_class,
    pks_slice: list[int],
    normalised,
    supports_model_version: bool,
    embedding_signature: str | None,
    use_text_hashes: bool,
    text_hashes: list[str] | None,
) -> None:
    """Build the bulk_update payload + fields list and write."""
    fields = (
        ["embedding"]
        + (
            ["embedding_model_version"]
            if supports_model_version and embedding_signature
            else []
        )
        + (["embedding_text_hash"] if use_text_hashes else [])
    )
    model_class.objects.bulk_update(
        _build_bulk_update_rows(
            model_class,
            pks_slice,
            normalised,
            supports_model_version=supports_model_version,
            embedding_signature=embedding_signature,
            use_text_hashes=use_text_hashes,
            text_hashes=text_hashes,
        ),
        fields=fields,
        batch_size=500,
    )


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


def _get_model_name() -> str:
    """Read the configured embedding model name from AppSetting."""
    try:
        from apps.core.models import AppSetting

        setting = AppSetting.objects.filter(key="embedding.model").first()
        if setting:
            return str(setting.value)
    except Exception:
        logger.debug(
            "AppSetting table not available, using default embedding model name"
        )
    return DEFAULT_MODEL_NAME


# Bounds for the user-tunable batch size (mirrored in RuntimeConfigView).
# Anything below the floor is too small to benefit from vectorisation;
# anything above the ceiling risks memory pressure on smaller hosts.
_BATCH_SIZE_MIN = 8
_BATCH_SIZE_MAX = 128
_BATCH_SIZE_HIGH = _BATCH_SIZE_MAX
_BATCH_SIZE_DEFAULT = 32
_OOM_ERROR_MARKERS = (
    "out of memory",
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
    signature = f"{resolved_model_name}:{dimension}"
    # Phase 4 fix #3 — write-through to AppSetting so the Confidence
    # Meter can read the signature without a cold model load.
    # Best-effort: failure to cache must not break the embed flow.
    _publish_signature_to_appsetting(signature)
    return signature


def _load_model(*args, **kwargs):
    """Compatibility hook for old tests; provider loading now lives in get_provider."""
    from apps.pipeline.services.embedding_providers import get_provider

    return get_provider()


def _load_legacy_model_or_none() -> Any | None:
    """Return a legacy local model only when tests or callers provide one."""
    try:
        model = _load_model()
    except Exception:
        logger.debug("Legacy embedding model hook unavailable", exc_info=True)
        return None
    return model if callable(getattr(model, "encode", None)) else None


def _thermal_guard_before_gpu_batch(*args, **kwargs) -> None:
    """Compatibility no-op; provider-backed embeddings do not run local GPU batches."""
    return None


def _publish_signature_to_appsetting(signature: str) -> None:
    """Cache the signature in AppSetting for fast lookup by other services.

    Single row keyed by ``embedding.current_signature``. Update is
    idempotent — overwrites if the value differs, no-op if the same
    (so concurrent embed workers don't fight). Best-effort: any DB
    error is logged at debug and the embed flow continues.
    """
    try:
        from apps.core.models import AppSetting

        AppSetting.objects.update_or_create(
            key="embedding.current_signature",
            defaults={"value": signature},
        )
    except Exception:
        logger.debug("Could not cache embedding signature to AppSetting", exc_info=True)


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


def _read_batch_size_override() -> int | None:
    """Read AppSetting override (system.embedding_batch_size); None on absence/invalid."""
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
    return None


def _resolve_provider_embedding_dimension() -> int:
    """Return the active provider's output dimension; falls back to EMBEDDING_DIM."""
    try:
        from apps.pipeline.services.embedding_providers import get_provider

        provider = get_provider()
        return int(getattr(provider, "dimension", EMBEDDING_DIM)) or EMBEDDING_DIM
    except Exception:  # noqa: BLE001 — provider abstraction optional; use configured dim.
        return EMBEDDING_DIM


def _read_hardware_recommended_batch_size() -> int | None:
    """Hardware-aware auto-tuning per FR-233; None on any failure."""
    try:
        from apps.pipeline.services.hardware_profile import (
            detect_profile,
            recommended_batch_size,
        )

        auto_batch = recommended_batch_size(
            dimension=_resolve_provider_embedding_dimension(),
            profile=detect_profile(),
        )
        if _BATCH_SIZE_MIN <= auto_batch <= _BATCH_SIZE_MAX:
            return auto_batch
    except Exception:
        logger.debug(
            "Hardware-aware batch sizing unavailable; using mode-based default",
            exc_info=True,
        )
    return None


def _get_configured_batch_size() -> int:
    """Resolve the configured embedding batch size before model-aware tuning.

    Priority: AppSetting override → hardware-aware auto-tune → performance-mode default.
    """
    override = _read_batch_size_override()
    if override is not None:
        return override
    auto_batch = _read_hardware_recommended_batch_size()
    if auto_batch is not None:
        return auto_batch
    return _BATCH_SIZE_HIGH if _get_performance_mode() == "high" else _BATCH_SIZE_DEFAULT


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
    """Detect OOM-style failures from provider clients."""
    message = str(exc).lower()
    return any(marker in message for marker in _OOM_ERROR_MARKERS)


def _clear_embedding_runtime_memory() -> None:
    """Best-effort memory cleanup after an OOM before retrying."""
    logger.debug("Runtime memory cleanup skipped; embeddings use paid providers.")


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


def _save_fallback_checkpoint(
    *,
    job_id: str | None,
    failing_provider: str,
    fallback_provider: str,
    reason_code: str,
) -> None:
    """Mark the SyncJob row that a provider fallback happened mid-run (FR-234).

    Written before the AppSetting swap + provider-cache clear so that if the
    worker crashes in that window, an operator inspecting the row sees the
    fallback was in-flight. Resume correctness is still carried by the
    ``embedding IS NULL`` filter — this checkpoint is for observability.
    """
    if not job_id:
        return
    try:
        from apps.sync.models import SyncJob

        SyncJob.objects.filter(job_id=job_id).update(
            is_resumable=True,
            checkpoint_stage="embed_fallback",
            message=(
                f"Provider fallback: {failing_provider} → {fallback_provider} "
                f"(reason={reason_code}). Resume continues with the new provider."
            ),
        )
    except Exception:
        logger.exception("Failed to persist fallback checkpoint for job_id=%s", job_id)


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


# FR-237 — L2-normalization audit. The FAISS index and NumPy fallback both use
# inner-product style scoring. They are mathematically identical to cosine
# scoring only for L2-normalized vectors. Without a runtime check, a regression
# in `_l2_normalize` or any later write step would silently bias every cosine
# score by the row magnitude. Sources:
#   - Wang et al. 2017, "Normalized Word Embedding and Orthogonal Transform
#     for Bilingual Word Translation," NAACL §2 — establishes that cosine
#     similarity on un-normalized vectors is biased by magnitude.
#   - IEEE 754-2019 §5.4 — single-precision rounding tolerance for
#     unit-magnitude floats is below 1e-6.
_L2_AUDIT_TOLERANCE: float = 1e-6


class L2NormalizationAuditError(ValueError):
    """Raised when post-quality-gate vectors fail the L2-norm invariant.

    Carries the row index of the worst offender and the observed deviation
    so the caller (and the operator log) can pinpoint which source row drove
    the failure. Inherits ValueError so existing broad-except handlers in
    the embedding pipeline log it without crashing the run.
    """

    def __init__(self, *, max_dev: float, worst_row: int, n_rows: int) -> None:
        self.max_dev = float(max_dev)
        self.worst_row = int(worst_row)
        self.n_rows = int(n_rows)
        super().__init__(
            f"L2-norm audit failed: max deviation {self.max_dev:.3e} > "
            f"tolerance {_L2_AUDIT_TOLERANCE:.3e} at row {self.worst_row} "
            f"of {self.n_rows}"
        )


def _audit_l2_normalization(
    arr: np.ndarray,
    *,
    tolerance: float = _L2_AUDIT_TOLERANCE,
) -> None:
    """Verify every row of *arr* is L2-unit. No-op on zero-row input.

    Called from ``_flush_embeddings_slice`` after the quality gate has
    pruned rows but before bulk_update writes to the DB. Catches drift
    introduced between ``_l2_normalize`` and persistence — which could
    otherwise propagate silently into FAISS and bias cosine scores.

    Cost: one ``np.linalg.norm`` over the batch (~2 µs for a 64-row × 1024-
    dim float32 matrix on a modern CPU). Trivial overhead vs. the embed
    forward pass that produced *arr*.

    FR-248 hardening: NaN/Inf precheck. IEEE 754-2019 §6.2 states that
    every comparison involving NaN evaluates False, so a `max_dev >
    tolerance` check would silently slip a NaN row through. The
    explicit ``np.isnan`` precheck closes that gap (Higham 2002 §1.4
    — adversarial inputs must fail loudly).
    """
    if arr.shape[0] == 0:
        return
    if np.any(np.isnan(arr)):
        first_bad = int(np.argmax(np.any(np.isnan(arr), axis=1)))
        raise L2NormalizationAuditError(
            max_dev=float("nan"),
            worst_row=first_bad,
            n_rows=int(arr.shape[0]),
        )
    if np.any(np.isinf(arr)):
        first_bad = int(np.argmax(np.any(np.isinf(arr), axis=1)))
        raise L2NormalizationAuditError(
            max_dev=float("inf"),
            worst_row=first_bad,
            n_rows=int(arr.shape[0]),
        )
    norms = np.linalg.norm(arr, axis=1)
    deviations = np.abs(norms - 1.0)
    max_dev = float(deviations.max())
    if max_dev > tolerance:
        worst_row = int(deviations.argmax())
        raise L2NormalizationAuditError(
            max_dev=max_dev,
            worst_row=worst_row,
            n_rows=int(arr.shape[0]),
        )


def _register_in_nrt_delta(
    *,
    model_class: type,
    pks_slice: list[int],
    normalised: np.ndarray,
) -> None:
    """FR-246 — push freshly-embedded ContentItem rows into the NRT delta.

    Cold-start safe: any failure (DB lookup, delta-add) is logged and
    swallowed so the flush continues. The base 15-minute FAISS rebuild
    is the eventual-consistency floor; the delta is purely an
    optimisation (Bialecki 2012 SIGIR-OSIR §3 NRT pattern).
    """
    if pks_slice is None or len(pks_slice) == 0 or normalised.shape[0] == 0:
        return
    try:
        from apps.content.models import ContentItem

        if model_class is not ContentItem:
            return
        rows = list(
            ContentItem.objects.filter(pk__in=pks_slice).values_list(
                "pk",
                "content_type",
            )
        )
        ct_by_pk = {pk: ct for pk, ct in rows}
        from .nrt_delta_index import get_live_delta

        delta = get_live_delta()
        for idx, pk in enumerate(pks_slice):
            ct = ct_by_pk.get(pk)
            if ct is None:
                continue
            delta.add(int(pk), str(ct), normalised[idx])
    except Exception:  # noqa: BLE001 — defensive; never crash the flush.
        logger.exception("FR-246 — failed to register flush slice in NRT delta")


def _l2_audit_passed(normalised: np.ndarray) -> bool:
    """Run the FR-237 audit; emit ops-feed alert + return False on failure.

    Wrapper around ``_audit_l2_normalization`` that adapts the raise-on-fail
    invariant into a "drop the bad slice" policy at the flush boundary.
    Re-raising mid-flush would crash the entire embed run; dropping one
    slice loses 64-256 rows worth of fresh embeddings (the next pass
    re-encodes them via the embedding-text-hash supersede path). This is
    the smallest blast radius per Nygard 2018 *Release It!* §5
    circuit-breaker pattern.
    """
    try:
        _audit_l2_normalization(normalised)
        return True
    except L2NormalizationAuditError as audit_exc:
        logger.error("FR-237 L2 audit failed: %s", audit_exc)
        emit(
            "embeddings.l2_audit_failed",
            str(audit_exc),
            source="embeddings",
            severity="high",
            runtime_context={
                "max_dev": audit_exc.max_dev,
                "worst_row": audit_exc.worst_row,
                "n_rows": audit_exc.n_rows,
            },
        )
        return False


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Provider-aware encode helper (plan Part 1)
# ---------------------------------------------------------------------------


_FALLBACK_RETRY_COOLDOWN_SECONDS = 10
"""Seconds to wait between the failed primary call and the fallback retry.

Matches the plan's ``Retry(countdown=10)`` intent for FR-234. Prevents the
new provider from being hit immediately after the old one tripped a
rate-limit / auth error — some providers (OpenAI, Google) share org-level
throttles at the IP layer, so an instant retry can trip the same limit.
"""


_PROVIDER_FALLBACK_REASON_CODES = ("auth", "rate_limit", "budget", "transient")


def _try_get_active_provider():
    """Return the active embedding provider."""
    try:
        from apps.pipeline.services.embedding_providers import get_provider

        return get_provider()
    except Exception:
        logger.exception("get_provider failed")
        raise


def _encode_via_provider_with_fallback(
    *,
    provider,
    batch_texts: list[str],
    batch_size: int,
    job_id: str | None,
):
    """Call provider.embed; on auth/budget/rate_limit/transient errors, swap to fallback.

    Returns the EmbeddingResult AND the (possibly swapped) provider so the
    caller can record cost ledger entries against the actual provider used.
    Re-raises non-recoverable errors.
    """
    from apps.pipeline.services.embedding_providers import (
        BudgetExceededError,
        ProviderError,
    )

    captured_exc: Exception | None = None
    reason_code = "provider_error"
    try:
        return provider.embed(
            batch_texts, batch_size=batch_size, job_id=job_id
        ), provider
    except BudgetExceededError as exc:
        captured_exc = exc
        reason_code = "budget"
    except ProviderError as exc:
        captured_exc = exc
        reason_code = getattr(exc, "reason", "provider_error")
        if reason_code not in _PROVIDER_FALLBACK_REASON_CODES:
            raise
    # Recoverable error path — captured_exc is guaranteed set by the except blocks above.
    fallback = _attempt_graceful_fallback(
        failing_provider_name=getattr(provider, "name", "unknown"),
        reason=str(captured_exc),
        reason_code=reason_code,
        job_id=job_id,
    )
    if fallback is None:
        raise captured_exc
    time.sleep(_FALLBACK_RETRY_COOLDOWN_SECONDS)
    return fallback.embed(batch_texts, batch_size=batch_size, job_id=job_id), fallback


def _encode_batch_via_provider(
    *,
    batch_texts: list[str],
    model: Any,
    batch_size: int,
    job_id: str | None,
) -> np.ndarray:
    """Encode a batch through the active provider abstraction.

    API providers go through provider.embed with graceful fallback (FR-234)
    and record token + cost usage in ``EmbeddingCostLedger``.
    """
    if callable(getattr(model, "encode", None)):
        return np.asarray(model.encode(batch_texts), dtype=np.float32)
    provider = _try_get_active_provider()
    result, used_provider = _encode_via_provider_with_fallback(
        provider=provider,
        batch_texts=batch_texts,
        batch_size=batch_size,
        job_id=job_id,
    )
    if job_id:
        _record_provider_usage(
            job_id=job_id,
            provider_name=getattr(used_provider, "name", "unknown"),
            signature=getattr(used_provider, "signature", ""),
            items=len(batch_texts),
            tokens=getattr(result, "tokens_input", 0),
            cost_usd=getattr(result, "cost_usd", 0.0),
        )
    return result.vectors


def _read_fallback_provider_name() -> str:
    """Read ``AppSetting("embedding.fallback_provider")``; default ``openai``."""
    from apps.core.models import AppSetting

    fallback_row = AppSetting.objects.filter(key="embedding.fallback_provider").first()
    fallback_name = str(fallback_row.value).strip().lower() if fallback_row else "openai"
    return fallback_name or "openai"


def _swap_active_provider(fallback_name: str):
    """Persist the new provider name + reset cache + return the new provider instance."""
    from apps.core.models import AppSetting

    AppSetting.objects.update_or_create(
        key="embedding.provider",
        defaults={"value": fallback_name},
    )
    from apps.pipeline.services.embedding_providers import clear_cache, get_provider

    clear_cache()
    return get_provider()


def _attempt_graceful_fallback(
    *,
    failing_provider_name: str,
    reason: str,
    reason_code: str,
    job_id: str | None = None,
) -> Any | None:
    """Switch ``embedding.provider`` to the configured fallback and return the new provider.

    Called from ``_encode_batch_via_provider`` when the primary provider raises
    a recoverable error (auth / rate-limit / budget / transient). Persists a
    SyncJob fallback checkpoint (FR-234) so the operator sees the in-flight
    state, updates ``AppSetting("embedding.provider")``, clears the provider
    cache, and emits an operator alert. Returns ``None`` on any internal
    failure so the caller re-raises the original error.
    """
    try:
        fallback_name = _read_fallback_provider_name()
        if fallback_name == failing_provider_name:
            logger.warning(
                "Fallback provider equals failing provider (%s); cannot recover",
                failing_provider_name,
            )
            return None
        _save_fallback_checkpoint(
            job_id=job_id,
            failing_provider=failing_provider_name,
            fallback_provider=fallback_name,
            reason_code=reason_code,
        )
        new_provider = _swap_active_provider(fallback_name)
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
        logger.exception(
            "Graceful fallback failed for provider=%s",
            failing_provider_name,
        )
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
        from apps.notifications.models import OperatorAlert
        from apps.notifications.services import emit_operator_alert

        emit_operator_alert(
            event_type="embedding.provider_fallback",
            severity="warning",
            title="Embedding provider fallback active",
            message=(
                f"Embedding provider changed from {failing} to {fallback} "
                f"because {reason_code}: {reason_message[:500]}"
            ),
            source_area=OperatorAlert.AREA_MODELS,
            dedupe_key=f"embedding.provider_fallback:{failing}:{fallback}",
            related_route="/jobs",
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


def _quality_gate_should_skip(
    *,
    model_class: type,
    pks_slice: list[int],
    embedding_signature: str | None,
) -> bool:
    """Pre-flight check: gate runs only for ContentItem with non-empty PKs + a signature."""
    return (
        getattr(model_class, "__name__", "") != "ContentItem"
        or not pks_slice
        or embedding_signature is None
    )


def _fetch_existing_quality_gate_rows(
    model_class: type,
    pks_slice: list[int],
) -> tuple[dict, bool] | None:
    """Bulk-fetch the (embedding, signature, text) rows the gate inspects.

    Returns ``(by_pk_dict, has_signature_field)`` on success, ``None`` if
    the fetch failed (caller treats as gate-disabled).
    """
    try:
        has_signature_field = _model_supports_field(
            model_class, "embedding_model_version"
        )
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
        return None
    return existing, has_signature_field


def _build_quality_gate_instance(thresholds: tuple):
    """Construct the QualityGate with provider lookup + threshold kwargs."""
    from apps.pipeline.services.embedding_quality_gate import (
        QualityGate,
        load_provider_ranking,
    )

    try:
        from apps.pipeline.services.embedding_providers import get_provider

        provider = get_provider()
    except Exception:  # noqa: BLE001 — gate works without a provider (uses cosine alone).
        provider = None
    return QualityGate(
        provider_ranking=load_provider_ranking(),
        provider=provider,
        quality_delta_threshold=thresholds[0],
        noop_cosine_threshold=thresholds[1],
        stability_threshold=thresholds[2],
    )


def _extract_existing_quality_gate_inputs(
    row: dict | None,
    has_signature_field: bool,
) -> tuple[np.ndarray | None, str, str | None]:
    """Pull (old_vec, old_sig, text) out of an existing-row dict."""
    if row is None:
        return None, "", None
    raw_emb = row.get("embedding")
    old_vec = None
    if raw_emb is not None:
        try:
            old_vec = np.asarray(raw_emb, dtype=np.float32)
        except Exception:  # noqa: BLE001 — corrupt vector becomes "no prior" so the gate accepts the new one.
            old_vec = None
    old_sig = (row.get("embedding_model_version") or "") if has_signature_field else ""
    title = row.get("title") or ""
    distilled = row.get("distilled_text") or ""
    return old_vec, old_sig, f"{title}\n\n{distilled}".strip()


def _run_quality_gate(
    *,
    model_class: type,
    pks_slice: list[int],
    normalised: np.ndarray,
    embedding_signature: str | None,
) -> tuple[list[int] | None, list[int]]:
    """Apply the measure-twice gate to this flush batch.

    Returns ``(kept_indices, kept_pks)``. ``kept_indices=None`` means the
    gate is disabled (caller should act as pre-feature). Only ContentItem
    currently goes through the gate.
    """
    try:
        from apps.pipeline.services.embedding_quality_gate import (
            is_gate_enabled,
            load_gate_thresholds,
            persist_decisions,
        )
    except ImportError:
        return None, pks_slice
    if not is_gate_enabled() or _quality_gate_should_skip(
        model_class=model_class,
        pks_slice=pks_slice,
        embedding_signature=embedding_signature,
    ):
        return None, pks_slice
    fetch_result = _fetch_existing_quality_gate_rows(model_class, pks_slice)
    if fetch_result is None:
        return None, pks_slice
    existing, has_signature_field = fetch_result
    gate = _build_quality_gate_instance(load_gate_thresholds())
    decisions_to_log: list = []
    kept_indices: list[int] = []
    kept_pks: list[int] = []
    for idx, pk in enumerate(pks_slice):
        old_vec, old_sig, text = _extract_existing_quality_gate_inputs(
            existing.get(pk),
            has_signature_field,
        )
        decision = gate.evaluate(
            text=text,
            old_vec=old_vec,
            old_sig=old_sig,
            new_vec=normalised[idx],
            new_sig=embedding_signature,
        )
        decisions_to_log.append(
            (pk, "content_item", decision, old_sig, embedding_signature),
        )
        if decision.action in ("REPLACE", "ACCEPT_NEW"):
            kept_indices.append(idx)
            kept_pks.append(pk)
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


# Checkpoint cadence — every Nth batch flushes the in-memory vector buffer to
# DB so a worker crash mid-run doesn't lose all the work since the last
# successful batch. The same cadence throttles the SyncJob progress save so
# the embeddings phase doesn't issue O(N/batch_size) UPDATE statements.
_EMBEDDING_CHECKPOINT_FLUSH_EVERY_N_BATCHES = 5


def _build_content_item_text_inputs(
    items: list[tuple],
) -> tuple[list[int], list[str], list[str]]:
    """Build (pks, texts, text_hashes) from raw ContentItem rows.

    Each text = ``{title}\n\n{body}``. ``body`` prefers ``post.clean_text``
    over ``distilled_text``. Empty rows skipped. Texts > _MAX_EMBED_CHARS
    truncated at the nearest sentence boundary.
    """
    pks: list[int] = []
    texts: list[str] = []
    text_hashes: list[str] = []  # Group D.2 — SHA-256 of exact embed text
    for pk, title, clean_text, distilled in items:
        title_clean = (title or "").strip()
        body_source = (clean_text or "").strip() or (distilled or "").strip()
        text = f"{title_clean}\n\n{body_source}".strip() if body_source else title_clean
        if not text:
            continue
        if len(text) > _MAX_EMBED_CHARS:
            text = _truncate_at_sentence(text, _MAX_EMBED_CHARS)
        pks.append(pk)
        texts.append(text)
        text_hashes.append(_compute_embed_text_hash(text))
    return pks, texts, text_hashes


def _build_sentence_text_inputs(
    sentences: list[tuple],
) -> tuple[list[int], list[str]]:
    """Build (pks, texts) from raw Sentence rows. Skips empty sentences."""
    pks: list[int] = []
    texts: list[str] = []
    for pk, text in sentences:
        if text and text.strip():
            pks.append(pk)
            texts.append(text.strip())
    return pks, texts


def _encode_one_batch_with_oom_recovery(
    *,
    batch_texts: list[str],
    model,
    batch_size: int,
    model_name: str,
    job_id: str | None,
) -> tuple[Any, int] | None:
    """Encode one batch; on OOM, return (None, retry_batch_size) so the caller can retry.

    Returns:
        (vectors, batch_size) on success — caller advances the cursor.
        (None, retry_batch_size) on OOM — caller retries SAME cursor with new size.
        Re-raises non-OOM exceptions.
    """
    try:
        vectors = _encode_batch_via_provider(
            batch_texts=batch_texts,
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
        return None, retry_batch_size
    return vectors, batch_size


def _flush_loop_slice(
    *,
    model_class,
    pks: list[int],
    raw_vectors_list: list,
    embedding_signature: str,
    text_hashes: list[str] | None,
    flushed_count: int,
    cursor: int,
) -> None:
    """Slice + flush helper used by both the pause-flush and checkpoint-flush paths."""
    _flush_embeddings_slice(
        model_class,
        pks[flushed_count:cursor],
        raw_vectors_list,
        embedding_signature=embedding_signature,
        text_hashes=(
            text_hashes[flushed_count:cursor] if text_hashes is not None else None
        ),
    )


def _handle_embedding_pause(  # noqa: forbidden-pattern too-many-args  # justification: kwargs preserve readability at the single shared callsite; collapsing into a state object would obscure which state matters at the pause boundary.
    *,
    model_class,
    pks: list[int],
    raw_vectors_list: list,
    embedding_signature: str,
    text_hashes: list[str] | None,
    flushed_count: int,
    cursor: int,
    job_id: str | None,
    pause_reason: str,
) -> None:
    """Flush buffered vectors, mark the SyncJob paused, then raise JobPaused."""
    _flush_loop_slice(
        model_class=model_class,
        pks=pks,
        raw_vectors_list=raw_vectors_list,
        embedding_signature=embedding_signature,
        text_hashes=text_hashes,
        flushed_count=flushed_count,
        cursor=cursor,
    )
    _mark_embedding_job_paused(job_id, pause_reason)
    from apps.core.pause_contract import JobPaused

    raise JobPaused(pause_reason)


def _run_embedding_loop(  # noqa: forbidden-pattern too-many-args  # justification: kwargs are the deliberate API to keep callsite intent explicit; collapsing to a dict obscures which fields the loop actually reads.
    *,
    model_class,
    pks: list[int],
    texts: list[str],
    text_hashes: list[str] | None,
    model,
    batch_size: int,
    embedding_signature: str,
    model_name: str,
    job_id: str | None,
    on_progress,
) -> None:
    """Encode + checkpoint-flush in batches.

    Shared between :func:`generate_content_item_embeddings` and
    :func:`generate_sentence_embeddings`. Handles pause / OOM-recovery /
    checkpoint flushing uniformly.

    ``on_progress(processed, total, batch_num)`` is invoked after every
    successful batch so callers can publish progress / save SyncJob rows.
    """
    raw_vectors_list: list = []
    total = len(texts)
    state = {"batch_num": 0, "flushed_count": 0, "cursor": 0, "batch_size": batch_size}
    while state["cursor"] < total:
        pause_reason = _get_embedding_pause_reason(job_id)
        if pause_reason:
            _handle_embedding_pause(
                model_class=model_class,
                pks=pks,
                raw_vectors_list=raw_vectors_list,
                embedding_signature=embedding_signature,
                text_hashes=text_hashes,
                flushed_count=state["flushed_count"],
                cursor=state["cursor"],
                job_id=job_id,
                pause_reason=pause_reason,
            )
        _process_one_embedding_batch(
            state=state,
            model_class=model_class,
            pks=pks,
            texts=texts,
            text_hashes=text_hashes,
            raw_vectors_list=raw_vectors_list,
            model=model,
            embedding_signature=embedding_signature,
            model_name=model_name,
            job_id=job_id,
            on_progress=on_progress,
        )
    # Tail flush — helper no-ops on empty buffer.
    _flush_loop_slice(
        model_class=model_class,
        pks=pks,
        raw_vectors_list=raw_vectors_list,
        embedding_signature=embedding_signature,
        text_hashes=text_hashes,
        flushed_count=state["flushed_count"],
        cursor=total,
    )


def _process_one_embedding_batch(  # noqa: forbidden-pattern too-many-args  # justification: state-mutating shared body, single callsite.
    *,
    state: dict,
    model_class,
    pks: list[int],
    texts: list[str],
    text_hashes: list[str] | None,
    raw_vectors_list: list,
    model,
    embedding_signature: str,
    model_name: str,
    job_id: str | None,
    on_progress,
) -> None:
    """Encode-and-buffer one batch + checkpoint-flush every Nth batch.

    Mutates ``state`` in place so the outer loop sees cursor / batch_num /
    flushed_count / batch_size advances even after OOM-driven batch shrinks.
    """
    batch_texts = texts[state["cursor"] : state["cursor"] + state["batch_size"]]
    vectors, state["batch_size"] = _encode_one_batch_with_oom_recovery(
        batch_texts=list(batch_texts),
        model=model,
        batch_size=state["batch_size"],
        model_name=model_name,
        job_id=job_id,
    )
    if vectors is None:
        return  # OOM auto-retried with smaller batch_size next iteration
    raw_vectors_list.append(vectors)
    state["batch_num"] += 1
    state["cursor"] += len(batch_texts)
    on_progress(
        processed=state["cursor"], total=len(texts), batch_num=state["batch_num"]
    )
    if state["batch_num"] % _EMBEDDING_CHECKPOINT_FLUSH_EVERY_N_BATCHES == 0:
        _flush_loop_slice(
            model_class=model_class,
            pks=pks,
            raw_vectors_list=raw_vectors_list,
            embedding_signature=embedding_signature,
            text_hashes=text_hashes,
            flushed_count=state["flushed_count"],
            cursor=state["cursor"],
        )
        state["flushed_count"] = state["cursor"]


def _build_content_item_queryset(
    content_item_ids: list[int] | None,
    force_reembed: bool,
    embedding_signature: str,
):
    """Filter ContentItem rows down to "still needs an embedding"."""
    from apps.content.models import ContentItem

    # Group A.6 — exclude rows flagged as cross-source duplicates. Their
    # embedding is reused from ``duplicate_of`` at retrieval time, so
    # generating one here would just waste provider calls and disk.
    qs = ContentItem.objects.filter(is_deleted=False, duplicate_of__isnull=True)
    if content_item_ids is not None:
        qs = qs.filter(pk__in=content_item_ids)
    if not force_reembed:
        qs = qs.exclude(
            embedding__isnull=False,
            embedding_model_version=embedding_signature,
        )
    return qs.values_list("pk", "title", "post__clean_text", "distilled_text")


def _make_content_item_progress_callback(job_id: str | None):
    """Return an ``on_progress(processed, total, batch_num)`` that publishes the
    Content embeddings progress + writes ``SyncJob.embedding_items_completed``."""
    if not job_id:
        return lambda **_: None
    from apps.sync.models import SyncJob
    from apps.pipeline.tasks import _publish_progress

    job = SyncJob.objects.filter(job_id=job_id).first()

    def _on_progress(*, processed: int, total: int, batch_num: int) -> None:
        pct = processed / total
        if job:
            job.embedding_items_completed = processed
            # Throttle SyncJob writes — saving every batch issues
            # O(N/batch_size) UPDATEs; every Nth batch cuts that drastically
            # with negligible progress-reporting lag.
            if (
                batch_num % _EMBEDDING_CHECKPOINT_FLUSH_EVERY_N_BATCHES == 0
                or processed == total
            ):
                job.save(update_fields=["embedding_items_completed", "updated_at"])
        _publish_progress(
            job_id,
            "running",
            0.8 + (pct * 0.1),
            f"Content embeddings: {processed}/{total}...",
            embedding_progress=pct * 0.5,  # CIs are first half
            ml_progress=0.7 + (pct * 0.15),
        )

    return _on_progress


def generate_content_item_embeddings(
    content_item_ids: list[int] | None = None,
    job_id: str | None = None,
    force_reembed: bool = False,
) -> dict[str, int]:
    """Generate and store embeddings for ContentItem.embedding (destination embeddings).

    Each ContentItem's embedding = L2-normalized encoding of:
        '{title}\\n\\n{post.clean_text or distilled_text}'.strip()

    Args:
        content_item_ids: List of ContentItem PKs to embed.
                          None = all items with is_deleted=False.

    Returns:
        Dict with 'embedded' and 'skipped' counts.
    """
    from apps.content.models import ContentItem

    provider = _try_get_active_provider()
    model = _load_legacy_model_or_none()
    model_name = _get_model_name() if model is not None else getattr(
        provider, "model_name", _get_model_name()
    )
    embedding_signature = (
        get_current_embedding_signature(model=model, model_name=model_name)
        if model is not None
        else getattr(
            provider,
            "signature",
            get_current_embedding_signature(model=None, model_name=model_name),
        )
    )
    batch_size = _get_batch_size(None)
    items = list(
        _build_content_item_queryset(
            content_item_ids,
            force_reembed,
            embedding_signature,
        )
    )
    if not items:
        return {"embedded": 0, "skipped": 0}
    pks, texts, text_hashes = _build_content_item_text_inputs(items)
    if not texts:
        return {"embedded": 0, "skipped": len(items)}
    logger.info("Embedding %d content items...", len(texts))
    start = time.monotonic()
    _run_embedding_loop(
        model_class=ContentItem,
        pks=pks,
        texts=texts,
        text_hashes=text_hashes,
        model=model,
        batch_size=batch_size,
        embedding_signature=embedding_signature,
        model_name=model_name,
        job_id=job_id,
        on_progress=_make_content_item_progress_callback(job_id),
    )
    logger.info("Encoded %d items in %.2fs.", len(texts), time.monotonic() - start)
    return {"embedded": len(pks), "skipped": len(items) - len(pks)}


def _build_sentence_queryset(
    content_item_ids: list[int] | None,
    force_reembed: bool,
    embedding_signature: str,
):
    """Filter Sentence rows down to "in HOST_SCAN_WORD_LIMIT window AND still needs embedding"."""
    from apps.content.models import Sentence

    qs = Sentence.objects.filter(content_item__is_deleted=False)
    if content_item_ids is not None:
        qs = qs.filter(content_item__pk__in=content_item_ids)
    if not force_reembed:
        qs = qs.exclude(
            embedding__isnull=False,
            embedding_model_version=embedding_signature,
        )
    return qs.filter(word_position__lte=settings.HOST_SCAN_WORD_LIMIT).values_list(
        "pk", "text"
    )


def _make_sentence_progress_callback(job_id: str | None):
    """Return an ``on_progress(processed, total, batch_num)`` for sentence embeddings."""
    if not job_id:
        return lambda **_: None
    from apps.pipeline.tasks import _publish_progress

    def _on_progress(*, processed: int, total: int, batch_num: int) -> None:
        pct = processed / total
        _publish_progress(
            job_id,
            "running",
            0.9 + (pct * 0.09),
            f"Sentence embeddings: {processed}/{total}...",
            embedding_progress=0.5 + (pct * 0.5),  # Sentences = second half
            ml_progress=0.85 + (pct * 0.14),
        )

    return _on_progress


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

    provider = _try_get_active_provider()
    model = _load_legacy_model_or_none()
    model_name = _get_model_name() if model is not None else getattr(
        provider, "model_name", _get_model_name()
    )
    embedding_signature = (
        get_current_embedding_signature(model=model, model_name=model_name)
        if model is not None
        else getattr(
            provider,
            "signature",
            get_current_embedding_signature(model=None, model_name=model_name),
        )
    )
    batch_size = _get_batch_size(None)
    sentences = list(
        _build_sentence_queryset(
            content_item_ids,
            force_reembed,
            embedding_signature,
        )
    )
    if not sentences:
        return {"embedded": 0, "skipped": 0}
    pks, texts = _build_sentence_text_inputs(sentences)
    if not texts:
        return {"embedded": 0, "skipped": len(sentences)}
    logger.info("Embedding %d sentences...", len(texts))
    start = time.monotonic()
    _run_embedding_loop(
        model_class=Sentence,
        pks=pks,
        texts=texts,
        text_hashes=None,
        model=model,
        batch_size=batch_size,
        embedding_signature=embedding_signature,
        model_name=model_name,
        job_id=job_id,
        on_progress=_make_sentence_progress_callback(job_id),
    )
    logger.info("Encoded %d sentences in %.2fs.", len(texts), time.monotonic() - start)
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
    """Return a status dict about the active paid embedding provider."""
    model_name = _get_model_name()
    runtime_resolution = get_effective_runtime_resolution()
    model = _model_cache.get(f"{model_name}::{runtime_resolution['device']}")
    profile = _describe_model_runtime(
        model_name=model_name,
        configured_batch_size=_get_configured_batch_size(),
        model=model,
    )
    return {
        "model_name": model_name,
        "loaded": True,
        "device": runtime_resolution["device"],
        "fp16": False,
        "mode": runtime_resolution["performance_mode"],
        "effective_runtime_mode": runtime_resolution["effective_runtime_mode"],
        "effective_runtime_reason": runtime_resolution["reason"],
        "batch_size": _get_batch_size(None),
        "configured_batch_size": profile["configured_batch_size"],
        "embedding_dim": profile["embedding_dim"],
        "active_signature": profile["active_signature"],
        "storage_dimension_cap": profile["storage_dimension_cap"],
        "dimension_compatible": profile["dimension_compatible"],
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }
