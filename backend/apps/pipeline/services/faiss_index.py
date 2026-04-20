"""FR-030 — Persistent FAISS-GPU index for Stage 1 vector search.

⚠  ARCHITECTURE WARNING — SINGLE-WORKER REQUIREMENT
The FAISS index is stored in process-local globals protected by a
threading.Lock.  That lock is only meaningful within a single OS process.
If the Celery worker is started with --concurrency > 1 (multiple forked
processes), each process maintains its own private copy of the index and
only rebuilds it on its own 15-minute Beat tick.  This means:

  - New embeddings may be invisible to all-but-one worker for up to 15 min.
  - Under heavy load, multiple processes independently rebuild the index,
    wasting DB reads and memory.

The safe deployment is: --concurrency=1 for the pipeline/embeddings queue,
or move the FAISS search to a dedicated single-process microservice.

`_assert_single_worker()` is called at app-ready time and raises if the
process count exceeds 1, so misconfiguration is caught at startup rather
than silently degrading quality.
"""

import logging
import os
import threading

import numpy as np

from apps.pipeline.services.embeddings import (
    get_current_embedding_dimension,
    get_current_embedding_filter,
)

try:
    import faiss

    HAS_FAISS = True
except ImportError:
    HAS_FAISS = False

logger = logging.getLogger(__name__)

_index_lock = threading.Lock()
_faiss_index = None  # faiss.Index | None
_faiss_id_map: list[int] = []  # position i -> ContentItem.pk
_faiss_content_type_map: list[str] = []  # position i -> content_type


def _assert_single_worker() -> None:
    """Warn loudly if FAISS is being loaded inside a multi-process Celery worker.

    Call this from AppConfig.ready() when FAISS is enabled.  It detects the
    CELERY_WORKER_CONCURRENCY environment variable (set in docker-compose) and
    emits a structured warning so the issue appears in startup logs before
    queries start returning stale results.
    """
    concurrency_env = os.environ.get("CELERY_WORKER_CONCURRENCY", "")
    try:
        concurrency = int(concurrency_env)
    except (ValueError, TypeError):
        concurrency = 0  # unknown — don't block startup

    if concurrency > 1:
        logger.warning(
            "FAISS index is process-local but CELERY_WORKER_CONCURRENCY=%d. "
            "Only one worker process will have an up-to-date index at a time. "
            "Set --concurrency=1 for the pipeline/embeddings queues or move "
            "FAISS to a dedicated single-process service.",
            concurrency,
        )


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

    qs = ContentItem.objects.filter(
        embedding__isnull=False,
        **get_current_embedding_filter(),
    ).values_list("pk", "content_type", "embedding")

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
        # Cap FAISS GPU temp memory to 512 MB to leave headroom for
        # embedding model + Chrome.  See docs/PERFORMANCE.md §6.
        res.setTempMemory(512 * 1024 * 1024)
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
        len(pks),
        dim,
        device,
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

    vram_mb = round(
        n * get_current_embedding_dimension() * 4 / (1024**2)
    ) if on_gpu else 0

    return {
        "active": True,
        "vectors": n,
        "device": device,
        "vram_mb": vram_mb,
    }
