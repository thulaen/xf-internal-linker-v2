"""Main suggestion pipeline service.

3-stage retrieval pipeline:
  Stage 1 — coarse cosine similarity between destination and host-content embeddings
  Stage 2 — fine-grained sentence-level cosine similarity
  Stage 3 — composite scoring (semantic + keyword + node affinity + quality)

V2 changes from V1:
  - Replaces raw SQLite + .npy file artifacts with Django ORM + pgvector VectorField
  - Replaces Flask mark_job_progress with the channel-layer _publish_progress helper
  - All data is loaded from PostgreSQL (ContentItem.embedding, Sentence.embedding)
  - Supports rerun_modes: skip_pending, supersede_pending, full_regenerate
"""

from __future__ import annotations

import gc
import logging
from dataclasses import dataclass
from typing import Any, Callable

import numpy as np

from .feedback_rerank import FeedbackRerankService
from .slate_diversity import apply_slate_diversity
from .ranker import (
    ContentKey,
    ContentRecord,
    ScoredCandidate,
    SentenceRecord,
    select_final_candidates,
)

# Re-export settings loader functions so existing imports keep working.
from .pipeline_loaders import (  # noqa: F401
    DEFAULT_WEIGHTS,
    _get_max_anchor_words,
    _get_max_existing_links_per_host,
    _get_max_host_reuse,
    _get_paragraph_window,
    _load_all_pipeline_settings,
    _load_anchor_diversity_settings,
    _load_click_distance_settings,
    _load_clustering_settings,
    _load_feedback_rerank_settings,
    _load_field_aware_relevance_settings,
    _load_ga4_gsc_settings,
    _load_keyword_stuffing_settings,
    _load_learned_anchor_settings,
    _load_link_freshness_settings,
    _load_link_farm_settings,
    _load_phrase_matching_settings,
    _load_rare_term_propagation_settings,
    _load_silo_settings,
    _load_slate_diversity_settings,
    _load_weighted_authority_settings,
    _load_weights,
)

# Re-export data loader functions so existing imports keep working.
from .pipeline_data import (  # noqa: F401
    EMBEDDING_DIM,
    _coerce_embedding_vector,
    _destination_text,
    _get_pending_destinations,
    _load_content_records,
    _load_destination_embeddings,
    _load_existing_links,
    _load_learned_anchor_rows_by_destination,
    _load_pipeline_content,
    _load_pipeline_embeddings,
    _load_pipeline_resources,
    _load_sentence_embeddings,
    _load_sentence_records,
    _supersede_pending_suggestions,
)

# Re-export stage functions so existing imports keep working.
from .pipeline_stages import (  # noqa: F401
    BLOCK_SIZE,
    FALLBACK_CANDIDATES_PER_DESTINATION,
    MIN_SEMANTIC_SCORE,
    STAGE1_TOP_K,
    STAGE2_TOP_K,
    _collect_destination_result,
    _score_all_destinations,
    _score_sentences_stage2,
    _score_single_destination,
    _stage1_candidates,
    _stage1_numpy_fallback,
)

# Re-export persistence functions so existing imports keep working.
from .pipeline_persist import (  # noqa: F401
    _build_suggestion_records,
    _persist_diagnostics,
    _persist_suggestions,
)

logger = logging.getLogger(__name__)

_PCT_MULTIPLIER = 100  # maxsize


@dataclass
class PipelineResult:
    run_id: str
    items_in_scope: int
    suggestions_created: int
    destinations_skipped: int

    @property
    def suggestions_skipped(self) -> int:
        return self.destinations_skipped


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def run_pipeline(
    run_id: str,
    *,
    rerun_mode: str = "skip_pending",
    destination_scope_ids: set[int] | None = None,
    destination_content_item_ids: set[int] | None = None,
    host_scope_ids: set[int] | None = None,
    progress_fn: Callable[[float, str], None] | None = None,
) -> PipelineResult:
    """Execute the full 3-stage ML suggestion pipeline."""

    def _progress(pct: float, msg: str) -> None:
        logger.info("[run=%s] %.0f%% — %s", run_id, pct * _PCT_MULTIPLIER, msg)
        if progress_fn:
            progress_fn(pct, msg)

    _progress(0.02, "Loading settings and weights...")
    settings = _load_all_pipeline_settings()
    settings.setdefault("anchor_diversity", _load_anchor_diversity_settings())
    settings.setdefault("keyword_stuffing", _load_keyword_stuffing_settings())
    settings.setdefault("link_farm", _load_link_farm_settings())

    _progress(0.04, "Initializing feedback reranker...")
    feedback_rerank_service = FeedbackRerankService(settings["feedback_rerank"])
    if settings["feedback_rerank"].enabled:
        feedback_rerank_service.load_historical_stats()

    _progress(0.05, "Loading pipeline data...")
    resource_kwargs = dict(
        destination_scope_ids=destination_scope_ids,
        destination_content_item_ids=destination_content_item_ids,
        host_scope_ids=host_scope_ids,
        rerun_mode=rerun_mode,
        rare_term_settings=settings["rare_term"],
        keyword_stuffing_settings=settings["keyword_stuffing"],
        link_farm_settings=settings["link_farm"],
        progress_fn=_progress,
        fr099_fr105_settings=settings.get("fr099_fr105"),
    )
    data = _load_pipeline_resources(**resource_kwargs)
    if isinstance(data, PipelineResult):
        return data

    stages_kwargs = dict(
        run_id=run_id,
        rerun_mode=rerun_mode,
        data=data,
        settings=settings,
        feedback_rerank_service=feedback_rerank_service,
        progress_fn=_progress,
    )
    return _execute_pipeline_stages(**stages_kwargs)


def _execute_pipeline_stages(
    *,
    run_id: str,
    rerun_mode: str,
    data: dict[str, Any],
    settings: dict[str, Any],
    feedback_rerank_service: Any,
    progress_fn: Callable,
) -> PipelineResult:
    """Run Stage 1, Stage 2+3, and finalize the pipeline."""
    progress_fn(0.25, "Stage 1: coarse content-level candidate retrieval...")
    stage1_kwargs = dict(
        destination_keys=data["destination_keys"],
        dest_embeddings=data["dest_embeddings"],
        content_records=data["content_records"],
        content_to_sentence_ids=data["content_to_sentence_ids"],
        top_k=STAGE1_TOP_K,
        block_size=BLOCK_SIZE,
    )
    stage1_candidates: dict[ContentKey, list[int]] = _stage1_candidates(**stage1_kwargs)

    progress_fn(0.50, "Stage 2+3: sentence scoring and ranking...")
    settings.update(
        max_existing_links_per_host=data["max_existing_links_per_host"],
        max_anchor_words=data["max_anchor_words"],
        learned_anchor_rows=data["learned_anchor_rows_by_destination"],
        anchor_history_by_destination=data.get("anchor_history_by_destination", {}),
        rare_term_profiles=data["rare_term_profiles"],
        keyword_stuffing_by_destination=data.get("keyword_stuffing_by_destination", {}),
        link_farm_by_destination=data.get("link_farm_by_destination", {}),
        pagerank_bounds=data["march_2026_pagerank_bounds"],
    )
    # W3c — load HITS / PPR / TrustRank snapshots once and bundle them with
    # weights into a GraphSignalRanker. ``build_graph_signal_ranker`` returns
    # None when the feature is disabled, every weight is zero, or no W1
    # job has populated the store yet — in which case the ranker is a no-op.
    from .graph_signal_ranker import build_graph_signal_ranker

    graph_signal_settings = settings.get("graph_signals") or {}
    graph_signal_ranker = build_graph_signal_ranker(
        weights=graph_signal_settings.get("weights", {}),
        enabled=bool(graph_signal_settings.get("enabled", True)),
    )

    # Slice 5 — Phase 6 ranker-time contribution dispatcher (six
    # picks wired: VADER #22, KenLM #23, LDA #18, Node2Vec #37,
    # BPR #38, FM #39). Each pick has a paper-backed default
    # ``ranking_weight`` in apps/suggestions/recommended_weights.py;
    # cold-start safe — adapters return 0.0 when their underlying
    # model file isn't trained yet, so flipping every pick on doesn't
    # perturb a fresh install until the W1 jobs populate models.
    # Killswitch: AppSetting key ``phase6_ranker.enabled``.
    from .phase6_ranker_contribution import build_phase6_contribution

    phase6_killswitch = bool(
        settings.get(
            "phase6_ranker_enabled",
            settings.get("phase6_ranker", {}).get("enabled", True),
        )
    )
    phase6_contribution = build_phase6_contribution(
        enabled_global=phase6_killswitch,
    )

    # PR-Anchor — anti-generic / pro-descriptive anchor signals.
    # Three composable algos (Aho-Corasick blacklist + Damerau-
    # Levenshtein/Jaccard descriptiveness + Shannon-entropy /
    # Iglewicz-Hoaglin outlier detection). build_* returns None when
    # the master toggle is off or ranking_weight = 0, so the ranker
    # short-circuits cleanly.
    from .anchor_garbage_signals import build_anchor_garbage_signals

    anchor_garbage_dispatcher = build_anchor_garbage_signals()

    scoring_kwargs = dict(
        destination_keys=data["destination_keys"],
        dest_embeddings=data["dest_embeddings"],
        stage1_candidates=stage1_candidates,
        content_records=data["content_records"],
        sentence_ids_ordered=data["sentence_ids_ordered"],
        sentence_embeddings=data["sentence_embeddings"],
        sentence_records=data["sentence_records"],
        sentence_id_to_row=data["sentence_id_to_row"],
        existing_links=data["existing_links"],
        existing_outgoing_counts=data["existing_outgoing_counts"],
        settings=settings,
        feedback_rerank_service=feedback_rerank_service,
        progress_fn=progress_fn,
        items_in_scope=data["items_in_scope"],
        fr099_fr105_caches=data.get("fr099_fr105_caches"),
        graph_signal_ranker=graph_signal_ranker,
        phase6_contribution=phase6_contribution,
        anchor_garbage_dispatcher=anchor_garbage_dispatcher,
    )
    candidates_by_destination, diagnostics = _score_all_destinations(**scoring_kwargs)

    finalize_kwargs = dict(
        run_id=run_id,
        rerun_mode=rerun_mode,
        settings=settings,
        destination_keys=data["destination_keys"],
        dest_embeddings=data["dest_embeddings"],
        sentence_embeddings=data["sentence_embeddings"],
        candidates_by_destination=candidates_by_destination,
        diagnostics=diagnostics,
        content_records=data["content_records"],
        sentence_records=data["sentence_records"],
        paragraph_window=data["paragraph_window"],
        items_in_scope=data["items_in_scope"],
        # Pick #28 — corpus stats reused at suggestion-write time.
        keyword_baseline=data.get("keyword_baseline"),
        progress_fn=progress_fn,
    )
    return _finalize_pipeline(**finalize_kwargs)


def _finalize_pipeline(
    *,
    run_id: str,
    rerun_mode: str,
    settings: dict[str, Any],
    destination_keys: tuple[ContentKey, ...],
    dest_embeddings: np.ndarray,
    sentence_embeddings: np.ndarray,
    candidates_by_destination: dict[ContentKey, list[ScoredCandidate]],
    diagnostics: list[tuple],
    content_records: dict[ContentKey, ContentRecord],
    sentence_records: dict[int, SentenceRecord],
    paragraph_window: int,
    items_in_scope: int,
    progress_fn: Callable,
    keyword_baseline: Any = None,
) -> PipelineResult:
    """Apply diversity/filtering, persist suggestions, and return the result."""
    embedding_lookup: dict[ContentKey, np.ndarray] = {
        dest_key: dest_embeddings[i] for i, dest_key in enumerate(destination_keys)
    }

    del dest_embeddings, sentence_embeddings
    gc.collect()

    if settings["slate_diversity"].enabled:
        progress_fn(0.87, "FR-15: applying slate diversity reranking...")
        selected_candidates = apply_slate_diversity(
            candidates_by_destination=candidates_by_destination,
            embedding_lookup=embedding_lookup,
            settings=settings["slate_diversity"],
            max_per_host=settings["max_host_reuse"],
        )
    else:
        progress_fn(
            0.87,
            "Resolving host-reuse, circular-pair, and paragraph-cluster filters...",
        )
        blocked_diagnostics: dict[ContentKey, str] = {}
        selected_candidates = select_final_candidates(
            candidates_by_destination,
            max_host_reuse=settings["max_host_reuse"],
            sentence_records=sentence_records,
            paragraph_window=paragraph_window,
            blocked_diagnostics=blocked_diagnostics,
        )
        for dest_key, reason in blocked_diagnostics.items():
            diagnostics.append((dest_key[0], dest_key[1], reason, None))

    progress_fn(0.92, "Persisting suggestions...")
    suggestions_created = _persist_suggestions(
        run_id=run_id,
        selected_candidates=selected_candidates,
        content_records=content_records,
        sentence_records=sentence_records,
        rerun_mode=rerun_mode,
        # Pick #28 — pass the same KeywordBaseline the keyword-
        # stuffing detector used so QL-Dirichlet doesn't have to
        # walk the corpus a second time.
        keyword_baseline=keyword_baseline,
    )

    _persist_diagnostics(run_id=run_id, diagnostics=diagnostics)

    progress_fn(1.0, f"Pipeline complete — {suggestions_created} suggestions created.")
    return PipelineResult(
        run_id=run_id,
        items_in_scope=items_in_scope,
        suggestions_created=suggestions_created,
        destinations_skipped=items_in_scope - suggestions_created,
    )
