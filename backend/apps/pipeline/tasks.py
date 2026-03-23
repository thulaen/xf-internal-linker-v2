"""
Celery tasks for the ML pipeline.

These tasks wrap the ML services (migrated from V1 in Phase 2) and
publish real-time progress events via the Django Channels layer.

Phase 1: Task stubs with correct signatures and progress event publishing.
Phase 2: Wire in actual ML service calls from backend/services/.

Task routing (configured in base.py):
  pipeline queue  → run_pipeline, verify_suggestions
  embeddings queue → generate_embeddings, import_content
"""

import logging
import uuid
from typing import Any

from asgiref.sync import async_to_sync
from celery import shared_task
from channels.layers import get_channel_layer

logger = logging.getLogger(__name__)


def _publish_progress(job_id: str, state: str, progress: float, message: str, **extra: Any) -> None:
    """
    Publish a job progress event to the WebSocket channel group.

    This is called from within Celery tasks to push live updates
    to connected Angular clients via Django Channels.
    """
    channel_layer = get_channel_layer()
    if channel_layer is None:
        logger.warning("Channel layer not available — progress event not sent.")
        return

    event = {
        "type": "job.progress",
        "job_id": job_id,
        "state": state,
        "progress": round(progress, 3),
        "message": message,
        **extra,
    }

    try:
        async_to_sync(channel_layer.group_send)(f"job_{job_id}", event)
    except Exception:
        logger.exception("Failed to publish progress event for job %s", job_id)


@shared_task(bind=True, name="pipeline.run_pipeline")
def run_pipeline(self, run_id: str, host_scope: dict, destination_scope: dict,
                 rerun_mode: str = "skip_pending") -> dict:
    """
    Execute the full 3-stage ML suggestion pipeline for a set of destinations.

    Stages:
      1. Load destinations and embed their distilled_text (if not cached)
      2. For each destination, find candidate host sentences via cosine similarity
      3. Score and rank candidates, extract anchors, create Suggestion records

    Phase 2 will wire in the actual ML services. For now this stub:
    - Updates the PipelineRun record state
    - Publishes progress events to WebSocket
    - Returns a summary dict

    Args:
        run_id: UUID string of the PipelineRun record
        host_scope: dict describing which content items can host links
        destination_scope: dict describing which content items to link to
        rerun_mode: 'skip_pending' | 'supersede_pending' | 'full_regenerate'
    """
    from apps.suggestions.models import PipelineRun
    from datetime import datetime, timezone
    import time

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

    try:
        _publish_progress(job_id, "running", 0.0, "Pipeline started — loading content...")

        # ── Phase 2 will replace this stub with real ML calls ──
        # Stage 1: Load + embed destinations
        _publish_progress(job_id, "running", 0.1, "Loading destinations...")

        # Stage 2: Find candidate host sentences
        _publish_progress(job_id, "running", 0.4, "Searching for host sentences...")

        # Stage 3: Rank + create suggestions
        _publish_progress(job_id, "running", 0.8, "Ranking candidates and creating suggestions...")

        duration = time.monotonic() - started_at
        run.run_state = "completed"
        run.duration_seconds = duration
        run.save(update_fields=["run_state", "duration_seconds", "updated_at"])

        _publish_progress(job_id, "completed", 1.0, "Pipeline complete.",
                          suggestions_created=run.suggestions_created,
                          destinations_processed=run.destinations_processed)

        return {
            "run_id": run_id,
            "state": "completed",
            "suggestions_created": run.suggestions_created,
            "duration_seconds": duration,
        }

    except Exception as exc:
        logger.exception("Pipeline run %s failed", run_id)
        run.run_state = "failed"
        run.error_message = str(exc)
        run.duration_seconds = time.monotonic() - started_at
        run.save(update_fields=["run_state", "error_message", "duration_seconds", "updated_at"])

        _publish_progress(job_id, "failed", 0.0, f"Pipeline failed: {exc}", error=str(exc))
        raise


@shared_task(bind=True, name="pipeline.generate_embeddings")
def generate_embeddings(self, content_item_ids: list[int]) -> dict:
    """
    Generate and store embeddings for a list of ContentItem IDs.

    Uses the sentence-transformers model (multi-qa-MiniLM-L6-cos-v1)
    to embed distilled_text for each content item and stores the result
    in the pgvector embedding column.

    Phase 2 will wire in the actual embeddings service.

    Args:
        content_item_ids: list of ContentItem primary keys to embed
    """
    job_id = str(uuid.uuid4())
    _publish_progress(job_id, "running", 0.0,
                      f"Generating embeddings for {len(content_item_ids)} items...")

    # Phase 2: call embeddings service and update ContentItem.embedding columns
    _publish_progress(job_id, "completed", 1.0, "Embeddings complete.")

    return {"embedded": len(content_item_ids), "job_id": job_id}


@shared_task(bind=True, name="pipeline.import_content")
def import_content(self, scope_ids: list[int] | None = None, mode: str = "full") -> dict:
    """
    Import/sync content from XenForo via REST API or JSONL export.

    Mode options:
      'quick'  — fetch only IDs and titles (fast, for stale detection)
      'titles' — fetch titles + metadata (for PageRank/velocity recalc)
      'full'   — fetch full post bodies (for sentence splitting + embedding)

    Phase 2 will wire in the actual XenForo API client.

    Args:
        scope_ids: list of ScopeItem PKs to sync (None = all enabled)
        mode: 'quick' | 'titles' | 'full'
    """
    job_id = str(uuid.uuid4())
    _publish_progress(job_id, "running", 0.0, f"Starting {mode} content import...")

    # Phase 2: call XenForo API / JSONL importer
    _publish_progress(job_id, "completed", 1.0, "Content import complete.")

    return {"mode": mode, "job_id": job_id}


@shared_task(bind=True, name="pipeline.verify_suggestions")
def verify_suggestions(self, suggestion_ids: list[str] | None = None) -> dict:
    """
    Check whether applied suggestions are still live on the forum via XenForo API.

    Marks suggestions as 'verified' if the link is confirmed live,
    or 'stale' if the host post was edited and no longer contains the link.

    Args:
        suggestion_ids: list of Suggestion UUID strings (None = all applied)
    """
    job_id = str(uuid.uuid4())
    count = len(suggestion_ids) if suggestion_ids else "all"
    _publish_progress(job_id, "running", 0.0, f"Verifying {count} applied suggestions...")

    # Phase 2: call XenForo API to verify each link is still live
    _publish_progress(job_id, "completed", 1.0, "Verification complete.")

    return {"verified": 0, "stale": 0, "job_id": job_id}
