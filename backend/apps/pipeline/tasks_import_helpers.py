"""Parsing and persistence helpers for the import pipeline.

Split from ``tasks_import.py`` -- pure structural refactoring, no behavior
change.  Every function here was previously in ``tasks_import.py``.
"""

from __future__ import annotations

import logging
from html import unescape
from typing import Any, NamedTuple

logger = logging.getLogger(__name__)


class _ParsedItem(NamedTuple):
    """Intermediate bag of values extracted from a raw API item dict."""

    c_id: int | None
    first_post_id: int | None
    title: str
    view_url: str
    raw_body: str
    view_count: int
    reply_count: int
    download_count: int
    post_date: Any
    last_post_date: Any


# ---------------------------------------------------------------------------
# Tiny pure helpers
# ---------------------------------------------------------------------------
def plain_title(value: Any) -> str:
    """Return a plain-text title from a string or WP rendered dict."""
    if isinstance(value, dict):
        value = value.get("rendered", "")
    return str(unescape(value or "")).strip() or "Untitled"


def parse_wp_timestamp(value: str | None) -> Any:
    """Parse an ISO8601 timestamp as returned by the WordPress REST API."""
    from django.utils.dateparse import parse_datetime

    if not value:
        return None
    parsed = parse_datetime(value)
    if parsed is None:
        parsed = parse_datetime(f"{value}Z")
    return parsed


# ---------------------------------------------------------------------------
# Source-specific parsers
# ---------------------------------------------------------------------------


def _parse_wp_item(item_data: dict[str, Any]) -> _ParsedItem:
    """Extract metadata from a WordPress REST API item dict."""
    c_id = item_data.get("id")
    title = plain_title(item_data.get("title"))
    view_url = item_data.get("link", "")
    raw_body = item_data.get("content", {}).get("rendered", "") or item_data.get(
        "excerpt", {}
    ).get("rendered", "")
    post_date = parse_wp_timestamp(item_data.get("date_gmt") or item_data.get("date"))
    last_post_date = parse_wp_timestamp(
        item_data.get("modified_gmt") or item_data.get("modified")
    )
    return _ParsedItem(
        c_id=c_id,
        first_post_id=None,
        title=title,
        view_url=view_url,
        raw_body=raw_body,
        view_count=0,
        reply_count=0,
        download_count=0,
        post_date=post_date,
        last_post_date=last_post_date,
    )


def _parse_xf_item(
    item_data: dict[str, Any],
    c_type: str,
    state: Any,
    xf_client: Any | None,
) -> tuple[_ParsedItem, Any | None]:
    """Extract metadata from a XenForo API item dict.

    Returns the parsed item *and* the (possibly lazily initialised) xf_client.
    """
    from apps.sync.services.xenforo_api import XenForoAPIClient

    c_id = (
        item_data.get("thread_id")
        if c_type == "thread"
        else item_data.get("resource_id")
    )
    if not c_id:
        c_id = item_data.get("content_id")
    first_post_id = item_data.get("first_post_id")
    title = plain_title(item_data.get("title"))
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
    if (
        not raw_body
        and state.mode == "full"
        and state.source == "api"
        and c_type == "thread"
        and first_post_id
    ):
        if xf_client is None:
            xf_client = XenForoAPIClient()
        raw_body = xf_client.get_post(first_post_id).get("post", {}).get("message", "")

    parsed = _ParsedItem(
        c_id=c_id,
        first_post_id=first_post_id,
        title=title,
        view_url=view_url,
        raw_body=raw_body,
        view_count=view_count,
        reply_count=reply_count,
        download_count=download_count,
        post_date=None,
        last_post_date=None,
    )
    return parsed, xf_client


# ---------------------------------------------------------------------------
# DB persistence helpers
# ---------------------------------------------------------------------------


def _upsert_content_item(
    parsed: _ParsedItem,
    c_type: str,
    current_scope: Any,
) -> Any:
    """Create or fully update a ``ContentItem`` row and return it.

    Pick #4 — After the upsert succeeds we mark the resulting primary
    key in the Bloom-filter registry. The W1 ``bloom_filter_ids_rebuild``
    scheduled job is the durable source of truth (rebuilt weekly from
    the ContentItem table); marking inline here keeps the in-process
    filter current within a session so other consumers — diagnostics
    panels, future "is this a new id?" fast-skip paths in bulk
    importers — get accurate ``is_known`` answers without waiting for
    the next rebuild.
    """
    from apps.content.models import ContentItem
    from apps.pipeline.services.link_parser import normalize_internal_url
    from apps.sources.bloom_filter_registry import REGISTRY as BLOOM_REGISTRY

    canonical_url = normalize_internal_url(parsed.view_url) or parsed.view_url
    content_item, _ = ContentItem.objects.get_or_create(
        content_id=int(parsed.c_id),  # type: ignore[arg-type]
        content_type=c_type,
        defaults={
            "title": parsed.title,
            "scope": current_scope,
            "url": canonical_url,
            "xf_post_id": parsed.first_post_id,
            "post_date": parsed.post_date,
            "last_post_date": parsed.last_post_date,
        },
    )
    content_item.title = parsed.title
    content_item.scope = current_scope
    content_item.url = canonical_url
    content_item.view_count = parsed.view_count
    content_item.reply_count = parsed.reply_count
    content_item.download_count = parsed.download_count
    if parsed.post_date is not None:
        content_item.post_date = parsed.post_date
    if parsed.last_post_date is not None:
        content_item.last_post_date = parsed.last_post_date
    content_item.xf_post_id = parsed.first_post_id
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
    # Pick #4 — keep the Bloom-filter registry warm. ``mark`` is O(1)
    # and forgives a missing snapshot (creates an empty filter on first
    # call), so the importer doesn't have to special-case cold start.
    try:
        BLOOM_REGISTRY.mark(content_item.pk)
    except Exception:
        # The Bloom filter is an optimisation — never let it block an
        # import. The next weekly rebuild will pick the row up anyway.
        logger.debug(
            "BloomFilterRegistry.mark failed for pk=%s — continuing import",
            content_item.pk,
            exc_info=True,
        )
    return content_item


def _persist_content_body(
    content_item: Any,
    raw_body: str,
    clean_text: str,
    new_hash: str,
    first_post_id: int | None,
) -> None:
    """Save Post, Sentences, and distilled text inside a transaction."""
    from django.db import transaction

    from apps.content.models import Post, Sentence
    from apps.pipeline.services.distiller import distill_body
    from apps.pipeline.services.sentence_splitter import split_sentence_spans

    with transaction.atomic():
        content_item.content_hash = new_hash

        post, _ = Post.objects.get_or_create(content_item=content_item)
        post.raw_bbcode = raw_body
        post.clean_text = clean_text
        post.char_count = len(clean_text)
        post.word_count = len(clean_text.split())
        post.xf_post_id = first_post_id
        post.save(
            update_fields=[
                "raw_bbcode",
                "clean_text",
                "char_count",
                "word_count",
                "xf_post_id",
            ]
        )

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
                word_position=len(clean_text[: span.start_char].split()),
            )
            for span in spans
        ]

        with transaction.atomic():
            Sentence.objects.filter(content_item=content_item).delete()
            Sentence.objects.bulk_create(sentence_objs)

        content_item.distilled_text = distill_body(
            [s.text for s in sentence_objs], max_sentences=5
        )
        content_item.save(
            update_fields=["content_hash", "distilled_text", "updated_at"]
        )


# ---------------------------------------------------------------------------
# Resource-update sub-handler for XenForo resources.
# ---------------------------------------------------------------------------
def handle_resource_updates(
    xf_client: Any,
    resource: dict[str, Any],
    pk: int,
) -> None:
    """Fetch and ingest XenForo resource updates (changelog entries)."""
    from django.db import models
    from requests import RequestException
    from urllib.error import URLError

    from apps.content.models import ContentItem, Sentence
    from apps.pipeline.services.sentence_splitter import split_sentence_spans
    from apps.pipeline.services.text_cleaner import clean_bbcode

    try:
        updates_resp = xf_client.get_resource_updates(resource.get("resource_id"))
        update_list = updates_resp.get("resource_updates", []) or updates_resp.get(
            "updates", []
        )
        if not update_list:
            return

        content_item = ContentItem.objects.get(pk=pk)
        post = content_item.post
        max_pos = (
            Sentence.objects.filter(post=post).aggregate(models.Max("position"))[
                "position__max"
            ]
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
    except (TimeoutError, RequestException, URLError) as exc:
        logger.warning(
            "Failed to fetch updates for resource %s: %s",
            resource.get("resource_id"),
            exc,
        )


# ---------------------------------------------------------------------------
# Checkpoint flushing helper.
# ---------------------------------------------------------------------------
def _maybe_flush_and_checkpoint(
    state: Any,
    job: Any,
    interval: int = 25,
    stage: str = "ingest",
) -> None:
    """Flush job progress, save checkpoints, and honor safe pause requests."""
    from apps.core.pause_contract import JobPaused, should_pause_now
    from apps.pipeline.tasks import _save_checkpoint

    should_flush = state.items_synced % interval == 0 and state.items_synced > 0
    should_pause, pause_reason = should_pause_now(
        job_type="imports",
        job_id=str(state.job_id),
    )

    if should_flush or should_pause:
        job.items_synced = state.items_synced
        job.items_updated = state.items_updated
        job.save(update_fields=["items_synced", "items_updated", "updated_at"])
        if state.updated_pks:
            _save_checkpoint(
                state.job_id, stage, state.updated_pks[-1], state.items_synced
            )

    if should_pause:
        has_checkpoint = bool(state.updated_pks or getattr(job, "checkpoint_stage", ""))
        job.status = "paused"
        job.is_resumable = has_checkpoint
        job.message = f"Paused at safe checkpoint: {pause_reason}"
        job.save(update_fields=["status", "is_resumable", "message", "updated_at"])
        raise JobPaused(pause_reason)
