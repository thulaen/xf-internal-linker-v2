from __future__ import annotations
import logging
import traceback
from typing import Any

from celery import shared_task
from django.db import connection

from apps.core.helpers import HelperConstraint

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# FR-30 — FAISS index refresh
# ---------------------------------------------------------------------------

@shared_task(name="pipeline.refresh_faiss_index", time_limit=3600, soft_time_limit=3540)
@HelperConstraint(
    cpu_intensive=False,
    gpu_required=True,
    storage_writes_to="postgres_main",
    ram_peak_mb=2048,
    expected_seconds_p50=300,
)
def refresh_faiss_index():
    """FR-30 — Rebuild the FAISS index to pick up newly generated embeddings."""
    if not connection.in_atomic_block:
        connection.close()

    from apps.audit.error_ingest import ingest_error
    from apps.audit.models import ErrorLog
    from apps.pipeline.services.faiss_index import build_faiss_index

    try:
        build_faiss_index()
    except Exception as exc:
        ingest_error(
            job_type="faiss_init",
            step="refresh_faiss_index",
            error_message=str(exc) or exc.__class__.__name__,
            raw_exception=traceback.format_exc(),
            why="Periodic FAISS index rebuild failed.",
            severity=ErrorLog.SEVERITY_HIGH,
        )
        raise

# ---------------------------------------------------------------------------
# FR-245 — Platt calibration fit task.
# ---------------------------------------------------------------------------

@shared_task(name="pipeline.calibration_fit", time_limit=600, soft_time_limit=540)
@HelperConstraint(
    cpu_intensive=True,
    gpu_required=False,
    storage_writes_to="postgres_main",
    ram_peak_mb=256,
    expected_seconds_p50=30,
)
def calibration_fit():
    """FR-245 — fit a Platt sigmoid against approved/rejected feedback."""
    if not connection.in_atomic_block:
        connection.close()

    from apps.pipeline.services.score_calibration import train_calibration_sigmoid
    try:
        train_calibration_sigmoid()
    except Exception as exc:
        from apps.audit.error_ingest import ingest_error
        ingest_error(
            job_type="calibration",
            step="calibration_fit",
            error_message=str(exc),
            raw_exception=traceback.format_exc(),
            why="Platt calibration fit failed.",
        )

@shared_task(name="pipeline.nrt_delta_flush", time_limit=300)
@HelperConstraint(
    cpu_intensive=False,
    gpu_required=False,
    storage_writes_to="postgres_main",
    ram_peak_mb=2048,
    expected_seconds_p50=60,
)
def nrt_delta_flush():
    """Flush the NRT delta index into the primary FAISS index."""
    if not connection.in_atomic_block:
        connection.close()
    from apps.pipeline.services.nrt_delta_index import flush_delta_index
    flush_delta_index()

@shared_task(bind=True, name="pipeline.backfill_long_tail_embeddings", time_limit=3600)
@HelperConstraint(
    cpu_intensive=False,
    gpu_required=False,
    storage_writes_to="postgres_main",
    ram_peak_mb=4096,
    expected_seconds_p50=180,
)
def backfill_long_tail_embeddings(self, *, body_to_distilled_ratio: float = 0.3, max_items: int = 5000) -> dict:
    """Identify ContentItems with missing/stale embeddings and generate them."""
    if not connection.in_atomic_block:
        connection.close()
    from apps.pipeline.services.embedding_backfill import run_backfill
    return run_backfill(body_to_distilled_ratio=body_to_distilled_ratio, max_items=max_items)

@shared_task(bind=True, name="pipeline.reembed_null_embeddings", time_limit=3600)
@HelperConstraint(
    cpu_intensive=False,
    gpu_required=False,
    storage_writes_to="postgres_main",
    ram_peak_mb=4096,
    expected_seconds_p50=120,
)
def reembed_null_embeddings(self, *, max_items: int = 1000) -> dict:
    """Find ContentItems with NULL embeddings and generate them."""
    if not connection.in_atomic_block:
        connection.close()
    from apps.pipeline.services.embedding_repair import repair_null_embeddings
    return repair_null_embeddings(max_items=max_items)

@shared_task(bind=True, name="pipeline.refresh_passage_embeddings", time_limit=3600)
@HelperConstraint(
    cpu_intensive=False,
    gpu_required=False,
    storage_writes_to="postgres_main",
    ram_peak_mb=4096,
    expected_seconds_p50=120,
)
def refresh_passage_embeddings(self, *, max_items: int = 1000) -> dict:
    """Refresh passage-level embeddings for ContentItems."""
    if not connection.in_atomic_block:
        connection.close()
    from apps.pipeline.services.passage_refresh import refresh_passages
    return refresh_passages(max_items=max_items)

@shared_task(bind=True, name="pipeline.train_opq_codebook", time_limit=3600)
@HelperConstraint(
    cpu_intensive=True,
    gpu_required=False,
    storage_writes_to="postgres_main",
    ram_peak_mb=512,
    expected_seconds_p50=180,
)
def train_opq_codebook(self, *, sample_size: int = 100_000) -> dict:
    """Train the Optimized Product Quantization (OPQ) codebook for FAISS."""
    if not connection.in_atomic_block:
        connection.close()
    from apps.pipeline.services.opq_trainer import train_codebook
    return train_codebook(sample_size=sample_size)
