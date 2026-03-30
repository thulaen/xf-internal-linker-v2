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
    """Return 'cuda' or 'cpu' based on ML_PERFORMANCE_MODE."""
    mode = os.environ.get("ML_PERFORMANCE_MODE", "BALANCED").upper()
    if mode == "HIGH_PERFORMANCE":
        try:
            import torch
            if torch.cuda.is_available():
                return "cuda"
        except ImportError:
            pass
    return "cpu"


def _load_model(model_name: str = DEFAULT_MODEL_NAME) -> Any:
    """Load and cache a sentence-transformers model."""
    if model_name in _model_cache:
        return _model_cache[model_name]

    from sentence_transformers import SentenceTransformer

    device = _resolve_device()
    logger.info("Loading embedding model '%s' on device='%s'...", model_name, device)
    start = time.monotonic()
    model = SentenceTransformer(model_name, device=device, trust_remote_code=True)
    elapsed = time.monotonic() - start
    logger.info("Model loaded in %.2fs.", elapsed)
    _model_cache[model_name] = model
    if device == "cpu":
        try:
            import torch

            torch.set_num_threads(4)
        except Exception:
            pass
    return model


def _get_model_name() -> str:
    """Read the configured embedding model name from AppSetting."""
    try:
        from apps.core.models import AppSetting
        setting = AppSetting.objects.filter(key="embedding_model").first()
        if setting:
            return str(setting.value)
    except Exception:
        pass
    return DEFAULT_MODEL_NAME


def _get_batch_size() -> int:
    mode = os.environ.get("ML_PERFORMANCE_MODE", "BALANCED").upper()
    return 128 if mode == "HIGH_PERFORMANCE" else 32


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
    raw_vectors = model.encode(
        texts,
        batch_size=batch_size,
        show_progress_bar=False,
        convert_to_numpy=True,
    )
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

    # Only embed sentences within the HOST_SCAN_WORD_LIMIT window
    qs = qs.filter(word_position__lte=settings.HOST_SCAN_WORD_LIMIT).values_list("pk", "text")

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
    raw_vectors = model.encode(
        texts,
        batch_size=batch_size,
        show_progress_bar=False,
        convert_to_numpy=True,
    )
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
) -> dict[str, int]:
    """Generate both ContentItem and Sentence embeddings in one call.

    Returns combined stats dict.
    """
    ci_stats = generate_content_item_embeddings(content_item_ids)
    sent_stats = generate_sentence_embeddings(content_item_ids)
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
        "mode": os.environ.get("ML_PERFORMANCE_MODE", "BALANCED"),
        "batch_size": _get_batch_size(),
        "embedding_dim": EMBEDDING_DIM,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }
