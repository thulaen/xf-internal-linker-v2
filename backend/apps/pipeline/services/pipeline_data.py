"""Pipeline database data loaders.

Extracted from pipeline.py to satisfy file-length limits.
Content records, sentence records, existing links, destination/sentence
embeddings, and rerun-mode helpers live here.
"""

from __future__ import annotations

import logging
from collections import Counter, defaultdict
from typing import Any, Callable

import numpy as np
import pyroaring as pr
from django.conf import settings

from .anchor_diversity import build_anchor_history
from .keyword_stuffing import (
    build_keyword_baseline,
    evaluate_keyword_stuffing,
)
from .learned_anchor import LearnedAnchorInputRow
from .link_farm import detect_link_farm_rings
from .ranker import (
    ContentKey,
    ContentRecord,
    ExistingLinkKey,
    SentenceRecord,
    derive_march_2026_pagerank_bounds,
)
from .text_tokens import tokenize_text
from .rare_term_propagation import build_rare_term_profiles

logger = logging.getLogger(__name__)

try:
    from .embeddings import (
        EMBEDDING_DIM,
        get_current_embedding_dimension,
        get_current_embedding_filter,
    )
except ImportError:
    EMBEDDING_DIM = 1024  # RANGE: default BGE-M3 embedding dimension

    def get_current_embedding_dimension(*, model=None, model_name=None):
        return EMBEDDING_DIM

    def get_current_embedding_filter(*, prefix="", model=None, model_name=None):
        return {}


# Iterator / fetch batch sizes
_CONTENT_ITERATOR_CHUNK = 500  # maxsize for ContentItem iterator
_SENTENCE_FETCH_BATCH = 2000  # maxsize for sentence cursor fetch
_EMBEDDING_FETCH_BATCH = 1000  # maxsize for embedding cursor fetch


def _sql_in_clause_params(values: list[int]) -> tuple[str, list[int]]:
    placeholders = ", ".join(["%s"] * len(values))
    return placeholders, list(values)


def _coerce_embedding_vector(raw_embedding: Any) -> np.ndarray:
    if isinstance(raw_embedding, np.ndarray):
        return raw_embedding.astype(np.float32, copy=False)
    if isinstance(raw_embedding, str):
        stripped = raw_embedding.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            stripped = stripped[1:-1]
        return np.fromstring(stripped, sep=",", dtype=np.float32)
    return np.asarray(raw_embedding, dtype=np.float32)


def _destination_text(title: str, distilled_text: str) -> str:
    title_clean = (title or "").strip()
    distilled_clean = (distilled_text or "").strip()
    if distilled_clean:
        return f"{title_clean}\n\n{distilled_clean}".strip()
    return title_clean


# ---------------------------------------------------------------------------
# Pipeline resource orchestrators
# ---------------------------------------------------------------------------


def _load_pipeline_content(
    *,
    destination_scope_ids: set[int] | None,
    destination_content_item_ids: set[int] | None,
    host_scope_ids: set[int] | None,
    rare_term_settings: Any,
    keyword_stuffing_settings: Any,
    progress_fn: Callable,
) -> Any:
    """Load content records, sentences, existing links, and rare-term profiles.

    Returns PipelineResult on early exit (no content), or a tuple of loaded
    content-level resources on success.
    """
    from .pipeline import PipelineResult
    from .pipeline_loaders import (
        _get_max_anchor_words,
        _get_max_existing_links_per_host,
        _get_paragraph_window,
    )

    progress_fn(0.05, "Loading content records...")
    content_records = _load_content_records(
        destination_scope_ids=destination_scope_ids,
        host_scope_ids=host_scope_ids,
    )
    if not content_records:
        progress_fn(1.0, "No content records found — pipeline complete.")
        return PipelineResult(
            run_id="", items_in_scope=0, suggestions_created=0, destinations_skipped=0
        )

    progress_fn(0.08, "Loading sentence records...")
    sentence_records, content_to_sentence_ids = _load_sentence_records(
        set(content_records.keys())
    )

    progress_fn(0.12, "Loading existing links...")
    existing_links = _load_existing_links()
    existing_outgoing_counts: dict[ContentKey, int] = Counter(
        from_key for from_key, _to_key in existing_links
    )
    max_existing_links_per_host = _get_max_existing_links_per_host()
    max_anchor_words = _get_max_anchor_words()
    paragraph_window = _get_paragraph_window()
    learned_anchor_rows_by_destination = _load_learned_anchor_rows_by_destination()
    anchor_history_by_destination = _load_active_anchor_history()
    rare_term_profiles: dict = {}
    if rare_term_settings.enabled:
        progress_fn(0.14, "Building rare-term propagation profiles...")
        rare_term_source_records = (
            content_records
            if destination_scope_ids is None
            and host_scope_ids is None
            and destination_content_item_ids is None
            else _load_content_records()
        )
        rare_term_profiles = build_rare_term_profiles(
            rare_term_source_records,
            settings=rare_term_settings,
        )

    keyword_baseline = None
    keyword_stuffing_by_destination: dict[ContentKey, dict[str, object]] = {}
    if keyword_stuffing_settings.enabled:
        keyword_source_records = (
            content_records
            if destination_scope_ids is None
            and host_scope_ids is None
            and destination_content_item_ids is None
            else _load_content_records()
        )
        keyword_baseline = build_keyword_baseline(keyword_source_records)

    link_farm_by_destination = {}

    return dict(
        content_records=content_records,
        sentence_records=sentence_records,
        content_to_sentence_ids=content_to_sentence_ids,
        existing_links=existing_links,
        existing_outgoing_counts=existing_outgoing_counts,
        max_existing_links_per_host=max_existing_links_per_host,
        max_anchor_words=max_anchor_words,
        paragraph_window=paragraph_window,
        learned_anchor_rows_by_destination=learned_anchor_rows_by_destination,
        anchor_history_by_destination=anchor_history_by_destination,
        rare_term_profiles=rare_term_profiles,
        keyword_baseline=keyword_baseline,
        keyword_stuffing_by_destination=keyword_stuffing_by_destination,
        link_farm_by_destination=link_farm_by_destination,
    )


def _load_pipeline_resources(
    *,
    destination_scope_ids: set[int] | None,
    destination_content_item_ids: set[int] | None,
    host_scope_ids: set[int] | None,
    rerun_mode: str,
    rare_term_settings: Any,
    keyword_stuffing_settings: Any,
    link_farm_settings: Any,
    progress_fn: Callable,
) -> Any:
    """Load all pipeline resources including embeddings.

    Returns PipelineResult on early exit (no data), or a tuple of all loaded
    resources on success.
    """
    from .pipeline import PipelineResult

    content_data = _load_pipeline_content(
        destination_scope_ids=destination_scope_ids,
        destination_content_item_ids=destination_content_item_ids,
        host_scope_ids=host_scope_ids,
        rare_term_settings=rare_term_settings,
        keyword_stuffing_settings=keyword_stuffing_settings,
        progress_fn=progress_fn,
    )
    if isinstance(content_data, PipelineResult):
        return content_data

    content_records = content_data["content_records"]
    if content_data.get("keyword_baseline") is not None:
        progress_fn(0.145, "Scoring keyword stuffing baselines...")
        content_data["keyword_stuffing_by_destination"] = {
            key: evaluate_keyword_stuffing(
                destination=record,
                baseline=content_data["keyword_baseline"],
                settings=keyword_stuffing_settings,
            )
            for key, record in content_records.items()
        }

    if link_farm_settings.enabled:
        progress_fn(0.148, "Detecting reciprocal link rings...")
        content_data["link_farm_by_destination"] = detect_link_farm_rings(
            existing_links=content_data["existing_links"],
            settings=link_farm_settings,
        )

    progress_fn(0.15, "Applying rerun mode filter...")
    pending_destinations = _get_pending_destinations(rerun_mode)
    if rerun_mode == "supersede_pending":
        _supersede_pending_suggestions(list(content_records.keys()))

    embedding_data = _load_pipeline_embeddings(
        content_records=content_records,
        pending_destinations=pending_destinations,
        destination_content_item_ids=destination_content_item_ids,
        progress_fn=progress_fn,
    )
    if isinstance(embedding_data, PipelineResult):
        return embedding_data

    content_data.update(embedding_data)
    return content_data


def _load_pipeline_embeddings(
    *,
    content_records: dict[ContentKey, ContentRecord],
    pending_destinations: set[ContentKey],
    destination_content_item_ids: set[int] | None,
    progress_fn: Callable,
) -> Any:
    """Load destination and sentence embeddings from pgvector.

    Returns PipelineResult on early exit, or a tuple of embedding resources.
    """
    from .pipeline import PipelineResult

    progress_fn(0.18, "Loading destination embeddings from pgvector...")
    destination_keys, dest_embeddings = _load_destination_embeddings(
        content_records,
        pending_destinations=pending_destinations,
        destination_content_item_ids=destination_content_item_ids,
    )
    items_in_scope = len(destination_keys)

    if items_in_scope == 0:
        progress_fn(1.0, "No destinations to process — pipeline complete.")
        return PipelineResult(
            run_id="", items_in_scope=0, suggestions_created=0, destinations_skipped=0
        )

    progress_fn(0.22, "Loading sentence embeddings from pgvector...")
    sentence_ids_ordered, sentence_embeddings = _load_sentence_embeddings(
        set(content_records.keys())
    )

    if sentence_embeddings.shape[0] == 0:
        progress_fn(1.0, "No sentence embeddings available — pipeline complete.")
        return PipelineResult(
            run_id="",
            items_in_scope=items_in_scope,
            suggestions_created=0,
            destinations_skipped=items_in_scope,
        )

    sentence_id_to_row = {
        sentence_id: index for index, sentence_id in enumerate(sentence_ids_ordered)
    }
    march_2026_pagerank_bounds = derive_march_2026_pagerank_bounds(content_records)

    return dict(
        destination_keys=destination_keys,
        dest_embeddings=dest_embeddings,
        items_in_scope=items_in_scope,
        sentence_ids_ordered=sentence_ids_ordered,
        sentence_embeddings=sentence_embeddings,
        sentence_id_to_row=sentence_id_to_row,
        march_2026_pagerank_bounds=march_2026_pagerank_bounds,
    )


# ---------------------------------------------------------------------------
# Data loaders
# ---------------------------------------------------------------------------


def _load_content_records(
    *,
    destination_scope_ids: set[int] | None = None,
    host_scope_ids: set[int] | None = None,
) -> dict[ContentKey, ContentRecord]:
    """Load all non-deleted content items with scope hierarchy via Django ORM."""
    from apps.content.models import ContentItem

    qs = ContentItem.objects.filter(is_deleted=False).select_related(
        "scope",
        "scope__parent",
        "scope__parent__parent",
        "scope__silo_group",
        "post",
    )

    if destination_scope_ids is not None or host_scope_ids is not None:
        scope_ids = set(destination_scope_ids or set()) | set(host_scope_ids or set())
        qs = qs.filter(scope_id__in=scope_ids)

    records: dict[ContentKey, ContentRecord] = {}
    for ci in qs.iterator(chunk_size=_CONTENT_ITERATOR_CHUNK):
        scope = ci.scope
        parent = scope.parent if scope else None
        grandparent = parent.parent if parent else None
        silo_group = scope.silo_group if scope else None

        primary_post_char_count = 0
        if hasattr(ci, "post") and ci.post:
            primary_post_char_count = ci.post.char_count or 0

        text = _destination_text(ci.title, ci.distilled_text or "")
        key: ContentKey = (ci.pk, ci.content_type)
        records[key] = ContentRecord(
            content_id=ci.pk,
            content_type=ci.content_type,
            title=ci.title or "",
            distilled_text=ci.distilled_text or "",
            scope_id=scope.pk if scope else 0,
            scope_type=scope.scope_type if scope else "",
            parent_id=parent.pk if parent else None,
            parent_type=parent.scope_type if parent else "",
            grandparent_id=grandparent.pk if grandparent else None,
            grandparent_type=grandparent.scope_type if grandparent else "",
            silo_group_id=silo_group.pk if silo_group else None,
            silo_group_name=silo_group.name if silo_group else "",
            reply_count=ci.reply_count or 0,
            march_2026_pagerank_score=float(ci.march_2026_pagerank_score or 0.0),
            link_freshness_score=float(ci.link_freshness_score or 0.5),
            content_value_score=float(ci.content_value_score or 0.5),
            click_distance_score=float(ci.click_distance_score or 0.5),
            primary_post_char_count=primary_post_char_count,
            tokens=tokenize_text(text),
            scope_title=scope.title if scope else "",
            parent_scope_title=parent.title if parent else "",
            grandparent_scope_title=grandparent.title if grandparent else "",
            cluster_id=ci.cluster_id,
            is_canonical=ci.is_canonical,
        )
    return records


def _load_sentence_records(
    content_keys: set[ContentKey],
) -> tuple[dict[int, SentenceRecord], dict[ContentKey, pr.BitMap]]:
    """Load sentence records for the given content keys with bounded memory use."""
    from django.db import connection

    content_pks = sorted({pk for pk, _ in content_keys})
    if not content_pks:
        return {}, {}

    in_clause, params = _sql_in_clause_params(content_pks)
    query = f"""
        SELECT s.id, s.content_item_id, ci.content_type, s.text, s.char_count, s.position
        FROM content_sentence s
        JOIN content_contentitem ci ON s.content_item_id = ci.id
        WHERE s.content_item_id IN ({in_clause})
          AND ci.is_deleted = FALSE
          AND s.word_position <= %s
    """

    sentence_records: dict[int, SentenceRecord] = {}
    content_to_sentence_ids: dict[ContentKey, pr.BitMap] = defaultdict(pr.BitMap)

    with connection.cursor() as cursor:
        cursor.execute(query, [*params, settings.HOST_SCAN_WORD_LIMIT])
        while True:
            rows = cursor.fetchmany(_SENTENCE_FETCH_BATCH)
            if not rows:
                break

            for sid, cid, ctype, text, char_count, position in rows:
                text = text or ""
                ckey: ContentKey = (cid, ctype)
                sentence_records[sid] = SentenceRecord(
                    sentence_id=sid,
                    content_id=cid,
                    content_type=ctype,
                    text=text,
                    char_count=char_count or len(text),
                    tokens=tokenize_text(text),
                    position=position or 0,
                )
                content_to_sentence_ids[ckey].add(sid)

    return sentence_records, dict(content_to_sentence_ids)


def _load_existing_links() -> set[ExistingLinkKey]:
    from apps.graph.models import ExistingLink

    qs = ExistingLink.objects.values_list(
        "from_content_item__pk",
        "from_content_item__content_type",
        "to_content_item__pk",
        "to_content_item__content_type",
    )
    return {
        (
            (from_pk, from_type),
            (to_pk, to_type),
        )
        for from_pk, from_type, to_pk, to_type in qs
    }


def _load_learned_anchor_rows_by_destination() -> dict[
    ContentKey, list[LearnedAnchorInputRow]
]:
    from apps.graph.models import ExistingLink

    rows_by_destination: dict[ContentKey, list[LearnedAnchorInputRow]] = defaultdict(
        list
    )
    for row in ExistingLink.objects.values(
        "to_content_item__pk",
        "to_content_item__content_type",
        "from_content_item_id",
        "anchor_text",
    ):
        destination_key: ContentKey = (
            row["to_content_item__pk"],
            row["to_content_item__content_type"],
        )
        rows_by_destination[destination_key].append(
            LearnedAnchorInputRow(
                source_content_id=int(row["from_content_item_id"]),
                anchor_text=row["anchor_text"] or "",
            )
        )
    return dict(rows_by_destination)


def _load_active_anchor_history():
    """Load active suggestion anchor history for FR-045."""
    from apps.suggestions.models import Suggestion

    rows = Suggestion.objects.filter(
        status__in=("pending", "approved", "applied", "verified")
    ).values_list(
        "destination__pk",
        "destination__content_type",
        "anchor_phrase",
        "anchor_edited",
    )
    return build_anchor_history(
        (
            (destination_id, destination_type),
            (anchor_edited or anchor_phrase or ""),
        )
        for destination_id, destination_type, anchor_phrase, anchor_edited in rows
    )


def _get_pending_destinations(rerun_mode: str) -> set[ContentKey]:
    if rerun_mode != "skip_pending":
        return set()

    from apps.suggestions.models import Suggestion

    qs = Suggestion.objects.filter(status="pending").values_list(
        "destination__pk", "destination__content_type"
    )
    return {(pk, ct) for pk, ct in qs}


def _supersede_pending_suggestions(destination_keys: list[ContentKey]) -> None:
    from apps.suggestions.models import Suggestion

    dest_pks = [pk for pk, _ in destination_keys]
    Suggestion.objects.filter(
        destination__pk__in=dest_pks,
        status="pending",
    ).update(status="superseded")


def _load_destination_embeddings(
    content_records: dict[ContentKey, ContentRecord],
    *,
    pending_destinations: set[ContentKey],
    destination_content_item_ids: set[int] | None = None,
) -> tuple[tuple[ContentKey, ...], np.ndarray]:
    """Load L2-normalized destination embeddings from pgvector."""
    from apps.content.models import ContentItem

    candidate_keys = [
        key
        for key in content_records
        if key not in pending_destinations
        and (
            destination_content_item_ids is None
            or key[0] in destination_content_item_ids
        )
    ]
    if not candidate_keys:
        return (), np.empty((0, get_current_embedding_dimension()), dtype=np.float32)

    pks = [pk for pk, _ in candidate_keys]
    qs = ContentItem.objects.filter(
        pk__in=pks,
        embedding__isnull=False,
        **get_current_embedding_filter(),
    ).values_list("pk", "content_type", "embedding")

    found: dict[ContentKey, np.ndarray] = {}
    for pk, ct, emb in qs:
        if emb is not None:
            found[(pk, ct)] = _coerce_embedding_vector(emb)

    valid_keys = [key for key in candidate_keys if key in found]
    if not valid_keys:
        return (), np.empty((0, get_current_embedding_dimension()), dtype=np.float32)

    matrix = np.vstack([found[key] for key in valid_keys]).astype(
        np.float32, copy=False
    )
    return tuple(valid_keys), matrix


def _load_sentence_embeddings(
    content_keys: set[ContentKey],
) -> tuple[list[int], np.ndarray]:
    """Load sentence embeddings from pgvector with bounded memory use."""
    from django.db import connection

    content_pks = sorted({pk for pk, _ in content_keys})
    if not content_pks:
        return [], np.empty((0, get_current_embedding_dimension()), dtype=np.float32)

    in_clause, params = _sql_in_clause_params(content_pks)
    query = f"""
        SELECT id, embedding
        FROM content_sentence
        WHERE content_item_id IN ({in_clause})
          AND word_position <= %s
          AND embedding IS NOT NULL
          AND embedding_model_version = %s
        ORDER BY id
    """
    ids: list[int] = []
    vectors: list[list[float]] = []

    with connection.cursor() as cursor:
        cursor.execute(
            query,
            [
                *params,
                settings.HOST_SCAN_WORD_LIMIT,
                get_current_embedding_filter()["embedding_model_version"],
            ],
        )
        while True:
            rows = cursor.fetchmany(_EMBEDDING_FETCH_BATCH)
            if not rows:
                break
            for sentence_id, embedding in rows:
                ids.append(sentence_id)
                vectors.append(_coerce_embedding_vector(embedding))

    if not ids:
        return [], np.empty((0, get_current_embedding_dimension()), dtype=np.float32)

    return ids, np.vstack(vectors).astype(np.float32, copy=False)
