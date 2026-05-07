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


# FR-247 — Fast-path observability. SLO-tracked counter per pathway so a
# silent C++ → Python regression (50-100x slowdown) is visible to
# operators within one pipeline pass instead of hiding behind aggregated
# latency. Source: Beyer et al. 2016 *Site Reliability Engineering*
# Chapter 4 ("Service Level Objectives") — pathway latency must be
# SLO-tracked with a counter per pathway. Sridharan 2018 *Distributed
# Systems Observability* Chapter 4 — counter cardinality budget.
#
# Counters live in process memory (no Prometheus client required); the
# operator-facing surface is the `/performance` dashboard that already
# reads runtime status from helpers like ``get_slate_diversity_runtime_status``.
_PATH_COUNTERS: dict[str, int] = {"cpp": 0, "python": 0}


def _record_stage2_path(path: str) -> None:
    """FR-247 — increment the in-memory pathway counter."""
    _PATH_COUNTERS[path] = _PATH_COUNTERS.get(path, 0) + 1


def get_stage2_path_counters() -> dict[str, int]:
    """Read-only view for `/performance` dashboard + diagnostics.

    Returns a fresh copy so callers can't mutate the live counters.
    Reset by calling :func:`reset_stage2_path_counters` (used in tests).
    """
    return dict(_PATH_COUNTERS)


def reset_stage2_path_counters() -> None:
    """Reset both counters to 0. Test-only; do not call from production."""
    _PATH_COUNTERS["cpp"] = 0
    _PATH_COUNTERS["python"] = 0


def get_stage2_path_runtime_status() -> dict[str, object]:
    """Plain-English status of the FR-247 fast path. Mirrors the shape
    of `slate_diversity.get_slate_diversity_runtime_status()`.

    Includes an `alert` flag set when the Python share exceeds the
    configured threshold (`pipeline.cpp_path_alert_threshold`, default
    5%). The dashboard turns the card red when this flag is true.
    """
    counters = get_stage2_path_counters()
    total = counters["cpp"] + counters["python"]
    if total == 0:
        return {
            "available": HAS_CPP_SIMSEARCH,
            "path": "cpp_extension" if HAS_CPP_SIMSEARCH else "python_fallback",
            "reason": (
                "C++ simsearch extension is loaded; no Stage-2 calls have "
                "fired yet this run."
                if HAS_CPP_SIMSEARCH
                else "Python fallback is active — the C++ simsearch "
                "extension failed to load."
            ),
            "cpp_calls": 0,
            "python_calls": 0,
            "python_share": 0.0,
            "alert": False,
        }
    python_share = counters["python"] / total
    threshold = _read_cpp_alert_threshold()
    return {
        "available": HAS_CPP_SIMSEARCH,
        "path": "cpp_extension" if counters["cpp"] >= counters["python"] else "python_fallback",
        "reason": (
            f"{counters['cpp']:,} C++ / {counters['python']:,} Python calls "
            f"(Python share {python_share:.1%}, alert at {threshold:.1%})"
        ),
        "cpp_calls": counters["cpp"],
        "python_calls": counters["python"],
        "python_share": python_share,
        "alert": python_share > threshold,
    }


def _read_cpp_alert_threshold() -> float:
    """Read `pipeline.cpp_path_alert_threshold`; default 0.05.

    Beyer 2016 Chapter 4 — SLO violations triggered at 5% pathway
    divergence. Operators can override per-site via /settings.
    """
    try:
        from apps.suggestions.recommended_weights import recommended_float as _rf
        return _rf("pipeline.cpp_path_alert_threshold")
    except Exception:  # noqa: BLE001 — cold-start safe.
        return 0.05

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


def _stage1_mmr_settings() -> tuple[bool, int, float]:
    """Return ``(enabled, overfetch_multiplier, lambda)`` for FR-239 wire-in.

    Looked up at call time (not at module import) so AppSetting overrides
    take effect without a restart. Defaults match Carbonell & Goldstein
    1998 SIGIR §3 (overfetch=2, lambda=0.7) — see
    docs/specs/fr239-stage1-mmr-overfetch.md.
    """
    from apps.suggestions.recommended_weights import (
        recommended_bool,
        recommended_float as _recommended_float,
        recommended_int as _recommended_int,
    )
    return (
        recommended_bool("pipeline.stage1_mmr_enabled"),
        max(1, _recommended_int("pipeline.stage1_overfetch_multiplier")),
        _recommended_float("pipeline.stage1_mmr_lambda"),
    )


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


def _run_faiss_block_search(  # noqa: forbidden-pattern too-many-args  # justification: host_scores_out is the FR-238 diagnostic surface; bundling the search-config args (host_pk_set/block_size/top_k/faiss_search) into a dataclass would obscure their direct role at the FAISS boundary.
    dest_embeddings: np.ndarray,
    destination_keys: tuple[ContentKey, ...],
    host_pk_set: set[int],
    block_size: int,
    top_k: int,
    content_to_sentence_ids: dict[ContentKey, list[int]],
    faiss_search,
    *,
    host_scores_out: dict[ContentKey, list[tuple[ContentKey, float]]] | None = None,
) -> dict[ContentKey, list[int]]:
    """Block-wise FAISS NN search; expand hits to sentence IDs.

    FR-238 — when ``host_scores_out`` is given, write
    ``dest_key -> [(host_key, score), ...]`` in FAISS-returned order.
    Self-links and zero-sentence hosts are filtered from BOTH lists in
    lock-step (Wang/Lin/Metzler 2011 SIGIR §3 cascade score propagation).
    """
    result: dict[ContentKey, list[int]] = {}
    n_dest = len(destination_keys)
    for block_start in range(0, n_dest, block_size):
        block_end = min(block_start + block_size, n_dest)
        dest_block = dest_embeddings[block_start:block_end]
        dest_keys_block = destination_keys[block_start:block_end]
        hits_per_query = faiss_search(dest_block, k=top_k, host_pk_set=host_pk_set)
        for dest_key, hits in zip(dest_keys_block, hits_per_query):
            sentence_ids: list[int] = []
            host_score_entries: list[tuple[ContentKey, float]] = []
            for hit in hits:
                pk, ct, score = _unpack_faiss_hit(hit)
                host_key = (pk, ct)
                if host_key == dest_key:
                    continue
                host_sentences = content_to_sentence_ids.get(host_key, [])
                if not host_sentences:
                    continue
                sentence_ids.extend(host_sentences)
                host_score_entries.append((host_key, score))
            if sentence_ids:
                result[dest_key] = sentence_ids
                if host_scores_out is not None:
                    host_scores_out[dest_key] = host_score_entries
    return result


def _unpack_faiss_hit(hit: tuple) -> tuple[int, str, float]:
    """Adapt FAISS hit tuples to the (pk, content_type, score) shape.

    FR-238 changed ``faiss_search`` to emit a 3-tuple including the
    inner-product score. Older callers (and the older test mocks shipped
    before this commit) still emit 2-tuples ``(pk, content_type)``. This
    adapter accepts either shape — 2-tuple gets a sentinel ``score=0.0``
    so downstream code doesn't blow up. Sentinel is mathematically
    distinct from a real cosine (which is in [-1, 1] but in practice
    >>0 for top-K survivors), so a sentinel value is recognisable as
    "unscored" by inspection.
    """
    if len(hit) >= 3:
        return int(hit[0]), str(hit[1]), float(hit[2])
    return int(hit[0]), str(hit[1]), 0.0


def _stage1_semantic_candidates(
    *,
    destination_keys: tuple[ContentKey, ...],
    dest_embeddings: np.ndarray,
    content_records: dict[ContentKey, ContentRecord],
    content_to_sentence_ids: dict[ContentKey, list[int]],
    top_k: int,
    block_size: int,
    host_scores_out: dict[ContentKey, list[tuple[ContentKey, float]]] | None = None,
) -> dict[ContentKey, list[int]]:
    """FAISS-or-NumPy cosine; FR-238 host_scores_out + FR-239 MMR overfetch."""
    host_keys = [
        key
        for key in content_records
        if key in content_to_sentence_ids and content_to_sentence_ids[key]
    ]
    if not host_keys:
        return {}

    mmr_enabled, overfetch_mult, mmr_lambda = _stage1_mmr_settings()
    effective_top_k = top_k * overfetch_mult if mmr_enabled else top_k
    # When MMR will run, we always need host_scores to drive the rerank.
    internal_host_scores: dict[ContentKey, list[tuple[ContentKey, float]]] = (
        host_scores_out if host_scores_out is not None else {}
    )

    raw = _retrieve_stage1_candidates(
        destination_keys=destination_keys,
        dest_embeddings=dest_embeddings,
        host_keys=host_keys,
        content_to_sentence_ids=content_to_sentence_ids,
        top_k=effective_top_k,
        block_size=block_size,
        internal_host_scores=internal_host_scores,
    )
    if not mmr_enabled or not raw:
        return raw
    return _apply_stage1_mmr(
        raw=raw,
        host_scores=internal_host_scores,
        content_to_sentence_ids=content_to_sentence_ids,
        target_top_k=top_k,
        mmr_lambda=mmr_lambda,
    )


def _retrieve_stage1_candidates(
    *,
    destination_keys: tuple[ContentKey, ...],
    dest_embeddings: np.ndarray,
    host_keys: list[ContentKey],
    content_to_sentence_ids: dict[ContentKey, list[int]],
    top_k: int,
    block_size: int,
    internal_host_scores: dict[ContentKey, list[tuple[ContentKey, float]]],
) -> dict[ContentKey, list[int]]:
    """FAISS-first retrieval with NumPy fallback. Extracted from
    ``_stage1_semantic_candidates`` so the FR-239 MMR wrapper stays
    legible. ``internal_host_scores`` is always populated.
    """
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
        return _run_faiss_block_search(
            dest_embeddings, destination_keys, host_pk_set,
            block_size, top_k, content_to_sentence_ids, faiss_search,
            host_scores_out=internal_host_scores,
        )
    if HAS_FAISS:
        logger.warning(
            "FAISS installed but no embeddings in DB — returning empty Stage 1 results"
        )
        return {}
    return _stage1_numpy_fallback(
        destination_keys=destination_keys,
        dest_embeddings=dest_embeddings,
        host_keys=host_keys,
        content_to_sentence_ids=content_to_sentence_ids,
        top_k=top_k,
        block_size=block_size,
        host_scores_out=internal_host_scores,
    )


def _apply_stage1_mmr(
    *,
    raw: dict[ContentKey, list[int]],
    host_scores: dict[ContentKey, list[tuple[ContentKey, float]]],
    content_to_sentence_ids: dict[ContentKey, list[int]],
    target_top_k: int,
    mmr_lambda: float,
) -> dict[ContentKey, list[int]]:
    """FR-239 — MMR-rerank the per-destination host pool to ``target_top_k``.

    Carbonell & Goldstein 1998 SIGIR §3 — diversity-aware reduction. Loads
    host embeddings via the existing ``_fetch_host_embedding_matrix``
    helper (one DB hit batch-keyed on the union of all FAISS-returned
    host PKs). Falls back gracefully when an embedding is missing — that
    candidate is treated as fully-diverse per the documented contract in
    ``mmr_rerank_keys``.
    """
    from .slate_diversity import mmr_rerank_keys

    all_host_keys = sorted(
        {hk for entries in host_scores.values() for hk, _ in entries}
    )
    if not all_host_keys:
        return raw
    valid_host_keys, host_matrix = _fetch_host_embedding_matrix(all_host_keys)
    embedding_lookup: dict[ContentKey, np.ndarray] = (
        {key: host_matrix[i] for i, key in enumerate(valid_host_keys)}
        if host_matrix is not None
        else {}
    )

    out: dict[ContentKey, list[int]] = {}
    for dest_key, host_score_entries in list(host_scores.items()):
        if not host_score_entries:
            continue
        diverse_picks = mmr_rerank_keys(
            host_score_entries,
            embedding_lookup,
            k=target_top_k,
            lambda_=mmr_lambda,
        )
        # Caller's diagnostic view reflects the post-MMR diverse set,
        # not the pre-MMR overfetched set.
        host_scores[dest_key] = list(diverse_picks)
        sentence_ids: list[int] = []
        for host_key, _score in diverse_picks:
            sentence_ids.extend(content_to_sentence_ids.get(host_key, []))
        if sentence_ids:
            out[dest_key] = sentence_ids
    return out


def _fetch_host_embedding_matrix(
    host_keys: list[ContentKey],
) -> tuple[list[ContentKey], np.ndarray | None]:
    """Fetch embeddings for host content items and return (valid_host_keys, matrix).

    Returns ([], None) when no valid embeddings are found.
    """
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
        return [], None
    host_matrix = np.vstack([host_emb_map[k] for k in valid_host_keys]).astype(
        np.float32, copy=False
    )
    return valid_host_keys, host_matrix


def _stage1_numpy_fallback(
    *,
    destination_keys: tuple[ContentKey, ...],
    dest_embeddings: np.ndarray,
    host_keys: list[ContentKey],
    content_to_sentence_ids: dict[ContentKey, list[int]],
    top_k: int,
    block_size: int,
    host_scores_out: dict[ContentKey, list[tuple[ContentKey, float]]] | None = None,
) -> dict[ContentKey, list[int]]:
    """NumPy cosine fallback; FR-238 plumbs host_scores_out (Wang/Lin/Metzler 2011)."""
    valid_host_keys, host_matrix = _fetch_host_embedding_matrix(host_keys)
    if not valid_host_keys:
        return {}

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
            host_score_entries: list[tuple[ContentKey, float]] = []
            for h_idx in top_indices:
                host_key = valid_host_keys[h_idx]
                if host_key == dest_key:
                    continue
                host_sentences = content_to_sentence_ids.get(host_key, [])
                if not host_sentences:
                    continue
                sentence_ids.extend(host_sentences)
                host_score_entries.append((host_key, float(row[h_idx])))

            if sentence_ids:
                result[dest_key] = sentence_ids
                if host_scores_out is not None:
                    host_scores_out[dest_key] = host_score_entries

    return result


# ---------------------------------------------------------------------------
# Stage 2 — sentence-level scoring
# ---------------------------------------------------------------------------


def _build_candidate_row_ids(
    sentence_ids: list[int],
    sentence_id_to_row: dict[int, int],
) -> tuple[list[int], list[int]]:
    """Map candidate sentence IDs to their row indices in the embedding matrix."""
    candidate_rows: list[int] = []
    candidate_ids: list[int] = []
    for sid in sentence_ids:
        row = sentence_id_to_row.get(sid)
        if row is not None:
            candidate_rows.append(row)
            candidate_ids.append(sid)
    return candidate_rows, candidate_ids


def _topk_numpy_scores(
    destination_embedding: np.ndarray,
    sentence_embeddings: np.ndarray,
    candidate_rows: list[int],
    top_k: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Compute cosine scores via NumPy and return (top_idx, top_scores)."""
    candidate_matrix = sentence_embeddings[candidate_rows]
    scores = candidate_matrix @ destination_embedding
    k = min(top_k, len(scores))
    top_idx = np.argpartition(scores, -k)[-k:]
    top_idx = top_idx[np.argsort(-scores[top_idx])]
    return top_idx, scores[top_idx]


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
    candidate_rows, candidate_ids = _build_candidate_row_ids(sentence_ids, sentence_id_to_row)
    if not candidate_rows:
        return []
    if HAS_CPP_SIMSEARCH:
        top_idx, top_scores = simsearch.score_and_topk(
            destination_embedding, sentence_embeddings, candidate_rows, top_k,
        )
        _record_stage2_path("cpp")
    else:
        top_idx, top_scores = _topk_numpy_scores(
            destination_embedding, sentence_embeddings, candidate_rows, top_k,
        )
        _record_stage2_path("python")
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


def _score_kwargs_from_settings(settings: dict[str, Any]) -> dict[str, Any]:
    """Extract the 23 score_destination_matches kwargs that come from the settings dict."""
    return {
        "max_existing_links_per_host": settings["max_existing_links_per_host"],
        "max_anchor_words": settings["max_anchor_words"],
        "learned_anchor_rows_by_destination": settings["learned_anchor_rows"],
        "anchor_history_by_destination": settings["anchor_history_by_destination"],
        "rare_term_profiles": settings["rare_term_profiles"],
        "keyword_stuffing_by_destination": settings["keyword_stuffing_by_destination"],
        "link_farm_by_destination": settings["link_farm_by_destination"],
        "weights": settings["weights"],
        "march_2026_pagerank_bounds": settings["pagerank_bounds"],
        "weighted_authority_ranking_weight": settings["weighted_authority"]["ranking_weight"],
        "link_freshness_ranking_weight": settings["link_freshness"]["ranking_weight"],
        "phrase_matching_settings": settings["phrase_matching"],
        "learned_anchor_settings": settings["learned_anchor"],
        "rare_term_settings": settings["rare_term"],
        "field_aware_settings": settings["field_aware"],
        "ga4_gsc_ranking_weight": settings["ga4_gsc"]["ranking_weight"],
        "click_distance_ranking_weight": settings["click_distance"]["ranking_weight"],
        "anchor_diversity_settings": settings["anchor_diversity"],
        "keyword_stuffing_settings": settings["keyword_stuffing"],
        "link_farm_settings": settings["link_farm"],
        "silo_settings": settings["silo"],
        "clustering_settings": settings["clustering"],
        "min_semantic_score": MIN_SEMANTIC_SCORE,
    }


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
    phase6_contribution: Any = None,
    anchor_garbage_dispatcher: Any = None,
) -> tuple[dict[ContentKey, list[ScoredCandidate]], list[tuple]]:
    """Score every destination through Stage 2 + Stage 3, with reranking."""
    candidates_by_destination: dict[ContentKey, list[ScoredCandidate]] = {}
    diagnostics: list[tuple[int, str, str, dict[str, Any] | None]] = []
    shared = dict(
        dest_embeddings=dest_embeddings, stage1_candidates=stage1_candidates,
        content_records=content_records, sentence_ids_ordered=sentence_ids_ordered,
        sentence_embeddings=sentence_embeddings, sentence_records=sentence_records,
        sentence_id_to_row=sentence_id_to_row, existing_links=existing_links,
        existing_outgoing_counts=existing_outgoing_counts, settings=settings,
        feedback_rerank_service=feedback_rerank_service,
        candidates_by_destination=candidates_by_destination, diagnostics=diagnostics,
        fr099_fr105_caches=fr099_fr105_caches, graph_signal_ranker=graph_signal_ranker,
        phase6_contribution=phase6_contribution, anchor_garbage_dispatcher=anchor_garbage_dispatcher,
    )
    for dest_idx, dest_key in enumerate(destination_keys):
        _score_single_destination(dest_idx=dest_idx, dest_key=dest_key, **shared)
        if dest_idx % _SCORING_PROGRESS_INTERVAL == 0 and dest_idx > 0:
            pct = 0.50 + 0.35 * (dest_idx / items_in_scope)
            progress_fn(pct, f"Scored {dest_idx}/{items_in_scope} destinations...")
    return candidates_by_destination, diagnostics


def _score_single_destination(  # noqa: forbidden-pattern — 19-arg orchestrator; grouping into _ScoreCtx is a separate refactor
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
    phase6_contribution: Any = None,
    anchor_garbage_dispatcher: Any = None,
) -> None:
    """Score a single destination through Stage 2 + Stage 3."""
    destination = content_records[dest_key]
    host_sentence_ids = stage1_candidates.get(dest_key, [])
    matches = _score_sentences_stage2(
        destination_embedding=dest_embeddings[dest_idx], sentence_ids=host_sentence_ids,
        sentence_ids_ordered=sentence_ids_ordered, sentence_embeddings=sentence_embeddings,
        sentence_records=sentence_records, sentence_id_to_row=sentence_id_to_row, top_k=STAGE2_TOP_K,
    )
    if not matches:
        diagnostics.append((dest_key[0], dest_key[1], "no_semantic_matches", None))
        return
    blocked_reasons: set[str] = set()
    scored = score_destination_matches(
        destination, matches,
        content_records=content_records, sentence_records=sentence_records,
        existing_links=existing_links, existing_outgoing_counts=existing_outgoing_counts,
        **_score_kwargs_from_settings(settings),
        blocked_reasons=blocked_reasons, fr099_fr105_caches=fr099_fr105_caches,
        fr099_fr105_settings=settings.get("fr099_fr105"), graph_signal_ranker=graph_signal_ranker,
        phase6_contribution=phase6_contribution, anchor_garbage_dispatcher=anchor_garbage_dispatcher,
    )
    _collect_destination_result(
        dest_key=dest_key, destination=destination, scored=scored,
        blocked_reasons=blocked_reasons, settings=settings, content_records=content_records,
        feedback_rerank_service=feedback_rerank_service,
        candidates_by_destination=candidates_by_destination, diagnostics=diagnostics,
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
