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


def _fetch_thread_full_body(xf_client: Any, thread_id: int) -> str:
    """Fetch thread posts using Head-Tail sampling strategy.

    Strategy (FR-053):
      - First 20 pages: Captures core context, original post, and SEO signals.
      - Last 10 pages: Captures latest updates, freshest keywords, and active sentiment.
      - Skip middle: Balances context coverage with performance for long-running threads.

    Returns the combined BBCode message body.
    """
    if not thread_id:
        return ""

    messages: list[str] = []
    seen_post_ids: set[int] = set()

    try:
        # 1. Fetch first page to get total pagination info
        resp = xf_client.get_posts(thread_id, page=1)
        pagination = resp.get("pagination", {})
        last_page = int(pagination.get("last_page", 1))
        
        posts_p1 = resp.get("posts", [])
        if not posts_p1:
            return ""

        def collect_posts(page_num: int) -> None:
            """Internal helper to fetch and deduplicate posts from a specific page."""
            p_resp = xf_client.get_posts(thread_id, page=page_num)
            for post in p_resp.get("posts", []):
                p_id = post.get("post_id")
                if p_id and p_id not in seen_post_ids:
                    messages.append(post.get("message", ""))
                    seen_post_ids.add(p_id)

        # Process first 20 pages (the "Head")
        head_limit = min(20, last_page)
        for p in range(1, head_limit + 1):
            if p == 1:
                # Reuse the already fetched page 1 data
                for post in posts_p1:
                    p_id = post.get("post_id")
                    if p_id:
                        messages.append(post.get("message", ""))
                        seen_post_ids.add(p_id)
            else:
                collect_posts(p)

        # Process last 10 pages (the "Tail")
        if last_page > head_limit:
            tail_start = max(head_limit + 1, last_page - 9)
            for p in range(tail_start, last_page + 1):
                collect_posts(p)

        return "\n\n".join(filter(None, messages))

    except Exception as exc:
        msg = f"Failed to fetch full body for thread {thread_id}: {exc}"
        logger.error(msg, exc_info=True)
        emit(
            "import.thread_body_failed",
            msg,
            source="import",
            severity="error",
            related_entity_type="thread",
            related_entity_id=str(thread_id),
            runtime_context={"error": str(exc)},
        )
        return ""


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
    ):
        if xf_client is None:
            xf_client = XenForoAPIClient()
        raw_body = _fetch_thread_full_body(xf_client, c_id)

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
    """Save Post, Sentences, distilled text, and entity salience.

    Pick #19 — readability grades from ``clean_text`` via
    :func:`apps.sources.readability.score`, persisted on the Post row.

    Pick #26 — top-K salient entities from the **same** spaCy Doc
    that sentence-splitting builds, persisted on the ContentItem row
    as ``salient_entities``. Reusing the Doc (via
    ``split_sentence_spans_with_doc``) avoids a second NLP parse of
    the same body.
    """
    from django.db import transaction

    from apps.content.models import Post, Sentence
    from apps.pipeline.services.distiller import distill_body
    from apps.pipeline.services.sentence_splitter import (
        split_sentence_spans_with_doc,
    )
    from apps.pipeline.services.nlp_enrichment import NLPEnricher
    from apps.sources.entity_salience import rank_entities
    from apps.sources.readability import score as readability_score

    with transaction.atomic():
        content_item.content_hash = new_hash
        content_item.content_version += 1
        content_item.embedding_model_version = ""
        content_item.embedding_text_hash = ""

        # Group D.4 — capture quotation density from the raw body BEFORE
        # the text_cleaner strip ran. We don't have the pre-strip text
        # here directly, but ``raw_body`` is the post's BBCode source
        # which still contains the [QUOTE]…[/QUOTE] blocks at this point
        # in the flow. Cheap one-pass regex; failure is non-fatal.
        try:
            from apps.pipeline.services.text_cleaner import compute_quotation_density

            content_item.quotation_density = compute_quotation_density(raw_body)
        except Exception:
            # Never block an import on a future originality-signal column.
            content_item.quotation_density = 0.0

        # Group A.6 — cross-source content dedup. If this exact body has
        # already been imported under a different source_key (e.g. the
        # same article exists as both an XF Resource sticky and a WP
        # blog post), point this row at the canonical one and skip the
        # embedding pass. The lookup is indexed (migration 0032) so the
        # check is sub-millisecond. Helper never raises — falls back to
        # ``None`` on any error so the import keeps moving.
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
            # Source content drifted away from the canonical — clear the
            # link so the embedding pass can regenerate this row's vector.
            content_item.duplicate_of = None

        # Pick #19 — Flesch-Kincaid + Gunning Fog. The helper already
        # iterates clean_text once to count words/sentences/syllables
        # (it doesn't reuse ``post.word_count`` because the bare
        # ``len(clean_text.split())`` here doesn't filter punctuation
        # the way the readability tokeniser does — the two counts are
        # close but not identical). One pass through clean_text inside
        # the helper is the cleanest way to compute both grades.
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

        # Reuse the same Doc for sentence boundaries AND entity
        # ranking — splitting and entity-ranking are two consumers
        # of one parse, the canonical anti-duplication move.
        spans, doc = split_sentence_spans_with_doc(clean_text)

        # Pick #26 — Gamon et al. 2013 entity salience. Top 10
        # entities is plenty for downstream consumers (review UI,
        # explain panel) and keeps the JSON payload bounded. Cold-
        # start safe: regex-fallback (no spaCy) skips ranking and
        # leaves salient_entities = []. Empty body yields the same.
        if doc is not None:
            try:
                ranked = rank_entities(
                    doc,
                    title=content_item.title or None,
                    top_k=10,
                )
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
                # Salience is a feature-store optimisation, not a
                # hard dependency. Log and carry on with the import.
                logger.exception(
                    "rank_entities failed for content_item=%s; "
                    "leaving salient_entities unchanged",
                    content_item.pk,
                )
        else:
            content_item.salient_entities = []

        # Group G (Harmonious-12) — NLP enrichment metadata.
        # Captures acronyms, lemmas, noun-chunks, lexical richness,
        # MinHash sketches, phonetic keys, and char-ngram vectors.
        try:
            enricher = NLPEnricher()
            enriched, char_ngram_vector, token_data = enricher.enrich(clean_text, doc=doc)
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
                "NLP enrichment failed for content_item=%s; "
                "leaving nlp_metadata empty",
                content_item.pk,
            )
            content_item.nlp_metadata = {}
            content_item.char_ngram_vector = None
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
            created_sentences = Sentence.objects.bulk_create(sentence_objs)

            # Pick #54 Lemmatization Infrastructure — Token persistence
            if doc is not None:
                from apps.content.models import Token

                token_objs = []
                # Map created sentences back to their spans to reuse doc info
                for sent_obj in created_sentences:
                    span = doc.char_span(sent_obj.start_char, sent_obj.end_char)
                    if span:
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
                Token.objects.bulk_create(token_objs)

        content_item.distilled_text = distill_body(
            [s.text for s in sentence_objs], max_sentences=5
        )

        # Pick #25 — Callan 1994 passage-aligned windows. Reuses the
        # sentence list we already created above (single sentence-
        # split pass, two consumers). Failures are absorbed because
        # passages are advisory, not a hard dependency.
        try:
            from apps.sources.passages import segment_from_sentences

            sentence_texts = [s.text for s in sentence_objs]
            passage_records = segment_from_sentences(sentence_texts)
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
                "segment_from_sentences failed for content_item=%s; "
                "leaving passages unchanged",
                content_item.pk,
            )
        # ``salient_entities`` and ``passages`` were set above in the
        # same transaction (or left unchanged on helper failure).
        content_item.save(
            update_fields=[
                "content_hash",
                "content_version",
                "embedding_model_version",
                "embedding_text_hash",
                "distilled_text",
                "salient_entities",
                "passages",
                # Group A.6 — must be in update_fields or the dedup
                # link assignment above is silently dropped.
                "duplicate_of",
                # Group D.4 — same reason: the new quotation_density
                # value won't persist unless it's in this list.
                "quotation_density",
                # Group G (Harmonious-12) — NLP enrichment metadata.
                "nlp_metadata",
                "char_ngram_vector",
                "updated_at",
            ]
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
        msg = f"Failed to fetch updates for resource {resource.get('resource_id')}: {exc}"
        logger.warning(msg)
        emit(
            "import.resource_updates_failed",
            msg,
            source="import",
            severity="warning",
            related_entity_type="resource",
            related_entity_id=str(resource.get("resource_id")),
            runtime_context={"error": str(exc)},
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
