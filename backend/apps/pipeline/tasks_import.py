"""Main import functions for the import_content Celery task.

Pure structural refactoring -- no behavior change.  Parsing and persistence
helpers live in ``tasks_import_helpers.py``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from apps.pipeline.tasks_import_helpers import (
    _maybe_flush_and_checkpoint,
    _parse_wp_item,
    _parse_xf_item,
    _persist_content_body,
    _upsert_content_item,
    handle_resource_updates,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Shared state bag passed between helpers so we avoid ``nonlocal`` closures.
# ---------------------------------------------------------------------------
@dataclass
class ImportState:
    """Mutable accumulator carried through an import run."""

    job_id: str = ""
    source: str = "api"
    mode: str = "full"
    force_reembed: bool = False
    items_synced: int = 0
    items_updated: int = 0
    updated_pks: list[int] = field(default_factory=list)
    touched_scope_ids: set[int] = field(default_factory=set)
    resume_last_item_id: int | None = None
    resume_stage: str = ""


# ---------------------------------------------------------------------------
# process_import_item  (main orchestrator -- delegates to helpers)
# ---------------------------------------------------------------------------
def process_import_item(
    item_data: dict[str, Any],
    current_scope: Any,
    state: ImportState,
    xf_client: Any | None,
) -> tuple[int | None, Any | None]:
    """Process a single content item and return ``(pk_or_none, xf_client)``.

    The caller must write ``xf_client`` back into its own local variable
    because we may lazily initialise it here.
    """
    from apps.graph.services.graph_sync import sync_existing_links_for_content_item
    from apps.pipeline.services.text_cleaner import (
        clean_import_text,
        generate_content_hash,
    )

    state.items_synced += 1
    state.touched_scope_ids.add(current_scope.pk)

    c_type = str(item_data.get("content_type", "thread"))

    # -- 1. Parse source-specific fields ------------------------------------
    if state.source == "wp":
        parsed = _parse_wp_item(item_data)
    else:
        parsed, xf_client = _parse_xf_item(item_data, c_type, state, xf_client)

    if not parsed.c_id:
        return None, xf_client

    # -- 2. Upsert the ContentItem row --------------------------------------
    content_item = _upsert_content_item(parsed, c_type, current_scope)

    # FR-097: Skip items already processed before the checkpoint.
    if (
        state.resume_last_item_id is not None
        and state.resume_stage == "ingest"
        and content_item.pk <= state.resume_last_item_id
    ):
        return None, xf_client

    if not parsed.raw_body:
        return None, xf_client

    # -- 3. Check content hash for changes ----------------------------------
    clean_text = clean_import_text(parsed.raw_body)
    new_hash = generate_content_hash(parsed.title, clean_text)
    if content_item.content_hash == new_hash:
        if state.mode == "full":
            sync_existing_links_for_content_item(
                content_item,
                parsed.raw_body,
                allow_disappearance=True,
            )
        return (content_item.pk if state.force_reembed else None), xf_client

    # -- 4. Persist body, sentences, and distilled text ---------------------
    _persist_content_body(
        content_item, parsed.raw_body, clean_text, new_hash, parsed.first_post_id
    )

    sync_existing_links_for_content_item(
        content_item,
        parsed.raw_body,
        allow_disappearance=(state.mode == "full"),
    )

    return content_item.pk, xf_client


# ---------------------------------------------------------------------------
# Per-source import dispatchers.
# ---------------------------------------------------------------------------
_MAX_PAGES = 500


def import_xenforo_scopes(
    state: ImportState,
    job: Any,
    scope_ids: list[int] | None,
    publish_progress: Any,
) -> None:
    """Import content from XenForo API (threads and resources)."""
    from apps.content.models import ScopeItem
    from apps.sync.services.xenforo_api import XenForoAPIClient

    xf_client = XenForoAPIClient()
    scopes = ScopeItem.objects.filter(
        is_enabled=True, scope_type__in=["node", "resource_category"]
    )
    if scope_ids:
        scopes = scopes.filter(pk__in=scope_ids)

    total_scopes = max(scopes.count(), 1)
    for index, scope in enumerate(scopes, start=1):
        publish_progress(
            state.job_id,
            "running",
            ((index - 1) / total_scopes) * 0.7,
            f"Syncing XenForo scope: {scope.title}",
        )
        if scope.scope_type == "node":
            _import_xenforo_threads(state, job, scope, xf_client, publish_progress)
        else:
            _import_xenforo_resources(state, job, scope, xf_client, publish_progress)


def _import_xenforo_threads(
    state: ImportState,
    job: Any,
    scope: Any,
    xf_client: Any,
    publish_progress: Any,
) -> None:
    """Paginate through XenForo threads for a single forum node."""
    page = 1
    while page <= _MAX_PAGES:
        resp = xf_client.get_threads(scope.scope_id, page=page)
        threads = resp.get("threads", [])
        if not threads:
            break
        for thread in threads:
            thread["content_type"] = "thread"
            pk, xf_client = process_import_item(thread, scope, state, xf_client)
            if pk:
                state.updated_pks.append(pk)
                state.items_updated += 1
        _maybe_flush_and_checkpoint(state, job)
        if page >= resp.get("pagination", {}).get("last_page", 1):
            break
        page += 1


def _import_xenforo_resources(
    state: ImportState,
    job: Any,
    scope: Any,
    xf_client: Any,
    publish_progress: Any,
) -> None:
    """Paginate through XenForo resources for a single resource category."""
    page = 1
    while page <= _MAX_PAGES:
        resp = xf_client.get_resources(scope.scope_id, page=page)
        resources = resp.get("resources", [])
        if not resources:
            break
        for resource in resources:
            resource["content_type"] = "resource"
            pk, xf_client = process_import_item(resource, scope, state, xf_client)
            if pk:
                state.updated_pks.append(pk)
                state.items_updated += 1
                if state.mode == "full":
                    handle_resource_updates(xf_client, resource, pk)
        _maybe_flush_and_checkpoint(state, job)
        if page >= resp.get("pagination", {}).get("last_page", 1):
            break
        page += 1


def import_wordpress_content(
    state: ImportState,
    job: Any,
    publish_progress: Any,
) -> None:
    """Import content from WordPress REST API (posts and pages)."""
    from apps.content.models import ScopeItem
    from apps.core.views import get_wordpress_runtime_config
    from apps.sync.models import SyncJob
    from apps.sync.services.wordpress_api import WordPressAPIClient

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

    last_sync_date = ""
    if state.mode != "full":
        last_job = SyncJob.objects.filter(source="wp", status="completed").first()
        if last_job and last_job.completed_at:
            last_sync_date = last_job.completed_at.isoformat()
            logger.info(
                "Using incremental sync for WordPress: after=%s", last_sync_date
            )

    for index, (content_type, label, iterator) in enumerate(
        [
            ("wp_post", "WordPress posts", client.iter_posts(after=last_sync_date)),
            ("wp_page", "WordPress pages", client.iter_pages(after=last_sync_date)),
        ],
        start=1,
    ):
        publish_progress(
            state.job_id,
            "running",
            0.1 + ((index - 1) / 2) * 0.5,
            f"Syncing {label}...",
        )
        for item in iterator:
            item["content_type"] = content_type
            pk, _ = process_import_item(item, wp_scopes[content_type], state, None)
            if pk:
                state.updated_pks.append(pk)
                state.items_updated += 1
            _maybe_flush_and_checkpoint(state, job)


def import_jsonl_content(
    state: ImportState,
    job: Any,
    file_path: str,
) -> None:
    """Import content from a JSONL file."""
    from apps.content.models import ScopeItem
    from apps.sync.services.jsonl_importer import import_from_jsonl

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
        pk, _ = process_import_item(item, scope, state, None)
        if pk:
            state.updated_pks.append(pk)
            state.items_updated += 1
        _maybe_flush_and_checkpoint(state, job, interval=50)


def update_scope_counts(touched_scope_ids: set[int]) -> None:
    """Recalculate content_count for every scope that was touched."""
    if not touched_scope_ids:
        return

    from django.db import models

    from apps.content.models import ContentItem, ScopeItem

    count_map = {
        row["scope_id"]: row["total"]
        for row in (
            ContentItem.objects.filter(scope_id__in=touched_scope_ids)
            .values("scope_id")
            .annotate(total=models.Count("pk"))
        )
    }
    scopes = list(ScopeItem.objects.filter(pk__in=touched_scope_ids))
    for scope in scopes:
        scope.content_count = count_map.get(scope.pk, 0)
    if scopes:
        ScopeItem.objects.bulk_update(scopes, ["content_count"])


def run_post_import_steps(
    state: ImportState,
    job_id: str,
    publish_progress: Any,
) -> None:
    """Run graph refresh, embeddings, PageRank, and velocity after import."""
    import time

    from apps.graph.services.graph_sync import refresh_existing_links
    from apps.pipeline.services.embeddings import generate_all_embeddings
    from apps.pipeline.tasks import _save_checkpoint

    if state.mode == "full" and state.source in {"api", "wp"}:
        if state.updated_pks:
            _save_checkpoint(
                job_id, "graph_sync", state.updated_pks[-1], state.items_synced
            )
        publish_progress(
            job_id,
            "running",
            0.82,
            "Refreshing internal-link graph across indexed content...",
        )
        refresh_existing_links()

    if state.updated_pks:
        unique_updated_pks = sorted(set(state.updated_pks))
        _save_checkpoint(job_id, "embed", unique_updated_pks[-1], state.items_synced)
        publish_progress(
            job_id,
            "running",
            0.87,
            f"Generating embeddings for {len(unique_updated_pks)} items...",
        )
        generate_all_embeddings(unique_updated_pks)

    if state.mode in {"titles", "full"}:
        publish_progress(
            job_id,
            "running",
            0.93,
            "Recalculating March 2026 PageRank and velocity...",
        )
        from apps.pipeline.services.velocity import run_velocity
        from apps.pipeline.services.weighted_pagerank import run_weighted_pagerank

        run_weighted_pagerank()
        run_velocity(reference_ts=int(time.time()))
