"""Parsing and persistence helpers for the import pipeline.

Split from ``tasks_import.py`` -- pure structural refactoring, no behavior
change.  Every function here was previously in ``tasks_import.py``.
"""

from __future__ import annotations

import logging
from html import unescape
from typing import Any, NamedTuple

from apps.ops_feed.services import emit

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


# ---------------------------------------------------------------------------
# XenForo sampling logic (FR-053 Head-Tail)
# ---------------------------------------------------------------------------


_THREAD_HEAD_PAGES = 20
_THREAD_TAIL_PAGES = 10


def _absorb_posts_dedup(
    posts: list[dict[str, Any]],
    seen_post_ids: set[int],
    messages: list[str],
) -> None:
    """Append messages from a posts list into ``messages``, skipping ids already seen."""
    for post in posts:
        p_id = post.get("post_id")
        if p_id and p_id not in seen_post_ids:
            messages.append(post.get("message", ""))
            seen_post_ids.add(p_id)


def _fetch_and_absorb_page(
    xf_client: Any,
    thread_id: int,
    page_num: int,
    seen_post_ids: set[int],
    messages: list[str],
) -> None:
    """Fetch one page from the XenForo API and absorb its posts into the running list."""
    p_resp = xf_client.get_posts(thread_id, page=page_num)
    _absorb_posts_dedup(p_resp.get("posts", []), seen_post_ids, messages)


def _emit_thread_body_failure(thread_id: int, exc: Exception, msg: str) -> None:
    """Emit a structured failure event when the Head-Tail fetch raises (caller logs)."""
    emit(
        "import.thread_body_failed",
        msg,
        source="import",
        severity="error",
        related_entity_type="thread",
        related_entity_id=str(thread_id),
        runtime_context={"error": str(exc)},
    )


def _fetch_thread_full_body(xf_client: Any, thread_id: int) -> str:
    """Fetch thread posts using Head-Tail sampling strategy.

    Strategy (FR-053): first 20 pages (head) capture core context + SEO signals;
    last 10 pages (tail) capture freshest updates and active sentiment; the middle
    is skipped to balance context coverage with performance on long threads.
    Returns the combined BBCode message body.
    """
    if not thread_id:
        return ""
    messages: list[str] = []
    seen_post_ids: set[int] = set()
    try:
        resp = xf_client.get_posts(thread_id, page=1)
        last_page = int(resp.get("pagination", {}).get("last_page", 1))
        posts_p1 = resp.get("posts", [])
        if not posts_p1:
            return ""
        _absorb_posts_dedup(posts_p1, seen_post_ids, messages)
        head_limit = min(_THREAD_HEAD_PAGES, last_page)
        for p in range(2, head_limit + 1):
            _fetch_and_absorb_page(xf_client, thread_id, p, seen_post_ids, messages)
        if last_page > head_limit:
            tail_start = max(head_limit + 1, last_page - (_THREAD_TAIL_PAGES - 1))
            for p in range(tail_start, last_page + 1):
                _fetch_and_absorb_page(xf_client, thread_id, p, seen_post_ids, messages)
        return "\n\n".join(filter(None, messages))
    except Exception as exc:
        msg = f"Failed to fetch full body for thread {thread_id}: {exc}"
        logger.error(msg, exc_info=True)
        _emit_thread_body_failure(thread_id, exc, msg)
        return ""


def _extract_xf_fields(item_data: dict[str, Any], c_type: str) -> dict[str, Any]:
    """Pure metadata extraction from a XenForo item dict (no I/O, no defaults beyond fallbacks)."""
    c_id = (
        item_data.get("thread_id")
        if c_type == "thread"
        else item_data.get("resource_id")
    )
    if not c_id:
        c_id = item_data.get("content_id")
    raw_body = (
        item_data.get("message")
        or item_data.get("post_body")
        or item_data.get("description")
        or item_data.get("tag_line")
        or item_data.get("raw_body")
        or ""
    )
    return {
        "c_id": c_id,
        "first_post_id": item_data.get("first_post_id"),
        "title": plain_title(item_data.get("title")),
        "view_url": item_data.get("view_url") or item_data.get("url", ""),
        "raw_body": raw_body,
        "view_count": int(item_data.get("view_count") or 0),
        "reply_count": int(item_data.get("reply_count") or 0),
        "download_count": int(item_data.get("download_count") or 0),
    }


def _maybe_fetch_thread_body(
    state: Any,
    c_type: str,
    raw_body: str,
    c_id: int | None,
    xf_client: Any | None,
) -> tuple[str, Any | None]:
    """Lazily init the XF API client and fetch the full thread body when raw_body is empty."""
    if raw_body or state.mode != "full" or state.source != "api" or c_type != "thread":
        return raw_body, xf_client
    from apps.sync.services.xenforo_api import XenForoAPIClient

    if xf_client is None:
        xf_client = XenForoAPIClient()
    return _fetch_thread_full_body(xf_client, c_id), xf_client


def _parse_xf_item(
    item_data: dict[str, Any],
    c_type: str,
    state: Any,
    xf_client: Any | None,
) -> tuple[_ParsedItem, Any | None]:
    """Extract metadata from a XenForo API item dict; returns parsed item + xf_client."""
    fields = _extract_xf_fields(item_data, c_type)
    raw_body, xf_client = _maybe_fetch_thread_body(
        state, c_type, fields["raw_body"], fields["c_id"], xf_client
    )
    parsed = _ParsedItem(
        c_id=fields["c_id"],
        first_post_id=fields["first_post_id"],
        title=fields["title"],
        view_url=fields["view_url"],
        raw_body=raw_body,
        view_count=fields["view_count"],
        reply_count=fields["reply_count"],
        download_count=fields["download_count"],
        post_date=None,
        last_post_date=None,
    )
    return parsed, xf_client


# ---------------------------------------------------------------------------
# DB persistence helpers
# ---------------------------------------------------------------------------


_CONTENT_ITEM_UPDATE_FIELDS = [
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


def _apply_parsed_fields(
    content_item: Any,
    parsed: _ParsedItem,
    current_scope: Any,
    canonical_url: str,
) -> None:
    """Copy parsed metadata onto the ContentItem and save the canonical 11-field set."""
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
    content_item.save(update_fields=_CONTENT_ITEM_UPDATE_FIELDS)


def _mark_bloom_filter_safe(pk: int) -> None:
    """Mark a primary key in the in-process Bloom-filter registry; swallow + log on failure.

    Pick #4 — keep the Bloom-filter registry warm. ``mark`` is O(1) and forgives a
    missing snapshot (creates an empty filter on first call), so the importer doesn't
    have to special-case cold start. The W1 ``bloom_filter_ids_rebuild`` scheduled job
    is the durable source of truth; marking inline here keeps consumers current within
    a session.
    """
    from apps.sources.bloom_filter_registry import REGISTRY as BLOOM_REGISTRY

    try:
        BLOOM_REGISTRY.mark(pk)
    except Exception:
        logger.debug(
            "BloomFilterRegistry.mark failed for pk=%s — continuing import",
            pk,
            exc_info=True,
        )


def _upsert_content_item(
    parsed: _ParsedItem,
    c_type: str,
    current_scope: Any,
) -> Any:
    """Create or fully update a ``ContentItem`` row and return it."""
    from apps.content.models import ContentItem
    from apps.pipeline.services.link_parser import normalize_internal_url

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
    _apply_parsed_fields(content_item, parsed, current_scope, canonical_url)
    _mark_bloom_filter_safe(content_item.pk)
    return content_item


_PERSIST_CONTENT_ITEM_UPDATE_FIELDS = [
    "content_hash",
    "content_version",
    "embedding_model_version",
    "embedding_text_hash",
    "distilled_text",
    "salient_entities",
    "passages",
    "duplicate_of",
    "quotation_density",
    "nlp_metadata",
    "char_ngram_vector",
    "updated_at",
]


def _bump_content_version(content_item: Any, new_hash: str) -> None:
    """Reset embedding state and bump the content version after a body change."""
    content_item.content_hash = new_hash
    content_item.content_version += 1
    content_item.embedding_model_version = ""
    content_item.embedding_text_hash = ""


def _set_quotation_density_safe(content_item: Any, raw_body: str) -> None:
    """Capture quotation density from raw BBCode; fall back to 0.0 on any failure."""
    try:
        from apps.pipeline.services.text_cleaner import compute_quotation_density

        content_item.quotation_density = compute_quotation_density(raw_body)
    except Exception:
        logger.debug(
            "compute_quotation_density failed for content_item=%s — falling back to 0.0",
            getattr(content_item, "pk", None),
            exc_info=True,
        )
        content_item.quotation_density = 0.0


def _apply_cross_source_dedup(content_item: Any, new_hash: str) -> None:
    """Link to or unlink from the canonical duplicate row based on content hash."""
    from apps.content.identity import find_cross_source_duplicate

    canonical = find_cross_source_duplicate(
        content_hash=new_hash,
        exclude_id=content_item.pk,
    )
    if canonical is not None and canonical.pk != getattr(
        content_item, "duplicate_of_id", None
    ):
        content_item.duplicate_of = canonical
    elif canonical is None and content_item.duplicate_of_id:
        content_item.duplicate_of = None


def _upsert_post_with_readability(
    content_item: Any,
    raw_body: str,
    clean_text: str,
    first_post_id: int | None,
) -> Any:
    """Get-or-create the Post, score readability, save the row, return the Post."""
    from apps.content.models import Post
    from apps.sources.readability import score as readability_score

    readability = readability_score(clean_text)
    post, _ = Post.objects.get_or_create(content_item=content_item)
    post.raw_bbcode = raw_body
    post.clean_text = clean_text
    post.char_count = len(clean_text)
    post.word_count = len(clean_text.split())
    post.xf_post_id = first_post_id
    post.flesch_kincaid_grade = readability.flesch_kincaid_grade
    post.gunning_fog_grade = readability.gunning_fog
    post.save(
        update_fields=[
            "raw_bbcode",
            "clean_text",
            "char_count",
            "word_count",
            "xf_post_id",
            "flesch_kincaid_grade",
            "gunning_fog_grade",
        ]
    )
    return post


def _set_salient_entities_safe(content_item: Any, doc: Any) -> None:
    """Rank top-K entities from a spaCy Doc; fall back to [] on missing Doc or any error."""
    from apps.sources.entity_salience import rank_entities

    if doc is None:
        content_item.salient_entities = []
        return
    try:
        ranked = rank_entities(doc, title=content_item.title or None, top_k=10)
        content_item.salient_entities = [
            {
                "text": e.text,
                "label": e.label,
                "salience": e.salience,
                "mention_count": e.mention_count,
            }
            for e in ranked
        ]
    except Exception:
        logger.exception(
            "rank_entities failed for content_item=%s; leaving salient_entities unchanged",
            content_item.pk,
        )


def _set_nlp_enrichment_safe(content_item: Any, clean_text: str, doc: Any) -> None:
    """Run NLPEnricher and store enriched metadata; fall back to empty dict on any error."""
    from apps.pipeline.services.nlp_enrichment import NLPEnricher

    try:
        enricher = NLPEnricher()
        enriched, char_ngram_vector, _token_data = enricher.enrich(clean_text, doc=doc)
        content_item.nlp_metadata = {
            "lemmas": enriched.lemmas,
            "noun_chunks": enriched.noun_chunks,
            "acronyms": enriched.acronyms,
            "lexical_richness": enriched.lexical_richness,
            "minhash_sketch": enriched.minhash_sketch,
            "phonetic_keys": enriched.phonetic_keys,
            "summary": enriched.summary,
        }
        content_item.char_ngram_vector = char_ngram_vector
    except Exception:
        logger.exception(
            "NLP enrichment failed for content_item=%s; leaving nlp_metadata empty",
            content_item.pk,
        )
        content_item.nlp_metadata = {}
        content_item.char_ngram_vector = None


def _build_sentence_objs(content_item: Any, post: Any, spans: Any, clean_text: str) -> list[Any]:
    """Build (unsaved) Sentence objects from sentence spans, preserving char/word positions."""
    from apps.content.models import Sentence

    return [
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


def _build_token_objs(created_sentences: list[Any], doc: Any) -> list[Any]:
    """Map every saved Sentence's char range back to spaCy tokens, return unsaved Token objects."""
    from apps.content.models import Token

    token_objs: list[Any] = []
    for sent_obj in created_sentences:
        span = doc.char_span(sent_obj.start_char, sent_obj.end_char)
        if span is None:
            continue
        for token in span:
            token_objs.append(
                Token(
                    sentence=sent_obj,
                    text=token.text,
                    lemma=token.lemma_,
                    pos=token.pos_,
                    is_stop=token.is_stop,
                    start_char=token.idx - sent_obj.start_char,
                    end_char=token.idx + len(token.text) - sent_obj.start_char,
                )
            )
    return token_objs


def _persist_sentences_and_tokens(
    content_item: Any,
    post: Any,
    spans: Any,
    clean_text: str,
    doc: Any,
) -> list[Any]:
    """Wipe + bulk_create Sentence rows; bulk_create Tokens when a Doc is available."""
    from django.db import transaction

    from apps.content.models import Sentence, Token

    sentence_objs = _build_sentence_objs(content_item, post, spans, clean_text)
    with transaction.atomic():
        Sentence.objects.filter(content_item=content_item).delete()
        created_sentences = Sentence.objects.bulk_create(sentence_objs)
        if doc is not None:
            Token.objects.bulk_create(_build_token_objs(created_sentences, doc))
    return sentence_objs


def _set_passages_safe(content_item: Any, sentence_objs: list[Any]) -> None:
    """Segment passages from the sentence list; leave attribute unchanged on any failure."""
    try:
        from apps.sources.passages import segment_from_sentences

        passage_records = segment_from_sentences([s.text for s in sentence_objs])
        content_item.passages = [
            {
                "index": p.index,
                "text": p.text,
                "token_count": p.token_count,
                "token_start": p.token_start,
                "token_end": p.token_end,
            }
            for p in passage_records
        ]
    except Exception:
        logger.exception(
            "segment_from_sentences failed for content_item=%s; leaving passages unchanged",
            content_item.pk,
        )


def _persist_content_body(
    content_item: Any,
    raw_body: str,
    clean_text: str,
    new_hash: str,
    first_post_id: int | None,
) -> None:
    """Save Post, Sentences, distilled text, and entity salience.

    Pick #19 readability + Pick #26 entity salience + Pick #25 passages + Pick #54
    token persistence + Group A.6 cross-source dedup + Group D.4 quotation density +
    Group G (Harmonious-12) NLP enrichment all share one spaCy Doc parse.
    """
    from django.db import transaction

    from apps.pipeline.services.distiller import distill_body
    from apps.pipeline.services.sentence_splitter import split_sentence_spans_with_doc

    with transaction.atomic():
        _bump_content_version(content_item, new_hash)
        _set_quotation_density_safe(content_item, raw_body)
        _apply_cross_source_dedup(content_item, new_hash)
        post = _upsert_post_with_readability(
            content_item, raw_body, clean_text, first_post_id
        )
        spans, doc = split_sentence_spans_with_doc(clean_text)
        _set_salient_entities_safe(content_item, doc)
        _set_nlp_enrichment_safe(content_item, clean_text, doc)
        sentence_objs = _persist_sentences_and_tokens(
            content_item, post, spans, clean_text, doc
        )
        content_item.distilled_text = distill_body(
            [s.text for s in sentence_objs], max_sentences=5
        )
        _set_passages_safe(content_item, sentence_objs)
        content_item.save(update_fields=_PERSIST_CONTENT_ITEM_UPDATE_FIELDS)


# ---------------------------------------------------------------------------
# Resource-update sub-handler for XenForo resources.
# ---------------------------------------------------------------------------
def _build_update_sentences(
    content_item: Any,
    post: Any,
    update_body: str,
    base_position: int,
) -> tuple[list[Any], int]:
    """Clean BBCode + split into sentences; return (sentence_list, new_max_position).

    Pure transformer — no DB writes. ``base_position`` is the highest existing
    Sentence.position for the post; the returned sentences receive consecutive
    positions starting at ``base_position + 1``.
    """
    from apps.content.models import Sentence
    from apps.pipeline.services.sentence_splitter import split_sentence_spans
    from apps.pipeline.services.text_cleaner import clean_bbcode

    sentence_objs: list[Sentence] = []
    max_pos = base_position
    for span in split_sentence_spans(clean_bbcode(update_body)):
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
    return sentence_objs, max_pos


def _emit_resource_updates_failure(
    resource: dict[str, Any],
    exc: Exception,
    msg: str,
) -> None:
    """Emit a structured warning when the resource-updates fetch raises (caller logs)."""
    emit(
        "import.resource_updates_failed",
        msg,
        source="import",
        severity="warning",
        related_entity_type="resource",
        related_entity_id=str(resource.get("resource_id")),
        runtime_context={"error": str(exc)},
    )


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
            sentence_objs, max_pos = _build_update_sentences(
                content_item, post, update_body, max_pos
            )
            Sentence.objects.bulk_create(sentence_objs)
    except (TimeoutError, RequestException, URLError) as exc:
        msg = f"Failed to fetch updates for resource {resource.get('resource_id')}: {exc}"
        logger.warning(msg)
        _emit_resource_updates_failure(resource, exc, msg)


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
