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
from .advanced_graph_signals import (
    AdvancedGraphSignalsCaches,
    AdvancedGraphSignalsSettings,
)
from .fr099_fr105_signals import FR099FR105Caches, FR099FR105Settings
from .graph_topology_caches import (
    build_articulation_point_cache,
    build_bridge_edge_cache,
    build_host_silo_distribution_cache,
    build_katz_cache,
    build_kcore_cache,
    build_query_tfidf_cache,
)
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
from .text_tokens import tokenize_text, tokenize_text_stemmed
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
# Shared utilities
# ---------------------------------------------------------------------------


def _empty_pipeline_result(*, items_in_scope: int = 0, destinations_skipped: int = 0):
    """Return a zero-result PipelineResult for early-exit paths."""
    from .pipeline import PipelineResult

    return PipelineResult(
        run_id="",
        items_in_scope=items_in_scope,
        suggestions_created=0,
        destinations_skipped=destinations_skipped,
    )


def _full_corpus_if_scoped(
    content_records,
    destination_scope_ids,
    host_scope_ids,
    destination_content_item_ids,
):
    """Return content_records unchanged when no scope filter is active.

    When any scope filter is active, content_records are a subset; return the
    full site corpus so baselines are computed against the complete dataset.
    """
    if (
        destination_scope_ids is None
        and host_scope_ids is None
        and destination_content_item_ids is None
    ):
        return content_records
    return _load_content_records()


# ---------------------------------------------------------------------------
# Helpers for _load_pipeline_content
# ---------------------------------------------------------------------------


def _apply_langid_filter(
    content_records: dict[ContentKey, ContentRecord],
    progress_fn: Callable,
) -> dict[ContentKey, ContentRecord]:
    """Apply FastText LangID candidate filter; returns input unchanged on cold-start.

    Pick #14 — Joulin 2016 EACL. Toggle: fasttext_langid.candidate_filter.enabled.
    """
    from apps.sources.language_filter import filter_english_content_records

    pre_filter_count = len(content_records)
    filtered = filter_english_content_records(content_records)
    if len(filtered) != pre_filter_count:
        progress_fn(
            0.06,
            f"FastText LangID filter dropped "
            f"{pre_filter_count - len(filtered)} non-English records "
            f"({len(filtered)} kept)",
        )
    return filtered


def _load_link_and_anchor_data(
    existing_links: set[ExistingLinkKey],
) -> dict:
    """Load link-count settings, learned anchors, and active anchor history."""
    from .pipeline_loaders import (
        _get_max_anchor_words,
        _get_max_existing_links_per_host,
        _get_paragraph_window,
    )

    return dict(
        existing_outgoing_counts=Counter(
            from_key for from_key, _to_key in existing_links
        ),
        max_existing_links_per_host=_get_max_existing_links_per_host(),
        max_anchor_words=_get_max_anchor_words(),
        paragraph_window=_get_paragraph_window(),
        learned_anchor_rows_by_destination=_load_learned_anchor_rows_by_destination(),
        anchor_history_by_destination=_load_active_anchor_history(),
    )


def _load_rare_term_profiles(
    rare_term_settings: Any,
    content_records: dict[ContentKey, ContentRecord],
    destination_scope_ids,
    host_scope_ids,
    destination_content_item_ids,
    progress_fn: Callable,
) -> dict:
    """Build rare-term propagation profiles; returns {} when disabled."""
    if not rare_term_settings.enabled:
        return {}
    progress_fn(0.14, "Building rare-term propagation profiles...")
    source_records = _full_corpus_if_scoped(
        content_records,
        destination_scope_ids,
        host_scope_ids,
        destination_content_item_ids,
    )
    return build_rare_term_profiles(source_records, settings=rare_term_settings)


def _load_keyword_baseline_if_enabled(
    keyword_stuffing_settings: Any,
    content_records: dict[ContentKey, ContentRecord],
    destination_scope_ids,
    host_scope_ids,
    destination_content_item_ids,
):
    """Build keyword-stuffing corpus baseline; returns None when disabled."""
    if not keyword_stuffing_settings.enabled:
        return None
    source_records = _full_corpus_if_scoped(
        content_records,
        destination_scope_ids,
        host_scope_ids,
        destination_content_item_ids,
    )
    return build_keyword_baseline(source_records)


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
    fr099_fr105_settings: FR099FR105Settings | None = None,
    advanced_graph_signals_settings: AdvancedGraphSignalsSettings | None = None,
) -> Any:
    """Load content records, sentences, existing links, and rare-term profiles."""
    if fr099_fr105_settings is None:
        fr099_fr105_settings = FR099FR105Settings()
    if advanced_graph_signals_settings is None:
        advanced_graph_signals_settings = AdvancedGraphSignalsSettings()
    progress_fn(0.05, "Loading content records...")
    content_records = _load_content_records(
        destination_scope_ids=destination_scope_ids, host_scope_ids=host_scope_ids
    )
    if not content_records:
        progress_fn(1.0, "No content records found — pipeline complete.")
        return _empty_pipeline_result()
    progress_fn(0.08, "Loading sentence records...")
    content_records = _apply_langid_filter(content_records, progress_fn)
    sentence_records, content_to_sentence_ids = _load_sentence_records(content_records)
    progress_fn(0.12, "Loading existing links...")
    existing_links = _load_existing_links()
    link_anchor_data = _load_link_and_anchor_data(existing_links)
    scope_args = (destination_scope_ids, host_scope_ids, destination_content_item_ids)
    rare_term_profiles = _load_rare_term_profiles(
        rare_term_settings, content_records, *scope_args, progress_fn
    )
    keyword_baseline = _load_keyword_baseline_if_enabled(
        keyword_stuffing_settings, content_records, *scope_args
    )
    fr099_fr105_caches = _build_fr099_fr105_caches(
        content_records=content_records,
        existing_links=existing_links,
        fr099_fr105_settings=fr099_fr105_settings,
        progress_fn=progress_fn,
    )
    advanced_graph_signals_caches = _build_advanced_graph_signals_caches(
        content_records=content_records,
        advanced_graph_signals_settings=advanced_graph_signals_settings,
        progress_fn=progress_fn,
    )
    return dict(
        content_records=content_records,
        sentence_records=sentence_records,
        content_to_sentence_ids=content_to_sentence_ids,
        existing_links=existing_links,
        rare_term_profiles=rare_term_profiles,
        keyword_baseline=keyword_baseline,
        keyword_stuffing_by_destination={},
        link_farm_by_destination={},
        fr099_fr105_caches=fr099_fr105_caches,
        advanced_graph_signals_caches=advanced_graph_signals_caches,
        **link_anchor_data,
    )


def _build_advanced_graph_signals_caches(
    *,
    content_records: dict[ContentKey, ContentRecord],
    advanced_graph_signals_settings: AdvancedGraphSignalsSettings,
    progress_fn: Callable,
) -> AdvancedGraphSignalsCaches | None:
    """Build request-time cache inputs for FR-260 through FR-265 signals."""
    if not advanced_graph_signals_settings.any_enabled:
        return None
    progress_fn(0.151, "Loading advanced graph signal caches...")
    node_to_index = {key: index for index, key in enumerate(content_records)}
    if not node_to_index:
        return None
    spectral_scores = _build_tosd_lambda_array(
        node_to_index=node_to_index,
    )
    local_degrees, global_degrees = _build_icpc_degree_arrays(
        node_to_index=node_to_index,
    )
    node_blocks, block_transition_matrix = _build_sbma_block_arrays(
        node_to_index=node_to_index,
    )
    size = len(node_to_index)
    return AdvancedGraphSignalsCaches(
        node_to_index=node_to_index,
        spectral_scores=spectral_scores,
        transition_counts={},
        out_degrees=np.zeros(size, dtype=np.int32),
        local_degrees=local_degrees,
        global_degrees=global_degrees,
        block_probabilities={},
        flat_distances={},
        density_gradients=np.zeros(size, dtype=np.float64),
        persona_matches={},
        node_blocks=node_blocks,
        block_transition_matrix=block_transition_matrix,
    )


def _build_tosd_lambda_array(
    *,
    node_to_index: dict[ContentKey, int],
) -> np.ndarray:
    """Return TOSD spectral values from the current graph run."""
    try:
        from apps.graph.api import current_tosd_lambdas

        precomputed = current_tosd_lambdas()
    except Exception:
        logger.exception("Failed to load current TOSD graph lambdas.")
        precomputed = {}
    spectral_scores = np.zeros(len(node_to_index), dtype=np.float64)
    for key, value in precomputed.items():
        index = node_to_index.get(key)
        if index is not None:
            spectral_scores[index] = float(value)
    return spectral_scores


def _build_icpc_degree_arrays(
    *,
    node_to_index: dict[ContentKey, int],
) -> tuple[np.ndarray, np.ndarray]:
    """Return ICPC local and global in-degree arrays from the current graph run."""
    try:
        from apps.graph.api import current_icpc_degrees

        precomputed = current_icpc_degrees()
    except Exception:
        logger.exception("Failed to load current ICPC graph degrees.")
        precomputed = {}
    local_degrees = np.zeros(len(node_to_index), dtype=np.int32)
    global_degrees = np.zeros(len(node_to_index), dtype=np.int32)
    for key, (local, global_) in precomputed.items():
        index = node_to_index.get(key)
        if index is not None:
            local_degrees[index] = local
            global_degrees[index] = global_
    return local_degrees, global_degrees


def _build_sbma_block_arrays(
    *,
    node_to_index: dict[ContentKey, int],
) -> tuple[np.ndarray, dict[tuple[int, int], float]]:
    """Return SBMA node blocks and transition matrix from the current graph run."""
    try:
        from apps.graph.api import current_sbma_blocks

        precomputed_blocks, matrix = current_sbma_blocks()
    except Exception:
        logger.exception("Failed to load current SBMA graph blocks.")
        precomputed_blocks, matrix = {}, {}
    node_blocks = np.full(len(node_to_index), -1, dtype=np.int32)
    for key, block_id in precomputed_blocks.items():
        index = node_to_index.get(key)
        if index is not None:
            node_blocks[index] = int(block_id)
    return node_blocks, matrix


# ---------------------------------------------------------------------------
# Helpers for _build_fr099_fr105_caches
# ---------------------------------------------------------------------------


def _build_simple_graph_caches(
    fr099_fr105_settings: FR099FR105Settings,
    content_keys: list[ContentKey],
    existing_links: set[ExistingLinkKey],
) -> tuple:
    """Build katz, articulation-point, k-core, and bridge-edge caches (FR-099..102)."""
    katz_cache = (
        build_katz_cache(content_keys, existing_links)
        if fr099_fr105_settings.kmig.enabled
        else None
    )
    articulation_cache = (
        build_articulation_point_cache(content_keys, existing_links)
        if fr099_fr105_settings.tapb.enabled
        else None
    )
    kcore_cache = (
        build_kcore_cache(content_keys, existing_links)
        if fr099_fr105_settings.kcib.enabled
        else None
    )
    bridge_cache = (
        build_bridge_edge_cache(content_keys, existing_links)
        if fr099_fr105_settings.berp.enabled
        else None
    )
    return katz_cache, articulation_cache, kcore_cache, bridge_cache


def _build_silo_cache_if_enabled(
    fr099_fr105_settings: FR099FR105Settings,
    content_records: dict[ContentKey, ContentRecord],
    existing_links: set[ExistingLinkKey],
):
    """Build FR-104 HGTE host-silo distribution cache; returns None when disabled."""
    if not fr099_fr105_settings.hgte.enabled:
        return None
    dest_silo_by_key: dict[ContentKey, int | None] = {
        key: getattr(record, "silo_group_id", None)
        for key, record in content_records.items()
    }
    silo_ids = {s for s in dest_silo_by_key.values() if s is not None}
    return build_host_silo_distribution_cache(
        existing_links=existing_links,
        dest_silo_by_key=dest_silo_by_key,
        num_silos=max(1, len(silo_ids)),
    )


def _build_query_cache_if_enabled(
    fr099_fr105_settings: FR099FR105Settings,
    content_records: dict[ContentKey, ContentRecord],
):
    """Build FR-105 RSQVA query-TFIDF cache; returns None when disabled."""
    if not fr099_fr105_settings.rsqva.enabled:
        return None
    return _load_query_tfidf_cache(content_records)


def _build_fr099_fr105_caches(
    *,
    content_records: dict[ContentKey, ContentRecord],
    existing_links: set[ExistingLinkKey],
    fr099_fr105_settings: FR099FR105Settings,
    progress_fn: Callable,
) -> FR099FR105Caches:
    """Build the 6 graph-topology precompute caches for FR-099 through FR-105."""
    if not fr099_fr105_settings.any_enabled:
        return FR099FR105Caches()
    progress_fn(0.15, "Building FR-099..FR-105 graph-topology caches...")
    content_keys = list(content_records.keys())
    katz_cache, articulation_cache, kcore_cache, bridge_cache = (
        _build_simple_graph_caches(fr099_fr105_settings, content_keys, existing_links)
    )
    silo_cache = _build_silo_cache_if_enabled(
        fr099_fr105_settings, content_records, existing_links
    )
    query_cache = _build_query_cache_if_enabled(fr099_fr105_settings, content_records)
    return FR099FR105Caches(
        katz_cache=katz_cache,
        articulation_cache=articulation_cache,
        kcore_cache=kcore_cache,
        bridge_cache=bridge_cache,
        silo_cache=silo_cache,
        query_cache=query_cache,
    )


def _load_query_tfidf_cache(
    content_records: dict[ContentKey, ContentRecord],
):
    """Load FR-105 RSQVA query TF-IDF vectors from the ContentItem column.

    Returns an empty cache if no vectors have been refreshed yet
    (daily refresh task is deferred to a follow-up session).
    """
    try:
        from apps.content.models import ContentItem

        page_vectors: dict[ContentKey, np.ndarray] = {}
        content_ids = [key[0] for key in content_records.keys()]
        # Only load items that actually have a vector column populated.
        qs = (
            ContentItem.objects.filter(
                id__in=content_ids,
                gsc_query_tfidf_vector__isnull=False,
            )
            .only("id", "content_type", "gsc_query_tfidf_vector")
            .iterator(chunk_size=500)
        )
        for item in qs:
            vec = _coerce_embedding_vector(item.gsc_query_tfidf_vector)
            if vec is None or vec.size == 0:
                continue
            page_vectors[(item.id, item.content_type)] = vec
        return build_query_tfidf_cache(
            page_vectors=page_vectors,
            # Query counts are not separately tracked on ContentItem today;
            # use a conservative fallback of 10 per page when the vector
            # column is populated. When the refresh task ships it can also
            # persist a query_count scalar for richer diagnostics.
            page_query_counts={k: 10 for k in page_vectors},
            gsc_days_available=30 if page_vectors else 0,
        )
    except Exception:
        logger.exception(
            "Failed to load FR-105 RSQVA query-TFIDF cache; returning empty."
        )
        return build_query_tfidf_cache(
            page_vectors={},
            page_query_counts={},
            gsc_days_available=0,
        )


# ---------------------------------------------------------------------------
# Helpers for _load_pipeline_resources
# ---------------------------------------------------------------------------


def _score_keyword_stuffing_if_enabled(
    content_data: dict,
    keyword_stuffing_settings: Any,
    progress_fn: Callable,
) -> None:
    """Score keyword stuffing per destination; mutates content_data in place."""
    if content_data.get("keyword_baseline") is None:
        return
    progress_fn(0.145, "Scoring keyword stuffing baselines...")
    content_records = content_data["content_records"]
    content_data["keyword_stuffing_by_destination"] = {
        key: evaluate_keyword_stuffing(
            destination=record,
            baseline=content_data["keyword_baseline"],
            settings=keyword_stuffing_settings,
        )
        for key, record in content_records.items()
    }


def _detect_link_farm_if_enabled(
    content_data: dict,
    link_farm_settings: Any,
    progress_fn: Callable,
) -> None:
    """Detect reciprocal link rings; mutates content_data in place."""
    if not link_farm_settings.enabled:
        return
    progress_fn(0.148, "Detecting reciprocal link rings...")
    content_data["link_farm_by_destination"] = detect_link_farm_rings(
        existing_links=content_data["existing_links"],
        settings=link_farm_settings,
    )


def _load_pipeline_resources(  # noqa  # forbidden-pattern too-many-args  # justification: 9-arg public API; grouping into a settings dataclass is a separate refactor.
    *,
    destination_scope_ids: set[int] | None,
    destination_content_item_ids: set[int] | None,
    host_scope_ids: set[int] | None,
    rerun_mode: str,
    rare_term_settings: Any,
    keyword_stuffing_settings: Any,
    link_farm_settings: Any,
    progress_fn: Callable,
    fr099_fr105_settings: FR099FR105Settings | None = None,
    advanced_graph_signals_settings: AdvancedGraphSignalsSettings | None = None,
) -> Any:
    """Load all pipeline resources including embeddings."""
    from .pipeline import PipelineResult

    content_data = _load_pipeline_content(
        destination_scope_ids=destination_scope_ids,
        destination_content_item_ids=destination_content_item_ids,
        host_scope_ids=host_scope_ids,
        rare_term_settings=rare_term_settings,
        keyword_stuffing_settings=keyword_stuffing_settings,
        progress_fn=progress_fn,
        fr099_fr105_settings=fr099_fr105_settings,
        advanced_graph_signals_settings=advanced_graph_signals_settings,
    )
    if isinstance(content_data, PipelineResult):
        return content_data

    _score_keyword_stuffing_if_enabled(
        content_data, keyword_stuffing_settings, progress_fn
    )
    _detect_link_farm_if_enabled(content_data, link_farm_settings, progress_fn)

    progress_fn(0.15, "Applying rerun mode filter...")
    pending_destinations = _get_pending_destinations(rerun_mode)
    if rerun_mode == "supersede_pending":
        _supersede_pending_suggestions(list(content_data["content_records"].keys()))

    embedding_data = _load_pipeline_embeddings(
        content_records=content_data["content_records"],
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
    """Load destination and sentence embeddings from pgvector."""
    progress_fn(0.18, "Loading destination embeddings from pgvector...")
    destination_keys, dest_embeddings = _load_destination_embeddings(
        content_records,
        pending_destinations=pending_destinations,
        destination_content_item_ids=destination_content_item_ids,
    )
    items_in_scope = len(destination_keys)
    if items_in_scope == 0:
        progress_fn(1.0, "No destinations to process — pipeline complete.")
        return _empty_pipeline_result()
    progress_fn(0.22, "Loading sentence embeddings from pgvector...")
    sentence_ids_ordered, sentence_embeddings = _load_sentence_embeddings(
        set(content_records.keys())
    )
    if sentence_embeddings.shape[0] == 0:
        progress_fn(1.0, "No sentence embeddings available — pipeline complete.")
        return _empty_pipeline_result(
            items_in_scope=items_in_scope, destinations_skipped=items_in_scope
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


def _resolve_scope_hierarchy(ci) -> tuple:
    """Return (scope, parent, grandparent, silo_group) from a ContentItem."""
    scope = ci.scope
    parent = scope.parent if scope else None
    grandparent = parent.parent if parent else None
    silo_group = scope.silo_group if scope else None
    return scope, parent, grandparent, silo_group


def _build_content_record_from_ci(
    ci,
    scope,
    parent,
    grandparent,
    silo_group,
    text: str,
) -> ContentRecord:
    """Construct a ContentRecord from a loaded ContentItem and its resolved scope."""
    primary_post_char_count = 0
    if hasattr(ci, "post") and ci.post:
        primary_post_char_count = ci.post.char_count or 0
    surface_tokens = tokenize_text(text)
    return ContentRecord(
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
        tokens=surface_tokens,
        stemmed_tokens=tokenize_text_stemmed(text),  # Pick #21 — dual token sets
        scope_title=scope.title if scope else "",
        parent_scope_title=parent.title if parent else "",
        grandparent_scope_title=grandparent.title if grandparent else "",
        cluster_id=ci.cluster_id,
        is_canonical=ci.is_canonical,
        nlp_metadata=ci.nlp_metadata or {},
        # FR-249 — passed to compute_embedding_age_decay in ranker.py.
        updated_at=getattr(ci, "updated_at", None),
    )


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
        scope, parent, grandparent, silo_group = _resolve_scope_hierarchy(ci)
        text = _destination_text(ci.title, ci.distilled_text or "")
        key: ContentKey = (ci.pk, ci.content_type)
        records[key] = _build_content_record_from_ci(
            ci, scope, parent, grandparent, silo_group, text
        )
    return records


def _parse_sentence_loader_input(
    content_records_or_keys,
) -> tuple[dict, list[int]]:
    """Parse dict-or-iterable input; returns (content_records, sorted_content_pks)."""
    if hasattr(content_records_or_keys, "keys"):
        content_records = content_records_or_keys
        keys_iter = content_records.keys()
    else:
        content_records = {}  # No nlp_metadata; SentenceRecord falls back to {}.
        keys_iter = content_records_or_keys
    content_pks = sorted({pk for pk, _ in keys_iter})
    return content_records, content_pks


def _build_sentence_record_from_row(
    row_tuple: tuple,
    content_records: dict,
) -> tuple[ContentKey, SentenceRecord]:
    """Build a SentenceRecord from a raw SQL cursor row."""
    sid, cid, ctype, text, char_count, position = row_tuple
    text = text or ""
    ckey: ContentKey = (cid, ctype)
    return ckey, SentenceRecord(
        sentence_id=sid,
        content_id=cid,
        content_type=ctype,
        text=text,
        char_count=char_count or len(text),
        tokens=tokenize_text(text),
        stemmed_tokens=tokenize_text_stemmed(text),  # Pick #21
        position=position or 0,
        nlp_metadata=content_records[ckey].nlp_metadata
        if ckey in content_records
        else {},
    )


def _load_sentence_records(
    content_records_or_keys,
) -> tuple[dict[int, SentenceRecord], dict[ContentKey, pr.BitMap]]:
    """Load sentence records for the given content keys with bounded memory use.

    Accepts either ``dict[ContentKey, ContentRecord]`` (production: iterates
    ``.keys()``) or any iterable of ``ContentKey`` tuples (tests + tools that
    don't need the full ContentRecord). Bug fix 2026-05-05: prior signature
    only accepted dicts and raised AttributeError on set inputs.
    """
    from django.db import connection

    content_records, content_pks = _parse_sentence_loader_input(content_records_or_keys)
    if not content_pks:
        return {}, {}

    query = """
        SELECT s.id, s.content_item_id, ci.content_type, s.text, s.char_count, s.position
        FROM content_sentence s
        JOIN content_contentitem ci ON s.content_item_id = ci.id
        WHERE s.content_item_id = ANY(%s)
          AND ci.is_deleted = FALSE
          AND s.word_position <= %s
    """
    sentence_records: dict[int, SentenceRecord] = {}
    content_to_sentence_ids: dict[ContentKey, pr.BitMap] = defaultdict(pr.BitMap)
    with connection.cursor() as cursor:
        cursor.execute(query, [content_pks, settings.HOST_SCAN_WORD_LIMIT])
        while True:
            rows = cursor.fetchmany(_SENTENCE_FETCH_BATCH)
            if not rows:
                break
            for row in rows:
                ckey, record = _build_sentence_record_from_row(row, content_records)
                sentence_records[record.sentence_id] = record
                content_to_sentence_ids[ckey].add(record.sentence_id)
    return sentence_records, dict(content_to_sentence_ids)


def _load_existing_links() -> set[ExistingLinkKey]:
    from apps.graph.models import ExistingLink

    # ``.iterator(chunk_size=10_000)`` streams from the DB so a forum
    # with 1M+ ExistingLink rows doesn't materialise the full set in
    # one go. The result-set still has to fit in RAM (it's a Python set
    # of tuples, ~150 MB at 1M rows) but iteration peak memory drops
    # by 2-3× because we don't double-buffer the materialised QuerySet
    # cache alongside the set we're building.
    qs = ExistingLink.objects.values_list(
        "from_content_item__pk",
        "from_content_item__content_type",
        "to_content_item__pk",
        "to_content_item__content_type",
    ).iterator(chunk_size=10_000)
    out: set[ExistingLinkKey] = set()
    for from_pk, from_type, to_pk, to_type in qs:
        out.add(((from_pk, from_type), (to_pk, to_type)))
    return out


def _load_learned_anchor_rows_by_destination() -> (
    dict[ContentKey, list[LearnedAnchorInputRow]]
):
    from apps.graph.models import ExistingLink

    rows_by_destination: dict[ContentKey, list[LearnedAnchorInputRow]] = defaultdict(
        list
    )
    # Performance refactor 2026-05-04: stream ExistingLink rows in 2000-
    # row chunks via a server-side cursor so a corpus with 1M+ links
    # doesn't materialise into Python memory at once. The accumulating
    # dict still grows linearly with destinations but each row is
    # released after defaultdict insert.
    link_rows = ExistingLink.objects.values(
        "to_content_item__pk",
        "to_content_item__content_type",
        "from_content_item_id",
        "anchor_text",
    ).iterator(chunk_size=2000)
    for row in link_rows:
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

    query = """
        SELECT id, embedding
        FROM content_sentence
        WHERE content_item_id = ANY(%s)
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
                content_pks,
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
