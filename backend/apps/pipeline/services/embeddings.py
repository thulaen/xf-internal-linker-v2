"""Embedding generation service.

V2 change from V1: eliminates .npy file artifacts entirely.
Embeddings are stored directly in pgvector VectorField columns on
ContentItem and Sentence models. The sentence-transformers model is
loaded once and cached in process.

Performance mode is controlled by ML_PERFORMANCE_MODE env var:
  BALANCED (default) — CPU only, batch_size=32
  HIGH_PERFORMANCE  — GPU if CUDA available, batch_size=128
"""

from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timezone
from typing import Any

import numpy as np
from django.conf import settings

try:
    from extensions import l2norm

    HAS_CPP_EXT = True
except ImportError:
    HAS_CPP_EXT = False

logger = logging.getLogger(__name__)

DEFAULT_MODEL_NAME = "BAAI/bge-m3"
EMBEDDING_DIM = 1024

_model_cache: dict[str, Any] = {}


# ---------------------------------------------------------------------------
# Model loading
# ---------------------------------------------------------------------------


def _resolve_device() -> str:
    """Return 'cuda' or 'cpu' based on ML_PERFORMANCE_MODE.

    When CUDA is selected, applies mode-dependent VRAM fraction limits
    as documented in docs/PERFORMANCE.md §6 (GPU Self-Limiting) AND runs a
    tiny warmup op (plan item 15). A driver can report CUDA available but
    fail on the first real op (bad VRAM state, thermal throttle at boot,
    etc.); warmup catches those silent failures so we fall back to CPU
    with a loud alert instead of crashing mid-pipeline.

    If the user asked for HIGH_PERFORMANCE but GPU is unavailable, emit the
    named operator-alert rule from notifications/alert_rules.py so they know
    the system silently dropped to CPU (plan item 10, rule d).
    """
    mode = os.environ.get("ML_PERFORMANCE_MODE", "BALANCED").upper()
    if mode == "HIGH_PERFORMANCE":
        try:
            import torch

            if torch.cuda.is_available():
                if not _cuda_warmup_ok():
                    _emit_gpu_fallback_alert("CUDA warmup failed")
                    return "cpu"
                _apply_vram_fraction()
                return "cuda"
            _emit_gpu_fallback_alert("CUDA not available")
        except ImportError:
            logger.debug("torch not installed, falling back to CPU")
            _emit_gpu_fallback_alert("torch not installed")
    return "cpu"


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


def _apply_vram_fraction() -> None:
    """Set per-process VRAM cap based on current performance mode.

    Safe/Balanced = 25% (1.5 GB on RTX 3050 6 GB).
    High Performance = 60% (3.6 GB on RTX 3050 6 GB).

    These percentages are relative to detected VRAM — they scale
    automatically with GPU upgrades.  See docs/PERFORMANCE.md §6.
    """
    try:
        import torch
        from django.conf import settings as django_settings

        # Read current performance mode from AppSetting if available,
        # fall back to env var.
        perf_mode = "balanced"
        try:
            from apps.core.models import AppSetting

            perf_mode = (
                AppSetting.objects.filter(key="system.performance_mode")
                .values_list("value", flat=True)
                .first()
                or "balanced"
            )
        except Exception:
            logger.debug(
                "AppSetting table not available, using default performance mode for VRAM fraction"
            )

        if perf_mode.lower() in ("high", "high_performance"):
            fraction = getattr(django_settings, "CUDA_MEMORY_FRACTION_HIGH", 0.60)
        else:
            fraction = getattr(django_settings, "CUDA_MEMORY_FRACTION_SAFE", 0.25)

        torch.cuda.set_per_process_memory_fraction(fraction)
        logger.info(
            "GPU VRAM fraction set to %.0f%% (mode=%s)", fraction * 100, perf_mode
        )
    except Exception:
        logger.warning("Failed to set VRAM fraction", exc_info=True)


def _check_gpu_temperature() -> bool:
    """Check GPU temperature against the hard ceiling.

    Returns True if safe to proceed, False if too hot.
    76°C ceiling is NON-NEGOTIABLE.  See docs/PERFORMANCE.md §6.
    """
    try:
        import pynvml

        pynvml.nvmlInit()
        handle = pynvml.nvmlDeviceGetHandleByIndex(0)
        temp = pynvml.nvmlDeviceGetTemperature(handle, pynvml.NVML_TEMPERATURE_GPU)
        pynvml.nvmlShutdown()

        from django.conf import settings as django_settings

        ceiling = getattr(django_settings, "GPU_TEMP_CEILING_C", 76)

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


def _wait_for_gpu_cooldown() -> None:
    """Block until GPU temperature drops below the resume threshold.

    Resume threshold: 68°C (configurable via GPU_TEMP_RESUME_C).
    """
    import time

    from django.conf import settings as django_settings

    resume_temp = getattr(django_settings, "GPU_TEMP_RESUME_C", 68)
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


def _load_model(model_name: str = DEFAULT_MODEL_NAME) -> Any:
    """Load and cache a sentence-transformers model."""
    if model_name in _model_cache:
        return _model_cache[model_name]

    from sentence_transformers import SentenceTransformer

    device = _resolve_device()
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
    _model_cache[model_name] = model
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

            torch.set_num_threads(4)
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


def _get_batch_size() -> int:
    """Resolve the embedding batch size.

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

    mode = os.environ.get("ML_PERFORMANCE_MODE", "BALANCED").upper()
    return _BATCH_SIZE_HIGH if mode == "HIGH_PERFORMANCE" else _BATCH_SIZE_DEFAULT


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
    batch_size = _get_batch_size()

    qs = ContentItem.objects.filter(is_deleted=False)
    if content_item_ids is not None:
        qs = qs.filter(pk__in=content_item_ids)

    if not force_reembed:
        qs = qs.filter(embedding__isnull=True)

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
    for i in range(0, total_items, batch_size):
        batch_texts = texts[i : i + batch_size]
        batch_vectors = model.encode(
            batch_texts,
            batch_size=batch_size,
            show_progress_bar=False,
            convert_to_numpy=True,
        )
        raw_vectors_list.append(batch_vectors)

        # Report progress
        if job_id:
            batch_num += 1
            processed = min(i + batch_size, total_items)
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

    # Persist final count regardless of whether the last batch fell on a multiple-of-5 boundary.
    if job_id and job:
        job.save(update_fields=["embedding_items_completed", "updated_at"])

    raw_vectors = np.vstack(raw_vectors_list)
    vectors = _l2_normalize(raw_vectors)
    elapsed = time.monotonic() - start
    logger.info("Encoded %d items in %.2fs.", len(texts), elapsed)

    # Bulk-update the embedding column
    to_update = [
        ContentItem(pk=pk, embedding=vec.tolist())
        for pk, vec in zip(pks, vectors, strict=True)
    ]
    ContentItem.objects.bulk_update(to_update, fields=["embedding"], batch_size=500)

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
    batch_size = _get_batch_size()

    qs = Sentence.objects.filter(
        content_item__is_deleted=False,
    )
    if content_item_ids is not None:
        qs = qs.filter(content_item__pk__in=content_item_ids)

    if not force_reembed:
        qs = qs.filter(embedding__isnull=True)

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

    for i in range(0, total_sentences, batch_size):
        batch_texts = texts[i : i + batch_size]
        batch_vectors = model.encode(
            batch_texts,
            batch_size=batch_size,
            show_progress_bar=False,
            convert_to_numpy=True,
        )
        raw_vectors_list.append(batch_vectors)

        # Report progress
        if job_id:
            from apps.pipeline.tasks import _publish_progress

            processed = min(i + batch_size, total_sentences)
            pct = processed / total_sentences

            _publish_progress(
                job_id,
                "running",
                0.9 + (pct * 0.09),
                f"Sentence embeddings: {processed}/{total_sentences}...",
                embedding_progress=0.5 + (pct * 0.5),  # Sentences are second half
                ml_progress=0.85 + (pct * 0.14),
            )

    raw_vectors = np.vstack(raw_vectors_list)
    vectors = _l2_normalize(raw_vectors)
    elapsed = time.monotonic() - start
    logger.info("Encoded %d sentences in %.2fs.", len(texts), elapsed)

    from apps.content.models import Sentence as SentenceModel

    to_update = [
        SentenceModel(pk=pk, embedding=vectors[idx].tolist())
        for idx, pk in enumerate(pks)
    ]
    SentenceModel.objects.bulk_update(to_update, fields=["embedding"], batch_size=500)

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
    loaded = model_name in _model_cache
    device = _resolve_device()
    return {
        "model_name": model_name,
        "loaded": loaded,
        "device": device,
        "fp16": device == "cuda",
        "mode": os.environ.get("ML_PERFORMANCE_MODE", "BALANCED"),
        "batch_size": _get_batch_size(),
        "embedding_dim": EMBEDDING_DIM,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }
