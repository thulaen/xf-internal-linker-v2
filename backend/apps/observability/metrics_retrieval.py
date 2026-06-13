"""Retrieval-stage instrumentation helpers.

Wires timing and candidate-count metrics for stage-1 candidate retrieval
(semantic FAISS, BM25, hybrid RRF). Every observation goes into the
existing reserved metrics from metric_specs.py.

Call sites
----------
- apps.pipeline.services.candidate_retrievers.run_retrievers
  (times the full multi-retriever run, records per-retriever latency
  and whether any retriever returned zero candidates for a destination)
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from collections.abc import Iterator

from apps.observability.instruments import safe_inc, safe_observe
from apps.observability.api import get_metric


@contextmanager
def retriever_latency_timer(retriever_name: str) -> Iterator[None]:
    """Time a single retriever's retrieve() call.

    Emits xf_index_search_seconds so the vmalert FaissSearchLatencyHigh
    alert fires correctly.

    Usage::

        with retriever_latency_timer("semantic"):
            partial = retriever.retrieve(context)
    """
    started = time.perf_counter()
    try:
        yield
    finally:
        safe_observe(get_metric("xf_index_search_seconds"), time.perf_counter() - started)


def observe_retrieval_empty(retriever_name: str, destination_count: int) -> None:
    """Increment empty-retrieval counter when a retriever returns no candidates.

    Emits xf_scoring_rejected_total{reason="no_retrieval_candidates_<retriever>}
    so operators can correlate empty BM25 vs empty semantic retrievals.
    """
    if destination_count == 0:
        safe_inc(
            get_metric("xf_scoring_rejected_total"),
            reason=f"no_retrieval_candidates_{retriever_name}",
        )
