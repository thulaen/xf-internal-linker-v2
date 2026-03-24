"""
Celery tasks for the ML pipeline.

These tasks wrap the ML services and publish real-time progress events
via the Django Channels layer so Angular can display live job status.

Task routing (configured in base.py):
  pipeline queue   → run_pipeline, verify_suggestions
  embeddings queue → generate_embeddings, import_content
"""

import logging
import time
import uuid
from typing import Any, Optional

from asgiref.sync import async_to_sync
from celery import shared_task
from channels.layers import get_channel_layer

logger = logging.getLogger(__name__)


def _publish_progress(job_id: str, state: str, progress: float, message: str, **extra: Any) -> None:
    """Publish a job progress event to the WebSocket channel group."""
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
def run_pipeline(
    self,
    run_id: str,
    host_scope: dict,
    destination_scope: dict,
    rerun_mode: str = "skip_pending",
) -> dict:
    """Execute the full 3-stage ML suggestion pipeline.

    Stages:
      1. Load destinations + sentence embeddings from pgvector
      2. Stage 1 coarse + Stage 2 sentence-level cosine similarity
      3. Composite scoring, anchor extraction, Suggestion record creation

    Args:
        run_id: UUID string of the PipelineRun record
        host_scope: dict — reserved for scope filtering (e.g. {'scope_ids': [1,2]})
        destination_scope: dict — reserved for scope filtering
        rerun_mode: 'skip_pending' | 'supersede_pending' | 'full_regenerate'
    """
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
        host_scope_ids = (
            set(host_scope["scope_ids"])
            if host_scope and "scope_ids" in host_scope
            else None
        )

        result = _run(
            run_id=run_id,
            rerun_mode=rerun_mode,
            destination_scope_ids=destination_scope_ids,
            host_scope_ids=host_scope_ids,
            progress_fn=_progress,
        )

        duration = time.monotonic() - started_at
        run.run_state = "completed"
        run.duration_seconds = duration
        run.save(update_fields=["run_state", "duration_seconds", "updated_at"])

        _publish_progress(
            job_id, "completed", 1.0, "Pipeline complete.",
            suggestions_created=result.suggestions_created,
            destinations_processed=result.items_in_scope,
        )

        return {
            "run_id": run_id,
            "state": "completed",
            "suggestions_created": result.suggestions_created,
            "items_in_scope": result.items_in_scope,
            "duration_seconds": round(duration, 2),
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
def generate_embeddings(self, content_item_ids: list[int] | None = None) -> dict:
    """Generate and store embeddings for ContentItems and their Sentences.

    Stores results directly in pgvector VectorField columns (no .npy files).

    Args:
        content_item_ids: List of ContentItem PKs to embed.
                          None = all non-deleted items.
    """
    job_id = str(uuid.uuid4())
    count_label = len(content_item_ids) if content_item_ids is not None else "all"
    _publish_progress(job_id, "running", 0.0,
                      f"Generating embeddings for {count_label} items...")

    try:
        from apps.pipeline.services.embeddings import generate_all_embeddings

        _publish_progress(job_id, "running", 0.1, "Loading embedding model...")
        stats = generate_all_embeddings(content_item_ids)

        _publish_progress(
            job_id, "completed", 1.0,
            f"Embeddings complete — {stats['content_items_embedded']} items, "
            f"{stats['sentences_embedded']} sentences.",
            **stats,
        )
        return {"job_id": job_id, **stats}

    except Exception as exc:
        logger.exception("Embedding job %s failed", job_id)
        _publish_progress(job_id, "failed", 0.0, f"Embeddings failed: {exc}", error=str(exc))
        raise


_MAX_PAGES = 500  # Safety cap: stop pagination if API returns bad metadata


@shared_task(bind=True, name="pipeline.import_content")
def import_content(
    self,
    scope_ids: list[int] | None = None,
    mode: str = "full",
    source: str = "api",
    file_path: str | None = None,
    job_id: str | None = None,
) -> dict:
    """Import/sync content from XenForo via REST API or JSONL export.

    After import, updates PageRank and velocity scores, then re-embeds
    any content whose text changed.

    Args:
        job_id: Optional pre-generated UUID string. When supplied by the upload
                view the Angular client can subscribe to the WebSocket channel
                before the task starts publishing progress events.
    """
    from django.db import models
    from django.utils import timezone
    from django.conf import settings
    from apps.sync.models import SyncJob
    from apps.content.models import ContentItem, ScopeItem, Post, Sentence
    from apps.sync.services.xenforo_api import XenForoAPIClient
    from apps.sync.services.jsonl_importer import import_from_jsonl
    from apps.pipeline.services.text_cleaner import clean_bbcode, generate_content_hash
    from apps.pipeline.services.sentence_splitter import split_sentence_spans
    from apps.pipeline.services.distiller import distill_body
    from apps.pipeline.services.link_parser import extract_internal_links, sync_existing_links
    from apps.pipeline.services.embeddings import generate_all_embeddings

    job_id = job_id or str(uuid.uuid4())
    
    # Try to find existing SyncJob or create if not exists (e.g. if started from API)
    job, created = SyncJob.objects.get_or_create(
        job_id=job_id,
        defaults={
            "source": source,
            "mode": mode,
            "status": "running",
            "started_at": timezone.now()
        }
    )
    if not created:
        job.status = "running"
        job.started_at = timezone.now()
        job.save(update_fields=["status", "started_at", "updated_at"])

    _publish_progress(job_id, "running", 0.0, f"Starting {mode} content import from {source}...")

    items_synced = 0
    items_updated = 0
    
    updated_pks = []
    
    def _process_item(item_data: dict, current_scope: ScopeItem) -> Optional[int]:
        """Process a single item (thread/resource) and return its PK if updated, else None."""
        nonlocal items_synced
        items_synced += 1
        
        # Determine content type and IDs
        c_type = item_data.get("content_type", "thread")
        c_id = item_data.get("thread_id") if c_type == "thread" else item_data.get("resource_id")
        if not c_id:
            return None
            
        first_post_id = item_data.get("first_post_id")
        title = item_data.get("title", "Untitled")
        view_url = item_data.get("view_url", "")
        
        content_item, _ = ContentItem.objects.get_or_create(
            content_id=c_id,
            content_type=c_type,
            defaults={
                "title": title,
                "scope": current_scope,
                "url": view_url,
                "xf_post_id": first_post_id,
            }
        )
        
        # Update metadata
        content_item.view_count = item_data.get("view_count", 0)
        content_item.reply_count = item_data.get("reply_count", 0)
        content_item.download_count = item_data.get("download_count", 0)
        content_item.save(update_fields=["view_count", "reply_count", "download_count", "updated_at"])

        # Check if body sync needed
        # In JSONL source, the body might already be in the data
        raw_bbcode = (
            item_data.get("message") or 
            item_data.get("post_body") or 
            item_data.get("description") or 
            item_data.get("tag_line")
        )
        
        # If no body in data and mode is full, we must fetch it from API if source is API
        if not raw_bbcode and mode == "full" and source == "api":
            if c_type == "thread" and first_post_id:
                client = XenForoAPIClient()
                post_resp = client.get_post(first_post_id)
                raw_bbcode = post_resp.get("post", {}).get("message", "")
        
        if raw_bbcode:
            clean_text = clean_bbcode(raw_bbcode)
            new_hash = generate_content_hash(title, clean_text)
            
            if content_item.content_hash != new_hash:
                from django.db import transaction
                with transaction.atomic():
                    content_item.content_hash = new_hash
                    
                    # Update Post
                    post, _ = Post.objects.get_or_create(content_item=content_item)
                    post.raw_bbcode = raw_bbcode
                    post.clean_text = clean_text
                    post.char_count = len(clean_text)
                    post.word_count = len(clean_text.split())
                    post.xf_post_id = first_post_id
                    post.save()
                    
                    # 1. Update Sentences
                    Sentence.objects.filter(content_item=content_item).delete()
                    spans = split_sentence_spans(clean_text)
                    sentence_objs = [
                        Sentence(
                            content_item=content_item,
                            post=post,
                            text=span.text,
                            position=span.position,
                            char_count=len(span.text),
                            start_char=span.start_char,
                            end_char=span.end_char,
                            word_position=len(clean_text[:span.start_char].split())
                        )
                        for span in spans
                    ]
                    Sentence.objects.bulk_create(sentence_objs)
                    
                    # 2. Refine Distillation
                    sentence_texts = [s.text for s in sentence_objs]
                    content_item.distilled_text = distill_body(sentence_texts, max_sentences=5)
                    content_item.save(update_fields=["content_hash", "distilled_text", "updated_at"])
                    
                    # 3. Graph Refresh
                    from urllib.parse import urlparse
                    xf_base_url = getattr(settings, "XENFORO_BASE_URL", "")
                    forum_domains = [urlparse(xf_base_url).netloc] if xf_base_url else []
                    edges = extract_internal_links(raw_bbcode, c_id, c_type, forum_domains=forum_domains)
                    sync_existing_links(content_item, edges)
                
                return content_item.pk
        return None

    try:
        # ── Source: REST API ──────────────────────────────────────────
        if source == "api":
            client = XenForoAPIClient()
            scopes = ScopeItem.objects.filter(is_enabled=True)
            if scope_ids:
                scopes = scopes.filter(pk__in=scope_ids)

            total_scopes = scopes.count()
            for i, scope in enumerate(scopes):
                pct = (i / total_scopes) * 0.8
                _publish_progress(job_id, "running", pct, f"Syncing scope: {scope.title}")

                if scope.scope_type == "node":
                    page = 1
                    while page <= _MAX_PAGES:
                        resp = client.get_threads(scope.scope_id, page=page)
                        threads = resp.get("threads", [])
                        if not threads:
                            break

                        for thread in threads:
                            thread["content_type"] = "thread"
                            pk = _process_item(thread, scope)
                            if pk:
                                updated_pks.append(pk)
                                items_updated += 1

                        # Throttle DB updates for progress
                        if items_synced % 25 == 0:
                            job.items_synced = items_synced
                            job.items_updated = items_updated
                            job.save(update_fields=["items_synced", "items_updated", "updated_at"])

                        pagination = resp.get("pagination", {})
                        if page >= pagination.get("last_page", 1):
                            break
                        page += 1
                    else:
                        logger.warning("Pagination safety cap (%d pages) reached for scope %s", _MAX_PAGES, scope.scope_id)

                elif scope.scope_type == "resource_category":
                    page = 1
                    while page <= _MAX_PAGES:
                        resp = client.get_resources(scope.scope_id, page=page)
                        resources = resp.get("resources", [])
                        if not resources:
                            break

                        for res in resources:
                            res["content_type"] = "resource"
                            pk = _process_item(res, scope)
                            if pk:
                                updated_pks.append(pk)
                                items_updated += 1
                                
                                # Fetch and store resource updates as additional Sentences (mode=full only)
                                if mode == "full":
                                    try:
                                        updates_resp = client.get_resource_updates(res.get("resource_id"))
                                        update_list = updates_resp.get("resource_updates", []) or updates_resp.get("updates", [])
                                        if update_list:
                                            content_item = ContentItem.objects.get(pk=pk)
                                            post = content_item.post
                                            # Get current max position to append
                                            max_pos = Sentence.objects.filter(post=post).aggregate(models.Max("position"))["position__max"] or 0
                                            
                                            for update in update_list:
                                                update_body = update.get("message", "")
                                                if update_body:
                                                    clean = clean_bbcode(update_body)
                                                    spans = split_sentence_spans(clean)
                                                    sentence_objs = []
                                                    for span in spans:
                                                        max_pos += 1
                                                        sentence_objs.append(Sentence(
                                                            content_item=content_item,
                                                            post=post,
                                                            text=span.text,
                                                            position=max_pos,
                                                            char_count=len(span.text),
                                                            start_char=span.start_char,
                                                            end_char=span.end_char,
                                                            # updates are usually at the end, so word_position is approximate
                                                            word_position=post.word_count + 1 
                                                        ))
                                                    Sentence.objects.bulk_create(sentence_objs)
                                    except Exception as e:
                                        logger.warning("Failed to fetch updates for resource %s: %s", res.get("resource_id"), e)
                        
                        pagination = resp.get("pagination", {})
                        if page >= pagination.get("last_page", 1):
                            break
                        page += 1
                    else:
                        logger.warning("Pagination safety cap (%d pages) reached for scope %s", _MAX_PAGES, scope.scope_id)

        # ── Source: JSONL ─────────────────────────────────────────────
        elif source == "jsonl":
            if not file_path:
                raise ValueError("file_path is required for JSONL import.")
            
            # Security: ensure file_path is within project root (handled in service)
            for item in import_from_jsonl(file_path):
                # JSONL items must specify their scope_id
                s_id = item.get("scope_id")
                s_type = item.get("scope_type", "node")
                if not s_id:
                    continue
                    
                scope, _ = ScopeItem.objects.get_or_create(
                    scope_id=s_id, 
                    scope_type=s_type,
                    defaults={"title": f"Imported Scope {s_id}"}
                )
                pk = _process_item(item, scope)
                if pk:
                    updated_pks.append(pk)
                    items_updated += 1
                
                if items_synced % 50 == 0:
                    job.items_synced = items_synced
                    job.items_updated = items_updated
                    job.save(update_fields=["items_synced", "items_updated", "updated_at"])

        # Generate embeddings in batch for all items that were changed
        if updated_pks:
            _publish_progress(job_id, "running", 0.85, f"Generating embeddings for {len(updated_pks)} items...")
            generate_all_embeddings(updated_pks)

        # Post-import analytics
        if mode in ("titles", "full"):
            _publish_progress(job_id, "running", 0.9, "Recalculating PageRank and velocity...")
            from apps.pipeline.services.pagerank import run_pagerank
            run_pagerank()
            from apps.pipeline.services.velocity import run_velocity
            import time as _time
            run_velocity(reference_ts=int(_time.time()))

        job.status = "completed"
        job.progress = 1.0
        job.completed_at = timezone.now()
        job.items_synced = items_synced
        job.items_updated = items_updated
        job.message = f"Import complete. {items_synced} synced, {items_updated} updated."
        job.save()

        _publish_progress(
            job_id, "completed", 1.0, 
            f"Content import complete ({source}). {items_synced} items synced, {items_updated} updated."
        )
        return {"mode": mode, "job_id": job_id, "items_synced": items_synced, "items_updated": items_updated}

    except Exception as exc:
        logger.exception("Import job %s failed", job_id)
        
        job.status = "failed"
        job.error_message = str(exc)
        job.completed_at = timezone.now()
        job.save()

        _publish_progress(job_id, "failed", 0.0, f"Import failed: {exc}", error=str(exc))
        raise


@shared_task(bind=True, name="pipeline.verify_suggestions")
def verify_suggestions(self, suggestion_ids: list[str] | None = None) -> dict:
    """Check whether applied suggestions are still live via XenForo API.

    Marks suggestions as 'verified' if the link is confirmed live,
    or 'stale' if the host post was edited and no longer contains the link.
    """
    import uuid
    import logging
    from django.utils import timezone
    from apps.suggestions.models import Suggestion
    from apps.sync.services.xenforo_api import XenForoAPIClient

    job_id = str(uuid.uuid4())
    _publish_progress(job_id, "running", 0.0, f"Starting verification...")

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
        for i, sug in enumerate(suggestions):
            pct = (i / total)
            _publish_progress(job_id, "running", pct, f"Checking suggestion {str(sug.suggestion_id)[:8]}...")

            host_content = sug.host
            if not host_content or not host_content.xf_post_id:
                logger.warning("Suggestion %s host has no xf_post_id", sug.suggestion_id)
                continue

            try:
                post_resp = client.get_post(host_content.xf_post_id)
                post_data = post_resp.get("post", {})
                raw_bbcode = post_data.get("message", "")
                
                # Check for the destination URL in the BBCode
                destination_url = sug.destination.url
                if not destination_url:
                    logger.warning("Suggestion %s destination has no URL", sug.suggestion_id)
                    continue

                if destination_url in raw_bbcode:
                    sug.status = "verified"
                    sug.verified_at = timezone.now()
                    sug.save(update_fields=["status", "verified_at", "updated_at"])
                    verified += 1
                else:
                    sug.status = "stale"
                    sug.stale_reason = "Link not found in host post body"
                    sug.save(update_fields=["status", "stale_reason", "updated_at"])
                    stale += 1

            except Exception as e:
                logger.error("Failed to fetch host post for suggestion %s: %s", sug.suggestion_id, e)
                continue

        _publish_progress(job_id, "completed", 1.0, f"Verification complete. {verified} verified, {stale} stale.")
        return {"verified": verified, "stale": stale, "job_id": job_id}

    except Exception as exc:
        logger.exception("Verification job %s failed", job_id)
        _publish_progress(job_id, "failed", 0.0, f"Verification failed: {exc}", error=str(exc))
        raise
