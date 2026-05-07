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

from apps.ops_feed.services import emit
from apps.core.performance_mode import (
    PERFORMANCE_MODE_HIGH,
    get_requested_performance_mode,
)
from apps.pipeline.services.embeddings import (
    get_current_embedding_dimension,
    get_current_embedding_filter,
)

try:
    import faiss

    HAS_FAISS = True
except ImportError:
    # Set the symbol to None so module-level callers (and tests using
    # ``mock.patch.object(faiss_index, "faiss", ...)``) always have a
    # stable attribute. Code paths gate on ``HAS_FAISS`` before
    # touching it, so a ``None`` value never reaches the FAISS API.
    faiss = None  # type: ignore[assignment]
    HAS_FAISS = False

logger = logging.getLogger(__name__)

_index_lock = threading.Lock()
_faiss_index = None  # faiss.Index | None
_faiss_id_map: list[int] = []  # position i -> ContentItem.pk
_faiss_content_type_map: list[str] = []  # position i -> content_type


def _assert_single_worker() -> None:
    """Warn loudly if FAISS is being loaded inside a multi-process Celery worker.

    Call this from AppConfig.ready() when FAISS is enabled. It detects the
    CELERY_WORKER_CONCURRENCY environment variable (set in docker-compose) and
    raises an alert via two channels:

    1. A structured warning on the standard logger (legacy path).
    2. Group B.2/B.3 — a deduped row on `/error-log` via
       ``apps.audit.error_ingest.ingest_error`` so the operator sees the
       misconfiguration in the noob-friendly errors page, not just buried
       in container logs. The audit-log call is wrapped in a defensive
       try/except so a broken audit subsystem can't take down startup.
    """
    concurrency_env = os.environ.get("CELERY_WORKER_CONCURRENCY", "")
    try:
        concurrency = int(concurrency_env)
    except (ValueError, TypeError):
        concurrency = 0  # unknown — don't block startup

    if concurrency <= 1:
        return

    message = (
        f"FAISS index is process-local but CELERY_WORKER_CONCURRENCY={concurrency}. "
        "Only one worker process will have an up-to-date index at a time. "
        "Set --concurrency=1 for the pipeline/embeddings queues or move FAISS "
        "to a dedicated single-process service."
    )
    logger.warning(message)
    try:
        from apps.audit.error_ingest import ingest_error
        from apps.audit.models import ErrorLog

        ingest_error(
            job_type="faiss_init",
            step="single_worker_assertion",
            error_message=message,
            why=(
                "Multi-process Celery is incompatible with the process-local "
                "FAISS index. Each forked worker keeps its own copy and only "
                "rebuilds on its own beat tick, so suggestions can disagree "
                "across workers for up to 15 minutes."
            ),
            severity=ErrorLog.SEVERITY_CRITICAL,
        )
    except Exception:
        # Audit subsystem broken — leave the logger.warning above as the
        # signal of last resort. Do not crash worker startup over an
        # audit-log issue.
        logger.exception(
            "single-worker assertion fired but audit-log ingestion failed"
        )
    
    emit(
        "faiss.concurrency_warning",
        message,
        source="faiss",
        severity="critical",
        runtime_context={"concurrency": concurrency},
    )


def build_faiss_index() -> None:
    """Load all ContentItem embeddings from DB and build the FAISS index.

    Called once at startup (via apps.py ready()) and every 15 minutes by Celery Beat.
    Thread-safe — replaces the global index atomically.
    """
    global _faiss_index, _faiss_id_map, _faiss_content_type_map

    if not HAS_FAISS:
        msg = "faiss not installed — FAISS-GPU path disabled"
        logger.warning(msg)
        emit(
            "faiss.dependency_missing",
            msg,
            source="faiss",
            severity="warning",
        )
        return

    from apps.content.models import ContentItem
    from apps.pipeline.services.pipeline import _coerce_embedding_vector

    performance_mode = get_requested_performance_mode()

    # Group A.6 — keep cross-source duplicates out of the FAISS index.
    # Otherwise a single piece of content would surface twice in the
    # candidate list (once as the canonical row, once as the duplicate
    # that still has an old embedding from before it was deduped).
    qs = ContentItem.objects.filter(
        embedding__isnull=False,
        duplicate_of__isnull=True,
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
        msg = "FAISS index build: no embeddings found in DB"
        logger.warning(msg)
        emit(
            "faiss.build_empty",
            msg,
            source="faiss",
            severity="warning",
        )
        return

    matrix = np.vstack(vectors).astype(np.float32)
    dim = matrix.shape[1]

    index_cpu = faiss.IndexFlatIP(dim)
    index_cpu.add(matrix)

    if faiss.get_num_gpus() > 0 and performance_mode == PERFORMANCE_MODE_HIGH:
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

    msg = f"FAISS index built: {len(pks)} vectors, dim={dim}, device={device}"
    logger.info(msg)
    emit(
        "faiss.index_ready",
        msg,
        source="faiss",
        severity="success",
        runtime_context={"vectors": len(pks), "dim": dim, "device": device},
    )


def _filter_faiss_row(
    row_scores: np.ndarray,
    row_indices: np.ndarray,
    *,
    id_map: list[int],
    ct_map: list[str],
    host_pk_set: set[int] | None,
    k: int,
) -> list[tuple[int, str, float]]:
    """Map a single FAISS row to (pk, ct, score) hits, capped at k. FR-238."""
    hits: list[tuple[int, str, float]] = []
    for idx, score in zip(row_indices, row_scores):
        if idx < 0:
            continue
        pk = id_map[idx]
        ct = ct_map[idx]
        if host_pk_set is not None and pk not in host_pk_set:
            continue
        hits.append((pk, ct, float(score)))
        if len(hits) >= k:
            break
    return hits


def faiss_search(
    query_vectors: np.ndarray,
    k: int,
    host_pk_set: set[int] | None = None,
) -> list[list[tuple[int, str, float]]]:
    """Search the FAISS index. Returns (pk, content_type, score) per hit.

    FR-238 — score is now preserved (was discarded until 2026-05-07).
    Source: Wang, Lin & Metzler 2011 SIGIR §3 cascade-stage score
    propagation. ``score`` is FAISS ``IndexFlatIP`` inner product, ==
    cosine for L2-unit vectors (FR-237 enforces).
    """
    with _index_lock:
        index = _faiss_index
        id_map = list(_faiss_id_map)
        ct_map = list(_faiss_content_type_map)

    if index is None:
        return [[] for _ in range(len(query_vectors))]

    query = np.ascontiguousarray(query_vectors, dtype=np.float32)
    search_k = min(k * 2, len(id_map))  # over-fetch to allow filtering
    scores, indices = index.search(query, search_k)

    return [
        _filter_faiss_row(
            row_scores, row_indices,
            id_map=id_map, ct_map=ct_map,
            host_pk_set=host_pk_set, k=k,
        )
        for row_scores, row_indices in zip(scores, indices)
    ]


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
    except Exception:  # noqa: BLE001  # Best-effort fallback in service/helper code; downstream code logs / returns a safe default — must not raise to the pipeline orchestrator.
        device = "unknown"
        on_gpu = False

    vram_mb = (
        round(n * get_current_embedding_dimension() * 4 / (1024**2)) if on_gpu else 0
    )

    return {
        "active": True,
        "vectors": n,
        "device": device,
        "vram_mb": vram_mb,
    }
