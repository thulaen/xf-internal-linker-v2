"""Embedding pipeline instrumentation helpers.

Wires xf_embedding_* metrics into the real embedding code path.

Call sites
----------
- apps.pipeline.services.embeddings.generate_content_item_embeddings
- apps.pipeline.services.embeddings.generate_sentence_embeddings
- apps.pipeline.services.embeddings._run_embedding_loop (via the helpers below)

Also exposes observe_queue_depth so the Celery task wrapper can snapshot
the queue depth at the start of each embedding job.
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from collections.abc import Iterator

from apps.observability.instruments import safe_inc, safe_observe, safe_set
from apps.observability.api import get_metric


@contextmanager
def embedding_job_timer(model_name: str, item_count: int = 1) -> Iterator[None]:
    """Time one embedding batch and increment the jobs counter.

    Emits:
    - xf_embedding_jobs_total{model=<model_name>} += item_count
    - xf_embedding_latency_seconds{model=<model_name>}  (elapsed seconds)

    Usage::

        with embedding_job_timer("text-embedding-3-small", len(texts)):
            vectors = provider.encode(texts)
    """
    started = time.perf_counter()
    try:
        yield
    finally:
        elapsed = time.perf_counter() - started
        safe_inc(get_metric("xf_embedding_jobs_total"), float(item_count), model=model_name)
        safe_observe(get_metric("xf_embedding_latency_seconds"), elapsed, model=model_name)


def observe_embedding_failure(model_name: str, reason: str) -> None:
    """Increment the embedding model-error counter.

    Emits xf_embedding_model_errors_total{model=<model_name>, reason=<reason>}.
    """
    safe_inc(
        get_metric("xf_embedding_model_errors_total"),
        model=model_name,
        reason=reason,
    )


def observe_embedding_retry(model_name: str) -> None:
    """Increment the retry counter for a model call that had to be retried."""
    safe_inc(get_metric("xf_embedding_retry_count_total"), model=model_name)


def observe_queue_depth(queue_name: str, depth: int) -> None:
    """Set the xf_queue_depth gauge for a named queue.

    The EmbeddingQueueAgeHigh vmalert alert fires when this exceeds 500
    for queue="pipeline".
    """
    safe_set(get_metric("xf_queue_depth"), float(depth), queue=queue_name)
