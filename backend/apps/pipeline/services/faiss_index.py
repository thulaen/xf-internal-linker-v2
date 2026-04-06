"""FR-030 — Persistent FAISS-GPU index for Stage 1 vector search."""

import logging
import threading

import numpy as np

try:
    import faiss
    HAS_FAISS = True
except ImportError:
    HAS_FAISS = False

logger = logging.getLogger(__name__)

_index_lock = threading.Lock()
_faiss_index = None                       # faiss.Index | None
_faiss_id_map: list[int] = []            # position i -> ContentItem.pk
_faiss_content_type_map: list[str] = []  # position i -> content_type


def build_faiss_index() -> None:
    """Load all ContentItem embeddings from DB and build the FAISS index.

    Called once at startup (via apps.py ready()) and every 15 minutes by Celery Beat.
    Thread-safe — replaces the global index atomically.
    """
    global _faiss_index, _faiss_id_map, _faiss_content_type_map

    if not HAS_FAISS:
        logger.warning("faiss not installed — FAISS-GPU path disabled")
        return

    from django.conf import settings
    from apps.content.models import ContentItem
    from apps.pipeline.services.pipeline import _coerce_embedding_vector

    performance_mode = getattr(settings, "ML_PERFORMANCE_MODE", "STANDARD")

    qs = ContentItem.objects.filter(embedding__isnull=False).values_list(
        "pk", "content_type", "embedding"
    )

    pks: list[int] = []
    content_types: list[str] = []
    vectors: list[np.ndarray] = []

    for pk, ct, emb in qs:
        vec = _coerce_embedding_vector(emb)
        if vec is not None:
            pks.append(pk)
            content_types.append(ct)
            vectors.append(vec)

    if not vectors:
        logger.warning("FAISS index build: no embeddings found in DB")
        return

    matrix = np.vstack(vectors).astype(np.float32)
    dim = matrix.shape[1]

    index_cpu = faiss.IndexFlatIP(dim)
    index_cpu.add(matrix)

    if faiss.get_num_gpus() > 0 and performance_mode == "HIGH_PERFORMANCE":
        res = faiss.StandardGpuResources()
        index = faiss.index_cpu_to_gpu(res, 0, index_cpu)
        device = "GPU"
    else:
        index = index_cpu
        device = "CPU"

    with _index_lock:
        _faiss_index = index
        _faiss_id_map = pks
        _faiss_content_type_map = content_types

    logger.info(
        "FAISS index built: %d vectors, dim=%d, device=%s",
        len(pks), dim, device,
    )


def faiss_search(
    query_vectors: np.ndarray,
    k: int,
    host_pk_set: set[int] | None = None,
) -> list[list[tuple[int, str]]]:
    """Search the FAISS index for the top-K nearest host content items.

    Args:
        query_vectors: (B, D) float32 array of destination embeddings.
        k: number of neighbours to return per query.
        host_pk_set: if given, only return results whose PK is in this set.

    Returns:
        List of B lists. Each inner list contains (pk, content_type) tuples,
        ordered by descending similarity.
    """
    with _index_lock:
        index = _faiss_index
        id_map = list(_faiss_id_map)
        ct_map = list(_faiss_content_type_map)

    if index is None:
        return [[] for _ in range(len(query_vectors))]

    query = np.ascontiguousarray(query_vectors, dtype=np.float32)
    search_k = min(k * 2, len(id_map))  # over-fetch to allow filtering
    _scores, indices = index.search(query, search_k)

    results: list[list[tuple[int, str]]] = []
    for row in indices:
        hits: list[tuple[int, str]] = []
        for idx in row:
            if idx < 0:
                continue
            pk = id_map[idx]
            ct = ct_map[idx]
            if host_pk_set is not None and pk not in host_pk_set:
                continue
            hits.append((pk, ct))
            if len(hits) >= k:
                break
        results.append(hits)

    return results


def is_faiss_gpu_active() -> bool:
    """Return True when the index is loaded (GPU or CPU FAISS)."""
    with _index_lock:
        return _faiss_index is not None


def get_faiss_status() -> dict:
    """Return status dict for FR-028 diagnostics endpoint."""
    with _index_lock:
        index = _faiss_index
        n = len(_faiss_id_map)

    if not HAS_FAISS or index is None:
        return {"active": False, "vectors": 0, "device": "none", "vram_mb": 0}

    try:
        on_gpu = hasattr(index, "getDevice")
        device = f"GPU:{index.getDevice()}" if on_gpu else "CPU"
    except Exception:
        device = "unknown"
        on_gpu = False

    vram_mb = round(n * 1024 * 4 / (1024 ** 2)) if on_gpu else 0

    return {
        "active": True,
        "vectors": n,
        "device": device,
        "vram_mb": vram_mb,
    }
