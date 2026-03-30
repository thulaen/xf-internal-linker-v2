"""Celery tasks for pipeline, sync, embeddings, verification, and link health."""

from __future__ import annotations

import logging
import time
import uuid
from html import unescape
from typing import Any
from urllib.parse import urljoin, urlparse

import requests
from asgiref.sync import async_to_sync
from celery import shared_task
from channels.layers import get_channel_layer

logger = logging.getLogger(__name__)

_MAX_PAGES = 500
_MAX_BROKEN_LINK_SCAN_URLS = 10_000
_BROKEN_LINK_SCAN_DELAY_SECONDS = 0.5
_BROKEN_LINK_SCAN_TIMEOUT_SECONDS = 10


def _publish_progress(job_id: str, state: str, progress: float, message: str, **extra: Any) -> None:
    """Publish a job progress event to the WebSocket channel group."""
    channel_layer = get_channel_layer()
    if channel_layer is None:
        logger.warning("Channel layer not available; progress event not sent.")
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
            job_id,
            "completed",
            1.0,
            "Pipeline complete.",
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
    """Generate and store embeddings for ContentItems and Sentences."""
    job_id = str(uuid.uuid4())
    count_label = len(content_item_ids) if content_item_ids is not None else "all"
    _publish_progress(job_id, "running", 0.0, f"Generating embeddings for {count_label} items...")
    try:
        from apps.pipeline.services.embeddings import generate_all_embeddings

        _publish_progress(job_id, "running", 0.1, "Loading embedding model...")
        stats = generate_all_embeddings(content_item_ids)
        _publish_progress(
            job_id,
            "completed",
            1.0,
            f"Embeddings complete; {stats['content_items_embedded']} items, {stats['sentences_embedded']} sentences.",
            **stats,
        )
        return {"job_id": job_id, **stats}
    except Exception as exc:
        logger.exception("Embedding job %s failed", job_id)
        _publish_progress(job_id, "failed", 0.0, f"Embeddings failed: {exc}", error=str(exc))
        raise


@shared_task(bind=True, name="pipeline.recalculate_weighted_authority")
def recalculate_weighted_authority(self, job_id: str | None = None) -> dict:
    """Recompute March 2026 PageRank from the stored graph and current settings."""
    job_id = job_id or str(uuid.uuid4())
    _publish_progress(job_id, "running", 0.0, "Starting March 2026 PageRank recalculation...")

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
    except Exception as exc:
        logger.exception("March 2026 PageRank recalculation %s failed", job_id)
        _publish_progress(job_id, "failed", 0.0, f"March 2026 PageRank recalculation failed: {exc}", error=str(exc))
        raise


@shared_task(bind=True, name="pipeline.recalculate_link_freshness")
def recalculate_link_freshness(self, job_id: str | None = None) -> dict:
    """Recompute Link Freshness from the stored link-history rows and current settings."""
    job_id = job_id or str(uuid.uuid4())
    _publish_progress(job_id, "running", 0.0, "Starting Link Freshness recalculation...")

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
    except Exception as exc:
        logger.exception("Link Freshness recalculation %s failed", job_id)
        _publish_progress(job_id, "failed", 0.0, f"Link Freshness recalculation failed: {exc}", error=str(exc))
        raise


@shared_task(bind=True, name="pipeline.import_content")
def import_content(
    self,
    scope_ids: list[int] | None = None,
    mode: str = "full",
    source: str = "api",
    file_path: str | None = None,
    job_id: str | None = None,
) -> dict:
    """Import/sync content from XenForo, WordPress, or JSONL export."""
    from django.conf import settings
    from django.db import models, transaction
    from django.utils import timezone
    from django.utils.dateparse import parse_datetime

    from apps.content.models import ContentItem, Post, ScopeItem, Sentence
    from apps.core.views import get_wordpress_runtime_config
    from apps.graph.services.graph_sync import refresh_existing_links, sync_existing_links
    from apps.pipeline.services.distiller import distill_body
    from apps.pipeline.services.embeddings import generate_all_embeddings
    from apps.pipeline.services.link_parser import extract_internal_links, normalize_internal_url
    from apps.pipeline.services.sentence_splitter import split_sentence_spans
    from apps.pipeline.services.text_cleaner import clean_bbcode, clean_import_text, generate_content_hash
    from apps.sync.models import SyncJob
    from apps.sync.services.jsonl_importer import import_from_jsonl
    from apps.sync.services.wordpress_api import WordPressAPIClient
    from apps.sync.services.xenforo_api import XenForoAPIClient

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

    _publish_progress(job_id, "running", 0.0, f"Starting {mode} content import from {source}...")

    items_synced = 0
    items_updated = 0
    updated_pks: list[int] = []
    touched_scope_ids: set[int] = set()
    xf_client: XenForoAPIClient | None = None

    def _configured_domains() -> list[str]:
        domains: list[str] = []
        for raw_url in [
            getattr(settings, "XENFORO_BASE_URL", ""),
            get_wordpress_runtime_config().get("base_url", ""),
        ]:
            host = urlparse(raw_url).netloc.strip().lower()
            if host and host not in domains:
                domains.append(host)
        return domains

    def _plain_title(value: Any) -> str:
        if isinstance(value, dict):
            value = value.get("rendered", "")
        return str(unescape(value or "")).strip() or "Untitled"

    def _parse_wp_timestamp(value: str | None) -> Any:
        if not value:
            return None
        parsed = parse_datetime(value)
        if parsed is None:
            parsed = parse_datetime(f"{value}Z")
        return parsed

    def _flush_job_progress() -> None:
        job.items_synced = items_synced
        job.items_updated = items_updated
        job.save(update_fields=["items_synced", "items_updated", "updated_at"])

    def _update_scope_counts() -> None:
        if not touched_scope_ids:
            return
        count_map = {
            row["scope_id"]: row["total"]
            for row in (
                ContentItem.objects
                .filter(scope_id__in=touched_scope_ids)
                .values("scope_id")
                .annotate(total=models.Count("pk"))
            )
        }
        scopes = list(ScopeItem.objects.filter(pk__in=touched_scope_ids))
        for scope in scopes:
            scope.content_count = count_map.get(scope.pk, 0)
        if scopes:
            ScopeItem.objects.bulk_update(scopes, ["content_count"])

    def _process_item(item_data: dict[str, Any], current_scope: ScopeItem) -> int | None:
        nonlocal items_synced, xf_client

        items_synced += 1
        touched_scope_ids.add(current_scope.pk)

        c_type = str(item_data.get("content_type", "thread"))
        first_post_id = None
        raw_body = ""
        view_url = ""
        title = "Untitled"
        view_count = 0
        reply_count = 0
        download_count = 0
        post_date = None
        last_post_date = None

        if source == "wp":
            c_id = item_data.get("id")
            if not c_id:
                return None
            title = _plain_title(item_data.get("title"))
            view_url = item_data.get("link", "")
            raw_body = (
                item_data.get("content", {}).get("rendered", "")
                or item_data.get("excerpt", {}).get("rendered", "")
            )
            post_date = _parse_wp_timestamp(item_data.get("date_gmt") or item_data.get("date"))
            last_post_date = _parse_wp_timestamp(item_data.get("modified_gmt") or item_data.get("modified"))
        else:
            c_id = item_data.get("thread_id") if c_type == "thread" else item_data.get("resource_id")
            if not c_id:
                c_id = item_data.get("content_id")
            if not c_id:
                return None
            first_post_id = item_data.get("first_post_id")
            title = _plain_title(item_data.get("title"))
            view_url = item_data.get("view_url") or item_data.get("url", "")
            view_count = int(item_data.get("view_count") or 0)
            reply_count = int(item_data.get("reply_count") or 0)
            download_count = int(item_data.get("download_count") or 0)
            raw_body = (
                item_data.get("message")
                or item_data.get("post_body")
                or item_data.get("description")
                or item_data.get("tag_line")
                or item_data.get("raw_body")
                or ""
            )
            if not raw_body and mode == "full" and source == "api" and c_type == "thread" and first_post_id:
                if xf_client is None:
                    xf_client = XenForoAPIClient()
                raw_body = xf_client.get_post(first_post_id).get("post", {}).get("message", "")

        canonical_url = normalize_internal_url(view_url) or view_url
        content_item, _ = ContentItem.objects.get_or_create(
            content_id=int(c_id),
            content_type=c_type,
            defaults={
                "title": title,
                "scope": current_scope,
                "url": canonical_url,
                "xf_post_id": first_post_id,
                "post_date": post_date,
                "last_post_date": last_post_date,
            },
        )

        content_item.title = title
        content_item.scope = current_scope
        content_item.url = canonical_url
        content_item.view_count = view_count
        content_item.reply_count = reply_count
        content_item.download_count = download_count
        if post_date is not None:
            content_item.post_date = post_date
        if last_post_date is not None:
            content_item.last_post_date = last_post_date
        content_item.xf_post_id = first_post_id
        content_item.is_deleted = False
        content_item.save(
            update_fields=[
                "title",
                "scope",
                "url",
                "view_count",
                "reply_count",
                "download_count",
                "post_date",
                "last_post_date",
                "xf_post_id",
                "is_deleted",
                "updated_at",
            ]
        )

        if not raw_body:
            return None

        clean_text = clean_import_text(raw_body)
        new_hash = generate_content_hash(title, clean_text)
        if content_item.content_hash == new_hash:
            if mode == "full":
                edges = extract_internal_links(
                    raw_body,
                    int(c_id),
                    c_type,
                    forum_domains=_configured_domains(),
                )
                sync_existing_links(
                    content_item,
                    edges,
                    allow_disappearance=True,
                )
            return None

        with transaction.atomic():
            content_item.content_hash = new_hash

            post, _ = Post.objects.get_or_create(content_item=content_item)
            post.raw_bbcode = raw_body
            post.clean_text = clean_text
            post.char_count = len(clean_text)
            post.word_count = len(clean_text.split())
            post.xf_post_id = first_post_id
            post.save()

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
                    word_position=len(clean_text[:span.start_char].split()),
                )
                for span in spans
            ]
            Sentence.objects.bulk_create(sentence_objs)

            content_item.distilled_text = distill_body([item.text for item in sentence_objs], max_sentences=5)
            content_item.save(update_fields=["content_hash", "distilled_text", "updated_at"])

            edges = extract_internal_links(
                raw_body,
                int(c_id),
                c_type,
                forum_domains=_configured_domains(),
            )
            sync_existing_links(
                content_item,
                edges,
                allow_disappearance=(mode == "full"),
            )

        return content_item.pk

    try:
        if source == "api":
            xf_client = XenForoAPIClient()
            scopes = ScopeItem.objects.filter(is_enabled=True, scope_type__in=["node", "resource_category"])
            if scope_ids:
                scopes = scopes.filter(pk__in=scope_ids)

            total_scopes = max(scopes.count(), 1)
            for index, scope in enumerate(scopes, start=1):
                _publish_progress(
                    job_id,
                    "running",
                    ((index - 1) / total_scopes) * 0.7,
                    f"Syncing XenForo scope: {scope.title}",
                )
                if scope.scope_type == "node":
                    page = 1
                    while page <= _MAX_PAGES:
                        resp = xf_client.get_threads(scope.scope_id, page=page)
                        threads = resp.get("threads", [])
                        if not threads:
                            break
                        for thread in threads:
                            thread["content_type"] = "thread"
                            pk = _process_item(thread, scope)
                            if pk:
                                updated_pks.append(pk)
                                items_updated += 1
                        if items_synced % 25 == 0 and items_synced > 0:
                            _flush_job_progress()
                        if page >= resp.get("pagination", {}).get("last_page", 1):
                            break
                        page += 1
                else:
                    page = 1
                    while page <= _MAX_PAGES:
                        resp = xf_client.get_resources(scope.scope_id, page=page)
                        resources = resp.get("resources", [])
                        if not resources:
                            break
                        for resource in resources:
                            resource["content_type"] = "resource"
                            pk = _process_item(resource, scope)
                            if pk:
                                updated_pks.append(pk)
                                items_updated += 1
                                if mode == "full":
                                    try:
                                        updates_resp = xf_client.get_resource_updates(resource.get("resource_id"))
                                        update_list = updates_resp.get("resource_updates", []) or updates_resp.get("updates", [])
                                        if update_list:
                                            content_item = ContentItem.objects.get(pk=pk)
                                            post = content_item.post
                                            max_pos = (
                                                Sentence.objects.filter(post=post).aggregate(models.Max("position"))["position__max"]
                                                or 0
                                            )
                                            for update in update_list:
                                                update_body = update.get("message", "")
                                                if not update_body:
                                                    continue
                                                clean = clean_bbcode(update_body)
                                                sentence_objs: list[Sentence] = []
                                                for span in split_sentence_spans(clean):
                                                    max_pos += 1
                                                    sentence_objs.append(
                                                        Sentence(
                                                            content_item=content_item,
                                                            post=post,
                                                            text=span.text,
                                                            position=max_pos,
                                                            char_count=len(span.text),
                                                            start_char=span.start_char,
                                                            end_char=span.end_char,
                                                            word_position=post.word_count + 1,
                                                        )
                                                    )
                                                Sentence.objects.bulk_create(sentence_objs)
                                    except Exception as exc:
                                        logger.warning("Failed to fetch updates for resource %s: %s", resource.get("resource_id"), exc)
                        if items_synced % 25 == 0 and items_synced > 0:
                            _flush_job_progress()
                        if page >= resp.get("pagination", {}).get("last_page", 1):
                            break
                        page += 1

        elif source == "wp":
            wp_config = get_wordpress_runtime_config()
            client = WordPressAPIClient(
                base_url=wp_config["base_url"],
                username=wp_config["username"],
                app_password=wp_config["app_password"],
            )
            wp_scopes = {
                "wp_post": ScopeItem.objects.get_or_create(
                    scope_id=1,
                    scope_type="wp_posts",
                    defaults={"title": "WordPress Posts", "is_enabled": True},
                )[0],
                "wp_page": ScopeItem.objects.get_or_create(
                    scope_id=1,
                    scope_type="wp_pages",
                    defaults={"title": "WordPress Pages", "is_enabled": True},
                )[0],
            }
            for index, (content_type, label, iterator) in enumerate(
                [
                    ("wp_post", "WordPress posts", client.iter_posts()),
                    ("wp_page", "WordPress pages", client.iter_pages()),
                ],
                start=1,
            ):
                _publish_progress(job_id, "running", 0.1 + ((index - 1) / 2) * 0.5, f"Syncing {label}...")
                for item in iterator:
                    item["content_type"] = content_type
                    pk = _process_item(item, wp_scopes[content_type])
                    if pk:
                        updated_pks.append(pk)
                        items_updated += 1
                    if items_synced % 25 == 0 and items_synced > 0:
                        _flush_job_progress()

        elif source == "jsonl":
            if not file_path:
                raise ValueError("file_path is required for JSONL import.")
            for item in import_from_jsonl(file_path):
                scope_id = item.get("scope_id")
                scope_type = item.get("scope_type", "node")
                if not scope_id:
                    continue
                scope, _ = ScopeItem.objects.get_or_create(
                    scope_id=scope_id,
                    scope_type=scope_type,
                    defaults={"title": f"Imported Scope {scope_id}"},
                )
                pk = _process_item(item, scope)
                if pk:
                    updated_pks.append(pk)
                    items_updated += 1
                if items_synced % 50 == 0 and items_synced > 0:
                    _flush_job_progress()
        else:
            raise ValueError(f"Unsupported import source '{source}'.")

        _update_scope_counts()

        if mode == "full" and source in {"api", "wp"}:
            _publish_progress(job_id, "running", 0.82, "Refreshing internal-link graph across indexed content...")
            refresh_existing_links()

        if updated_pks:
            unique_updated_pks = sorted(set(updated_pks))
            _publish_progress(job_id, "running", 0.87, f"Generating embeddings for {len(unique_updated_pks)} items...")
            generate_all_embeddings(unique_updated_pks)

        if mode in {"titles", "full"}:
            _publish_progress(job_id, "running", 0.93, "Recalculating March 2026 PageRank and velocity...")
            from apps.pipeline.services.weighted_pagerank import run_weighted_pagerank
            from apps.pipeline.services.velocity import run_velocity

            run_weighted_pagerank()
            run_velocity(reference_ts=int(time.time()))

        job.status = "completed"
        job.progress = 1.0
        job.completed_at = timezone.now()
        job.items_synced = items_synced
        job.items_updated = items_updated
        job.message = f"Import complete. {items_synced} synced, {items_updated} updated."
        job.save()
        _publish_progress(
            job_id,
            "completed",
            1.0,
            f"Content import complete ({source}). {items_synced} items synced, {items_updated} updated.",
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


@shared_task(bind=True, name="pipeline.scan_broken_links", queue="default")
def scan_broken_links(self, job_id: str | None = None) -> dict:
    """Scan live URLs referenced in content and persist broken-link findings."""
    from django.conf import settings

    from apps.content.models import Post
    from apps.graph.models import BrokenLink, ExistingLink
    from apps.pipeline.services.link_parser import extract_urls

    job_id = job_id or str(uuid.uuid4())
    _publish_progress(job_id, "running", 0.0, "Collecting URLs for broken-link scan...")

    allowed_domains: list[str] | None = None
    for raw_url in [getattr(settings, "XENFORO_BASE_URL", ""), getattr(settings, "WORDPRESS_BASE_URL", "")]:
        host = urlparse(raw_url).netloc.strip().lower()
        if host:
            if allowed_domains is None:
                allowed_domains = []
            if host not in allowed_domains:
                allowed_domains.append(host)

    urls_to_scan: dict[tuple[int, str], dict[str, Any]] = {}
    hit_scan_cap = False

    existing_links = (
        ExistingLink.objects
        .select_related("from_content_item", "to_content_item")
        .filter(from_content_item__is_deleted=False)
        .exclude(to_content_item__url="")
        .order_by("from_content_item_id", "to_content_item_id")
    )
    for link in existing_links.iterator(chunk_size=250):
        if len(urls_to_scan) >= _MAX_BROKEN_LINK_SCAN_URLS:
            hit_scan_cap = True
            break
        urls_to_scan.setdefault(
            (link.from_content_item_id, link.to_content_item.url),
            {"source_content": link.from_content_item, "url": link.to_content_item.url},
        )

    if not hit_scan_cap:
        posts = (
            Post.objects
            .select_related("content_item")
            .filter(content_item__is_deleted=False)
            .exclude(raw_bbcode="")
            .order_by("content_item_id")
        )
        for post in posts.iterator(chunk_size=100):
            if len(urls_to_scan) >= _MAX_BROKEN_LINK_SCAN_URLS:
                hit_scan_cap = True
                break
            for url in extract_urls(post.raw_bbcode, allowed_domains=allowed_domains):
                urls_to_scan.setdefault((post.content_item_id, url), {"source_content": post.content_item, "url": url})
                if len(urls_to_scan) >= _MAX_BROKEN_LINK_SCAN_URLS:
                    hit_scan_cap = True
                    break

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

    flagged_urls = 0
    fixed_urls = 0
    with requests.Session() as session:
        session.headers.update({"User-Agent": "XF Internal Linker V2 Broken Link Scanner"})
        for index, scan_item in enumerate(urls_to_scan.values(), start=1):
            source_content = scan_item["source_content"]
            url = scan_item["url"]
            http_status, redirect_url = _probe_link_health(session, url)
            existing_record = (
                BrokenLink.objects.filter(source_content=source_content, url=url).values("status", "notes").first()
            )
            issue_detected = http_status == 0 or bool(redirect_url) or http_status >= 400
            if issue_detected:
                record_status = BrokenLink.STATUS_IGNORED if existing_record and existing_record["status"] == BrokenLink.STATUS_IGNORED else BrokenLink.STATUS_OPEN
                BrokenLink.objects.update_or_create(
                    source_content=source_content,
                    url=url,
                    defaults={
                        "http_status": http_status,
                        "redirect_url": redirect_url,
                        "status": record_status,
                        "notes": existing_record["notes"] if existing_record else "",
                    },
                )
                flagged_urls += 1
            elif existing_record:
                BrokenLink.objects.update_or_create(
                    source_content=source_content,
                    url=url,
                    defaults={
                        "http_status": http_status,
                        "redirect_url": "",
                        "status": BrokenLink.STATUS_FIXED,
                        "notes": existing_record["notes"],
                    },
                )
                fixed_urls += 1

            _publish_progress(
                job_id,
                "running",
                index / total_urls,
                f"Checked {index}/{total_urls}: {_status_label(http_status)}",
                scanned_urls=index,
                total_urls=total_urls,
                flagged_urls=flagged_urls,
                fixed_urls=fixed_urls,
                current_url=url,
                hit_scan_cap=hit_scan_cap,
            )
            if index < total_urls:
                time.sleep(_BROKEN_LINK_SCAN_DELAY_SECONDS)

    completion_message = (
        f"Broken link scan complete. {flagged_urls} issue(s) flagged, {fixed_urls} previously flagged link(s) resolved."
    )
    if hit_scan_cap:
        completion_message += f" Scan stopped at the {_MAX_BROKEN_LINK_SCAN_URLS:,} URL safety cap."
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
    )
    return {
        "job_id": job_id,
        "scanned_urls": total_urls,
        "flagged_urls": flagged_urls,
        "fixed_urls": fixed_urls,
        "hit_scan_cap": hit_scan_cap,
    }


@shared_task(bind=True, name="pipeline.verify_suggestions")
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
            _publish_progress(job_id, "running", index / total, f"Checking suggestion {str(suggestion.suggestion_id)[:8]}...")
            host_content = suggestion.host
            if not host_content or not host_content.xf_post_id:
                logger.warning("Suggestion %s host has no xf_post_id", suggestion.suggestion_id)
                continue
            try:
                raw_bbcode = client.get_post(host_content.xf_post_id).get("post", {}).get("message", "")
                destination_url = suggestion.destination.url
                if not destination_url:
                    logger.warning("Suggestion %s destination has no URL", suggestion.suggestion_id)
                    continue
                if destination_url in raw_bbcode:
                    suggestion.status = "verified"
                    suggestion.verified_at = timezone.now()
                    suggestion.save(update_fields=["status", "verified_at", "updated_at"])
                    verified += 1
                else:
                    suggestion.status = "stale"
                    suggestion.stale_reason = "Link not found in host post body"
                    suggestion.save(update_fields=["status", "stale_reason", "updated_at"])
                    stale += 1
            except Exception as exc:
                logger.error("Failed to fetch host post for suggestion %s: %s", suggestion.suggestion_id, exc)
                continue

        _publish_progress(job_id, "completed", 1.0, f"Verification complete. {verified} verified, {stale} stale.")
        return {"verified": verified, "stale": stale, "job_id": job_id}
    except Exception as exc:
        logger.exception("Verification %s failed", job_id)
        _publish_progress(job_id, "failed", 0.0, f"Verification failed: {exc}", error=str(exc))
        raise


@shared_task(bind=True, name="pipeline.recalculate_click_distance")
def recalculate_click_distance_task(self, job_id: str | None = None) -> dict:
    """Recompute Phase 15 Click-Distance scores for all active ContentItems."""
    job_id = job_id or str(uuid.uuid4())
    _publish_progress(job_id, "running", 0.0, "Starting Click-Distance structural prior recalculation...")

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
    except Exception as exc:
        logger.exception("Click-Distance recalculation %s failed", job_id)
        _publish_progress(job_id, "failed", 0.0, f"Click-Distance recalculation failed: {exc}", error=str(exc))
        raise


def _probe_link_health(session: requests.Session, url: str) -> tuple[int, str]:
    """Check a URL with HEAD first, then GET when HEAD is not supported."""
    try:
        response = session.head(url, allow_redirects=False, timeout=_BROKEN_LINK_SCAN_TIMEOUT_SECONDS)
        if response.status_code in {405, 501}:
            response = session.get(url, allow_redirects=False, timeout=_BROKEN_LINK_SCAN_TIMEOUT_SECONDS)
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


@shared_task(name="pipeline.run_clustering_pass")
def run_clustering_pass(job_id: str | None = None) -> dict:
    """Run a batch clustering pass over all ContentItems with embeddings."""
    from apps.content.models import ContentItem
    from apps.content.services.clustering import ClusteringService

    if not job_id:
        job_id = f"clustering_{int(time.time())}"

    logger.info("Starting batch clustering pass [%s]", job_id)
    _publish_progress(job_id, "running", 0.0, "Starting batch clustering pass...")

    # Filter items that have embeddings
    items = ContentItem.objects.filter(embedding__isnull=False).only("id", "embedding", "cluster_id")
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
            _publish_progress(job_id, "running", pct, f"Clustered {processed}/{total} items...")

    logger.info("Batch clustering pass [%s] complete. Processed %d items.", job_id, processed)
    _publish_progress(job_id, "completed", 1.0, f"Clustering complete. Processed {processed} items.")

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
            return {"status": "skipped", "reason": "R analytics stub — no candidate weights returned."}

        # ── Step 2: compare candidate to current weights ───────────────────
        current_weights = get_current_weights()
        changed_keys = {
            k for k, v in candidate_weights.items()
            if abs(float(v) - float(current_weights.get(k, v))) > CHANGE_THRESHOLD
        }
        if not changed_keys:
            logger.info("[monthly_r_auto_tune] Candidate weights within threshold — no change applied.")
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

    except Exception:
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

@shared_task(name="pipeline.nightly_data_retention")
def nightly_data_retention():
    """Purge stale data rows according to the retention policy.

    Scheduled daily at 03:00 UTC.

    Retention policy:
        SearchMetric rows       — 12 months
        PipelineRun logs        — 90 days
        ImpactReport            — FOREVER (never purged)
        Suggestion              — FOREVER (never purged)
        WeightAdjustmentHistory — FOREVER (never purged)
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
        logger.info("[nightly_data_retention] Deleted %d SearchMetric rows older than 12 months.", deleted)
    except Exception:
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
        logger.info("[nightly_data_retention] Deleted %d PipelineRun rows older than 90 days.", deleted)
    except Exception:
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
        logger.info("[nightly_data_retention] Deleted %d ContentMetricSnapshot rows (keeping last 2 per item).", deleted)
    except Exception:
        raw = traceback.format_exc()
        logger.exception("[nightly_data_retention] ContentMetricSnapshot purge failed.")
        ErrorLog.objects.create(
            job_type="data_retention",
            step="metric_snapshot_purge",
            error_message="ContentMetricSnapshot retention purge failed.",
            raw_exception=raw,
            why="Check database connectivity and the content.ContentMetricSnapshot table.",
        )

    logger.info("[nightly_data_retention] Complete. Results: %s", results)
    return results
