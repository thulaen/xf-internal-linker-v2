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
from json import JSONDecodeError
from requests import RequestException
from django.db import DatabaseError, IntegrityError
from urllib.error import URLError

logger = logging.getLogger(__name__)

_MAX_PAGES = 500
_MAX_BROKEN_LINK_SCAN_URLS = 10_000
_BROKEN_LINK_SCAN_DELAY_SECONDS = 0.1
_BROKEN_LINK_SCAN_TIMEOUT_SECONDS = 10

_RUNTIME_OWNER_OVERRIDE_BY_LANE = {
    "broken_link_scan": "RUNTIME_OWNER_BROKEN_LINK_SCAN",
    "graph_sync": "RUNTIME_OWNER_GRAPH_SYNC",
    "import": "RUNTIME_OWNER_IMPORT",
    "pipeline": "RUNTIME_OWNER_PIPELINE",
}


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


def _emit_job_alert(
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


def _runtime_owner_for_lane(lane: str) -> str:
    from django.conf import settings

    owner = getattr(
        settings, _RUNTIME_OWNER_OVERRIDE_BY_LANE.get(lane, ""), ""
    ) or getattr(
        settings,
        "HEAVY_RUNTIME_OWNER",
        "celery",
    )
    owner = str(owner).strip().lower()
    return owner if owner in {"celery", "csharp"} else "celery"


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
    """Persist checkpoint to SyncJob for crash-resilient resume (FR-097).

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


def _broken_link_scan_queue_payload() -> dict[str, Any]:
    from django.conf import settings

    return {
        "allowed_domains": _broken_link_allowed_domains(),
        "scan_cap": _MAX_BROKEN_LINK_SCAN_URLS,
        "batch_size": int(getattr(settings, "HTTP_WORKER_BROKEN_LINK_BATCH_SIZE", 250)),
        "timeout_seconds": _BROKEN_LINK_SCAN_TIMEOUT_SECONDS,
        "max_concurrency": int(
            getattr(settings, "HTTP_WORKER_BROKEN_LINK_MAX_CONCURRENCY", 50)
        ),
        "user_agent": "XF Internal Linker V2 Broken Link Scanner",
    }


def dispatch_broken_link_scan(job_id: str | None = None) -> dict[str, Any]:
    from apps.graph.services.http_worker_client import queue_job

    owner = _runtime_owner_for_lane("broken_link_scan")
    job_id = job_id or str(uuid.uuid4())
    if owner == "csharp":
        queue_job(
            job_id=job_id,
            job_type="broken_link_scan",
            payload=_broken_link_scan_queue_payload(),
        )
        return {
            "job_id": job_id,
            "message": "Broken link scan started.",
            "runtime_owner": "csharp",
        }

    scan_broken_links.delay(job_id=job_id)
    return {
        "job_id": job_id,
        "message": "Broken link scan started.",
        "runtime_owner": "celery",
    }


@shared_task(
    bind=True,
    name="pipeline.orchestrate_csharp_import",
    time_limit=7200,
    soft_time_limit=7140,
)
def orchestrate_csharp_import(
    self,
    scope_ids: list[int] | None = None,
    mode: str = "full",
    source: str = "api",
    file_path: str | None = None,
    job_id: str | None = None,
    force_reembed: bool = False,
) -> dict[str, Any]:
    """
    Orchestrator that runs the C# content import synchronously and then
    automatically triggers the Python ML enrichment (BGE-M3 and spaCy).
    """
    from apps.core.views import (
        get_graph_candidate_settings,
        get_silo_settings,
        get_wordpress_settings,
    )
    from apps.graph.services.http_worker_client import run_job
    from apps.sync.models import SyncJob

    job_id = job_id or str(uuid.uuid4())
    _publish_progress(
        job_id, "running", 0.0, f"Starting orchestrated C# {mode} import..."
    )

    payload = {
        "scope_ids": scope_ids or [],
        "mode": mode,
        "source": source,
        "file_path": file_path,
        "settings": {
            "silo": get_silo_settings(),
            "wordpress": get_wordpress_settings(),
            "graph_candidate": get_graph_candidate_settings(),
        },
    }

    try:
        # 1. Run C# Initial Ingest (Fast Path)
        results = run_job(
            job_id=job_id,
            job_type="import_content",
            payload=payload,
        )

        updated_pks = results.get("updated_pks", [])
        items_synced = results.get("items_synced", 0)

        # 1.5 Update SyncJob with ML info
        job = SyncJob.objects.filter(job_id=job_id).first()
        if job:
            job.ml_items_queued = len(updated_pks)
            job.items_synced = items_synced
            job.save(update_fields=["ml_items_queued", "items_synced", "updated_at"])

        # 2. spaCy NLP re-split + distillation (replaces C#'s regex sentences)
        if updated_pks:
            _publish_progress(
                job_id,
                "running",
                0.5,
                f"Running spaCy NLP enrichment for {len(updated_pks)} items...",
                ingest_progress=1.0,
                ml_progress=0.0,
                ml_items_queued=len(updated_pks),
                ml_items_completed=0,
            )
            from apps.content.models import ContentItem, Post, Sentence
            from apps.pipeline.services.distiller import distill_body
            from apps.pipeline.services.sentence_splitter import split_sentence_spans

            posts = (
                Post.objects.filter(content_item_id__in=updated_pks)
                .select_related("content_item")
                .only("id", "content_item_id", "clean_text")
            )
            new_sentences: list[Sentence] = []
            distilled: dict[int, str] = {}  # content_item_id → distilled_text

            total_spacy = posts.count()
            for index, post in enumerate(posts):
                clean = (post.clean_text or "").strip()
                if not clean:
                    continue
                spans = split_sentence_spans(clean)
                word_offset = 0
                for span in spans:
                    new_sentences.append(
                        Sentence(
                            content_item_id=post.content_item_id,
                            post_id=post.id,
                            text=span.text,
                            position=span.position,
                            start_char=span.start_char,
                            end_char=span.end_char,
                            char_count=len(span.text),
                            word_position=word_offset,
                        )
                    )
                    word_offset += len(span.text.split())
                distilled[post.content_item_id] = distill_body([s.text for s in spans])

                # Granular progress update
                if index % 20 == 0 or index == total_spacy - 1:
                    sp_pct = (index + 1) / total_spacy
                    if job:
                        job.spacy_items_completed = index + 1
                        job.save(update_fields=["spacy_items_completed", "updated_at"])
                    # FR-097: checkpoint during spaCy stage (every 20 items)
                    _save_checkpoint(
                        str(job_id), "spacy", post.content_item_id, index + 1
                    )
                    _publish_progress(
                        job_id,
                        "running",
                        0.5 + (sp_pct * 0.2),
                        f"SpaCy processing: {index + 1}/{total_spacy} items...",
                        spacy_progress=sp_pct,
                        ml_progress=sp_pct * 0.5,
                        ml_items_queued=total_spacy,
                        ml_items_completed=index + 1,
                    )

            # Atomically swap sentences: delete C# regex rows, insert spaCy rows.
            # The atomic block guarantees that if bulk_create fails mid-way, the
            # delete is rolled back and items are never left sentence-less.
            from django.db import transaction

            with transaction.atomic():
                Sentence.objects.filter(content_item_id__in=updated_pks).delete()
                Sentence.objects.bulk_create(new_sentences, batch_size=500)

            # Persist spaCy-quality distilled text on each ContentItem
            if distilled:
                ci_objs = ContentItem.objects.filter(id__in=list(distilled.keys()))
                for ci in ci_objs:
                    ci.distilled_text = distilled[ci.id]
                ContentItem.objects.bulk_update(
                    ci_objs, ["distilled_text"], batch_size=200
                )

        # 3. Trigger Python ML Enrichment (BGE-M3 embeddings)
        if updated_pks:
            _publish_progress(
                job_id,
                "running",
                0.9,
                f"spaCy done; triggering BGE-M3 embeddings for {len(updated_pks)} items...",
                ingest_progress=1.0,
                ml_progress=0.0,
                ml_items_queued=len(updated_pks),
                ml_items_completed=0,
            )
            generate_embeddings.delay(
                content_item_ids=updated_pks, job_id=job_id, force_reembed=force_reembed
            )

        _publish_progress(
            job_id,
            "completed" if not updated_pks else "running",
            1.0 if not updated_pks else 0.9,
            f"Sync complete: {items_synced} items imported and queued for ML.",
            ingest_progress=1.0,
            ml_progress=1.0 if not updated_pks else 0.0,
        )

        return {
            "job_id": job_id,
            "items_synced": items_synced,
            "ml_enrichment_queued": len(updated_pks),
            "runtime_owner": "csharp",
        }
    except (DatabaseError, TimeoutError, MemoryError, ValueError) as exc:
        logger.exception("Orchestrated C# import %s failed", job_id)
        _publish_progress(
            job_id, "failed", 0.0, f"Orchestration failed: {exc}", error=str(exc)
        )
        raise


def dispatch_import_content(
    *,
    scope_ids: list[int] | None = None,
    mode: str = "full",
    source: str = "api",
    file_path: str | None = None,
    job_id: str | None = None,
    force_reembed: bool = False,
) -> dict[str, Any]:
    owner = _runtime_owner_for_lane("import")
    job_id = job_id or str(uuid.uuid4())

    if owner == "csharp":
        orchestrate_csharp_import.delay(
            scope_ids=scope_ids,
            mode=mode,
            source=source,
            file_path=file_path,
            job_id=job_id,
            force_reembed=force_reembed,
        )
        return {
            "job_id": job_id,
            "runtime_owner": "csharp",
            "message": f"{source} import orchestrated (Fast Ingest -> ML Enrichment).",
        }

    import_content.delay(
        scope_ids=scope_ids,
        mode=mode,
        source=source,
        file_path=file_path,
        job_id=job_id,
        force_reembed=force_reembed,
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
    bind=True, name="pipeline.run_pipeline", time_limit=7200, soft_time_limit=7140
)
def run_pipeline(
    self,
    run_id: str,
    host_scope: dict,
    destination_scope: dict,
    rerun_mode: str = "skip_pending",
) -> dict:
    """Execute the full 3-stage ML suggestion pipeline."""
    from apps.suggestions.models import PipelineRun

    job_id = run_id
    try:
        run = PipelineRun.objects.get(run_id=run_id)
        run.run_state = "running"
        run.celery_task_id = self.request.id or ""
        run.save(update_fields=["run_state", "celery_task_id", "updated_at"])
    except PipelineRun.DoesNotExist:
        logger.error("PipelineRun %s not found", run_id)
        return {"error": "PipelineRun not found"}

    started_at = time.monotonic()

    def _progress(pct: float, msg: str) -> None:
        _publish_progress(job_id, "running", pct, msg)

    try:
        from apps.pipeline.services.pipeline import run_pipeline as _run

        destination_scope_ids = (
            set(destination_scope["scope_ids"])
            if destination_scope and "scope_ids" in destination_scope
            else None
        )
        destination_content_item_ids = (
            set(destination_scope["content_item_ids"])
            if destination_scope and "content_item_ids" in destination_scope
            else None
        )
        host_scope_ids = (
            set(host_scope["scope_ids"])
            if host_scope and "scope_ids" in host_scope
            else None
        )
        result = _run(
            run_id=run_id,
            rerun_mode=rerun_mode,
            destination_scope_ids=destination_scope_ids,
            destination_content_item_ids=destination_content_item_ids,
            host_scope_ids=host_scope_ids,
            progress_fn=_progress,
        )
        duration = time.monotonic() - started_at
        run.run_state = "completed"
        run.suggestions_created = result.suggestions_created
        run.destinations_processed = result.items_in_scope
        run.destinations_skipped = result.destinations_skipped
        run.duration_seconds = duration
        run.save(
            update_fields=[
                "run_state",
                "suggestions_created",
                "destinations_processed",
                "destinations_skipped",
                "duration_seconds",
                "updated_at",
            ]
        )
        _publish_progress(
            job_id,
            "completed",
            1.0,
            "Pipeline complete.",
            suggestions_created=result.suggestions_created,
            destinations_processed=result.items_in_scope,
        )
        # FR-025: compute value model scores (including co-occurrence signal) post-pipeline
        try:
            from apps.cooccurrence.tasks import apply_value_model_scores

            apply_value_model_scores.delay(run_id)
        except (ImportError, AttributeError):
            logger.warning(
                "apply_value_model_scores could not be queued for run %s", run_id
            )
        _emit_job_alert(
            "job.completed",
            "success",
            "Pipeline job completed",
            f"Pipeline finished. {result.suggestions_created} suggestions created from {result.items_in_scope} destinations.",
            job_id=job_id,
            job_type="pipeline",
        )
        return {
            "run_id": run_id,
            "state": "completed",
            "suggestions_created": result.suggestions_created,
            "items_in_scope": result.items_in_scope,
            "duration_seconds": round(duration, 2),
        }
    except (DatabaseError, TimeoutError, MemoryError, ValueError) as exc:
        logger.exception("Pipeline run %s failed", run_id)
        run.run_state = "failed"
        run.error_message = str(exc)
        run.duration_seconds = time.monotonic() - started_at
        run.save(
            update_fields=[
                "run_state",
                "error_message",
                "duration_seconds",
                "updated_at",
            ]
        )
        _publish_progress(
            job_id, "failed", 0.0, f"Pipeline failed: {exc}", error=str(exc)
        )
        _emit_job_alert(
            "job.failed",
            "error",
            "Pipeline job failed",
            f"The pipeline run stopped with an error: {exc}",
            job_id=job_id,
            job_type="pipeline",
        )
        raise


@shared_task(
    bind=True,
    name="pipeline.generate_embeddings",
    time_limit=7200,
    soft_time_limit=7140,
)
def generate_embeddings(
    self,
    content_item_ids: list[int] | None = None,
    job_id: str | None = None,
    force_reembed: bool = False,
) -> dict:
    """Generate and store embeddings for ContentItems and Sentences."""
    from django.utils import timezone
    from apps.sync.models import SyncJob
    from apps.pipeline.services.embeddings import generate_all_embeddings

    job_id = job_id or str(uuid.uuid4())
    count_label = len(content_item_ids) if content_item_ids is not None else "all"
    job = SyncJob.objects.filter(job_id=job_id).first()

    _publish_progress(
        job_id,
        "running",
        0.8,
        f"Generating embeddings for {count_label} items...",
        ingest_progress=1.0,
        ml_progress=0.7,
        embedding_progress=0.0,
    )
    try:
        # The service now handles granular progress reporting if job_id is provided
        stats = generate_all_embeddings(
            content_item_ids, job_id=job_id, force_reembed=force_reembed
        )

        # Rebuild FAISS index so new embeddings are available immediately
        # without waiting for the 15-minute periodic refresh.
        try:
            from apps.pipeline.services.faiss_index import build_faiss_index

            build_faiss_index()
        except (ImportError, MemoryError, FileNotFoundError):
            logger.warning("FAISS index rebuild after embeddings failed", exc_info=True)

        if job:
            job.status = "completed"
            job.completed_at = timezone.now()
            job.progress = 1.0
            job.save(update_fields=["status", "completed_at", "progress", "updated_at"])

        _publish_progress(
            job_id,
            "completed",
            1.0,
            f"ML Enrichment complete. {stats['content_items_embedded']} items embedded.",
            ingest_progress=1.0,
            ml_progress=1.0,
            embedding_progress=1.0,
            **stats,
        )
        _emit_job_alert(
            "job.completed",
            "success",
            "Embedding job completed",
            f"ML Enrichment complete. {stats['content_items_embedded']} items, {stats['sentences_embedded']} sentences embedded.",
            job_id=job_id,
            job_type="embed",
        )
        return {"job_id": job_id, **stats}
    except (MemoryError, TimeoutError, RuntimeError) as exc:
        logger.exception("Embedding job %s failed", job_id)
        if job:
            job.status = "failed"
            job.error_message = str(exc)
            job.save(update_fields=["status", "error_message", "updated_at"])

        _publish_progress(
            job_id,
            "failed",
            0.0,
            f"Embeddings failed: {exc}",
            error=str(exc),
            ingest_progress=1.0,
            ml_progress=0.0,
        )
        _emit_job_alert(
            "job.failed",
            "error",
            "Embedding job failed",
            f"The embedding run stopped with an error: {exc}",
            job_id=job_id,
            job_type="embed",
        )
        raise


@shared_task(
    bind=True,
    name="pipeline.recalculate_weighted_authority",
    time_limit=1800,
    soft_time_limit=1740,
)
def recalculate_weighted_authority(self, job_id: str | None = None) -> dict:
    """Recompute March 2026 PageRank from the stored graph and current settings."""
    job_id = job_id or str(uuid.uuid4())
    _publish_progress(
        job_id, "running", 0.0, "Starting March 2026 PageRank recalculation..."
    )

    try:
        from apps.pipeline.services.weighted_pagerank import run_weighted_pagerank

        diagnostics = run_weighted_pagerank()
        _publish_progress(
            job_id,
            "completed",
            1.0,
            "March 2026 PageRank recalculation complete.",
            **diagnostics,
        )
        return {"job_id": job_id, **diagnostics}
    except (DatabaseError, TimeoutError, MemoryError, ValueError) as exc:
        logger.exception("March 2026 PageRank recalculation %s failed", job_id)
        _publish_progress(
            job_id,
            "failed",
            0.0,
            f"March 2026 PageRank recalculation failed: {exc}",
            error=str(exc),
        )
        raise


@shared_task(
    bind=True,
    name="pipeline.recalculate_link_freshness",
    time_limit=1800,
    soft_time_limit=1740,
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
    from apps.graph.services.http_worker_client import queue_job

    owner = _runtime_owner_for_lane("graph_sync")
    job_id = job_id or str(uuid.uuid4())
    if owner == "csharp":
        from apps.core.views import get_graph_candidate_settings

        queue_job(
            job_id=job_id,
            job_type="graph_sync_refresh",
            payload={
                "settings": {
                    "graph_candidate": get_graph_candidate_settings(),
                }
            },
        )
        return {
            "job_id": job_id,
            "message": "Knowledge graph rebuild started.",
            "runtime_owner": "csharp",
        }

    build_knowledge_graph.delay(job_id=job_id)
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
    bind=True, name="pipeline.import_content", time_limit=7200, soft_time_limit=7140
)
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
    from django.utils import timezone

    from apps.pipeline.tasks_import import (
        ImportState,
        import_jsonl_content,
        import_wordpress_content,
        import_xenforo_scopes,
        run_post_import_steps,
        update_scope_counts,
    )
    from apps.sync.models import SyncJob

    job_id = job_id or str(uuid.uuid4())
    job, created = SyncJob.objects.get_or_create(
        job_id=job_id,
        defaults={
            "source": source,
            "mode": mode,
            "status": "running",
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
        job_id=job_id,
        source=source,
        mode=mode,
        force_reembed=force_reembed,
    )

    # ── FR-097: Resume from checkpoint if the job was previously interrupted ──
    if job.is_resumable and job.checkpoint_stage and job.checkpoint_last_item_id:
        state.resume_last_item_id = job.checkpoint_last_item_id
        state.resume_stage = job.checkpoint_stage
        logger.info(
            "Resuming import job %s from checkpoint: stage=%s, last_item_id=%d, items_processed=%d",
            job_id,
            state.resume_stage,
            state.resume_last_item_id,
            job.checkpoint_items_processed,
        )
        _publish_progress(
            job_id,
            "running",
            0.0,
            f"Resuming {mode} import from checkpoint (stage={state.resume_stage}, "
            f"after item {state.resume_last_item_id})...",
        )
        SyncJob.objects.filter(job_id=job_id).update(is_resumable=False)
    else:
        _publish_progress(
            job_id, "running", 0.0, f"Starting {mode} content import from {source}..."
        )

    try:
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

        update_scope_counts(state.touched_scope_ids)
        run_post_import_steps(state, job_id, _publish_progress)

        # FR-097: Clear checkpoint on successful completion.
        SyncJob.objects.filter(job_id=job_id).update(
            checkpoint_stage="",
            checkpoint_last_item_id=None,
            checkpoint_items_processed=0,
            is_resumable=False,
        )

        job.status = "completed"
        job.progress = 1.0
        job.completed_at = timezone.now()
        job.items_synced = state.items_synced
        job.items_updated = state.items_updated
        job.message = f"Import complete. {state.items_synced} synced, {state.items_updated} updated."
        job.save(
            update_fields=[
                "status",
                "progress",
                "completed_at",
                "items_synced",
                "items_updated",
                "message",
            ]
        )
        _publish_progress(
            job_id,
            "completed",
            1.0,
            f"Content import complete ({source}). {state.items_synced} items synced, {state.items_updated} updated.",
        )
        _emit_job_alert(
            "job.completed",
            "success",
            "Import job completed",
            f"Content import finished. {state.items_synced} items synced, {state.items_updated} updated.",
            job_id=job_id,
            job_type="import",
        )
        return {
            "mode": mode,
            "job_id": job_id,
            "items_synced": state.items_synced,
            "items_updated": state.items_updated,
        }
    except SoftTimeLimitExceeded:
        logger.warning(
            "Import job %s hit soft time limit; marking as resumable.", job_id
        )
        try:
            SyncJob.objects.filter(job_id=job_id).update(
                is_resumable=True,
                status="failed",
                error_message="Soft time limit exceeded -- job is resumable from checkpoint.",
            )
        except Exception:
            logger.debug("Failed to mark job %s as resumable", job_id, exc_info=True)
        _publish_progress(
            job_id,
            "failed",
            0.0,
            "Import interrupted (time limit). Job is resumable.",
            error="SoftTimeLimitExceeded",
        )
        raise
    except (DatabaseError, TimeoutError, MemoryError, ValueError) as exc:
        logger.exception("Import job %s failed", job_id)
        _has_checkpoint = bool(state.updated_pks)
        job.status = "failed"
        job.error_message = str(exc)
        job.completed_at = timezone.now()
        if _has_checkpoint:
            job.is_resumable = True
        job.save(
            update_fields=["status", "error_message", "completed_at", "is_resumable"]
        )
        _publish_progress(
            job_id, "failed", 0.0, f"Import failed: {exc}", error=str(exc)
        )
        _emit_job_alert(
            "job.failed",
            "error",
            "Import job failed",
            f"The content import stopped with an error: {exc}",
            job_id=job_id,
            job_type="import",
        )
        raise


def _get_broken_link_scan_http_worker_batch_size() -> int:
    from django.conf import settings

    raw_value = getattr(settings, "HTTP_WORKER_BROKEN_LINK_BATCH_SIZE", 250)
    try:
        return min(max(int(raw_value), 1), 1000)
    except (TypeError, ValueError):
        logger.warning(
            "Invalid HTTP_WORKER_BROKEN_LINK_BATCH_SIZE value %r; using %d.",
            raw_value,
            250,
        )
        return 250


def _iter_broken_link_scan_batches(
    scan_items: list[dict[str, Any]],
    batch_size: int,
):
    for start in range(0, len(scan_items), batch_size):
        yield scan_items[start : start + batch_size]


def _check_broken_links_via_http_worker(
    scan_items: list[dict[str, Any]],
) -> dict[tuple[int, str], tuple[int, str]]:
    from apps.graph.services.http_worker_client import (
        HttpWorkerError,
        check_broken_links,
    )

    batch_size = _get_broken_link_scan_http_worker_batch_size()
    checked_results: dict[tuple[int, str], tuple[int, str]] = {}

    for batch in _iter_broken_link_scan_batches(scan_items, batch_size):
        request_items = [
            {
                "source_content_id": int(item["source_content_id"]),
                "url": str(item["url"]),
            }
            for item in batch
        ]
        expected_keys = {
            (item["source_content_id"], item["url"]) for item in request_items
        }
        batch_results = check_broken_links(request_items)
        batch_map: dict[tuple[int, str], tuple[int, str]] = {}

        for row in batch_results:
            source_content_id = int(row.get("source_content_id") or 0)
            url = str(row.get("url") or "").strip()
            if source_content_id <= 0 or not url:
                raise HttpWorkerError(
                    "HttpWorker returned an invalid broken-link result row."
                )

            key = (source_content_id, url)
            if key not in expected_keys:
                raise HttpWorkerError(
                    "HttpWorker returned an unexpected broken-link result row."
                )

            batch_map[key] = (
                int(row.get("http_status") or 0),
                str(row.get("redirect_url") or ""),
            )

        missing_keys = expected_keys.difference(batch_map)
        if missing_keys:
            raise HttpWorkerError(
                "HttpWorker returned an incomplete broken-link result batch."
            )

        checked_results.update(batch_map)

    return checked_results


@shared_task(
    bind=True,
    name="pipeline.scan_broken_links",
    queue="default",
    time_limit=7200,
    soft_time_limit=7140,
)
def scan_broken_links(self, job_id: str | None = None) -> dict:
    """Scan live URLs referenced in content and persist broken-link findings."""
    from django.conf import settings
    from django.utils import timezone

    from apps.graph.services.http_worker_client import HttpWorkerError
    from apps.pipeline.tasks_broken_links import (
        build_existing_records_map,
        collect_urls_to_scan,
        persist_scan_results,
        scan_via_http_worker,
        scan_via_python_requests,
    )

    job_id = job_id or str(uuid.uuid4())
    _publish_progress(job_id, "running", 0.0, "Collecting URLs for broken-link scan...")

    urls_to_scan, hit_scan_cap = collect_urls_to_scan()
    total_urls = len(urls_to_scan)
    if total_urls == 0:
        _publish_progress(job_id, "completed", 1.0, "No URLs found to scan.")
        return {"job_id": job_id, "scanned_urls": 0, "flagged_urls": 0, "fixed_urls": 0}

    _publish_progress(
        job_id,
        "running",
        0.02,
        f"Scanning {total_urls} URL(s) for link health...",
        total_urls=total_urls,
        hit_scan_cap=hit_scan_cap,
    )

    checked_at = timezone.now()
    scan_items = list(urls_to_scan.values())
    existing_records = build_existing_records_map(urls_to_scan)
    to_create: list = []
    to_update: list = []
    probe_backend = "python_requests"
    http_worker_error = ""
    flagged_urls = 0
    fixed_urls = 0

    if getattr(settings, "HTTP_WORKER_ENABLED", False):
        try:
            flagged_urls, fixed_urls, probe_backend = scan_via_http_worker(
                scan_items,
                job_id=job_id,
                total_urls=total_urls,
                existing_records=existing_records,
                to_create=to_create,
                to_update=to_update,
                checked_at=checked_at,
                hit_scan_cap=hit_scan_cap,
            )
        except (
            TimeoutError,
            RequestException,
            URLError,
            RuntimeError,
            HttpWorkerError,
        ) as exc:
            http_worker_error = str(exc)
            probe_backend = "python_requests_fallback"
            logger.warning("HttpWorker broken-link scan fallback engaged: %s", exc)

    if probe_backend != "csharp_http_worker":
        flagged_urls, fixed_urls = scan_via_python_requests(
            scan_items,
            job_id=job_id,
            total_urls=total_urls,
            existing_records=existing_records,
            to_create=to_create,
            to_update=to_update,
            checked_at=checked_at,
            hit_scan_cap=hit_scan_cap,
            probe_backend=probe_backend,
            http_worker_error=http_worker_error,
        )

    persist_scan_results(to_create, to_update)

    completion_message = (
        f"Broken link scan complete. {flagged_urls} issue(s) flagged, "
        f"{fixed_urls} previously flagged link(s) resolved."
    )
    if hit_scan_cap:
        completion_message += (
            f" Scan stopped at the {_MAX_BROKEN_LINK_SCAN_URLS:,} URL safety cap."
        )
    _publish_progress(
        job_id,
        "completed",
        1.0,
        completion_message,
        scanned_urls=total_urls,
        total_urls=total_urls,
        flagged_urls=flagged_urls,
        fixed_urls=fixed_urls,
        hit_scan_cap=hit_scan_cap,
        probe_backend=probe_backend,
        http_worker_error=http_worker_error,
    )
    return {
        "job_id": job_id,
        "scanned_urls": total_urls,
        "flagged_urls": flagged_urls,
        "fixed_urls": fixed_urls,
        "hit_scan_cap": hit_scan_cap,
        "probe_backend": probe_backend,
        "http_worker_error": http_worker_error or None,
    }


@shared_task(
    bind=True, name="pipeline.verify_suggestions", time_limit=3600, soft_time_limit=3540
)
def verify_suggestions(self, suggestion_ids: list[str] | None = None) -> dict:
    """Check whether applied suggestions are still live via XenForo API."""
    from django.utils import timezone

    from apps.suggestions.models import Suggestion
    from apps.sync.services.xenforo_api import XenForoAPIClient

    job_id = str(uuid.uuid4())
    _publish_progress(job_id, "running", 0.0, "Starting verification...")

    client = XenForoAPIClient()
    suggestions = Suggestion.objects.filter(status="applied")
    if suggestion_ids:
        suggestions = suggestions.filter(pk__in=suggestion_ids)

    total = suggestions.count()
    if total == 0:
        _publish_progress(job_id, "completed", 1.0, "No applied suggestions to verify.")
        return {"verified": 0, "stale": 0, "job_id": job_id}

    verified = 0
    stale = 0
    try:
        for index, suggestion in enumerate(suggestions):
            _publish_progress(
                job_id,
                "running",
                index / total,
                f"Checking suggestion {str(suggestion.suggestion_id)[:8]}...",
            )
            host_content = suggestion.host
            if not host_content or not host_content.xf_post_id:
                logger.warning(
                    "Suggestion %s host has no xf_post_id", suggestion.suggestion_id
                )
                continue
            try:
                raw_bbcode = (
                    client.get_post(host_content.xf_post_id)
                    .get("post", {})
                    .get("message", "")
                )
                destination_url = suggestion.destination.url
                if not destination_url:
                    logger.warning(
                        "Suggestion %s destination has no URL", suggestion.suggestion_id
                    )
                    continue
                if destination_url in raw_bbcode:
                    suggestion.status = "verified"
                    suggestion.verified_at = timezone.now()
                    suggestion.save(
                        update_fields=["status", "verified_at", "updated_at"]
                    )
                    verified += 1
                else:
                    suggestion.status = "stale"
                    suggestion.stale_reason = "Link not found in host post body"
                    suggestion.save(
                        update_fields=["status", "stale_reason", "updated_at"]
                    )
                    stale += 1
            except (TimeoutError, RequestException, URLError) as exc:
                logger.error(
                    "Failed to fetch host post for suggestion %s: %s",
                    suggestion.suggestion_id,
                    exc,
                )
                continue

        _publish_progress(
            job_id,
            "completed",
            1.0,
            f"Verification complete. {verified} verified, {stale} stale.",
        )
        return {"verified": verified, "stale": stale, "job_id": job_id}
    except (DatabaseError, TimeoutError, MemoryError, ValueError) as exc:
        logger.exception("Verification %s failed", job_id)
        _publish_progress(
            job_id, "failed", 0.0, f"Verification failed: {exc}", error=str(exc)
        )
        raise


@shared_task(
    bind=True,
    name="pipeline.recalculate_click_distance",
    time_limit=1800,
    soft_time_limit=1740,
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


def _get_broken_link_scan_delay_seconds() -> float:
    from django.conf import settings

    raw_value = getattr(
        settings, "BROKEN_LINK_SCAN_DELAY_SECONDS", _BROKEN_LINK_SCAN_DELAY_SECONDS
    )
    try:
        return max(0.0, float(raw_value))
    except (TypeError, ValueError):
        logger.warning(
            "Invalid BROKEN_LINK_SCAN_DELAY_SECONDS value %r; using %.2f seconds.",
            raw_value,
            _BROKEN_LINK_SCAN_DELAY_SECONDS,
        )
        return _BROKEN_LINK_SCAN_DELAY_SECONDS


@shared_task(name="pipeline.run_clustering_pass", time_limit=1800, soft_time_limit=1740)
def run_clustering_pass(job_id: str | None = None) -> dict:
    """Run a batch clustering pass over all ContentItems with embeddings."""
    from apps.content.models import ContentItem
    from apps.content.services.clustering import ClusteringService

    if not job_id:
        job_id = f"clustering_{int(time.time())}"

    logger.info("Starting batch clustering pass [%s]", job_id)
    _publish_progress(job_id, "running", 0.0, "Starting batch clustering pass...")

    # Filter items that have embeddings
    items = ContentItem.objects.filter(embedding__isnull=False).only(
        "id", "embedding", "cluster_id"
    )
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
# Part 6 — Monthly R auto-tune task
# ---------------------------------------------------------------------------


@shared_task(bind=True, name="pipeline.monthly_r_auto_tune")
def monthly_r_auto_tune(self):
    """Monthly auto-tune of ranking weights from R analytics.

    Scheduled at 02:00 on the first Sunday of every month
    (crontab(hour=2, minute=0, day_of_week=0, day_of_month='1-7')).

    Phase 21 stub: step 1 (call R analytics to get candidate weights) is a
    no-op until the R analytics service returns candidate weights.  Only step 1
    needs to be filled in for FR-018 — everything else (threshold comparison,
    atomic write, history row, error logging) is already wired.
    """
    import traceback

    from apps.audit.models import ErrorLog
    from apps.suggestions.weight_preset_service import (
        apply_weights,
        get_current_weights,
        write_history,
    )

    CHANGE_THRESHOLD = 0.02  # Will be superseded by FR-018 spec value.

    try:
        # ── Step 1: call R analytics for candidate weights ─────────────────
        # STUB: R analytics service not yet available (FR-018).
        # Replace this block with the real R API call in Phase 21.
        # The return format must be dict[str, str] matching PRESET_DEFAULTS keys.
        candidate_weights: dict[str, str] | None = None  # noqa: F841

        if candidate_weights is None:
            logger.info("[monthly_r_auto_tune] R analytics not available yet — no-op.")
            return {
                "status": "skipped",
                "reason": "R analytics stub — no candidate weights returned.",
            }

        # ── Step 2: compare candidate to current weights ───────────────────
        current_weights = get_current_weights()
        changed_keys = {
            k
            for k, v in candidate_weights.items()
            if abs(float(v) - float(current_weights.get(k, v))) > CHANGE_THRESHOLD
        }
        if not changed_keys:
            logger.info(
                "[monthly_r_auto_tune] Candidate weights within threshold — no change applied."
            )
            return {"status": "no_change"}

        # ── Step 3: apply new weights atomically ───────────────────────────
        from django.db import transaction

        previous_weights = get_current_weights()
        with transaction.atomic():
            apply_weights(candidate_weights)
        new_weights = get_current_weights()

        # ── Step 4: write history row ──────────────────────────────────────
        r_run_id = str(getattr(self.request, "id", "") or "")
        write_history(
            source="r_auto",
            previous_weights=previous_weights,
            new_weights=new_weights,
            reason="Monthly R auto-tune",
            r_run_id=r_run_id,
        )

        logger.info(
            "[monthly_r_auto_tune] Applied new weights for %d key(s): %s",
            len(changed_keys),
            ", ".join(sorted(changed_keys)),
        )
        return {"status": "applied", "changed_keys": sorted(changed_keys)}

    except (DatabaseError, TimeoutError, MemoryError, ValueError):
        raw = traceback.format_exc()
        logger.exception("[monthly_r_auto_tune] Failed: %s", raw)
        ErrorLog.objects.create(
            job_type="auto_tune_weights",
            step="monthly_r_auto_tune",
            error_message="R auto-tune task failed — see raw_exception for details.",
            raw_exception=raw,
            why="The monthly R analytics auto-tune task raised an unexpected exception. Check the R analytics service.",
        )
        return {"status": "error"}


# ---------------------------------------------------------------------------
# Part 7 — Nightly data retention task
# ---------------------------------------------------------------------------


@shared_task(
    name="pipeline.nightly_data_retention", time_limit=1800, soft_time_limit=1740
)
def nightly_data_retention():
    """Purge stale data rows according to the retention policy.

    Scheduled daily at 03:00 UTC.

    Retention policy:
        SearchMetric rows           — 12 months
        PipelineRun logs            — 90 days
        ContentMetricSnapshot       — keep last 2 per item
        Superseded Suggestions      — 30 days
        AuditEntry                  — 6 months (180 days)
        ErrorLog                    — 30 days
        WebhookReceipt              — 30 days
        ImpactReport                — FOREVER (never purged)
        Suggestion (non-superseded) — FOREVER (never purged)
        WeightAdjustmentHistory     — FOREVER (never purged)
    """
    import traceback
    from datetime import timedelta

    from django.utils import timezone

    from apps.audit.models import ErrorLog

    now = timezone.now()
    results: dict[str, int] = {}

    try:
        from apps.analytics.models import SearchMetric

        cutoff_12m = now - timedelta(days=365)
        deleted, _ = SearchMetric.objects.filter(date__lt=cutoff_12m.date()).delete()
        results["search_metrics_deleted"] = deleted
        logger.info(
            "[nightly_data_retention] Deleted %d SearchMetric rows older than 12 months.",
            deleted,
        )
    except (DatabaseError, IntegrityError):
        raw = traceback.format_exc()
        logger.exception("[nightly_data_retention] SearchMetric purge failed.")
        ErrorLog.objects.create(
            job_type="data_retention",
            step="search_metric_purge",
            error_message="SearchMetric retention purge failed.",
            raw_exception=raw,
            why="Check database connectivity and the analytics.SearchMetric table.",
        )

    try:
        from apps.suggestions.models import PipelineRun

        cutoff_90d = now - timedelta(days=90)
        deleted, _ = PipelineRun.objects.filter(created_at__lt=cutoff_90d).delete()
        results["pipeline_runs_deleted"] = deleted
        logger.info(
            "[nightly_data_retention] Deleted %d PipelineRun rows older than 90 days.",
            deleted,
        )
    except (DatabaseError, IntegrityError):
        raw = traceback.format_exc()
        logger.exception("[nightly_data_retention] PipelineRun purge failed.")
        ErrorLog.objects.create(
            job_type="data_retention",
            step="pipeline_run_purge",
            error_message="PipelineRun retention purge failed.",
            raw_exception=raw,
            why="Check database connectivity and the suggestions.PipelineRun table.",
        )

    try:
        from apps.pipeline.services.velocity import prune_old_snapshots

        deleted = prune_old_snapshots(keep=2)
        results["metric_snapshots_deleted"] = deleted
        logger.info(
            "[nightly_data_retention] Deleted %d ContentMetricSnapshot rows (keeping last 2 per item).",
            deleted,
        )
    except (DatabaseError, IntegrityError):
        raw = traceback.format_exc()
        logger.exception("[nightly_data_retention] ContentMetricSnapshot purge failed.")
        ErrorLog.objects.create(
            job_type="data_retention",
            step="metric_snapshot_purge",
            error_message="ContentMetricSnapshot retention purge failed.",
            raw_exception=raw,
            why="Check database connectivity and the content.ContentMetricSnapshot table.",
        )

    # --- Superseded suggestions: 30 days ---
    try:
        from apps.suggestions.models import Suggestion

        cutoff_30d = now - timedelta(days=30)
        deleted, _ = Suggestion.objects.filter(
            status="superseded", updated_at__lt=cutoff_30d
        ).delete()
        results["superseded_suggestions_deleted"] = deleted
        logger.info(
            "[nightly_data_retention] Deleted %d superseded Suggestion rows older than 30 days.",
            deleted,
        )
    except (DatabaseError, IntegrityError):
        raw = traceback.format_exc()
        logger.exception("[nightly_data_retention] Superseded Suggestion purge failed.")
        ErrorLog.objects.create(
            job_type="data_retention",
            step="superseded_suggestion_purge",
            error_message="Superseded Suggestion retention purge failed.",
            raw_exception=raw,
            why="Check database connectivity and the suggestions.Suggestion table.",
        )

    # --- AuditEntry: 6 months (180 days) ---
    try:
        from apps.audit.models import AuditEntry

        cutoff_180d = now - timedelta(days=180)
        deleted, _ = AuditEntry.objects.filter(created_at__lt=cutoff_180d).delete()
        results["audit_entries_deleted"] = deleted
        logger.info(
            "[nightly_data_retention] Deleted %d AuditEntry rows older than 6 months.",
            deleted,
        )
    except (DatabaseError, IntegrityError):
        raw = traceback.format_exc()
        logger.exception("[nightly_data_retention] AuditEntry purge failed.")
        ErrorLog.objects.create(
            job_type="data_retention",
            step="audit_entry_purge",
            error_message="AuditEntry retention purge failed.",
            raw_exception=raw,
            why="Check database connectivity and the audit.AuditEntry table.",
        )

    # --- ErrorLog: 30 days ---
    try:
        cutoff_30d_err = now - timedelta(days=30)
        deleted, _ = ErrorLog.objects.filter(created_at__lt=cutoff_30d_err).delete()
        results["error_logs_deleted"] = deleted
        logger.info(
            "[nightly_data_retention] Deleted %d ErrorLog rows older than 30 days.",
            deleted,
        )
    except (DatabaseError, IntegrityError):
        raw = traceback.format_exc()
        logger.exception("[nightly_data_retention] ErrorLog purge failed.")
        # Cannot log to ErrorLog about ErrorLog failure — just log to stderr.

    # --- WebhookReceipt: 30 days ---
    try:
        from apps.sync.models import WebhookReceipt

        cutoff_30d_wh = now - timedelta(days=30)
        deleted, _ = WebhookReceipt.objects.filter(
            created_at__lt=cutoff_30d_wh
        ).delete()
        results["webhook_receipts_deleted"] = deleted
        logger.info(
            "[nightly_data_retention] Deleted %d WebhookReceipt rows older than 30 days.",
            deleted,
        )
    except (DatabaseError, IntegrityError):
        raw = traceback.format_exc()
        logger.exception("[nightly_data_retention] WebhookReceipt purge failed.")
        ErrorLog.objects.create(
            job_type="data_retention",
            step="webhook_receipt_purge",
            error_message="WebhookReceipt retention purge failed.",
            raw_exception=raw,
            why="Check database connectivity and the sync.WebhookReceipt table.",
        )

    logger.info("[nightly_data_retention] Complete. Results: %s", results)
    return results


@shared_task(name="pipeline.cleanup_stuck_sync_jobs")
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

    if count:
        stuck.update(
            status="failed",
            error_message="Job timed out — server was likely restarted mid-sync.",
            completed_at=timezone.now(),
        )
        logger.info(
            "[cleanup_stuck_sync_jobs] Marked %d stuck job(s) as failed.", count
        )
    else:
        logger.info("[cleanup_stuck_sync_jobs] No stuck jobs found.")

    return {"jobs_cleaned": count}


@shared_task(
    name="pipeline.sync_single_xf_item",
    time_limit=300,
    soft_time_limit=270,
    autoretry_for=(requests.RequestException, ConnectionError),
    max_retries=3,
    retry_backoff=60,
)
def sync_single_xf_item(
    content_id: int, content_type: str = "thread", node_id: int | None = None
) -> dict:
    """Real-time sync for a single XenForo item (thread or resource) via webhook."""
    from apps.content.models import ScopeItem
    from apps.sync.services.xenforo_api import XenForoAPIClient
    from apps.pipeline.tasks import import_content

    logger.info(
        "Real-time sync triggered for %s %d (node/cat: %s)",
        content_type,
        content_id,
        node_id,
    )

    try:
        client = XenForoAPIClient()

        # 1. Fetch item data to get node_id if not provided
        xf_node_id = node_id
        if not xf_node_id:
            if content_type == "thread":
                resp = client.get_thread(content_id)
                xf_node_id = resp.get("thread", {}).get("node_id")
            elif content_type == "resource":
                resp = client.get_resource_updates(content_id)  # hypothetical
                xf_node_id = resp.get("resource", {}).get("resource_category_id")

        if not xf_node_id:
            logger.error(
                "Could not determine node_id for %s %d", content_type, content_id
            )
            return {"error": "Missing node_id"}

        # 2. Find or create ScopeItem
        scope_type = "node" if content_type == "thread" else "resource_category"
        scope, created = ScopeItem.objects.get_or_create(
            scope_id=xf_node_id,
            scope_type=scope_type,
            defaults={
                "title": f"Auto-discovered {scope_type} {xf_node_id}",
                "is_enabled": True,
            },
        )

        if not scope.is_enabled:
            logger.info(
                "Scope %s is disabled; skipping sync for %s %d",
                scope.title,
                content_type,
                content_id,
            )
            return {"status": "skipped", "reason": "scope disabled"}

        # 3. Trigger the import logic for this specific scope
        # We reuse the existing robust logic in import_content
        return import_content(scope_ids=[scope.pk], mode="full", source="api")

    except (DatabaseError, TimeoutError, MemoryError, ValueError) as e:
        logger.exception("Failed to sync single item %d", content_id)
        return {"error": str(e)}


@shared_task(
    name="pipeline.sync_single_wp_item",
    time_limit=300,
    soft_time_limit=270,
    autoretry_for=(requests.RequestException, ConnectionError),
    max_retries=3,
    retry_backoff=60,
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
# Part 8 — FR-018 C# auto-tune tasks
# ---------------------------------------------------------------------------


@shared_task(
    bind=True,
    name="pipeline.monthly_cs_weight_tune",
    time_limit=600,
    soft_time_limit=540,
)
def monthly_cs_weight_tune(self):
    """Trigger a FR-018 weight-tune run via the C# HTTP-worker, then evaluate the result.

    Scheduled at 02:30 on the first Sunday of every month (offset from the R
    auto-tune so both do not run at the same second).

    Flow:
        1. Ask C# to collect signals + optimise → C# POSTs a RankingChallenger
           to /api/internal/weight-challenger/ if it finds an improvement.
        2. Chain evaluate_weight_challenger to score and optionally promote it.
    """
    import traceback
    import uuid as _uuid

    from apps.audit.models import ErrorLog

    run_id = str(_uuid.uuid4())

    try:
        from apps.graph.services.http_worker_client import HttpWorkerError, run_job

        result = run_job(
            "weight_tune",
            {"run_id": run_id, "lookback_days": 90},
            job_id=run_id,
        )

        status = result.get("status", "unknown")
        logger.info(
            "[monthly_cs_weight_tune] C# run finished: status=%s run_id=%s",
            status,
            run_id,
        )

        if status == "submitted":
            # C# already POSTed the challenger; evaluate it now.
            evaluate_weight_challenger.delay(run_id=run_id)

        return {"status": status, "run_id": run_id}

    except HttpWorkerError as exc:
        logger.warning("[monthly_cs_weight_tune] HTTP-worker unavailable: %s", exc)
        return {"status": "skipped", "reason": str(exc)}

    except (DatabaseError, TimeoutError, MemoryError, ValueError):
        raw = traceback.format_exc()
        logger.exception("[monthly_cs_weight_tune] Failed: %s", raw)
        ErrorLog.objects.create(
            job_type="auto_tune_weights",
            step="monthly_cs_weight_tune",
            error_message="C# weight-tune task failed.",
            raw_exception=raw,
            why="The monthly C# auto-tune task raised an unexpected exception.",
        )
        return {"status": "error"}


@shared_task(bind=True, name="pipeline.evaluate_weight_challenger")
def evaluate_weight_challenger(self, *, run_id: str):
    """Evaluate a pending RankingChallenger and promote it if it beats the champion.

    Promotion criteria (spec §4):
        challenger.predicted_quality_score > champion_quality_score * 1.05

    If the challenger qualifies, its weights are written to AppSetting and a
    WeightAdjustmentHistory row is created with source='cs_auto_tune'.
    If it does not qualify, the challenger is marked 'rejected'.

    Called automatically after monthly_cs_weight_tune, or manually via
    POST /api/settings/cs-tune/trigger/.
    """
    import traceback

    from django.db import transaction

    from apps.audit.models import ErrorLog
    from apps.suggestions.models import RankingChallenger
    from apps.suggestions.weight_preset_service import (
        apply_weights,
        get_current_weights,
        write_history,
    )

    from apps.pipeline.services.sprt_evaluator import ChallengerSPRTEvaluator

    try:
        challenger = RankingChallenger.objects.filter(
            run_id=run_id, status="pending"
        ).first()
        if challenger is None:
            logger.info(
                "[evaluate_weight_challenger] No pending challenger found for run_id=%s",
                run_id,
            )
            return {"status": "not_found", "run_id": run_id}

        cand_score = challenger.predicted_quality_score
        champ_score = challenger.champion_quality_score

        # If C# did not supply scores, fall back to approving automatically
        # (the bounds validation in WeightChallengerInternalView already guarantees safety).
        if cand_score is None or champ_score is None:
            logger.info(
                "[evaluate_weight_challenger] No quality scores on challenger %s — auto-promoting.",
                run_id,
            )
            should_promote = True
            sprt_decision = "auto"
        else:
            evaluator = ChallengerSPRTEvaluator(
                alpha=0.05,
                beta=0.10,
                min_improvement_ratio=1.05,
                assumed_std_dev=0.08,
            )
            sprt_result = evaluator.evaluate(cand_score, champ_score)
            should_promote = sprt_result.decision == "promote"
            sprt_decision = sprt_result.decision
            logger.info(
                "[evaluate_weight_challenger] SPRT for %s: %s (LR=%.4f, bounds=[%.4f, %.4f])",
                run_id,
                sprt_result.decision,
                sprt_result.log_likelihood_ratio,
                sprt_result.lower_boundary,
                sprt_result.upper_boundary,
            )

        if not should_promote:
            challenger.status = "rejected"
            challenger.save(update_fields=["status", "updated_at"])
            logger.info(
                "[evaluate_weight_challenger] Challenger %s rejected via SPRT (%s): "
                "score %.4f vs champion %.4f.",
                run_id,
                sprt_decision,
                cand_score,
                champ_score,
            )
            return {"status": "rejected", "run_id": run_id, "decision": sprt_decision}

        # Promote: apply the four tunable weights; leave all other weights untouched.
        previous_weights = get_current_weights()

        # Merge candidate values into the full current weights dict.
        promoted_weights = dict(previous_weights)
        for key, val in challenger.candidate_weights.items():
            promoted_weights[key] = str(val)

        with transaction.atomic():
            apply_weights(promoted_weights)

        new_weights = get_current_weights()

        history_row = write_history(
            source="cs_auto_tune",
            previous_weights=previous_weights,
            new_weights=new_weights,
            reason=f"FR-018 C# auto-tune promoted challenger {run_id[:16]}",
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
        return {"status": "promoted", "run_id": run_id}

    except (DatabaseError, TimeoutError, MemoryError, ValueError):
        raw = traceback.format_exc()
        logger.exception("[evaluate_weight_challenger] Failed: %s", raw)
        ErrorLog.objects.create(
            job_type="auto_tune_weights",
            step="evaluate_weight_challenger",
            error_message="Challenger evaluation failed.",
            raw_exception=raw,
            why="The evaluate_weight_challenger task raised an unexpected exception.",
        )
        return {"status": "error"}


@shared_task(name="pipeline.check_weight_rollback")
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
                error_message=f"Rollback check failed for challenger {challenger.run_id[:16]}.",
                raw_exception=raw,
                why="check_weight_rollback raised an unexpected exception for one challenger.",
            )


def _check_single_rollback(challenger):
    """Compare GSC clicks before vs after promotion for one challenger."""
    from apps.analytics.models import GSCDailyPerformance
    from django.db.models import Sum
    from datetime import timedelta
    from apps.suggestions.weight_preset_service import (
        apply_weights,
        get_current_weights,
        write_history,
    )
    from django.db import transaction

    REGRESSION_THRESHOLD = 0.85  # < 85% of baseline = regression

    promoted_at = challenger.updated_at.date()
    pre_start = promoted_at - timedelta(days=14)
    pre_end = promoted_at - timedelta(days=1)
    post_start = promoted_at
    post_end = promoted_at + timedelta(days=13)

    pre_clicks = (
        GSCDailyPerformance.objects.filter(date__range=(pre_start, pre_end)).aggregate(
            total=Sum("clicks")
        )["total"]
        or 0
    )
    post_clicks = (
        GSCDailyPerformance.objects.filter(
            date__range=(post_start, post_end)
        ).aggregate(total=Sum("clicks"))["total"]
        or 0
    )

    if pre_clicks < 50:
        logger.info(
            "[check_weight_rollback] Skipping challenger %s — insufficient pre-promotion GSC data (%d clicks).",
            challenger.run_id,
            pre_clicks,
        )
        return

    ratio = post_clicks / pre_clicks
    logger.info(
        "[check_weight_rollback] Challenger %s: post/pre click ratio = %.3f (threshold %.2f).",
        challenger.run_id,
        ratio,
        REGRESSION_THRESHOLD,
    )

    if ratio < REGRESSION_THRESHOLD:
        # Roll back: restore the baseline_weights snapshot stored on the challenger.
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
            source="cs_auto_tune",
            previous_weights=previous_weights,
            new_weights=new_weights,
            reason=(
                f"FR-018 auto-rollback: challenger {challenger.run_id[:16]} "
                f"caused GSC regression (post/pre={ratio:.2f})."
            ),
            r_run_id=challenger.run_id,
        )

        challenger.status = "rolled_back"
        challenger.save(update_fields=["status", "updated_at"])

        logger.info(
            "[check_weight_rollback] Rolled back challenger %s (ratio=%.3f).",
            challenger.run_id,
            ratio,
        )


# ── FR-019: GSC spike detection ───────────────────────────────────────────────


@shared_task(bind=True, name="pipeline.check_gsc_spikes")
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
    import json
    from datetime import date, timedelta

    from django.db.models import Avg

    from apps.analytics.models import SearchMetric
    from apps.content.models import ContentItem
    from apps.notifications.models import OperatorAlert
    from apps.notifications.services import emit_operator_alert

    # Load thresholds from prefs (defaults if not set)
    try:
        from apps.core.models import AppSetting

        raw = AppSetting.objects.filter(key="notifications.settings").first()
        prefs = json.loads(raw.value) if raw else {}
    except (JSONDecodeError, KeyError, TypeError):
        prefs = {}

    min_impressions_delta = int(prefs.get("gsc_spike_min_impressions_delta", 50))
    min_clicks_delta = int(prefs.get("gsc_spike_min_clicks_delta", 5))
    min_relative_lift = float(prefs.get("gsc_spike_min_relative_lift", 0.5))

    today = date.today()
    recent_end = today - timedelta(days=1)  # yesterday
    recent_start = recent_end - timedelta(days=2)  # 3-day window
    baseline_end = recent_start - timedelta(days=1)
    baseline_start = baseline_end - timedelta(days=6)  # 7-day baseline

    alerts_emitted = 0

    for item in ContentItem.objects.all().iterator():
        recent_qs = SearchMetric.objects.filter(
            content_item=item,
            source="gsc",
            date__gte=recent_start,
            date__lte=recent_end,
        ).aggregate(avg_impressions=Avg("impressions"), avg_clicks=Avg("clicks"))

        baseline_qs = SearchMetric.objects.filter(
            content_item=item,
            source="gsc",
            date__gte=baseline_start,
            date__lte=baseline_end,
        ).aggregate(avg_impressions=Avg("impressions"), avg_clicks=Avg("clicks"))

        r_imp = recent_qs["avg_impressions"] or 0.0
        r_clk = recent_qs["avg_clicks"] or 0.0
        b_imp = baseline_qs["avg_impressions"] or 0.0
        b_clk = baseline_qs["avg_clicks"] or 0.0

        # Skip if no baseline data
        if b_imp == 0 and b_clk == 0:
            continue

        imp_delta = r_imp - b_imp
        clk_delta = r_clk - b_clk
        imp_lift = (imp_delta / b_imp) if b_imp > 0 else 0.0
        clk_lift = (clk_delta / b_clk) if b_clk > 0 else 0.0

        impressions_spike = (
            imp_delta >= min_impressions_delta and imp_lift >= min_relative_lift
        )
        clicks_spike = clk_delta >= min_clicks_delta and clk_lift >= min_relative_lift

        if not (impressions_spike or clicks_spike):
            continue

        severity = (
            OperatorAlert.SEVERITY_URGENT
            if (imp_lift >= 2.0 or clk_lift >= 2.0)
            else OperatorAlert.SEVERITY_WARNING
        )
        title = "Google search demand spiked"
        message = (
            f"'{item.title[:60]}' — impressions: +{imp_delta:.0f} ({imp_lift*100:.0f}%), "
            f"clicks: +{clk_delta:.0f} ({clk_lift*100:.0f}%). Review the Analytics page."
        )

        try:
            emit_operator_alert(
                event_type="analytics.gsc_spike",
                severity=severity,
                title=title,
                message=message,
                source_area=OperatorAlert.AREA_ANALYTICS,
                dedupe_key=f"analytics.gsc_spike:{item.pk}:{today.isoformat()}",
                related_object_type="ContentItem",
                related_object_id=str(item.pk),
                related_route="/analytics",
                payload={
                    "content_item_id": item.pk,
                    "title": item.title,
                    "impressions_delta": round(imp_delta, 1),
                    "clicks_delta": round(clk_delta, 1),
                    "impressions_lift_pct": round(imp_lift * 100, 1),
                    "clicks_lift_pct": round(clk_lift * 100, 1),
                },
                cooldown_seconds=86400,  # 24-hour cooldown per page per day
            )
            alerts_emitted += 1
        except (ImportError, AttributeError, DatabaseError):
            logger.warning(
                "check_gsc_spikes: failed to emit alert for item %s",
                item.pk,
                exc_info=True,
            )

    logger.info("check_gsc_spikes: %d spike alerts emitted.", alerts_emitted)
    return {"alerts_emitted": alerts_emitted}


# ---------------------------------------------------------------------------
# FR-030 — FAISS-GPU index refresh
# ---------------------------------------------------------------------------


@shared_task(name="pipeline.refresh_faiss_index", time_limit=3600, soft_time_limit=3540)
def refresh_faiss_index():
    """FR-030 — Rebuild FAISS-GPU index to pick up newly generated embeddings."""
    from apps.pipeline.services.faiss_index import build_faiss_index

    build_faiss_index()
