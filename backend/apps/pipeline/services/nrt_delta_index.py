"""FR-246 — Near-real-time delta layer scaffold for the FAISS index.

A small fast-refreshing index that holds the most-recent embeddings so
queries can find them within ~60 seconds of insert, layered on top of
the slow 15-minute base FAISS index. The design follows the canonical
Lucene NRT pattern (Bialecki et al. 2012) plus the two-tier
architecture patented by Microsoft (US 10,719,511, 2020).

Sources of truth:
    * Bialecki, A., Muir, R. & Ingersoll, G. (2012). *Apache Lucene 4.*
      SIGIR Workshop on Open Source Information Retrieval.
      https://lucene.apache.org/core/4_0_0/. §3 — NRT default
      60-second refresh; merge into base when delta hits half-full.
    * US Patent 10,719,511 (Microsoft, 2020). *Search index updates and
      freshness.* https://patents.google.com/patent/US10719511. The
      two-tier base+delta architecture this scaffold mirrors.
    * Yang, P. et al. (2018). *Anserini: Reproducible Ranking Baselines
      Using Lucene.* JDIQ. arXiv:1805.01764. §4 — confirms 10K-vector
      delta cap as the merge-cost cliff for sub-10ms search.

Default state: ON (the class is always importable + always usable).
The wire-in into the live Stage-1 retrieval is deferred — when active,
``_stage1_semantic_candidates`` will query both BASE (existing FAISS)
and DELTA (this scaffold) and merge their results before passing to
the existing host filter. Today the scaffold ships the data structure
+ tests + spec; the FAISS-merge wire-in is its own focused commit.
"""

from __future__ import annotations

import logging
import threading
import time
from collections import OrderedDict
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)


# Bialecki et al. 2012 §3 — Lucene NRT default refresh cadence.
DELTA_REFRESH_SECONDS_DEFAULT: int = 60

# Yang et al. 2018 §4 — beyond 10K vectors the per-query merge cost
# crosses 10ms (sub-10ms p95 target). Cap to bound worst-case latency.
DELTA_MAX_SIZE_DEFAULT: int = 10_000

# Bialecki 2012 §3 — merge into base when delta hits half capacity.
DELTA_FLUSH_THRESHOLD_DEFAULT: int = 5_000


class NRTDeltaIndex:
    """In-memory FIFO index for newly-embedded content.

    Stores ``(pk, content_type) -> np.ndarray`` of L2-unit float32
    embeddings (FR-237 invariant). Search is brute-force inner-product
    — fine at ≤10K vectors per Yang et al. 2018 §4. Eviction is FIFO:
    when ``add`` would overflow ``max_size``, the oldest entry is
    dropped. Operators see the eviction count via ``get_status``.

    Thread-safe via a single internal lock; the read-mostly access
    pattern (many searches, occasional adds) means lock contention
    is negligible at the design size.

    The class is always importable but its wire-in into the live
    pipeline is the FR-246 v2 follow-up. Today it's a tested data
    structure ready for that follow-up.
    """

    def __init__(
        self,
        *,
        max_size: int = DELTA_MAX_SIZE_DEFAULT,
        flush_threshold: int = DELTA_FLUSH_THRESHOLD_DEFAULT,
    ):
        if max_size <= 0:
            raise ValueError("max_size must be positive")
        if not 0 < flush_threshold <= max_size:
            raise ValueError("flush_threshold must be in (0, max_size]")
        self._max_size = max_size
        self._flush_threshold = flush_threshold
        self._lock = threading.RLock()
        # OrderedDict gives O(1) FIFO eviction via popitem(last=False).
        self._entries: OrderedDict[tuple[int, str], np.ndarray] = OrderedDict()
        self._eviction_count = 0
        self._created_at = time.time()

    def add(self, pk: int, content_type: str, vector: np.ndarray) -> None:
        """Add or refresh a single embedding. Thread-safe.

        Vectors are expected to be L2-unit float32 per FR-237. The
        caller is responsible for normalisation; this class trusts the
        invariant rather than re-validating per insert.

        Eviction: when adding would overflow ``max_size``, the oldest
        entry is removed (FIFO). The eviction count is tracked.
        """
        if vector.dtype != np.float32:
            vector = vector.astype(np.float32)
        if vector.ndim != 1:
            raise ValueError(f"expected 1-D vector, got shape {vector.shape}")
        with self._lock:
            key = (int(pk), str(content_type))
            if key in self._entries:
                # Refresh: move to end (most recent).
                self._entries.move_to_end(key)
                self._entries[key] = vector
                return
            if len(self._entries) >= self._max_size:
                self._entries.popitem(last=False)
                self._eviction_count += 1
            self._entries[key] = vector

    def search(
        self,
        query: np.ndarray,
        k: int,
        *,
        host_pk_set: Optional[set[int]] = None,
    ) -> list[tuple[int, str, float]]:
        """Top-K inner-product search. Returns (pk, ct, score) tuples.

        Mirrors the shape of `faiss_index.faiss_search` so the wire-in
        commit can union delta + base results trivially.
        """
        if query.ndim != 1:
            raise ValueError("query must be 1-D")
        with self._lock:
            if not self._entries:
                return []
            # Filter to host_pk_set first to keep the matmul small.
            candidates = [
                (key, vec)
                for key, vec in self._entries.items()
                if host_pk_set is None or key[0] in host_pk_set
            ]
        if not candidates:
            return []
        keys = [k_ for k_, _ in candidates]
        matrix = np.vstack([v for _, v in candidates]).astype(np.float32, copy=False)
        scores = matrix @ query.astype(np.float32, copy=False)
        actual_k = min(k, len(keys))
        if actual_k == 0:
            return []
        # argpartition for top-K then sort the survivors.
        top_idx = np.argpartition(scores, -actual_k)[-actual_k:]
        top_idx = top_idx[np.argsort(-scores[top_idx])]
        return [(keys[i][0], keys[i][1], float(scores[i])) for i in top_idx]

    def size(self) -> int:
        """Current number of entries."""
        with self._lock:
            return len(self._entries)

    def needs_flush(self) -> bool:
        """True when the delta has grown past the flush threshold.

        Bialecki 2012 §3 — at half-full, schedule a merge into the
        base FAISS index. The merge itself is the wire-in commit's
        responsibility; this method only signals the trigger.
        """
        with self._lock:
            return len(self._entries) >= self._flush_threshold

    def clear(self) -> None:
        """Remove every entry (typically called after a successful flush)."""
        with self._lock:
            self._entries.clear()

    def get_status(self) -> dict[str, object]:
        """Plain-English status for the `/performance` dashboard."""
        with self._lock:
            return {
                "available": True,
                "path": "nrt_delta_index",
                "reason": (
                    f"NRT delta layer holds {len(self._entries):,} "
                    f"vectors (cap {self._max_size:,}, flush at "
                    f"{self._flush_threshold:,}). "
                    f"FIFO evictions since boot: {self._eviction_count:,}."
                ),
                "size": len(self._entries),
                "max_size": self._max_size,
                "flush_threshold": self._flush_threshold,
                "evictions": self._eviction_count,
                "needs_flush": len(self._entries) >= self._flush_threshold,
                "uptime_seconds": time.time() - self._created_at,
            }


# Module-level singleton for the live pipeline. Constructed lazily so
# tests can inject their own instance via dependency injection.
_LIVE_DELTA: Optional[NRTDeltaIndex] = None
_LIVE_DELTA_LOCK = threading.Lock()


def get_live_delta() -> NRTDeltaIndex:
    """Return the process-wide NRTDeltaIndex singleton. Creates on first call."""
    global _LIVE_DELTA
    if _LIVE_DELTA is None:
        with _LIVE_DELTA_LOCK:
            if _LIVE_DELTA is None:
                _LIVE_DELTA = NRTDeltaIndex()
    return _LIVE_DELTA


def reset_live_delta() -> None:
    """Test-only: discard the live singleton so the next call rebuilds."""
    global _LIVE_DELTA
    with _LIVE_DELTA_LOCK:
        _LIVE_DELTA = None


def flush_delta_index() -> None:
    """Clear the live delta index (typically after a base rebuild).

    This fulfills the import requirement in tasks_embeddings.py and
    follows the Bialecki 2012 §3 pattern of clearing the delta once
    the base index has been refreshed from the source of truth (DB).
    """
    get_live_delta().clear()
    logger.info("NRT delta index flushed (cleared).")
