"""Celery tasks for pipeline, sync, embeddings, verification, and link health."""

from __future__ import annotations
from celery.exceptions import SoftTimeLimitExceeded

import logging
import time
import uuid
from typing import Any
from urllib.parse import urljoin, urlparse

import requests
from asgiref.sync import async_to_sync
from celery import shared_task
from channels.layers import get_channel_layer

from apps.pipeline.decorators import with_weight_lock
from apps.core.pause_contract import JobPaused
from apps.core.helpers import HelperConstraint
from apps.core.helpers.resource_aware_retry import resource_aware_retry
from requests import RequestException
from django.db import DatabaseError, IntegrityError
from urllib.error import URLError

logger = logging.getLogger(__name__)

_MAX_BROKEN_LINK_SCAN_URLS = 10_000  # maxsize for broken-link scan
_BROKEN_LINK_SCAN_TIMEOUT_SECONDS = 10

# Batch sizes for bulk DB writes
_SENTENCE_BULK_CREATE_BATCH = 500  # maxsize for sentence bulk_create
_DISTILLED_TEXT_BULK_UPDATE_BATCH = 200  # maxsize for distilled-text bulk_update


# Data-retention cutoffs
_RETENTION_12_MONTHS = 365  # days
_RETENTION_6_MONTHS = 180  # days
_RETENTION_3_MONTHS = 90  # days

# AppSetting keys that surface the most recent prune cardinality to
# the dashboard ("Retention queue" panel). Each value is the count
# of rows that the *next* prune run would delete; the dashboard reads
# them via ``apps.core.runtime_flags`` / a lightweight diagnostics
# endpoint to render the operator-facing "X rows pending prune" line.
RETENTION_PREVIEW_KEY_IMPRESSIONS = "retention.queue.suggestion_impressions"
RETENTION_PREVIEW_KEY_PRESENTATIONS = "retention.queue.suggestion_presentations"
RETENTION_PREVIEW_KEY_NON_APPROVED = "retention.queue.non_approved_suggestions"
RETENTION_PREVIEW_KEY_LAST_RUN_AT = "retention.queue.last_run_at"

# Percentage multiplier for lift calculations
_PCT_MULTIPLIER = 100  # maxsize for percentage conversion

# GSC spike alert cooldown
_GSC_SPIKE_COOLDOWN = 86400  # seconds

# Preview truncation lengths (for log/alert messages)
_TITLE_PREVIEW_LEN = 60  # maxsize for title preview
_RUN_ID_PREVIEW_LEN = 16  # maxsize for run-id preview

# Progress-reporting interval for scoring loop
_SCORING_PROGRESS_INTERVAL = 100  # maxsize for scoring loop progress reporting

# Branded feature-name VERSION label used in user-facing messages
_PAGERANK_VERSION_LABEL = "Weighted PageRank"


def _publish_progress(
    job_id: str, state: str, progress: float, message: str, **extra: Any
) -> None:
    """Publish a job progress event to the WebSocket channel group."""
    channel_layer = get_channel_layer()
    if channel_layer is None:
        logger.warning("Channel layer not available; progress event not sent.")
        return

    # Ensure progress fields are initialized if not provided
    event = {
        "type": "job.progress",
        "job_id": job_id,
        "state": state,
        "progress": round(progress, 3),
        "message": message,
        "spacy_progress": extra.get("spacy_progress", 0.0),
        "embedding_progress": extra.get("embedding_progress", 0.0),
        **extra,
    }
    try:
        async_to_sync(channel_layer.group_send)(f"job_{job_id}", event)
    except (AttributeError, RuntimeError, ConnectionError):
        logger.exception("Failed to publish progress event for job %s", job_id)


def _emit_job_alert(  # noqa: forbidden-pattern too-many-args  # justification: shared by every task's success/failure path; bundling kwargs would obscure call sites
    event_type: str,
    severity: str,
    title: str,
    message: str,
    *,
    job_id: str,
    job_type: str,
    related_route: str = "/jobs",
    error_log_id: int | None = None,
) -> None:
    """Emit an operator alert for a job event. Never raises — alert failure must not kill the task."""
    try:
        from apps.notifications.services import emit_operator_alert
        from apps.notifications.models import OperatorAlert

        emit_operator_alert(
            event_type=event_type,
            severity=severity,
            title=title,
            message=message,
            source_area=OperatorAlert.AREA_JOBS,
            dedupe_key=f"{event_type}:{job_id}",
            related_object_type="SyncJob",
            related_object_id=job_id,
            related_route=related_route,
            payload={"job_id": job_id, "job_type": job_type},
            error_log_id=error_log_id,
        )
    except (ImportError, AttributeError, DatabaseError):
        logger.warning(
            "_emit_job_alert: failed to emit alert for job %s", job_id, exc_info=True
        )


def _broken_link_allowed_domains() -> list[str]:
    from django.conf import settings

    allowed_domains: list[str] = []
    for raw_url in [
        getattr(settings, "XENFORO_BASE_URL", ""),
        getattr(settings, "WORDPRESS_BASE_URL", ""),
    ]:
        host = urlparse(raw_url).netloc.strip().lower()
        if host and host not in allowed_domains:
            allowed_domains.append(host)
    return allowed_domains


def _save_checkpoint(
    job_id: str, stage: str, last_item_id: int, items_processed: int
) -> None:
    """Persist checkpoint to SyncJob for crash-resilient resume (FR-97).

    Uses a single UPDATE query -- no SELECT, no .save().
    Wrapped so a checkpoint failure never crashes the import.
    """
    try:
        from apps.sync.models import SyncJob

        SyncJob.objects.filter(job_id=job_id).update(
            checkpoint_stage=stage,
            checkpoint_last_item_id=last_item_id,
            checkpoint_items_processed=items_processed,
        )
    except Exception:
        logger.debug(
            "Checkpoint write failed for job %s (stage=%s)",
            job_id,
            stage,
            exc_info=True,
        )


def dispatch_broken_link_scan(job_id: str | None = None) -> dict[str, Any]:
    job_id = job_id or str(uuid.uuid4())
    scan_broken_links.delay(job_id=job_id)
    return {
        "job_id": job_id,
        "message": "Broken link scan started.",
        "runtime_owner": "celery",
    }


def dispatch_import_content(
    *,
    scope_ids: list[int] | None = None,
    mode: str = "full",
    source: str = "api",
    file_path: str | None = None,
    job_id: str | None = None,
    force_reembed: bool = False,
) -> dict[str, Any]:
    job_id = job_id or str(uuid.uuid4())

    import_content.apply_async(
        kwargs={
            "scope_ids": scope_ids,
            "mode": mode,
            "source": source,
            "file_path": file_path,
            "job_id": job_id,
            "force_reembed": force_reembed,
        },
        task_id=job_id,
    )
    return {
        "job_id": job_id,
        "runtime_owner": "celery",
        "message": f"{source} import queued.",
    }


def dispatch_pipeline_run(
    *,
    run_id: str,
    host_scope: dict[str, Any],
    destination_scope: dict[str, Any],
    rerun_mode: str = "skip_pending",
) -> dict[str, Any]:
    """Dispatch pipeline to Celery. Python owns all ranking permanently."""
    run_pipeline.delay(
        run_id=run_id,
        host_scope=host_scope,
        destination_scope=destination_scope,
        rerun_mode=rerun_mode,
    )
    return {
        "job_id": run_id,
        "runtime_owner": "celery",
        "message": "Pipeline queued.",
    }


@shared_task(
    bind=True,
    name="pipeline.run_pipeline",
    time_limit=7200,
    soft_time_limit=7140,
    acks_late=True,
)
@HelperConstraint(
    cpu_intensive=True,             # Stage 1-3 ranker walks
    gpu_required=False,             # GPU embed work happens inside generate_embeddings
    storage_writes_to="postgres_main",
    ram_peak_mb=2048,
    expected_seconds_p50=1800,
)
def run_pipeline(
    self,
    run_id: str,
    host_scope: dict,
    destination_scope: dict,
    rerun_mode: str = "skip_pending",
) -> dict:
    """Execute the full 3-stage ML suggestion pipeline."""
    run = _claim_pipeline_run(self, run_id)
    if run is None:
        return {"error": "PipelineRun not found"}
    started_at = time.monotonic()
    try:
        result = _execute_pipeline_run(
            run_id, host_scope, destination_scope, rerun_mode,
        )
        return _finalize_pipeline_success(run, run_id, result, started_at)
    except (DatabaseError, TimeoutError, MemoryError, ValueError) as exc:
        _finalize_pipeline_failure(run, run_id, exc, started_at)
        raise


def _claim_pipeline_run(task_self, run_id: str):
    """Mark the PipelineRun row 'running' + bind celery_task_id; return row or None."""
    from apps.suggestions.models import PipelineRun

    try:
        run = PipelineRun.objects.get(run_id=run_id)
    except PipelineRun.DoesNotExist:
        logger.error("PipelineRun %s not found", run_id)
        return None
    run.run_state = "running"
    run.celery_task_id = task_self.request.id or ""
    run.save(update_fields=["run_state", "celery_task_id", "updated_at"])
    return run


def _execute_pipeline_run(
    run_id: str, host_scope: dict, destination_scope: dict, rerun_mode: str,
):
    """Coerce scope dicts into id-sets and call the inner pipeline orchestrator."""
    from apps.pipeline.services.pipeline import run_pipeline as _run

    def _progress(pct: float, msg: str) -> None:
        _publish_progress(run_id, "running", pct, msg)

    def _ids(scope: dict | None, key: str) -> set | None:
        if scope and key in scope:
            return set(scope[key])
        return None

    return _run(
        run_id=run_id,
        rerun_mode=rerun_mode,
        destination_scope_ids=_ids(destination_scope, "scope_ids"),
        destination_content_item_ids=_ids(destination_scope, "content_item_ids"),
        host_scope_ids=_ids(host_scope, "scope_ids"),
        progress_fn=_progress,
    )


def _finalize_pipeline_success(run, run_id: str, result, started_at: float) -> dict:
    """Mark PipelineRun completed, publish completion event, schedule value-model task."""
    duration = time.monotonic() - started_at
    run.run_state = "completed"
    run.suggestions_created = result.suggestions_created
    run.destinations_processed = result.items_in_scope
    run.destinations_skipped = result.destinations_skipped
    run.duration_seconds = duration
    run.save(update_fields=[
        "run_state", "suggestions_created", "destinations_processed",
        "destinations_skipped", "duration_seconds", "updated_at",
    ])
    _publish_progress(
        run_id, "completed", 1.0, "Pipeline complete.",
        suggestions_created=result.suggestions_created,
        destinations_processed=result.items_in_scope,
    )
    # FR-025: compute value model scores (including co-occurrence) post-pipeline.
    try:
        from apps.cooccurrence.tasks import apply_value_model_scores
        apply_value_model_scores.delay(run_id)
    except (ImportError, AttributeError):
        logger.warning(
            "apply_value_model_scores could not be queued for run %s", run_id,
        )
    _emit_job_alert(
        "job.completed", "success", "Pipeline job completed",
        f"Pipeline finished. {result.suggestions_created} suggestions created "
        f"from {result.items_in_scope} destinations.",
        job_id=run_id, job_type="pipeline",
    )
    return {
        "run_id": run_id, "state": "completed",
        "suggestions_created": result.suggestions_created,
        "items_in_scope": result.items_in_scope,
        "duration_seconds": round(duration, 2),
    }


def _finalize_pipeline_failure(run, run_id: str, exc: Exception, started_at: float) -> None:
    """Mark PipelineRun failed, publish failure event, emit error alert."""
    logger.exception("Pipeline run %s failed", run_id)
    run.run_state = "failed"
    run.error_message = str(exc)
    run.duration_seconds = time.monotonic() - started_at
    run.save(update_fields=[
        "run_state", "error_message", "duration_seconds", "updated_at",
    ])
    _publish_progress(
        run_id, "failed", 0.0, f"Pipeline failed: {exc}", error=str(exc),
    )
    _emit_job_alert(
        "job.failed", "error", "Pipeline job failed",
        f"The pipeline run stopped with an error: {exc}",
        job_id=run_id, job_type="pipeline",
    )


@shared_task(
    bind=True,
    name="pipeline.generate_embeddings",
    time_limit=7200,
    soft_time_limit=7140,
    acks_late=True,
)
@HelperConstraint(
    gpu_required=True,              # BGE-M3 encode runs on GPU
    storage_writes_to="postgres_main",
    ram_peak_mb=4000,
    expected_seconds_p50=1200,
)
def generate_embeddings(
    self,
    content_item_ids: list[int] | None = None,
    job_id: str | None = None,
    force_reembed: bool = False,
) -> dict:
    """Generate and store embeddings for ContentItems and Sentences."""
    from apps.sync.models import SyncJob
    from apps.pipeline.services.embeddings import generate_all_embeddings

    job_id = job_id or str(uuid.uuid4())
    count_label = len(content_item_ids) if content_item_ids is not None else "all"
    job = SyncJob.objects.filter(job_id=job_id).first()
    _publish_progress(
        job_id, "running", 0.8,
        f"Generating embeddings for {count_label} items...",
        ingest_progress=1.0, ml_progress=0.7, embedding_progress=0.0,
    )
    try:
        stats = generate_all_embeddings(
            content_item_ids, job_id=job_id, force_reembed=force_reembed,
        )
        _refresh_faiss_after_embed_safe()
        return _finalize_embed_success(job, job_id, stats)
    except JobPaused as exc:
        return _handle_embed_paused(job, job_id, exc)
    except (MemoryError, TimeoutError, RuntimeError) as exc:
        _handle_embed_failed(job, job_id, exc)
        raise


def _refresh_faiss_after_embed_safe() -> None:
    """Rebuild FAISS so new embeddings are visible without waiting for the 15-min periodic refresh."""
    try:
        from apps.pipeline.services.faiss_index import build_faiss_index
        build_faiss_index()
    except (ImportError, MemoryError, FileNotFoundError):
        logger.warning("FAISS index rebuild after embeddings failed", exc_info=True)


def _finalize_embed_success(job, job_id: str, stats: dict) -> dict:
    """Mark SyncJob completed, publish completion event, emit success alert."""
    from django.utils import timezone

    if job:
        job.status = "completed"
        job.completed_at = timezone.now()
        job.progress = 1.0
        job.save(update_fields=["status", "completed_at", "progress", "updated_at"])
    _publish_progress(
        job_id, "completed", 1.0,
        f"ML Enrichment complete. {stats['content_items_embedded']} items embedded.",
        ingest_progress=1.0, ml_progress=1.0, embedding_progress=1.0,
        **stats,
    )
    _emit_job_alert(
        "job.completed", "success", "Embedding job completed",
        f"ML Enrichment complete. {stats['content_items_embedded']} items, "
        f"{stats['sentences_embedded']} sentences embedded.",
        job_id=job_id, job_type="embed",
    )
    return {"job_id": job_id, **stats}


def _handle_embed_paused(job, job_id: str, exc: Exception) -> dict:
    """Mark SyncJob paused + publish paused-progress event."""
    logger.info("Embedding job %s paused at safe boundary: %s", job_id, exc)
    if job:
        job.status = "paused"
        job.is_resumable = True
        job.message = f"Paused at embedding checkpoint: {exc}"
        job.save(update_fields=["status", "is_resumable", "message", "updated_at"])
    _publish_progress(
        job_id, "paused", job.progress if job else 0.0,
        "Embeddings paused. Resume will continue from the saved checkpoint.",
        ingest_progress=1.0, ml_progress=0.7,
    )
    return {"job_id": job_id, "status": "paused", "reason": str(exc)}


def _handle_embed_failed(job, job_id: str, exc: Exception) -> None:
    """Mark SyncJob failed + publish failure event + emit error alert; caller re-raises."""
    logger.exception("Embedding job %s failed", job_id)
    if job:
        job.status = "failed"
        job.error_message = str(exc)
        job.save(update_fields=["status", "error_message", "updated_at"])
    _publish_progress(
        job_id, "failed", 0.0, f"Embeddings failed: {exc}",
        error=str(exc), ingest_progress=1.0, ml_progress=0.0,
    )
    _emit_job_alert(
        "job.failed", "error", "Embedding job failed",
        f"The embedding run stopped with an error: {exc}",
        job_id=job_id, job_type="embed",
    )


@shared_task(
    bind=True,
    name="pipeline.recalculate_weighted_authority",
    time_limit=1800,
    soft_time_limit=1740,
)
@HelperConstraint(
    cpu_intensive=True,
    gpu_required=False,
    storage_writes_to="postgres_main",
    ram_peak_mb=512,
    expected_seconds_p50=120,
)
def recalculate_weighted_authority(self, job_id: str | None = None) -> dict:
    """Recompute Weighted PageRank from the stored graph and current settings."""
    job_id = job_id or str(uuid.uuid4())
    _publish_progress(
        job_id, "running", 0.0, f"Starting {_PAGERANK_VERSION_LABEL} recalculation..."
    )

    try:
        from apps.pipeline.services.weighted_pagerank import run_weighted_pagerank

        diagnostics = run_weighted_pagerank()
        _publish_progress(
            job_id,
            "completed",
            1.0,
            f"{_PAGERANK_VERSION_LABEL} recalculation complete.",
            **diagnostics,
        )
        return {"job_id": job_id, **diagnostics}
    except (DatabaseError, TimeoutError, MemoryError, ValueError) as exc:
        logger.exception("%s recalculation %s failed", _PAGERANK_VERSION_LABEL, job_id)
        _publish_progress(
            job_id,
            "failed",
            0.0,
            f"{_PAGERANK_VERSION_LABEL} recalculation failed: {exc}",
            error=str(exc),
        )
        raise


@shared_task(
    bind=True,
    name="pipeline.recalculate_link_freshness",
    time_limit=1800,
    soft_time_limit=1740,
)
@HelperConstraint(
    cpu_intensive=True,
    gpu_required=False,
    storage_writes_to="postgres_main",
    ram_peak_mb=512,
    expected_seconds_p50=180,
)
def recalculate_link_freshness(self, job_id: str | None = None) -> dict:
    """Recompute Link Freshness from the stored link-history rows and current settings."""
    job_id = job_id or str(uuid.uuid4())
    _publish_progress(
        job_id, "running", 0.0, "Starting Link Freshness recalculation..."
    )

    try:
        from apps.pipeline.services.link_freshness import run_link_freshness

        diagnostics = run_link_freshness()
        _publish_progress(
            job_id,
            "completed",
            1.0,
            "Link Freshness recalculation complete.",
            **diagnostics,
        )
        return {"job_id": job_id, **diagnostics}
    except (DatabaseError, TimeoutError, MemoryError, ValueError) as exc:
        logger.exception("Link Freshness recalculation %s failed", job_id)
        _publish_progress(
            job_id,
            "failed",
            0.0,
            f"Link Freshness recalculation failed: {exc}",
            error=str(exc),
        )
        raise


def dispatch_graph_rebuild(job_id: str | None = None) -> dict[str, Any]:
    job_id = job_id or str(uuid.uuid4())
    build_knowledge_graph.delay(job_id=job_id)
    return {
        "job_id": job_id,
        "message": "Knowledge graph rebuild started.",
        "runtime_owner": "celery",
    }
    return {
        "job_id": job_id,
        "message": "Knowledge graph rebuild started.",
        "runtime_owner": "celery",
    }


@shared_task(
    bind=True,
    name="pipeline.build_knowledge_graph",
    time_limit=1800,
    soft_time_limit=1740,
)
@HelperConstraint(
    cpu_intensive=True,
    gpu_required=False,
    storage_writes_to="postgres_main",
    ram_peak_mb=1024,
    expected_seconds_p50=240,
)
def build_knowledge_graph(self, job_id: str | None = None) -> dict:
    """Python fallback for building the bipartite knowledge graph."""
    job_id = job_id or str(uuid.uuid4())
    _publish_progress(job_id, "running", 0.0, "Starting knowledge graph build...")
    try:
        from apps.graph.services.graph_sync import refresh_existing_links

        count = refresh_existing_links()
        _publish_progress(
            job_id,
            "completed",
            1.0,
            f"Knowledge graph build complete; {count} items refreshed.",
        )
        return {"job_id": job_id, "items_refreshed": count}
    except (DatabaseError, TimeoutError, MemoryError, ValueError) as exc:
        logger.exception("Knowledge graph build %s failed", job_id)
        _publish_progress(
            job_id,
            "failed",
            0.0,
            f"Knowledge graph build failed: {exc}",
            error=str(exc),
        )
        raise


@shared_task(
    bind=True,
    name="pipeline.import_content",
    time_limit=7200,
    soft_time_limit=7140,
    acks_late=True,
)
@HelperConstraint(
    cpu_intensive=True,             # text_cleaner + NLP enrichment + spaCy
    gpu_required=False,
    storage_writes_to="postgres_main",
    ram_peak_mb=2048,
    expected_seconds_p50=2400,
)
@with_weight_lock("heavy")
def import_content(
    self,
    scope_ids: list[int] | None = None,
    mode: str = "full",
    source: str = "api",
    file_path: str | None = None,
    job_id: str | None = None,
    force_reembed: bool = False,
) -> dict:
    """Import/sync content from XenForo, WordPress, or JSONL export."""
    job_id = job_id or str(uuid.uuid4())
    job, state = _init_import_job_and_state(job_id, source, mode, force_reembed)
    _publish_import_start_or_resume(job, state, job_id, source, mode)
    try:
        _dispatch_import_source(state, job, source, scope_ids, file_path)
        return _finalize_import_success(job, state, job_id, source, mode)
    except JobPaused as exc:
        return _handle_import_paused(job, job_id, mode, exc)
    except SoftTimeLimitExceeded:
        _handle_import_soft_time_limit(job_id)
        raise
    except (DatabaseError, TimeoutError, MemoryError, ValueError) as exc:
        _handle_import_failed(job, state, job_id, exc)
        raise


def _init_import_job_and_state(job_id: str, source: str, mode: str, force_reembed: bool):
    """Get-or-create the SyncJob row and build a fresh ImportState."""
    from django.utils import timezone
    from apps.pipeline.tasks_import import ImportState
    from apps.sync.models import SyncJob

    job, created = SyncJob.objects.get_or_create(
        job_id=job_id,
        defaults={
            "source": source, "mode": mode, "status": "running",
            "started_at": timezone.now(),
        },
    )
    if not created:
        job.status = "running"
        job.started_at = timezone.now()
        job.source = source
        job.mode = mode
        job.save(update_fields=["status", "started_at", "source", "mode", "updated_at"])
    state = ImportState(
        job_id=job_id, source=source, mode=mode, force_reembed=force_reembed,
    )
    return job, state


def _publish_import_start_or_resume(job, state, job_id: str, source: str, mode: str) -> None:
    """FR-97: resume from checkpoint if the job was interrupted; otherwise publish start."""
    from apps.sync.models import SyncJob

    if job.is_resumable and job.checkpoint_stage and job.checkpoint_last_item_id:
        state.resume_last_item_id = job.checkpoint_last_item_id
        state.resume_stage = job.checkpoint_stage
        logger.info(
            "Resuming import job %s from checkpoint: stage=%s, last_item_id=%d, items_processed=%d",
            job_id, state.resume_stage, state.resume_last_item_id,
            job.checkpoint_items_processed,
        )
        _publish_progress(
            job_id, "running", 0.0,
            f"Resuming {mode} import from checkpoint (stage={state.resume_stage}, "
            f"after item {state.resume_last_item_id})...",
        )
        SyncJob.objects.filter(job_id=job_id).update(is_resumable=False)
    else:
        _publish_progress(
            job_id, "running", 0.0, f"Starting {mode} content import from {source}...",
        )


def _dispatch_import_source(
    state, job, source: str, scope_ids: list[int] | None, file_path: str | None,
) -> None:
    """Route to the source-specific importer."""
    from apps.pipeline.tasks_import import (
        import_jsonl_content, import_wordpress_content, import_xenforo_scopes,
    )
    if source == "api":
        import_xenforo_scopes(state, job, scope_ids, _publish_progress)
    elif source == "wp":
        import_wordpress_content(state, job, _publish_progress)
    elif source == "jsonl":
        if not file_path:
            raise ValueError("file_path is required for JSONL import.")
        import_jsonl_content(state, job, file_path)
    else:
        raise ValueError(f"Unsupported import source '{source}'.")


def _finalize_import_success(job, state, job_id: str, source: str, mode: str) -> dict:
    """Run post-import steps, mark the SyncJob completed, emit success alert."""
    from django.utils import timezone
    from apps.pipeline.tasks_import import run_post_import_steps, update_scope_counts
    from apps.sync.models import SyncJob

    update_scope_counts(state.touched_scope_ids)
    run_post_import_steps(state, job, job_id, _publish_progress)
    # FR-97: Clear checkpoint on successful completion.
    SyncJob.objects.filter(job_id=job_id).update(
        checkpoint_stage="", checkpoint_last_item_id=None,
        checkpoint_items_processed=0, is_resumable=False,
    )
    job.status = "completed"
    job.progress = 1.0
    job.completed_at = timezone.now()
    job.items_synced = state.items_synced
    job.items_updated = state.items_updated
    job.message = (
        f"Import complete. {state.items_synced} synced, {state.items_updated} updated."
    )
    job.save(update_fields=[
        "status", "progress", "completed_at",
        "items_synced", "items_updated", "message",
    ])
    _publish_progress(
        job_id, "completed", 1.0,
        f"Content import complete ({source}). {state.items_synced} items synced, "
        f"{state.items_updated} updated.",
    )
    _emit_job_alert(
        "job.completed", "success", "Import job completed",
        f"Content import finished. {state.items_synced} items synced, "
        f"{state.items_updated} updated.",
        job_id=job_id, job_type="import",
    )
    return {
        "mode": mode, "job_id": job_id,
        "items_synced": state.items_synced, "items_updated": state.items_updated,
    }


def _handle_import_paused(job, job_id: str, mode: str, exc: Exception) -> dict:
    """Mark the SyncJob paused + publish a paused-progress event."""
    from apps.sync.models import SyncJob

    logger.info("Import job %s paused at safe boundary: %s", job_id, exc)
    try:
        checkpoint_stage = (
            SyncJob.objects.filter(job_id=job_id)
            .values_list("checkpoint_stage", flat=True).first() or ""
        )
        SyncJob.objects.filter(job_id=job_id).update(
            status="paused",
            is_resumable=bool(checkpoint_stage),
            message=f"Paused at safe checkpoint: {exc}",
        )
    except Exception:
        logger.debug("Failed to mark job %s as paused", job_id, exc_info=True)
    _publish_progress(
        job_id, "paused", job.progress,
        "Import paused. Resume will continue from the saved checkpoint.",
        checkpoint_stage=getattr(job, "checkpoint_stage", ""),
    )
    return {
        "mode": mode, "job_id": job_id,
        "status": "paused", "reason": str(exc),
    }


def _handle_import_soft_time_limit(job_id: str) -> None:
    """Mark the SyncJob resumable + publish failure-progress; caller re-raises."""
    from apps.sync.models import SyncJob

    logger.warning("Import job %s hit soft time limit; marking as resumable.", job_id)
    try:
        SyncJob.objects.filter(job_id=job_id).update(
            is_resumable=True, status="failed",
            error_message="Soft time limit exceeded -- job is resumable from checkpoint.",
        )
    except Exception:
        logger.debug("Failed to mark job %s as resumable", job_id, exc_info=True)
    _publish_progress(
        job_id, "failed", 0.0, "Import interrupted (time limit). Job is resumable.",
        error="SoftTimeLimitExceeded",
    )


def _handle_import_failed(job, state, job_id: str, exc: Exception) -> None:
    """Mark the SyncJob failed (resumable iff state has progress); emit error alert."""
    from django.utils import timezone

    logger.exception("Import job %s failed", job_id)
    job.status = "failed"
    job.error_message = str(exc)
    job.completed_at = timezone.now()
    if bool(state.updated_pks):
        job.is_resumable = True
    job.save(update_fields=[
        "status", "error_message", "completed_at", "is_resumable",
    ])
    _publish_progress(
        job_id, "failed", 0.0, f"Import failed: {exc}", error=str(exc),
    )
    _emit_job_alert(
        "job.failed", "error", "Import job failed",
        f"The content import stopped with an error: {exc}",
        job_id=job_id, job_type="import",
    )


@shared_task(
    bind=True,
    name="pipeline.scan_broken_links",
    queue="default",
    time_limit=7200,
    soft_time_limit=7140,
    acks_late=True,
)
@HelperConstraint(
    cpu_intensive=False,            # network IO bound; CPU mostly idle
    gpu_required=False,
    storage_writes_to="postgres_main",
    ram_peak_mb=256,
    expected_seconds_p50=900,
)
def scan_broken_links(self, job_id: str | None = None) -> dict:
    """Scan live URLs referenced in content and persist broken-link findings."""
    from apps.pipeline.tasks_broken_links import collect_urls_to_scan

    job_id = job_id or str(uuid.uuid4())
    _publish_progress(job_id, "running", 0.0, "Collecting URLs for broken-link scan...")
    urls_to_scan, hit_scan_cap = collect_urls_to_scan()
    total_urls = len(urls_to_scan)
    if total_urls == 0:
        _publish_progress(job_id, "completed", 1.0, "No URLs found to scan.")
        return {"job_id": job_id, "scanned_urls": 0, "flagged_urls": 0, "fixed_urls": 0}
    _publish_progress(
        job_id, "running", 0.02,
        f"Scanning {total_urls} URL(s) for link health...",
        total_urls=total_urls, hit_scan_cap=hit_scan_cap,
    )
    flagged_urls, fixed_urls, probe_backend = _execute_broken_link_scan(
        job_id, urls_to_scan, total_urls, hit_scan_cap,
    )
    _publish_broken_link_scan_completion(
        job_id, total_urls, flagged_urls, fixed_urls, hit_scan_cap, probe_backend,
    )
    return {
        "job_id": job_id, "scanned_urls": total_urls,
        "flagged_urls": flagged_urls, "fixed_urls": fixed_urls,
        "hit_scan_cap": hit_scan_cap, "probe_backend": probe_backend,
    }


def _execute_broken_link_scan(
    job_id: str, urls_to_scan: dict, total_urls: int, hit_scan_cap: bool,
) -> tuple[int, int, str]:
    """Run the async-HTTP probes + persist results; return scan counters."""
    from django.utils import timezone
    from apps.pipeline.tasks_broken_links import (
        build_existing_records_map, persist_scan_results, scan_via_async_http,
    )

    checked_at = timezone.now()
    scan_items = list(urls_to_scan.values())
    existing_records = build_existing_records_map(urls_to_scan)
    to_create: list = []
    to_update: list = []
    flagged_urls, fixed_urls, probe_backend = scan_via_async_http(
        scan_items,
        job_id=job_id, total_urls=total_urls,
        existing_records=existing_records,
        to_create=to_create, to_update=to_update,
        checked_at=checked_at, hit_scan_cap=hit_scan_cap,
    )
    persist_scan_results(to_create, to_update)
    return flagged_urls, fixed_urls, probe_backend


def _publish_broken_link_scan_completion(
    job_id: str, total_urls: int, flagged_urls: int, fixed_urls: int,
    hit_scan_cap: bool, probe_backend: str,
) -> None:
    """Publish the completion progress + cap-warning suffix when applicable."""
    completion_message = (
        f"Broken link scan complete. {flagged_urls} issue(s) flagged, "
        f"{fixed_urls} previously flagged link(s) resolved."
    )
    if hit_scan_cap:
        completion_message += (
            f" Scan stopped at the {_MAX_BROKEN_LINK_SCAN_URLS:,} URL safety cap."
        )
    _publish_progress(
        job_id, "completed", 1.0, completion_message,
        scanned_urls=total_urls, total_urls=total_urls,
        flagged_urls=flagged_urls, fixed_urls=fixed_urls,
        hit_scan_cap=hit_scan_cap, probe_backend=probe_backend,
    )


@shared_task(
    bind=True, name="pipeline.verify_suggestions", time_limit=3600, soft_time_limit=3540
)
@HelperConstraint(
    cpu_intensive=False,            # network IO bound (HEAD probes)
    gpu_required=False,
    storage_writes_to="postgres_main",
    ram_peak_mb=256,
    expected_seconds_p50=300,
)
def verify_suggestions(self, suggestion_ids: list[str] | None = None) -> dict:
    """Check whether applied suggestions are still live via XenForo API."""
    from apps.suggestions.models import Suggestion
    from apps.sync.services.xenforo_api import XenForoAPIClient

    job_id = str(uuid.uuid4())
    _publish_progress(job_id, "running", 0.0, "Starting verification...")
    suggestions = Suggestion.objects.filter(status="applied")
    if suggestion_ids:
        suggestions = suggestions.filter(pk__in=suggestion_ids)
    total = suggestions.count()
    if total == 0:
        _publish_progress(job_id, "completed", 1.0, "No applied suggestions to verify.")
        return {"verified": 0, "stale": 0, "job_id": job_id}
    try:
        verified, stale = _run_suggestion_verifications(
            XenForoAPIClient(), suggestions, total, job_id,
        )
        _publish_progress(
            job_id, "completed", 1.0,
            f"Verification complete. {verified} verified, {stale} stale.",
        )
        return {"verified": verified, "stale": stale, "job_id": job_id}
    except (DatabaseError, TimeoutError, MemoryError, ValueError) as exc:
        logger.exception("Verification %s failed", job_id)
        _publish_progress(
            job_id, "failed", 0.0, f"Verification failed: {exc}", error=str(exc),
        )
        raise


def _run_suggestion_verifications(client, suggestions, total: int, job_id: str) -> tuple[int, int]:
    """Iterate suggestions, classify each as verified/stale, return counts."""
    verified = 0
    stale = 0
    for index, suggestion in enumerate(suggestions):
        _publish_progress(
            job_id, "running", index / total,
            f"Checking suggestion {str(suggestion.suggestion_id)[:8]}...",
        )
        result = _verify_one_suggestion(client, suggestion)
        if result == "verified":
            verified += 1
        elif result == "stale":
            stale += 1
    return verified, stale


def _verify_one_suggestion(client, suggestion) -> str:
    """Classify a single suggestion as verified/stale/skip + persist the new state."""
    from django.utils import timezone

    host_content = suggestion.host
    if not host_content or not host_content.xf_post_id:
        logger.warning(
            "Suggestion %s host has no xf_post_id", suggestion.suggestion_id,
        )
        return "skip"
    try:
        raw_bbcode = (
            client.get_post(host_content.xf_post_id)
            .get("post", {}).get("message", "")
        )
    except (TimeoutError, RequestException, URLError) as exc:
        logger.error(
            "Failed to fetch host post for suggestion %s: %s",
            suggestion.suggestion_id, exc,
        )
        return "skip"
    destination_url = suggestion.destination.url
    if not destination_url:
        logger.warning(
            "Suggestion %s destination has no URL", suggestion.suggestion_id,
        )
        return "skip"
    if destination_url in raw_bbcode:
        suggestion.status = "verified"
        suggestion.verified_at = timezone.now()
        suggestion.save(update_fields=["status", "verified_at", "updated_at"])
        return "verified"
    suggestion.status = "stale"
    suggestion.stale_reason = "Link not found in host post body"
    suggestion.save(update_fields=["status", "stale_reason", "updated_at"])
    return "stale"


@shared_task(
    bind=True,
    name="pipeline.recalculate_click_distance",
    time_limit=1800,
    soft_time_limit=1740,
)
@HelperConstraint(
    cpu_intensive=True,
    gpu_required=False,
    storage_writes_to="postgres_main",
    ram_peak_mb=512,
    expected_seconds_p50=180,
)
def recalculate_click_distance_task(self, job_id: str | None = None) -> dict:
    """Recompute Phase 15 Click-Distance scores for all active ContentItems."""
    job_id = job_id or str(uuid.uuid4())
    _publish_progress(
        job_id,
        "running",
        0.0,
        "Starting Click-Distance structural prior recalculation...",
    )

    try:
        from apps.pipeline.services.click_distance import ClickDistanceService

        service = ClickDistanceService()
        diagnostics = service.recalculate_all()

        _publish_progress(
            job_id,
            "completed",
            1.0,
            "Click-Distance recalculation complete.",
            **diagnostics,
        )
        return {"job_id": job_id, **diagnostics}
    except (DatabaseError, TimeoutError, MemoryError, ValueError) as exc:
        logger.exception("Click-Distance recalculation %s failed", job_id)
        _publish_progress(
            job_id,
            "failed",
            0.0,
            f"Click-Distance recalculation failed: {exc}",
            error=str(exc),
        )
        raise


def _probe_link_health(session: requests.Session, url: str) -> tuple[int, str]:
    """Check a URL with HEAD first, then GET when HEAD is not supported."""
    try:
        response = session.head(
            url, allow_redirects=False, timeout=_BROKEN_LINK_SCAN_TIMEOUT_SECONDS
        )
        if response.status_code in {405, 501}:
            response = session.get(
                url, allow_redirects=False, timeout=_BROKEN_LINK_SCAN_TIMEOUT_SECONDS
            )
    except requests.RequestException:
        logger.warning("Broken link scan request failed for %s", url, exc_info=True)
        return 0, ""

    redirect_url = ""
    if response.status_code in {301, 302, 307, 308}:
        location = response.headers.get("Location", "").strip()
        if location:
            redirect_url = urljoin(url, location)
    return response.status_code, redirect_url


def _status_label(http_status: int) -> str:
    return str(http_status) if http_status else "connection error"


@shared_task(name="pipeline.run_clustering_pass", time_limit=1800, soft_time_limit=1740)
@HelperConstraint(
    cpu_intensive=True,             # k-means + pgvector queries
    gpu_required=False,
    storage_writes_to="postgres_main",
    ram_peak_mb=1024,
    expected_seconds_p50=300,
)
def run_clustering_pass(job_id: str | None = None) -> dict:
    """Run a batch clustering pass over all ContentItems with embeddings."""
    from apps.content.models import ContentItem
    from apps.content.services.clustering import ClusteringService
    from apps.pipeline.services.embeddings import get_current_embedding_filter

    if not job_id:
        job_id = f"clustering_{int(time.time())}"

    logger.info("Starting batch clustering pass [%s]", job_id)
    _publish_progress(job_id, "running", 0.0, "Starting batch clustering pass...")

    # Filter items that have embeddings
    items = ContentItem.objects.filter(
        embedding__isnull=False,
        **get_current_embedding_filter(),
    ).only("id", "embedding", "cluster_id")
    total = items.count()

    if total == 0:
        _publish_progress(job_id, "completed", 1.0, "No items with embeddings found.")
        return {"status": "skipped", "message": "No items with embeddings."}

    service = ClusteringService()
    processed = 0

    for item in items:
        service.update_item_cluster(item.id)
        processed += 1
        if processed % 50 == 0:
            pct = processed / total
            _publish_progress(
                job_id, "running", pct, f"Clustered {processed}/{total} items..."
            )

    logger.info(
        "Batch clustering pass [%s] complete. Processed %d items.", job_id, processed
    )
    _publish_progress(
        job_id, "completed", 1.0, f"Clustering complete. Processed {processed} items."
    )

    return {"status": "completed", "processed": processed}


# ---------------------------------------------------------------------------
# Part 7 — Nightly data retention task
# ---------------------------------------------------------------------------


def _purge_aged_rows(  # noqa: forbidden-pattern too-many-args  # justification: shared by 9 retention blocks; bundling kwargs would add allocations and obscure the per-call config
    *,
    model_cls,
    cutoff_field: str,
    cutoff,
    extra_filter: dict | None = None,
    label: str,
    step: str,
    fix_hint: str,
    use_date: bool = False,
) -> int:
    """Delete rows older than ``cutoff`` from ``model_cls``; log failure to ErrorLog.

    Returns deleted row count (0 on failure). Replaces 9 near-identical
    try/except blocks in ``nightly_data_retention``.
    """
    import traceback
    from django.db import DatabaseError, IntegrityError
    from apps.audit.models import ErrorLog

    try:
        cutoff_value = cutoff.date() if use_date else cutoff
        qs_filter = {f"{cutoff_field}__lt": cutoff_value}
        if extra_filter:
            qs_filter.update(extra_filter)
        deleted, _ = model_cls.objects.filter(**qs_filter).delete()
        logger.info(
            "[nightly_data_retention] %s: deleted %d rows older than %s.",
            label, deleted, cutoff_value,
        )
        return deleted
    except (DatabaseError, IntegrityError):
        raw = traceback.format_exc()
        logger.exception("[nightly_data_retention] %s purge failed.", label)
        ErrorLog.objects.create(
            job_type="data_retention",
            step=step,
            error_message=f"{label} retention purge failed.",
            raw_exception=raw,
            why=fix_hint,
        )
        return 0


def _purge_with_bitmap_preview(  # noqa: forbidden-pattern too-many-args  # justification: shared by 3 IPS/IPW blocks (B.5, B.6, B.7); bundling reduces clarity at the per-call config sites
    *,
    queryset,
    use_bitmap: bool,
    label: str,
    step: str,
    fix_hint: str,
    preview_key: str | None = None,
) -> int:
    """Delete rows in ``queryset`` after taking a cardinality preview.

    For uint32-PK tables (SuggestionImpression, SuggestionPresentation),
    ``use_bitmap=True`` uses the Roaring bitmap path. UUID-PK tables
    (Suggestion) use ``use_bitmap=False`` and read cardinality via
    ``queryset.count()``.
    """
    import traceback
    from django.db import DatabaseError, IntegrityError
    from apps.audit.models import ErrorLog
    from apps.pipeline.services import waste_bitmaps

    try:
        if use_bitmap:
            bitmap = waste_bitmaps.bitmap_from_pks(queryset)
            pending = waste_bitmaps.cardinality_preview(bitmap)
        else:
            pending = queryset.count()
        deleted = 0
        if pending:
            deleted, _ = queryset.delete()
        logger.info(
            "[nightly_data_retention] %s: deleted %d rows (preview was %d).",
            label, deleted, pending,
        )
        if preview_key is not None:
            _persist_retention_preview(preview_key, value=0, last_count=pending)
        return deleted
    except (DatabaseError, IntegrityError):
        raw = traceback.format_exc()
        logger.exception("[nightly_data_retention] %s purge failed.", label)
        ErrorLog.objects.create(
            job_type="data_retention",
            step=step,
            error_message=f"{label} retention purge failed.",
            raw_exception=raw,
            why=fix_hint,
        )
        return 0


def _retention_progress_reporter(progress_callback):
    """Wrap ``progress_callback`` in a no-op-on-error closure for nightly_data_retention."""
    def _report(pct: float, message: str) -> None:
        if progress_callback is None:
            return
        try:
            progress_callback(pct, message)
        except Exception:  # pragma: no cover — defensive
            logger.warning(
                "[nightly_data_retention] progress_callback raised "
                "for pct=%s message=%s; continuing", pct, message,
            )
    return _report


@shared_task(
    name="pipeline.nightly_data_retention", time_limit=1800, soft_time_limit=1740
)
@HelperConstraint(
    cpu_intensive=False,            # bulk Postgres deletes; mostly DB-bound
    gpu_required=False,
    storage_writes_to="postgres_main",
    ram_peak_mb=256,
    expected_seconds_p50=600,
)
def nightly_data_retention(progress_callback=None):
    """Purge stale data rows according to the retention policy.

    Runs daily at 22:30 inside the operator window via
    ``apps.scheduled_updates.jobs.run_daily_data_retention`` (the
    primary caller). Also callable manually via
    ``nightly_data_retention.run()`` from the diagnostics manual-run
    view. The function name is kept (despite the ``nightly_`` prefix)
    for backward compatibility with the existing manual-run path and
    docstring references throughout the codebase.

    Retention policy:
        SearchMetric rows           — 12 months
        PipelineRun logs            — 90 days
        ContentMetricSnapshot       — keep last 2 per item
        Superseded Suggestions      — 30 days
        AuditEntry                  — 6 months (180 days)
        ErrorLog                    — 30 days
        WebhookReceipt              — 30 days
        SuggestionImpression        — 90 days  (B.5 — IPS / Cascade lookback)
        SuggestionPresentation      — 180 days (B.6 — IPW lookback)
        Pending / stale Suggestion  — 365 days (B.7 — non-approved trail)
        ImpactReport                — FOREVER (never purged)
        Approved Suggestion         — FOREVER (never purged — operator audit trail)
        WeightAdjustmentHistory     — FOREVER (never purged)

    *progress_callback*, when provided, is invoked as
    ``progress_callback(progress_pct: float, message: str)`` after each
    prune block so the scheduled-updates dashboard can render a live
    progress bar. Defaults to a no-op so the existing Celery / manual
    paths see no behavior change.
    """
    from django.utils import timezone

    _report = _retention_progress_reporter(progress_callback)
    now = timezone.now()
    results: dict[str, int] = {}
    _report(0.0, "Starting data retention sweep")
    _run_standard_purges(now, results)
    _run_advanced_purges(now, results, _report)
    _persist_retention_run_timestamp(now.isoformat())
    _report(100.0, "Data retention complete")
    logger.info("[nightly_data_retention] Complete. Results: %s", results)
    return results


def _run_standard_purges(now, results: dict[str, int]) -> None:
    """Execute the 8 plain age-based purge blocks via the spec table."""
    from datetime import timedelta
    from apps.audit.models import ErrorLog
    from apps.pipeline.services.velocity import prune_old_snapshots

    for spec in _build_standard_purge_specs(now):
        results[spec["result_key"]] = _purge_aged_rows(
            model_cls=spec["model_cls"],
            cutoff_field=spec["cutoff_field"],
            cutoff=spec["cutoff"],
            use_date=spec.get("use_date", False),
            extra_filter=spec.get("extra_filter"),
            label=spec["label"],
            step=spec["step"],
            fix_hint=spec["fix_hint"],
        )

    # ContentMetricSnapshot uses a "keep last N per item" rule, not an age
    # filter, so it doesn't fit the spec table.
    import traceback
    from django.db import DatabaseError, IntegrityError
    try:
        results["metric_snapshots_deleted"] = prune_old_snapshots(keep=2)
        logger.info(
            "[nightly_data_retention] ContentMetricSnapshot: deleted %d rows (keeping last 2 per item).",
            results["metric_snapshots_deleted"],
        )
    except (DatabaseError, IntegrityError):
        logger.exception("[nightly_data_retention] ContentMetricSnapshot purge failed.")
        ErrorLog.objects.create(
            job_type="data_retention", step="metric_snapshot_purge",
            error_message="ContentMetricSnapshot retention purge failed.",
            raw_exception=traceback.format_exc(),
            why="Check database connectivity and the content.ContentMetricSnapshot table.",
        )
        results["metric_snapshots_deleted"] = 0


def _build_standard_purge_specs(now) -> list[dict]:  # noqa: forbidden-pattern long-function  # justification: pure data table — adding a new retention rule = one entry; splitting would obscure the inventory.
    """Return the per-table spec list for ``_run_standard_purges``.

    Adding a new age-based retention rule = one entry here, not a new
    try/except block. Each entry maps directly to ``_purge_aged_rows``
    keyword args.
    """
    from datetime import timedelta
    from apps.analytics.models import SearchMetric
    from apps.audit.models import AuditEntry, ErrorLog
    from apps.crawler.models import CrawlerVisit
    from apps.suggestions.models import PipelineRun, Suggestion
    from apps.sync.models import WebhookReceipt

    return [
        {
            "model_cls": SearchMetric, "cutoff_field": "date", "use_date": True,
            "cutoff": now - timedelta(days=_RETENTION_12_MONTHS),
            "result_key": "search_metrics_deleted",
            "label": "SearchMetric (12 months)", "step": "search_metric_purge",
            "fix_hint": "Check database connectivity and the analytics.SearchMetric table.",
        },
        {
            "model_cls": PipelineRun, "cutoff_field": "created_at",
            "cutoff": now - timedelta(days=90),
            "result_key": "pipeline_runs_deleted",
            "label": "PipelineRun (90 days)", "step": "pipeline_run_purge",
            "fix_hint": "Check database connectivity and the suggestions.PipelineRun table.",
        },
        {
            "model_cls": Suggestion, "cutoff_field": "updated_at",
            "cutoff": now - timedelta(days=30),
            "extra_filter": {"status": "superseded"},
            "result_key": "superseded_suggestions_deleted",
            "label": "Superseded Suggestion (30 days)",
            "step": "superseded_suggestion_purge",
            "fix_hint": "Check database connectivity and the suggestions.Suggestion table.",
        },
        {
            "model_cls": AuditEntry, "cutoff_field": "created_at",
            "cutoff": now - timedelta(days=_RETENTION_6_MONTHS),
            "result_key": "audit_entries_deleted",
            "label": "AuditEntry (180 days)", "step": "audit_entry_purge",
            "fix_hint": "Check database connectivity and the audit.AuditEntry table.",
        },
        {
            "model_cls": ErrorLog, "cutoff_field": "created_at",
            "cutoff": now - timedelta(days=30),
            "result_key": "error_logs_deleted",
            "label": "ErrorLog (30 days)", "step": "error_log_purge",
            # Cannot log ErrorLog purge failures to ErrorLog itself; logger.exception covers.
            "fix_hint": "Cannot self-log; check Postgres logs for the ErrorLog table.",
        },
        {
            "model_cls": WebhookReceipt, "cutoff_field": "created_at",
            "cutoff": now - timedelta(days=30),
            "result_key": "webhook_receipts_deleted",
            "label": "WebhookReceipt (30 days)", "step": "webhook_receipt_purge",
            "fix_hint": "Check database connectivity and the sync.WebhookReceipt table.",
        },
        # Group D.7 — CrawlerVisit (D.5 dedup audit log; 90-day rolling window).
        # Heavy CrawledPageMeta rows are NOT pruned here — D.5/D.6 already dedupe them.
        {
            "model_cls": CrawlerVisit, "cutoff_field": "visited_at",
            "cutoff": now - timedelta(days=90),
            "result_key": "crawler_visits_deleted",
            "label": "CrawlerVisit (D.7, 90 days)", "step": "crawler_visit_purge",
            "fix_hint": (
                "Check database connectivity and the crawler.CrawlerVisit table. "
                "The dedup feature (D.5) requires this table; failure here means "
                "the visit log will keep growing until disk runs out."
            ),
        },
    ]


def _run_advanced_purges(now, results: dict[str, int], report) -> None:
    """Execute the 3 bitmap-preview purge blocks (B.5 / B.6 / B.7)."""
    from datetime import timedelta
    from apps.suggestions.models import Suggestion, SuggestionImpression, SuggestionPresentation

    report(60.0, "Pruning IPS / Cascade impressions (B.5)")
    # Pick #33 (IPS) and #34 (Cascade Click) read 90-day impressions to fit
    # propensity estimates; older rows fall out of every producer's window.
    # Roaring bitmap is for the cardinality preview only (audit A3 fix); the
    # actual DELETE goes through the queryset so Postgres uses the indexed range scan.
    results["suggestion_impressions_deleted"] = _purge_with_bitmap_preview(
        queryset=SuggestionImpression.objects.filter(
            impressed_at__lt=now - timedelta(days=_RETENTION_3_MONTHS),
        ),
        use_bitmap=True,
        label="SuggestionImpression (B.5, 90 days)",
        step="suggestion_impression_purge",
        fix_hint="Check database connectivity and the suggestions.SuggestionImpression table.",
        preview_key=RETENTION_PREVIEW_KEY_IMPRESSIONS,
    )
    report(75.0, "Pruning IPW presentations (B.6)")
    # Joachims 2017 IPW reranker uses a 180-day presentation window for
    # exposure denominators; older rows can be pruned safely.
    results["suggestion_presentations_deleted"] = _purge_with_bitmap_preview(
        queryset=SuggestionPresentation.objects.filter(
            presented_date__lt=(now - timedelta(days=_RETENTION_6_MONTHS)).date(),
        ),
        use_bitmap=True,
        label="SuggestionPresentation (B.6, 180 days)",
        step="suggestion_presentation_purge",
        fix_hint="Check database connectivity and the suggestions.SuggestionPresentation table.",
        preview_key=RETENTION_PREVIEW_KEY_PRESENTATIONS,
    )
    report(90.0, "Pruning aged-out non-approved Suggestions (B.7)")
    # Approved / applied / verified Suggestions are the operator audit trail
    # and are NEVER purged. Pending / stale rows that aged out a year without
    # operator action are noise. UUID PK forbids the bitmap path (uint32-only)
    # so we use direct queryset .count() for the preview.
    results["non_approved_suggestions_deleted"] = _purge_with_bitmap_preview(
        queryset=Suggestion.objects.filter(
            status__in=("pending", "stale"),
            updated_at__lt=now - timedelta(days=_RETENTION_12_MONTHS),
        ),
        use_bitmap=False,
        label="Pending/stale Suggestion (B.7, 365 days)",
        step="non_approved_suggestion_purge",
        fix_hint="Check database connectivity and the suggestions.Suggestion table.",
        preview_key=RETENTION_PREVIEW_KEY_NON_APPROVED,
    )


def _persist_retention_preview(key: str, *, value: int, last_count: int) -> None:
    """Write ``key`` and ``key.last_count`` to AppSetting for the dashboard.

    *value* is the post-prune cardinality (always ~0 right after a
    successful prune); *last_count* is what the prune just acted on.
    The dashboard panel renders both — "0 rows pending now, last
    sweep deleted 12,480" — so the operator sees both freshness and
    historical volume at a glance.
    """
    try:
        from apps.core.models import AppSetting

        AppSetting.objects.update_or_create(
            key=key,
            defaults={
                "value": str(int(value)),
                "value_type": "int",
                "category": "retention",
                "description": "Retention queue cardinality (post-prune).",
            },
        )
        AppSetting.objects.update_or_create(
            key=f"{key}.last_count",
            defaults={
                "value": str(int(last_count)),
                "value_type": "int",
                "category": "retention",
                "description": "Rows the most recent prune actually deleted.",
            },
        )
    except Exception as exc:  # pragma: no cover — defensive
        logger.warning("_persist_retention_preview(%s) failed: %s", key, exc)


def _persist_retention_run_timestamp(iso: str) -> None:
    """Write the last-run timestamp to AppSetting for the dashboard."""
    try:
        from apps.core.models import AppSetting

        AppSetting.objects.update_or_create(
            key=RETENTION_PREVIEW_KEY_LAST_RUN_AT,
            defaults={
                "value": iso,
                "value_type": "str",
                "category": "retention",
                "description": "ISO-8601 timestamp of the last successful retention sweep.",
            },
        )
    except Exception as exc:  # pragma: no cover — defensive
        logger.warning("_persist_retention_run_timestamp(%s) failed: %s", iso, exc)


@shared_task(name="pipeline.cleanup_stuck_sync_jobs")
@HelperConstraint(
    cpu_intensive=False,            # short DB-only sweep
    gpu_required=False,
    storage_writes_to="postgres_main",
    ram_peak_mb=64,
    expected_seconds_p50=10,
)
def cleanup_stuck_sync_jobs():
    """Mark SyncJob records that have been stuck in 'running' for over 2 hours as failed.

    This handles the case where the server was restarted or the laptop shut down
    mid-sync, leaving a job record that will never complete on its own.

    Scheduled daily at 03:30 UTC (after nightly_data_retention).
    """
    from datetime import timedelta
    from django.utils import timezone
    from apps.sync.models import SyncJob

    cutoff = timezone.now() - timedelta(hours=2)
    stuck = SyncJob.objects.filter(status="running", started_at__lt=cutoff)
    count = stuck.count()
    if not count:
        logger.info("[cleanup_stuck_sync_jobs] No stuck jobs found.")
        return {"jobs_cleaned": 0}
    resumable_count, no_checkpoint_count = _mark_stuck_jobs_failed(stuck, timezone.now())
    logger.info(
        "[cleanup_stuck_sync_jobs] Marked %d stuck job(s) as failed "
        "(%d resumable, %d need restart).",
        count, resumable_count, no_checkpoint_count,
    )
    return {"jobs_cleaned": count}


def _mark_stuck_jobs_failed(stuck_qs, now) -> tuple[int, int]:
    """Mark stuck jobs failed; return (resumable_count, no_checkpoint_count).

    Jobs with a checkpoint can resume from where they left off — flag
    is_resumable=True so the next import_content call picks up via the
    resume path. Jobs with no checkpoint must restart from scratch.
    """
    resumable_count = stuck_qs.exclude(checkpoint_stage="").update(
        status="failed", is_resumable=True,
        error_message=(
            "Job interrupted — server was likely restarted mid-sync. "
            "Resumable from last checkpoint."
        ),
        completed_at=now,
    )
    no_checkpoint_count = stuck_qs.filter(checkpoint_stage="").update(
        status="failed", is_resumable=False,
        error_message=(
            "Job timed out before any checkpoint — server was likely "
            "restarted mid-sync."
        ),
        completed_at=now,
    )
    return resumable_count, no_checkpoint_count


@shared_task(
    name="pipeline.sync_single_xf_item",
    time_limit=300,
    soft_time_limit=270,
    autoretry_for=(requests.RequestException, ConnectionError),
    max_retries=3,
    retry_backoff=60,
)
@HelperConstraint(
    cpu_intensive=False,            # network IO bound (XF API)
    gpu_required=False,
    storage_writes_to="postgres_main",
    ram_peak_mb=128,
    expected_seconds_p50=15,
)
def sync_single_xf_item(
    content_id: int, content_type: str = "thread", node_id: int | None = None
) -> dict:
    """Real-time sync for a single XenForo item (thread or resource) via webhook."""
    from apps.pipeline.tasks import import_content

    logger.info(
        "Real-time sync triggered for %s %d (node/cat: %s)",
        content_type, content_id, node_id,
    )
    try:
        xf_node_id = _resolve_xf_node_id(content_id, content_type, node_id)
        if not xf_node_id:
            logger.error(
                "Could not determine node_id for %s %d", content_type, content_id,
            )
            return {"error": "Missing node_id"}
        scope = _ensure_scope_for_xf_node(xf_node_id, content_type)
        if not scope.is_enabled:
            logger.info(
                "Scope %s is disabled; skipping sync for %s %d",
                scope.title, content_type, content_id,
            )
            return {"status": "skipped", "reason": "scope disabled"}
        return import_content(scope_ids=[scope.pk], mode="full", source="api")
    except (DatabaseError, TimeoutError, MemoryError, ValueError) as e:
        logger.exception("Failed to sync single item %d", content_id)
        return {"error": str(e)}


def _resolve_xf_node_id(
    content_id: int, content_type: str, node_id: int | None,
) -> int | None:
    """Return ``node_id`` if supplied; otherwise look it up via the XenForo API."""
    if node_id:
        return node_id
    from apps.sync.services.xenforo_api import XenForoAPIClient
    client = XenForoAPIClient()
    if content_type == "thread":
        return client.get_thread(content_id).get("thread", {}).get("node_id")
    if content_type == "resource":
        return (
            client.get_resource_updates(content_id)  # hypothetical
            .get("resource", {})
            .get("resource_category_id")
        )
    return None


def _ensure_scope_for_xf_node(xf_node_id: int, content_type: str):
    """Get-or-create a ScopeItem for the resolved XenForo node/category id."""
    from apps.content.models import ScopeItem

    scope_type = "node" if content_type == "thread" else "resource_category"
    scope, _ = ScopeItem.objects.get_or_create(
        scope_id=xf_node_id, scope_type=scope_type,
        defaults={
            "title": f"Auto-discovered {scope_type} {xf_node_id}",
            "is_enabled": True,
        },
    )
    return scope


@shared_task(
    name="pipeline.sync_single_wp_item",
    time_limit=300,
    soft_time_limit=270,
    autoretry_for=(requests.RequestException, ConnectionError),
    max_retries=3,
    retry_backoff=60,
)
@HelperConstraint(
    cpu_intensive=False,            # network IO bound (WP REST API)
    gpu_required=False,
    storage_writes_to="postgres_main",
    ram_peak_mb=128,
    expected_seconds_p50=15,
)
def sync_single_wp_item(post_id: int, content_type: str = "post") -> dict:
    """Real-time sync for a single WordPress post/page via webhook."""
    from apps.core.views import get_wordpress_runtime_config
    from apps.sync.services.wordpress_api import WordPressAPIClient
    from apps.pipeline.tasks import import_content

    logger.info("Real-time sync triggered for WordPress %s %d", content_type, post_id)

    try:
        wp_config = get_wordpress_runtime_config()
        client = WordPressAPIClient(
            base_url=wp_config["base_url"],
            username=wp_config["username"],
            app_password=wp_config["app_password"],
        )

        # 1. Fetch item data to verify it exists
        if content_type == "page":
            item = client.get_page(post_id)
        else:
            item = client.get_post(post_id)

        if not item:
            return {"error": "Item not found"}

        # 2. Trigger import logic
        # For single items we always use "full" to ensure we get the body and embeddings
        return import_content(
            mode="full", source="wp", job_id=f"wp_single_{post_id}_{int(time.time())}"
        )

    except (DatabaseError, TimeoutError, MemoryError, ValueError) as e:
        logger.exception("Failed to sync single WP item %d", post_id)
        return {"error": str(e)}


# ---------------------------------------------------------------------------
# Part 8 — FR-018 Python auto-tune tasks
# ---------------------------------------------------------------------------


@shared_task(
    bind=True,
    name="pipeline.monthly_weight_tune",
    time_limit=600,
    soft_time_limit=540,
    acks_late=True,
)
@HelperConstraint(
    cpu_intensive=True,             # TPE optimisation walk
    gpu_required=False,
    storage_writes_to="postgres_main",
    ram_peak_mb=512,
    expected_seconds_p50=240,
)
@with_weight_lock("medium")
def monthly_weight_tune(self):
    """Trigger an FR-018 weight-tune run via the Python WeightTuner, then evaluate.

    Scheduled at 13:45 UTC on the first Sunday of every month.
    """
    import traceback
    import uuid as _uuid

    from apps.audit.models import ErrorLog
    from apps.suggestions.services.weight_tuner import WeightTuner

    run_id = str(_uuid.uuid4())

    try:
        tuner = WeightTuner(lookback_days=90)
        challenger = tuner.run(run_id=run_id)

        if challenger:
            logger.info(
                "[monthly_weight_tune] Native tuner found improvement. run_id=%s",
                run_id,
            )
            # Chain evaluate_weight_challenger to score and optionally promote it.
            evaluate_weight_challenger.delay(run_id=run_id)
            return {
                "status": "submitted",
                "run_id": run_id,
                "challenger_id": str(challenger.pk),
            }
        else:
            logger.info("[monthly_weight_tune] No improvement found by native tuner.")
            return {"status": "skipped", "run_id": run_id}

    except (DatabaseError, TimeoutError, MemoryError, ValueError):
        raw = traceback.format_exc()
        logger.exception("[monthly_weight_tune] Failed: %s", raw)
        ErrorLog.objects.create(
            job_type="auto_tune_weights",
            step="monthly_weight_tune",
            error_message="Weight-tune task failed.",
            raw_exception=raw,
            why="The monthly auto-tune task raised an unexpected exception.",
        )
        return {"status": "error"}


_OPTIMISER_COVERAGE_NOTE = (
    "Optimiser covers 4 of 12 live ranker weights. "
    "Uncovered: weighted_authority, link_freshness, phrase_matching, "
    "learned_anchor, rare_term_propagation, field_aware_relevance, "
    "ga4_gsc, click_distance."
)


@shared_task(bind=True, name="pipeline.evaluate_weight_challenger")
@HelperConstraint(
    cpu_intensive=True,             # NDCG@k bootstrap evaluation
    gpu_required=False,
    storage_writes_to="postgres_main",
    ram_peak_mb=1024,
    expected_seconds_p50=600,
)
def evaluate_weight_challenger(self, *, run_id: str):
    """Evaluate a pending RankingChallenger and promote it if it beats the champion.

    Promotion criteria (spec §4):
        challenger.predicted_quality_score > champion_quality_score * 1.05

    If the challenger qualifies, its weights are written to AppSetting and a
    WeightAdjustmentHistory row is created with source='auto_tune'.
    If it does not qualify, the challenger is marked 'rejected'.

    Called automatically after monthly_weight_tune, or manually via
    POST /api/settings/weight-tune/trigger/.
    """
    from apps.suggestions.models import RankingChallenger

    try:
        challenger = (
            RankingChallenger.objects.filter(run_id=run_id, status="pending").first()
        )
        if challenger is None:
            logger.info(
                "[evaluate_weight_challenger] No pending challenger found for run_id=%s",
                run_id,
            )
            return {"status": "not_found", "run_id": run_id}
        decision = _decide_challenger_promotion(challenger, run_id)
        if not decision["should_promote"]:
            return _record_challenger_rejection(challenger, run_id, decision)
        return _promote_challenger(challenger, run_id)
    except (DatabaseError, TimeoutError, MemoryError, ValueError):
        return _log_challenger_evaluation_error()


def _decide_challenger_promotion(challenger, run_id: str) -> dict:
    """Run SPRT on the challenger; return promote/reject decision + diagnostics."""
    from apps.pipeline.services.sprt_evaluator import ChallengerSPRTEvaluator

    cand_score = challenger.predicted_quality_score
    champ_score = challenger.champion_quality_score
    # WeightTuner now always populates both quality scores. This branch
    # handles legacy challenger rows created before that fix where the
    # scores remained NULL (bounds validation in WeightChallengerInternalView
    # already guarantees safety).
    if cand_score is None or champ_score is None:
        logger.info(
            "[evaluate_weight_challenger] No quality scores on challenger %s — auto-promoting.",
            run_id,
        )
        return {"should_promote": True, "decision": "auto", "cand_score": None, "champ_score": None}
    evaluator = ChallengerSPRTEvaluator(
        alpha=0.05, beta=0.10, min_improvement_ratio=1.05, assumed_std_dev=0.08,
    )
    sprt_result = evaluator.evaluate(cand_score, champ_score)
    logger.info(
        "[evaluate_weight_challenger] SPRT for %s: %s (LR=%.4f, bounds=[%.4f, %.4f])",
        run_id, sprt_result.decision, sprt_result.log_likelihood_ratio,
        sprt_result.lower_boundary, sprt_result.upper_boundary,
    )
    return {
        "should_promote": sprt_result.decision == "promote",
        "decision": sprt_result.decision,
        "cand_score": cand_score,
        "champ_score": champ_score,
    }


def _record_challenger_rejection(challenger, run_id: str, decision: dict) -> dict:
    """Mark the challenger rejected + return the API response payload."""
    challenger.status = "rejected"
    challenger.save(update_fields=["status", "updated_at"])
    if decision["cand_score"] is not None:
        logger.info(
            "[evaluate_weight_challenger] Challenger %s rejected via SPRT (%s): "
            "score %.4f vs champion %.4f.",
            run_id, decision["decision"], decision["cand_score"], decision["champ_score"],
        )
    return {
        "status": "rejected", "run_id": run_id, "decision": decision["decision"],
        "coverage_note": _OPTIMISER_COVERAGE_NOTE,
    }


def _promote_challenger(challenger, run_id: str) -> dict:
    """Apply the challenger's weights, persist a history row, mark it promoted."""
    from django.db import transaction
    from apps.suggestions.weight_preset_service import (
        apply_weights, get_current_weights, write_history,
    )

    previous_weights = get_current_weights()
    # Merge candidate values into the full current weights dict.
    promoted_weights = dict(previous_weights)
    for key, val in challenger.candidate_weights.items():
        promoted_weights[key] = str(val)
    with transaction.atomic():
        apply_weights(promoted_weights)
    new_weights = get_current_weights()
    history_row = write_history(
        source="auto_tune",
        previous_weights=previous_weights,
        new_weights=new_weights,
        reason=f"FR-018 Python auto-tune promoted challenger {run_id[:_RUN_ID_PREVIEW_LEN]}",
        r_run_id=run_id,
    )
    challenger.status = "promoted"
    if history_row is not None:
        challenger.history = history_row
    challenger.save(update_fields=["status", "history", "updated_at"])
    logger.info(
        "[evaluate_weight_challenger] Challenger %s promoted. New weights: %s",
        run_id,
        {k: promoted_weights[k] for k in challenger.candidate_weights},
    )
    return {"status": "promoted", "run_id": run_id, "coverage_note": _OPTIMISER_COVERAGE_NOTE}


def _log_challenger_evaluation_error() -> dict:
    """Persist the eval-failure to ErrorLog + return error payload."""
    import traceback
    from apps.audit.models import ErrorLog

    raw = traceback.format_exc()
    logger.exception("[evaluate_weight_challenger] Failed.")
    ErrorLog.objects.create(
        job_type="auto_tune_weights",
        step="evaluate_weight_challenger",
        error_message="Challenger evaluation failed.",
        raw_exception=raw,
        why="The evaluate_weight_challenger task raised an unexpected exception.",
    )
    return {"status": "error"}


@shared_task(name="pipeline.check_weight_rollback")
@HelperConstraint(
    cpu_intensive=False,            # short DB read + comparison
    gpu_required=False,
    storage_writes_to="postgres_main",
    ram_peak_mb=128,
    expected_seconds_p50=15,
)
def check_weight_rollback():
    """Check recently-promoted challengers for a GSC regression and roll back if found.

    Scheduled weekly at 04:00 UTC on Sunday (runs after enough post-promotion
    data has accumulated).

    Rollback trigger: average GSC clicks in the 14-day window after promotion
    is more than 15% below the 14-day baseline before promotion.
    """
    import traceback
    from datetime import timedelta

    from django.utils import timezone

    from apps.audit.models import ErrorLog
    from apps.suggestions.models import RankingChallenger

    # Only inspect challengers promoted in the last 21 days.
    lookback = timezone.now() - timedelta(days=21)
    # Minimum 14 days post-promotion needed before we can judge.
    min_age = timezone.now() - timedelta(days=14)

    candidates = RankingChallenger.objects.filter(
        status="promoted",
        updated_at__gte=lookback,
        updated_at__lte=min_age,
    )

    for challenger in candidates:
        try:
            _check_single_rollback(challenger)
        except (DatabaseError, TimeoutError, MemoryError, ValueError):
            raw = traceback.format_exc()
            logger.exception(
                "[check_weight_rollback] Error checking challenger %s.",
                challenger.run_id,
            )
            ErrorLog.objects.create(
                job_type="auto_tune_weights",
                step="check_weight_rollback",
                error_message=f"Rollback check failed for challenger {challenger.run_id[:_RUN_ID_PREVIEW_LEN]}.",
                raw_exception=raw,
                why="check_weight_rollback raised an unexpected exception for one challenger.",
            )


_REGRESSION_THRESHOLD = 0.85  # post/pre click ratio < 85% of baseline = regression
_MIN_PRE_CLICKS_FOR_ROLLBACK = 50  # too little data → can't reliably detect regression


def _check_single_rollback(challenger):
    """Compare GSC clicks before vs after promotion for one challenger."""
    from datetime import timedelta

    promoted_at = challenger.updated_at.date()
    pre_clicks, post_clicks = _aggregate_gsc_click_windows(
        pre=(promoted_at - timedelta(days=14), promoted_at - timedelta(days=1)),
        post=(promoted_at, promoted_at + timedelta(days=13)),
    )
    if pre_clicks < _MIN_PRE_CLICKS_FOR_ROLLBACK:
        logger.info(
            "[check_weight_rollback] Skipping challenger %s — insufficient pre-promotion "
            "GSC data (%d clicks).",
            challenger.run_id, pre_clicks,
        )
        return
    ratio = post_clicks / pre_clicks
    logger.info(
        "[check_weight_rollback] Challenger %s: post/pre click ratio = %.3f (threshold %.2f).",
        challenger.run_id, ratio, _REGRESSION_THRESHOLD,
    )
    if ratio >= _REGRESSION_THRESHOLD:
        return
    _execute_rollback(challenger, ratio)


def _aggregate_gsc_click_windows(pre: tuple, post: tuple) -> tuple[int, int]:
    """Bulk-sum GSC clicks for the pre- and post-promotion windows."""
    from django.db.models import Sum
    from apps.analytics.models import GSCDailyPerformance

    def _sum(start, end) -> int:
        return GSCDailyPerformance.objects.filter(
            date__range=(start, end),
        ).aggregate(total=Sum("clicks"))["total"] or 0
    return _sum(*pre), _sum(*post)


def _execute_rollback(challenger, ratio: float) -> None:
    """Apply baseline_weights, write history, mark challenger rolled_back."""
    from django.db import transaction
    from apps.suggestions.weight_preset_service import (
        apply_weights, get_current_weights, write_history,
    )

    if not challenger.baseline_weights:
        logger.warning(
            "[check_weight_rollback] No baseline_weights on challenger %s — cannot roll back.",
            challenger.run_id,
        )
        return
    previous_weights = get_current_weights()
    rollback_target = dict(previous_weights)
    for key, val in challenger.baseline_weights.items():
        rollback_target[key] = str(val)
    with transaction.atomic():
        apply_weights(rollback_target)
    new_weights = get_current_weights()
    write_history(
        source="auto_tune",
        previous_weights=previous_weights,
        new_weights=new_weights,
        reason=(
            f"FR-018 auto-rollback: challenger {challenger.run_id[:_RUN_ID_PREVIEW_LEN]} "
            f"caused GSC regression (post/pre={ratio:.2f})."
        ),
        r_run_id=challenger.run_id,
    )
    challenger.status = "rolled_back"
    challenger.save(update_fields=["status", "updated_at"])
    logger.info(
        "[check_weight_rollback] Rolled back challenger %s (ratio=%.3f).",
        challenger.run_id, ratio,
    )


# ── FR-019: GSC spike detection ───────────────────────────────────────────────


@shared_task(bind=True, name="pipeline.check_gsc_spikes")
@HelperConstraint(
    cpu_intensive=False,            # GROUP BY queries against SearchMetric
    gpu_required=False,
    storage_writes_to="postgres_main",
    ram_peak_mb=256,
    expected_seconds_p50=120,
)
def check_gsc_spikes(self) -> dict:
    """
    Detect significant week-on-week Google Search Console demand spikes.

    For each ContentItem with at least 7 days of GSC data, compare the
    most recent 3-day average against the previous 7-day baseline. If
    either impressions or clicks jump above the configured thresholds,
    emit an analytics.gsc_spike operator alert.

    Thresholds are read from the notifications.settings AppSetting so
    the operator can tune them from the UI.
    """
    from apps.content.models import ContentItem

    thresholds, today, recent_window, baseline_window = _gsc_spike_setup()
    recent_stats, baseline_stats = _gsc_spike_aggregate_stats(recent_window, baseline_window)
    relevant_ids = recent_stats.keys() | baseline_stats.keys()
    items_by_pk = {it.pk: it for it in ContentItem.objects.filter(pk__in=relevant_ids)}
    alerts_emitted = 0
    for pk, item in items_by_pk.items():
        spike = _evaluate_gsc_spike(
            recent_stats.get(pk, {}), baseline_stats.get(pk, {}), thresholds,
        )
        if spike is None:
            continue
        if _emit_gsc_spike_alert(item, spike, today):
            alerts_emitted += 1
    logger.info("check_gsc_spikes: %d spike alerts emitted.", alerts_emitted)
    return {"alerts_emitted": alerts_emitted}


def _gsc_spike_setup() -> tuple[dict, "date", tuple, tuple]:
    """Read thresholds + compute the 3-day recent window and 7-day baseline window."""
    from datetime import date, timedelta
    from apps.core.models import AppSetting

    # Group D consolidation (2026-04-28): inline filter+json.loads is now one
    # call to the shared AppSetting.get_json helper.
    prefs = AppSetting.get_json("notifications.settings", {}) or {}
    thresholds = {
        "min_impressions_delta": int(prefs.get("gsc_spike_min_impressions_delta", 50)),
        "min_clicks_delta": int(prefs.get("gsc_spike_min_clicks_delta", 5)),
        "min_relative_lift": float(prefs.get("gsc_spike_min_relative_lift", 0.5)),
    }
    today = date.today()
    recent_end = today - timedelta(days=1)  # yesterday
    recent_start = recent_end - timedelta(days=2)  # 3-day window
    baseline_end = recent_start - timedelta(days=1)
    baseline_start = baseline_end - timedelta(days=6)  # 7-day baseline
    return thresholds, today, (recent_start, recent_end), (baseline_start, baseline_end)


def _gsc_spike_aggregate_stats(recent_window: tuple, baseline_window: tuple) -> tuple[dict, dict]:
    """Bulk-aggregate avg impressions+clicks for both windows in two queries (avoids N+1)."""
    from django.db.models import Avg
    from apps.analytics.models import SearchMetric

    def _bulk_avg(start, end) -> dict:
        return {
            row["content_item_id"]: row
            for row in SearchMetric.objects.filter(
                source="gsc", date__gte=start, date__lte=end,
            ).values("content_item_id").annotate(
                avg_impressions=Avg("impressions"), avg_clicks=Avg("clicks"),
            )
        }
    return _bulk_avg(*recent_window), _bulk_avg(*baseline_window)


def _evaluate_gsc_spike(recent_row: dict, baseline_row: dict, thresholds: dict) -> dict | None:
    """Return spike-diagnostic dict if either impressions or clicks crossed threshold; else None."""
    r_imp = recent_row.get("avg_impressions") or 0.0
    r_clk = recent_row.get("avg_clicks") or 0.0
    b_imp = baseline_row.get("avg_impressions") or 0.0
    b_clk = baseline_row.get("avg_clicks") or 0.0
    if b_imp == 0 and b_clk == 0:
        return None
    imp_delta = r_imp - b_imp
    clk_delta = r_clk - b_clk
    imp_lift = (imp_delta / b_imp) if b_imp > 0 else 0.0
    clk_lift = (clk_delta / b_clk) if b_clk > 0 else 0.0
    impressions_spike = (
        imp_delta >= thresholds["min_impressions_delta"]
        and imp_lift >= thresholds["min_relative_lift"]
    )
    clicks_spike = (
        clk_delta >= thresholds["min_clicks_delta"]
        and clk_lift >= thresholds["min_relative_lift"]
    )
    if not (impressions_spike or clicks_spike):
        return None
    return {
        "imp_delta": imp_delta, "clk_delta": clk_delta,
        "imp_lift": imp_lift, "clk_lift": clk_lift,
    }


def _emit_gsc_spike_alert(item, spike: dict, today) -> bool:
    """Emit one operator alert for a spike. Returns True iff emitted successfully."""
    from apps.notifications.models import OperatorAlert
    from apps.notifications.services import emit_operator_alert

    severity = (
        OperatorAlert.SEVERITY_URGENT
        if (spike["imp_lift"] >= 2.0 or spike["clk_lift"] >= 2.0)
        else OperatorAlert.SEVERITY_WARNING
    )
    message = (
        f"'{item.title[:_TITLE_PREVIEW_LEN]}' — "
        f"impressions: +{spike['imp_delta']:.0f} "
        f"({spike['imp_lift'] * _PCT_MULTIPLIER:.0f}%), "
        f"clicks: +{spike['clk_delta']:.0f} "
        f"({spike['clk_lift'] * _PCT_MULTIPLIER:.0f}%). Review the Analytics page."
    )
    try:
        emit_operator_alert(
            event_type="analytics.gsc_spike", severity=severity,
            title="Google search demand spiked", message=message,
            source_area=OperatorAlert.AREA_ANALYTICS,
            dedupe_key=f"analytics.gsc_spike:{item.pk}:{today.isoformat()}",
            related_object_type="ContentItem",
            related_object_id=str(item.pk),
            related_route="/analytics",
            payload={
                "content_item_id": item.pk, "title": item.title,
                "impressions_delta": round(spike["imp_delta"], 1),
                "clicks_delta": round(spike["clk_delta"], 1),
                "impressions_lift_pct": round(spike["imp_lift"] * _PCT_MULTIPLIER, 1),
                "clicks_lift_pct": round(spike["clk_lift"] * _PCT_MULTIPLIER, 1),
            },
            cooldown_seconds=_GSC_SPIKE_COOLDOWN,  # 24-hour cooldown per page
        )
        return True
    except (ImportError, AttributeError, DatabaseError):
        logger.warning(
            "check_gsc_spikes: failed to emit alert for item %s",
            item.pk, exc_info=True,
        )
        return False


# ---------------------------------------------------------------------------
# FR-30 — FAISS-GPU index refresh
# ---------------------------------------------------------------------------


@shared_task(name="pipeline.refresh_faiss_index", time_limit=3600, soft_time_limit=3540)
@HelperConstraint(
    cpu_intensive=False,            # FAISS-GPU rebuild — GPU-bound
    gpu_required=True,
    storage_writes_to="postgres_main",
    ram_peak_mb=2048,
    expected_seconds_p50=300,
)
def refresh_faiss_index():
    """FR-30 — Rebuild FAISS-GPU index to pick up newly generated embeddings.

    Group B.3 — any rebuild failure routes to /error-log via
    ``ingest_error`` so the noob-friendly errors page shows the
    breakage with a plain-English why and how-to-fix instead of a
    silent stack trace in container logs. Re-raises so Celery's own
    retry/visibility mechanics still see the failure.
    """
    import traceback

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
            why=(
                "Periodic FAISS index rebuild failed. The pipeline will fall "
                "back to NumPy cosine search on the next query, which still "
                "works but is slower."
            ),
            severity=ErrorLog.SEVERITY_HIGH,
        )
        raise


# ---------------------------------------------------------------------------
# Group D.8 — Long-tail full-body re-embed backfill.
#
# After D.1 + D.2 ship, the embed source flips from the 5-sentence
# distilled summary to the full ``Post.clean_text``. Existing rows
# keep their old (truncated) vector until something triggers a
# re-embed. This task picks the highest-signal-loss candidates first
# — posts whose body is at least 5× the size of their distilled
# summary — and queues them in batches.
#
# Checkpointed via an AppSetting key so the task can resume after a
# laptop close mid-run. Operator runs via Django shell or a future
# admin button; not on Celery beat (one-shot work).
# ---------------------------------------------------------------------------

_BACKFILL_CHECKPOINT_KEY = "pipeline.backfill.long_tail_embeddings.last_pk"
_BACKFILL_BATCH_SIZE = 100


@shared_task(
    bind=True,
    name="pipeline.backfill_long_tail_embeddings",
    time_limit=3600,
    soft_time_limit=3540,
)
@HelperConstraint(
    gpu_required=True,            # BGE-M3 encode runs on GPU
    storage_writes_to="postgres_main",
    ram_peak_mb=4000,             # BGE-M3 fp16 + batch + working memory
    expected_seconds_p50=600,
)
@resource_aware_retry(
    max_retries=5,
    oom_batch_shrink_ratio=0.5,
    batch_size_kwarg="batch_size",
)
def backfill_long_tail_embeddings(
    self,
    *,
    body_to_distilled_ratio: float = 5.0,
    max_items: int | None = None,
    batch_size: int = _BACKFILL_BATCH_SIZE,
):
    """One-shot backfill: re-embed posts where the old summary lost the most signal.

    Plain-English: find posts whose full body is at least
    ``body_to_distilled_ratio`` times longer than the 5-sentence
    summary we used to embed (default 5.0 — the post lost ≥ 80 % of
    its content). Re-embed those first using the new full-body
    pipeline (Group D.1) and write the new ``embedding_text_hash``
    (Group D.2). The model signature filter inside
    ``generate_content_item_embeddings`` skips items already on the
    current model.

    Resumable: stores the last processed PK in AppSetting under
    ``pipeline.backfill.long_tail_embeddings.last_pk`` so a worker
    restart picks up where the previous run stopped — nothing is
    re-processed and nothing is lost.

    Bounded: ``max_items`` caps the run. ``None`` = process every
    eligible item until done.
    """
    last_pk = _read_backfill_checkpoint()
    eligible = _build_long_tail_eligible_qs(last_pk, body_to_distilled_ratio)
    processed = 0
    batch: list[int] = []
    for pk in eligible.iterator(chunk_size=batch_size):
        batch.append(pk)
        if len(batch) >= batch_size:
            processed += _flush_backfill_batch(batch)
            batch = []
            if max_items is not None and processed >= max_items:
                logger.info(
                    "[backfill_long_tail_embeddings] Stopping at max_items=%d; re-run to continue.",
                    max_items,
                )
                return {"processed": processed, "checkpointed": True}
    if batch:
        processed += _flush_backfill_batch(batch)
    logger.info(
        "[backfill_long_tail_embeddings] Complete. processed=%d", processed,
    )
    return {"processed": processed, "checkpointed": False}


def _read_backfill_checkpoint() -> int:
    """Resume PK from the AppSetting checkpoint (0 on first run)."""
    from apps.core.models import AppSetting
    setting = AppSetting.objects.filter(key=_BACKFILL_CHECKPOINT_KEY).first()
    return int(setting.value) if (setting and setting.value.isdigit()) else 0


def _build_long_tail_eligible_qs(last_pk: int, body_to_distilled_ratio: float):
    """Build the queryset of long-tail-eligible ContentItem PKs (PK > last_pk).

    Integer ratio for the SQL multiplication. Float ratios round toward zero
    (e.g. 5.5 → 5) but the high-signal-loss heuristic is robust to that ±1 fuzz.
    """
    from django.db.models import F
    from django.db.models.functions import Length
    from apps.content.models import ContentItem

    int_ratio = max(1, int(body_to_distilled_ratio))
    return (
        ContentItem.objects.filter(
            is_deleted=False, duplicate_of__isnull=True, pk__gt=last_pk,
        )
        .annotate(
            body_len=Length("post__clean_text"),
            distilled_len=Length("distilled_text"),
        )
        # Has a non-empty body and distilled summary; body is at least
        # int_ratio times the summary. Items without a Post row are excluded
        # because Length(NULL) is NULL and NULL > anything is false.
        .filter(
            distilled_len__gt=0,
            body_len__gt=F("distilled_len") * int_ratio,
        )
        .order_by("pk")
        .values_list("pk", flat=True)
    )


def _flush_backfill_batch(batch: list[int]) -> int:
    """Embed + chunk passages for one batch, persist the checkpoint, return batch size."""
    from apps.content.models import ContentItem
    from apps.core.models import AppSetting
    from apps.pipeline.services.embeddings import generate_content_item_embeddings
    from apps.pipeline.services.passage_relevance import regenerate_passage_embeddings_for

    # 1. Generate full-body document embeddings.
    generate_content_item_embeddings(content_item_ids=batch, force_reembed=True)
    # 2. Trigger passage chunking for the same batch (single fetch, no N+1).
    for item in ContentItem.objects.filter(pk__in=batch):
        regenerate_passage_embeddings_for(item)
    AppSetting.objects.update_or_create(
        key=_BACKFILL_CHECKPOINT_KEY,
        defaults={"value": str(batch[-1])},
    )
    return len(batch)


# ---------------------------------------------------------------------------
# Phase 0.0 — Catch-up re-embed for orphan rows nulled by a migration.
#
# Some schema migrations (e.g. ``content/0010_bge_m3_embedding_dim_1024``)
# legitimately null all embedding rows because the pgvector dimension
# changed. Without an automatic catch-up step, ``ContentItem.embedding``
# stays NULL on every affected row until something triggers a re-embed —
# silently degrading retrieval. This task closes that gap:
#
#   - Walks ContentItems with ``embedding IS NULL`` in PK order.
#   - Calls ``generate_content_item_embeddings`` for each batch (which
#     itself respects the existing skip-on-unchanged filter and writes
#     ``embedding_text_hash`` per Group D.2).
#   - Checkpoints the last completed PK so a restart resumes cleanly.
#   - Idempotent: a fresh DB or one with no orphans completes
#     immediately with ``processed=0``.
#
# Migrations that null embeddings should queue this task at the end of
# their RunPython block so the gap closes automatically. The catch-up
# migration ``content/0042_queue_orphan_reembed.py`` runs it once for
# any orphans that pre-date this fix.
# ---------------------------------------------------------------------------

_NULL_REEMBED_CHECKPOINT_KEY = "pipeline.reembed.null_embeddings.last_pk"
_NULL_REEMBED_BATCH_SIZE = 100


@shared_task(
    bind=True,
    name="pipeline.reembed_null_embeddings",
    time_limit=3600,
    soft_time_limit=3540,
)
@HelperConstraint(
    gpu_required=True,            # BGE-M3 encode runs on GPU
    storage_writes_to="postgres_main",
    ram_peak_mb=4000,
    expected_seconds_p50=300,
)
@resource_aware_retry(
    max_retries=5,
    oom_batch_shrink_ratio=0.5,
    batch_size_kwarg="batch_size",
)
def reembed_null_embeddings(
    self,
    *,
    batch_size: int = _NULL_REEMBED_BATCH_SIZE,
    max_items: int | None = None,
):
    """Re-embed ContentItems whose embedding was nulled (e.g. by a dim-change migration).

    Plain-English: walks every ContentItem whose embedding column is
    blank and re-runs the embed pipeline for it. The skip-on-unchanged
    filter in ``generate_content_item_embeddings`` automatically
    excludes anything that already has a current-signature vector, so
    calling this task on a healthy corpus is a fast no-op. Resumable
    via an AppSetting checkpoint key so a laptop close mid-run loses
    nothing.

    Args:
        batch_size: how many orphans to embed per checkpointed batch.
                    Default 100 matches the long-tail backfill.
        max_items: cap the run to this many items (None = process every
                   orphan until the queue is empty).

    Returns:
        Dict with ``processed`` and ``complete`` (False iff capped at max_items).
    """
    from apps.core.models import AppSetting

    last_pk = _read_checkpoint_pk(_NULL_REEMBED_CHECKPOINT_KEY)
    orphans = _build_null_embedding_orphan_qs(last_pk)
    processed = 0
    batch: list[int] = []
    for pk in orphans.iterator(chunk_size=batch_size):
        batch.append(pk)
        if len(batch) >= batch_size:
            processed += _flush_null_reembed_batch(batch)
            batch = []
            if max_items is not None and processed >= max_items:
                logger.info(
                    "[reembed_null_embeddings] Stopping at max_items=%d; re-run to continue.",
                    max_items,
                )
                return {"processed": processed, "complete": False}
    if batch:
        processed += _flush_null_reembed_batch(batch)
    # Reset checkpoint when complete so the next run starts from PK 0.
    AppSetting.objects.filter(key=_NULL_REEMBED_CHECKPOINT_KEY).delete()
    logger.info("[reembed_null_embeddings] Complete. processed=%d", processed)
    return {"processed": processed, "complete": True}


def _read_checkpoint_pk(key: str) -> int:
    """Read an integer PK checkpoint from AppSetting (0 on first run)."""
    from apps.core.models import AppSetting
    setting = AppSetting.objects.filter(key=key).first()
    return int(setting.value) if (setting and setting.value.isdigit()) else 0


def _build_null_embedding_orphan_qs(last_pk: int):
    """Queryset of ContentItem PKs whose embedding is NULL and PK > last_pk."""
    from apps.content.models import ContentItem
    return (
        ContentItem.objects.filter(
            embedding__isnull=True, is_deleted=False,
            duplicate_of__isnull=True, pk__gt=last_pk,
        )
        .order_by("pk")
        .values_list("pk", flat=True)
    )


def _flush_null_reembed_batch(batch: list[int]) -> int:
    """Embed one batch + persist the checkpoint; return batch size."""
    from apps.core.models import AppSetting
    from apps.pipeline.services.embeddings import generate_content_item_embeddings

    generate_content_item_embeddings(content_item_ids=batch)
    AppSetting.objects.update_or_create(
        key=_NULL_REEMBED_CHECKPOINT_KEY,
        defaults={"value": str(batch[-1])},
    )
    return len(batch)


# ---------------------------------------------------------------------------
# Group E / FR-053 — Passage-Level Relevance Scoring.
#
# Bounded periodic task that catches any ContentItem whose passage
# embeddings are missing or stale and regenerates them via the
# existing BGE-M3 model. Per-call cap keeps the GPU from starving
# other Heavy work; the next tick picks up the rest.
# ---------------------------------------------------------------------------

_PASSAGE_REFRESH_CHECKPOINT_KEY = "pipeline.passage_relevance.last_pk"
_PASSAGE_REFRESH_BATCH_SIZE = 100


@shared_task(
    bind=True,
    name="pipeline.refresh_passage_embeddings",
    time_limit=1800,
    soft_time_limit=1740,
)
@HelperConstraint(
    gpu_required=True,            # passage encode runs on GPU
    storage_writes_to="postgres_main",
    ram_peak_mb=3500,
    expected_seconds_p50=180,
)
@resource_aware_retry(
    max_retries=5,
    oom_batch_shrink_ratio=0.5,
    batch_size_kwarg="max_items",
)
def refresh_passage_embeddings(self, *, max_items: int = _PASSAGE_REFRESH_BATCH_SIZE):
    """Regenerate stale or missing PassageEmbedding rows in bounded batches.

    Plain-English: walks ContentItems in PK order from the last
    checkpoint, calls ``passage_relevance.regenerate_passage_embeddings_for``
    on each. The regenerator is itself idempotent — items already at
    the current text-hash + model signature do zero work. The
    checkpoint advances after every item so a worker restart resumes
    cleanly.

    Bounded by ``max_items`` so a single tick never holds the GPU
    longer than the soft time limit; the next beat tick picks up the
    rest. When the cursor wraps (no eligible rows past the
    checkpoint), the checkpoint resets to 0 so the next tick starts
    a fresh sweep.
    """
    from apps.core.models import AppSetting

    last_pk = _read_checkpoint_pk(_PASSAGE_REFRESH_CHECKPOINT_KEY)
    pks = _next_passage_refresh_batch(last_pk, max_items)
    if not pks:
        # Wrap the cursor — next tick starts from PK 0 again.
        AppSetting.objects.update_or_create(
            key=_PASSAGE_REFRESH_CHECKPOINT_KEY, defaults={"value": "0"},
        )
        return {"processed": 0, "wrapped": True}
    processed, embedded, last_seen = _embed_passages_for_pks(pks, last_pk)
    AppSetting.objects.update_or_create(
        key=_PASSAGE_REFRESH_CHECKPOINT_KEY,
        defaults={"value": str(last_seen)},
    )
    logger.info(
        "[refresh_passage_embeddings] processed=%d embedded=%d checkpoint=%d",
        processed, embedded, last_seen,
    )
    return {"processed": processed, "embedded": embedded, "wrapped": False}


def _next_passage_refresh_batch(last_pk: int, max_items: int) -> list[int]:
    """Pull the next ``max_items`` ContentItem PKs past ``last_pk``."""
    from apps.content.models import ContentItem
    return list(
        ContentItem.objects.filter(
            is_deleted=False, duplicate_of__isnull=True, pk__gt=last_pk,
        )
        .order_by("pk")
        .values_list("pk", flat=True)[:max_items]
    )


def _embed_passages_for_pks(pks: list[int], last_pk: int) -> tuple[int, int, int]:
    """Regenerate passages for each PK; advance checkpoint past failures."""
    from apps.content.models import ContentItem
    from apps.pipeline.services.passage_relevance import regenerate_passage_embeddings_for

    processed = 0
    embedded = 0
    last_seen = last_pk
    for pk in pks:
        try:
            item = ContentItem.objects.select_related("post").filter(pk=pk).first()
            if item is None:
                continue
            embedded += regenerate_passage_embeddings_for(item)
            processed += 1
        except Exception:
            logger.exception(
                "[refresh_passage_embeddings] failed for content_item=%s — "
                "skipping and advancing checkpoint",
                pk,
            )
        last_seen = pk
    return processed, embedded, last_seen

@shared_task(
    bind=True,
    name="passage_relevance.train_opq_codebook",
    time_limit=3600,
    soft_time_limit=3540,
)
@HelperConstraint(
    gpu_required=False,           # OPQ training is CPU-bound (k-means + rotation)
    cpu_intensive=True,
    storage_writes_to="postgres_main",
    ram_peak_mb=1500,             # ~400 MB sample @ 100k * 1024-d float32 + working memory
    expected_seconds_p50=900,
)
@resource_aware_retry(
    max_retries=4,
    oom_batch_shrink_ratio=0.5,
    batch_size_kwarg="sample_size",
)
def train_opq_codebook(self, *, sample_size: int = 100_000) -> dict:
    """Train OPQ codebooks periodically to adapt to corpus drift.

    Plain-English: OPQ training loads up to ``sample_size`` passage
    embeddings into RAM at once (~400 MB at sample_size=100k for 1024-d
    float32). On a 16 GB box that's safe; on a tight box it may OOM.
    The ``@resource_aware_retry`` decorator catches an OOM, halves
    ``sample_size`` to 50k, then 25k, and retries automatically. The
    last-OOM size is remembered in AppSetting so the next scheduled run
    starts at the smaller size without OOMing again.
    """
    from apps.pipeline.services.opq_trainer import train_codebook

    train_codebook(sample_size=sample_size)
    return {"status": "completed", "sample_size": sample_size}
