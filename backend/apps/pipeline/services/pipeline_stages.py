"""Pipeline stage functions.

Extracted from pipeline.py to satisfy file-length limits.
Stage 1 (coarse retrieval), Stage 2 (sentence scoring), Stage 2+3 scoring
loop, persistence helpers, and related utilities live here.
"""

from __future__ import annotations

import logging
from typing import Any, Callable

import numpy as np

try:
    from extensions import simsearch

    HAS_CPP_SIMSEARCH = True
except ImportError:
    HAS_CPP_SIMSEARCH = False

from .graph_signal_ranker import GraphSignalRanker
from .ranker import (
    ContentKey,
    ContentRecord,
    ScoredCandidate,
    SentenceRecord,
    SentenceSemanticMatch,
    score_destination_matches,
)
from .pipeline_data import _coerce_embedding_vector
from .pipeline_persist import (  # noqa: F401
    _build_suggestion_records,
    _persist_diagnostics,
    _persist_suggestions,
)
from apps.suggestions.recommended_weights import (
    recommended_float,
    recommended_int,
)

logger = logging.getLogger(__name__)

STAGE1_TOP_K = recommended_int("pipeline.stage1_top_k")
STAGE2_TOP_K = recommended_int("pipeline.stage2_top_k")
MIN_SEMANTIC_SCORE = recommended_float("pipeline.min_semantic_score")
FALLBACK_CANDIDATES_PER_DESTINATION = 5
BLOCK_SIZE = 256  # maxsize for embedding block processing
_SCORING_PROGRESS_INTERVAL = 100  # maxsize for scoring loop progress reporting


# ---------------------------------------------------------------------------
# Stage 1 — coarse content-level candidate retrieval
# ---------------------------------------------------------------------------


def _stage1_candidates(
    *,
    destination_keys: tuple[ContentKey, ...],
    dest_embeddings: np.ndarray,
    content_records: dict[ContentKey, ContentRecord],
    content_to_sentence_ids: dict[ContentKey, list[int]],
    top_k: int,
    block_size: int,
    retrievers=None,
) -> dict[ContentKey, list[int]]:
    """Stage 1: find top-K host content items per destination via the retriever registry.

    Group C.1 refactor: delegates to
    :func:`apps.pipeline.services.candidate_retrievers.run_retrievers`
    so the candidate pool can be assembled from multiple retrievers
    (semantic, lexical, query-expanded). The default registry has a
    single :class:`SemanticRetriever`, which makes this behaviorally
    identical to the legacy single-source implementation.

    ``retrievers`` is an optional iterable of
    :class:`CandidateRetriever` — pass a custom list to override the
    default for testing or experimentation. When omitted, the
    registry returned by
    :func:`candidate_retrievers.default_retrievers` is used.

    Returns a mapping from destination_key -> flat list of candidate
    sentence IDs (all sentences from the retrieved host content items).
    """
    from .candidate_retrievers import (
        RetrievalContext,
        default_retrievers,
        run_retrievers,
    )

    active_retrievers = (
        list(retrievers) if retrievers is not None else default_retrievers()
    )
    context = RetrievalContext(
        destination_keys=destination_keys,
        dest_embeddings=dest_embeddings,
        content_records=content_records,
        content_to_sentence_ids=content_to_sentence_ids,
        top_k=top_k,
        block_size=block_size,
    )
    return run_retrievers(active_retrievers, context=context)


def _stage1_semantic_candidates(
    *,
    destination_keys: tuple[ContentKey, ...],
    dest_embeddings: np.ndarray,
    content_records: dict[ContentKey, ContentRecord],
    content_to_sentence_ids: dict[ContentKey, list[int]],
    top_k: int,
    block_size: int,
) -> dict[ContentKey, list[int]]:
    """Semantic retriever body — FAISS-or-NumPy cosine over BGE-M3 embeddings.

    This is the original ``_stage1_candidates`` logic, renamed and
    invoked from :class:`SemanticRetriever`. Kept as a free function
    so the FAISS bootstrap path (which has its own logging +
    just-in-time index build) doesn't need to live inside the
    retriever class.
    """
    # Build a host embedding matrix from content items that have sentence embeddings
    host_keys = [
        key
        for key in content_records
        if key in content_to_sentence_ids and content_to_sentence_ids[key]
    ]
    if not host_keys:
        return {}

    from .faiss_index import (
        is_faiss_gpu_active,
        faiss_search,
        build_faiss_index,
        HAS_FAISS,
    )

    host_pk_set = {pk for pk, _ in host_keys}
    use_faiss = is_faiss_gpu_active()
    if not use_faiss and HAS_FAISS:
        logger.info("FAISS index not active — building just-in-time for Stage 1")
        build_faiss_index()
        use_faiss = is_faiss_gpu_active()

    if use_faiss:
        # FAISS path — persistent GPU (or CPU-FAISS) index, no per-run DB fetch
        result: dict[ContentKey, list[int]] = {}
        n_dest = len(destination_keys)

        for block_start in range(0, n_dest, block_size):
            block_end = min(block_start + block_size, n_dest)
            dest_block = dest_embeddings[block_start:block_end]
            dest_keys_block = destination_keys[block_start:block_end]

            hits_per_query = faiss_search(dest_block, k=top_k, host_pk_set=host_pk_set)

            for dest_key, hits in zip(dest_keys_block, hits_per_query):
                sentence_ids: list[int] = []
                for pk, ct in hits:
                    host_key = (pk, ct)
                    if host_key == dest_key:
                        continue
                    sentence_ids.extend(content_to_sentence_ids.get(host_key, []))
                if sentence_ids:
                    result[dest_key] = sentence_ids

        return result

    if HAS_FAISS:
        # FAISS installed but no embeddings in DB — return empty (NumPy would too).
        logger.warning(
            "FAISS installed but no embeddings in DB — returning empty Stage 1 results"
        )
        return {}

    # NumPy fallback path — faiss package not installed -------------------------
    return _stage1_numpy_fallback(
        destination_keys=destination_keys,
        dest_embeddings=dest_embeddings,
        host_keys=host_keys,
        content_to_sentence_ids=content_to_sentence_ids,
        top_k=top_k,
        block_size=block_size,
    )


def _stage1_numpy_fallback(
    *,
    destination_keys: tuple[ContentKey, ...],
    dest_embeddings: np.ndarray,
    host_keys: list[ContentKey],
    content_to_sentence_ids: dict[ContentKey, list[int]],
    top_k: int,
    block_size: int,
) -> dict[ContentKey, list[int]]:
    """NumPy cosine-similarity fallback when FAISS is not installed."""
    from apps.content.models import ContentItem
    from apps.pipeline.services.embeddings import get_current_embedding_filter

    host_pks_list = [pk for pk, _ in host_keys]
    host_emb_qs = ContentItem.objects.filter(
        pk__in=host_pks_list,
        embedding__isnull=False,
        **get_current_embedding_filter(),
    ).values_list("pk", "content_type", "embedding")

    host_emb_map: dict[ContentKey, np.ndarray] = {
        (pk, ct): _coerce_embedding_vector(emb)
        for pk, ct, emb in host_emb_qs
        if emb is not None
    }
    valid_host_keys = [k for k in host_keys if k in host_emb_map]
    if not valid_host_keys:
        return {}

    host_matrix = np.vstack([host_emb_map[k] for k in valid_host_keys]).astype(
        np.float32, copy=False
    )

    result: dict[ContentKey, list[int]] = {}
    n_dest = len(destination_keys)

    for block_start in range(0, n_dest, block_size):
        block_end = min(block_start + block_size, n_dest)
        dest_block = dest_embeddings[block_start:block_end]
        dest_keys_block = destination_keys[block_start:block_end]

        sims = dest_block @ host_matrix.T

        for b_idx, dest_key in enumerate(dest_keys_block):
            row = sims[b_idx]
            top_indices = np.argpartition(row, -min(top_k, len(valid_host_keys)))[
                -top_k:
            ]
            top_indices = top_indices[np.argsort(-row[top_indices])]

            sentence_ids: list[int] = []
            for h_idx in top_indices:
                host_key = valid_host_keys[h_idx]
                if host_key == dest_key:
                    continue
                sentence_ids.extend(content_to_sentence_ids.get(host_key, []))

            if sentence_ids:
                result[dest_key] = sentence_ids

    return result


# ---------------------------------------------------------------------------
# Stage 2 — sentence-level scoring
# ---------------------------------------------------------------------------


def _score_sentences_stage2(
    *,
    destination_embedding: np.ndarray,
    sentence_ids: list[int],
    sentence_ids_ordered: list[int],
    sentence_embeddings: np.ndarray,
    sentence_records: dict[int, SentenceRecord],
    sentence_id_to_row: dict[int, int] | None = None,
    top_k: int,
) -> list[SentenceSemanticMatch]:
    """Stage 2: score candidate sentences by cosine similarity to destination."""
    if not sentence_ids:
        return []

    if sentence_id_to_row is None:
        sentence_id_to_row = {
            sentence_id: index for index, sentence_id in enumerate(sentence_ids_ordered)
        }

    candidate_rows: list[int] = []
    candidate_ids: list[int] = []
    for sid in sentence_ids:
        row = sentence_id_to_row.get(sid)
        if row is not None:
            candidate_rows.append(row)
            candidate_ids.append(sid)

    if not candidate_rows:
        return []

    if HAS_CPP_SIMSEARCH:
        top_idx, top_scores = simsearch.score_and_topk(
            destination_embedding,
            sentence_embeddings,
            candidate_rows,
            top_k,
        )
    else:
        candidate_matrix = sentence_embeddings[candidate_rows]
        scores = (
            candidate_matrix @ destination_embedding
        )  # cosine similarity (normalized)

        # Keep top-K
        k = min(top_k, len(scores))
        top_idx = np.argpartition(scores, -k)[-k:]
        top_idx = top_idx[np.argsort(-scores[top_idx])]
        top_scores = scores[top_idx]

    matches: list[SentenceSemanticMatch] = []
    for i, score in zip(top_idx, top_scores, strict=True):
        sid = candidate_ids[i]
        record = sentence_records.get(sid)
        if record is None:
            continue
        matches.append(
            SentenceSemanticMatch(
                host_content_id=record.content_id,
                host_content_type=record.content_type,
                sentence_id=sid,
                score_semantic=float(score),
            )
        )

    return matches


# ---------------------------------------------------------------------------
# Stage 2+3 scoring loop
# ---------------------------------------------------------------------------


def _score_all_destinations(
    *,
    destination_keys: tuple[ContentKey, ...],
    dest_embeddings: np.ndarray,
    stage1_candidates: dict[ContentKey, list[int]],
    content_records: dict[ContentKey, ContentRecord],
    sentence_ids_ordered: list[int],
    sentence_embeddings: np.ndarray,
    sentence_records: dict[int, SentenceRecord],
    sentence_id_to_row: dict[int, int],
    existing_links: set[tuple[ContentKey, ContentKey]],
    existing_outgoing_counts: dict[ContentKey, int],
    settings: dict[str, Any],
    feedback_rerank_service: Any,
    progress_fn: Callable,
    items_in_scope: int,
    fr099_fr105_caches: Any = None,
    graph_signal_ranker: GraphSignalRanker | None = None,
) -> tuple[dict[ContentKey, list[ScoredCandidate]], list[tuple]]:
    """Score every destination through Stage 2 + Stage 3, with reranking."""
    candidates_by_destination: dict[ContentKey, list[ScoredCandidate]] = {}
    diagnostics: list[tuple[int, str, str, dict[str, Any] | None]] = []

    for dest_idx, dest_key in enumerate(destination_keys):
        _score_single_destination(
            dest_idx=dest_idx,
            dest_key=dest_key,
            dest_embeddings=dest_embeddings,
            stage1_candidates=stage1_candidates,
            content_records=content_records,
            sentence_ids_ordered=sentence_ids_ordered,
            sentence_embeddings=sentence_embeddings,
            sentence_records=sentence_records,
            sentence_id_to_row=sentence_id_to_row,
            existing_links=existing_links,
            existing_outgoing_counts=existing_outgoing_counts,
            settings=settings,
            feedback_rerank_service=feedback_rerank_service,
            candidates_by_destination=candidates_by_destination,
            diagnostics=diagnostics,
            fr099_fr105_caches=fr099_fr105_caches,
            graph_signal_ranker=graph_signal_ranker,
        )

        if dest_idx % _SCORING_PROGRESS_INTERVAL == 0 and dest_idx > 0:
            pct = 0.50 + 0.35 * (dest_idx / items_in_scope)
            progress_fn(pct, f"Scored {dest_idx}/{items_in_scope} destinations...")

    return candidates_by_destination, diagnostics


def _score_single_destination(
    *,
    dest_idx: int,
    dest_key: ContentKey,
    dest_embeddings: np.ndarray,
    stage1_candidates: dict[ContentKey, list[int]],
    content_records: dict[ContentKey, ContentRecord],
    sentence_ids_ordered: list[int],
    sentence_embeddings: np.ndarray,
    sentence_records: dict[int, SentenceRecord],
    sentence_id_to_row: dict[int, int],
    existing_links: set[tuple[ContentKey, ContentKey]],
    existing_outgoing_counts: dict[ContentKey, int],
    settings: dict[str, Any],
    feedback_rerank_service: Any,
    candidates_by_destination: dict[ContentKey, list[ScoredCandidate]],
    diagnostics: list[tuple],
    fr099_fr105_caches: Any = None,
    graph_signal_ranker: GraphSignalRanker | None = None,
) -> None:
    """Score a single destination through Stage 2 + Stage 3."""
    destination = content_records[dest_key]
    host_sentence_ids = stage1_candidates.get(dest_key, [])

    matches = _score_sentences_stage2(
        destination_embedding=dest_embeddings[dest_idx],
        sentence_ids=host_sentence_ids,
        sentence_ids_ordered=sentence_ids_ordered,
        sentence_embeddings=sentence_embeddings,
        sentence_records=sentence_records,
        sentence_id_to_row=sentence_id_to_row,
        top_k=STAGE2_TOP_K,
    )

    if not matches:
        diagnostics.append((dest_key[0], dest_key[1], "no_semantic_matches", None))
        return

    blocked_reasons: set[str] = set()
    scored = score_destination_matches(
        destination,
        matches,
        content_records=content_records,
        sentence_records=sentence_records,
        existing_links=existing_links,
        existing_outgoing_counts=existing_outgoing_counts,
        max_existing_links_per_host=settings["max_existing_links_per_host"],
        max_anchor_words=settings["max_anchor_words"],
        learned_anchor_rows_by_destination=settings["learned_anchor_rows"],
        anchor_history_by_destination=settings["anchor_history_by_destination"],
        rare_term_profiles=settings["rare_term_profiles"],
        keyword_stuffing_by_destination=settings["keyword_stuffing_by_destination"],
        link_farm_by_destination=settings["link_farm_by_destination"],
        weights=settings["weights"],
        march_2026_pagerank_bounds=settings["pagerank_bounds"],
        weighted_authority_ranking_weight=settings["weighted_authority"][
            "ranking_weight"
        ],
        link_freshness_ranking_weight=settings["link_freshness"]["ranking_weight"],
        phrase_matching_settings=settings["phrase_matching"],
        learned_anchor_settings=settings["learned_anchor"],
        rare_term_settings=settings["rare_term"],
        field_aware_settings=settings["field_aware"],
        ga4_gsc_ranking_weight=settings["ga4_gsc"]["ranking_weight"],
        click_distance_ranking_weight=settings["click_distance"]["ranking_weight"],
        anchor_diversity_settings=settings["anchor_diversity"],
        keyword_stuffing_settings=settings["keyword_stuffing"],
        link_farm_settings=settings["link_farm"],
        silo_settings=settings["silo"],
        clustering_settings=settings["clustering"],
        blocked_reasons=blocked_reasons,
        min_semantic_score=MIN_SEMANTIC_SCORE,
        fr099_fr105_caches=fr099_fr105_caches,
        fr099_fr105_settings=settings.get("fr099_fr105"),
        graph_signal_ranker=graph_signal_ranker,
    )

    _collect_destination_result(
        dest_key=dest_key,
        destination=destination,
        scored=scored,
        blocked_reasons=blocked_reasons,
        settings=settings,
        content_records=content_records,
        feedback_rerank_service=feedback_rerank_service,
        candidates_by_destination=candidates_by_destination,
        diagnostics=diagnostics,
    )


def _collect_destination_result(
    *,
    dest_key: ContentKey,
    destination: ContentRecord,
    scored: list[ScoredCandidate],
    blocked_reasons: set[str],
    settings: dict[str, Any],
    content_records: dict[ContentKey, ContentRecord],
    feedback_rerank_service: Any,
    candidates_by_destination: dict[ContentKey, list[ScoredCandidate]],
    diagnostics: list[tuple],
) -> None:
    """Store scored candidates or record a diagnostic for this destination."""
    if scored:
        if settings["feedback_rerank"].enabled:
            scored = feedback_rerank_service.rerank_candidates(
                scored,
                host_scope_id_map={
                    c.host_content_id: content_records[
                        (c.host_content_id, c.host_content_type)
                    ].scope_id
                    for c in scored
                },
                destination_scope_id_map={destination.content_id: destination.scope_id},
            )
        candidates_by_destination[dest_key] = scored
        return

    if "cross_silo_blocked" in blocked_reasons:
        diagnostics.append(
            (
                dest_key[0],
                dest_key[1],
                "cross_silo_blocked",
                {
                    "mode": settings["silo"].mode,
                    "destination_silo_group_id": destination.silo_group_id,
                    "destination_silo_group_name": destination.silo_group_name,
                },
            )
        )
    elif "max_links_reached" in blocked_reasons:
        diagnostics.append((dest_key[0], dest_key[1], "max_links_reached", None))
    elif "anchor_too_long" in blocked_reasons:
        diagnostics.append((dest_key[0], dest_key[1], "anchor_too_long", None))
    elif "anchor_diversity_blocked" in blocked_reasons:
        diagnostics.append((dest_key[0], dest_key[1], "anchor_diversity_blocked", None))
    else:
        diagnostics.append((dest_key[0], dest_key[1], "all_candidates_filtered", None))
