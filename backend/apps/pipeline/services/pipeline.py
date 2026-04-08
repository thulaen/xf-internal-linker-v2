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
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Any, Callable

import numpy as np
import pyroaring as pr
from django.conf import settings
 
try:
    from extensions import inv_index, strpool  # noqa: F401
    HAS_CPP_EXT = True
except ImportError:
    HAS_CPP_EXT = False

try:
    from extensions import simsearch
    HAS_CPP_SIMSEARCH = True
except ImportError:
    HAS_CPP_SIMSEARCH = False

from .feedback_rerank import FeedbackRerankSettings, FeedbackRerankService
from .slate_diversity import SlateDiversitySettings, apply_slate_diversity
from .field_aware_relevance import FieldAwareRelevanceSettings
from .learned_anchor import LearnedAnchorInputRow, LearnedAnchorSettings
from .ranker import (
    ContentKey,
    ContentRecord,
    ExistingLinkKey,
    ScoredCandidate,
    SentenceRecord,
    SentenceSemanticMatch,
    SiloSettings,
    ClusteringSettings,
    derive_march_2026_pagerank_bounds,
    score_destination_matches,
    select_final_candidates,
)
from .text_tokens import tokenize_text
from .phrase_matching import PhraseMatchingSettings
from .rare_term_propagation import (
    RareTermPropagationSettings,
    build_rare_term_profiles,
)
from apps.suggestions.recommended_weights import recommended_float, recommended_str

logger = logging.getLogger(__name__)

STAGE1_TOP_K = 50
STAGE2_TOP_K = 10
FALLBACK_CANDIDATES_PER_DESTINATION = 5
BLOCK_SIZE = 256

DEFAULT_WEIGHTS = {
    "w_semantic": recommended_float("w_semantic"),
    "w_keyword": recommended_float("w_keyword"),
    "w_node": recommended_float("w_node"),
    "w_quality": recommended_float("w_quality"),
}


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
    """Execute the full 3-stage ML suggestion pipeline.

    Args:
        run_id: UUID string of the PipelineRun record.
        rerun_mode: 'skip_pending' | 'supersede_pending' | 'full_regenerate'
        destination_scope_ids: Restrict destinations to these ScopeItem PKs.
        destination_content_item_ids: Restrict destinations to these ContentItem PKs.
        host_scope_ids: Restrict hosts to these ScopeItem PKs.
        progress_fn: Optional callback(progress_0_to_1, message) for live updates.
    """

    def _progress(pct: float, msg: str) -> None:
        logger.info("[run=%s] %.0f%% — %s", run_id, pct * 100, msg)
        if progress_fn:
            progress_fn(pct, msg)

    suggestions_created = 0
    items_in_scope = 0

    _progress(0.02, "Loading settings and weights...")
    weights = _load_weights()
    silo_settings = _load_silo_settings()
    weighted_authority_settings = _load_weighted_authority_settings()
    link_freshness_settings = _load_link_freshness_settings()
    phrase_matching_settings = _load_phrase_matching_settings()
    learned_anchor_settings = _load_learned_anchor_settings()
    rare_term_settings = _load_rare_term_propagation_settings()
    field_aware_settings = _load_field_aware_relevance_settings()
    ga4_gsc_settings = _load_ga4_gsc_settings()
    click_distance_settings = _load_click_distance_settings()
    feedback_rerank_settings = _load_feedback_rerank_settings()
    clustering_settings = _load_clustering_settings()
    slate_diversity_settings = _load_slate_diversity_settings()
    max_host_reuse = _get_max_host_reuse()

    _progress(0.04, "Initializing feedback reranker...")
    feedback_rerank_service = FeedbackRerankService(feedback_rerank_settings)
    if feedback_rerank_settings.enabled:
        feedback_rerank_service.load_historical_stats()

    _progress(0.05, "Loading content records...")
    content_records = _load_content_records(
        destination_scope_ids=destination_scope_ids,
        host_scope_ids=host_scope_ids,
    )
    if not content_records:
        _progress(1.0, "No content records found — pipeline complete.")
        return PipelineResult(
            run_id=run_id,
            items_in_scope=0,
            suggestions_created=0,
            destinations_skipped=0,
        )

    _progress(0.08, "Loading sentence records...")
    sentence_records, content_to_sentence_ids = _load_sentence_records(
        set(content_records.keys())
    )

    _progress(0.12, "Loading existing links...")
    existing_links = _load_existing_links()
    # Count outgoing links per host — used by the max-links-per-host guard.
    existing_outgoing_counts: dict[ContentKey, int] = Counter(
        from_key for from_key, _to_key in existing_links
    )
    max_existing_links_per_host = _get_max_existing_links_per_host()
    max_anchor_words = _get_max_anchor_words()
    paragraph_window = _get_paragraph_window()
    learned_anchor_rows_by_destination = _load_learned_anchor_rows_by_destination()
    rare_term_profiles = {}
    if rare_term_settings.enabled:
        _progress(0.14, "Building rare-term propagation profiles...")
        rare_term_source_records = (
            content_records
            if destination_scope_ids is None and host_scope_ids is None and destination_content_item_ids is None
            else _load_content_records()
        )
        rare_term_profiles = build_rare_term_profiles(
            rare_term_source_records,
            settings=rare_term_settings,
        )

    _progress(0.15, "Applying rerun mode filter...")
    pending_destinations = _get_pending_destinations(rerun_mode)
    if rerun_mode == "supersede_pending":
        _supersede_pending_suggestions(list(content_records.keys()))

    _progress(0.18, "Loading destination embeddings from pgvector...")
    destination_keys, dest_embeddings = _load_destination_embeddings(
        content_records,
        pending_destinations=pending_destinations,
        destination_content_item_ids=destination_content_item_ids,
    )
    items_in_scope = len(destination_keys)

    if items_in_scope == 0:
        _progress(1.0, "No destinations to process — pipeline complete.")
        return PipelineResult(
            run_id=run_id,
            items_in_scope=0,
            suggestions_created=0,
            destinations_skipped=0,
        )

    _progress(0.22, "Loading sentence embeddings from pgvector...")
    sentence_ids_ordered, sentence_embeddings = _load_sentence_embeddings(
        set(content_records.keys())
    )

    if sentence_embeddings.shape[0] == 0:
        _progress(1.0, "No sentence embeddings available — pipeline complete.")
        return PipelineResult(
            run_id=run_id,
            items_in_scope=items_in_scope,
            suggestions_created=0,
            destinations_skipped=items_in_scope,
        )

    sentence_id_to_row = {
        sentence_id: index
        for index, sentence_id in enumerate(sentence_ids_ordered)
    }

    march_2026_pagerank_bounds = derive_march_2026_pagerank_bounds(content_records)

    _progress(0.25, "Stage 1: coarse content-level candidate retrieval...")
    stage1_candidates: dict[ContentKey, list[int]] = _stage1_candidates(
        destination_keys=destination_keys,
        dest_embeddings=dest_embeddings,
        content_records=content_records,
        content_to_sentence_ids=content_to_sentence_ids,
        top_k=STAGE1_TOP_K,
        block_size=BLOCK_SIZE,
    )

    _progress(0.50, "Stage 2+3: sentence scoring and ranking...")
    candidates_by_destination: dict[ContentKey, list[ScoredCandidate]] = {}
    diagnostics: list[tuple[int, str, str, dict[str, Any] | None]] = []

    for dest_idx, dest_key in enumerate(destination_keys):
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
            continue

        blocked_reasons: set[str] = set()
        scored = score_destination_matches(
            destination,
            matches,
            content_records=content_records,
            sentence_records=sentence_records,
            existing_links=existing_links,
            existing_outgoing_counts=existing_outgoing_counts,
            max_existing_links_per_host=max_existing_links_per_host,
            max_anchor_words=max_anchor_words,
            learned_anchor_rows_by_destination=learned_anchor_rows_by_destination,
            rare_term_profiles=rare_term_profiles,
            weights=weights,
            march_2026_pagerank_bounds=march_2026_pagerank_bounds,
            weighted_authority_ranking_weight=weighted_authority_settings["ranking_weight"],
            link_freshness_ranking_weight=link_freshness_settings["ranking_weight"],
            phrase_matching_settings=phrase_matching_settings,
            learned_anchor_settings=learned_anchor_settings,
            rare_term_settings=rare_term_settings,
            field_aware_settings=field_aware_settings,
            ga4_gsc_ranking_weight=ga4_gsc_settings["ranking_weight"],
            click_distance_ranking_weight=click_distance_settings["ranking_weight"],
            silo_settings=silo_settings,
            clustering_settings=clustering_settings,
            blocked_reasons=blocked_reasons,
        )

        if scored:
            if feedback_rerank_settings.enabled:
                scored = feedback_rerank_service.rerank_candidates(
                    scored,
                    host_scope_id_map={
                        c.host_content_id: content_records[(c.host_content_id, c.host_content_type)].scope_id
                        for c in scored
                    },
                    destination_scope_id_map={
                        destination.content_id: destination.scope_id
                    }
                )
            candidates_by_destination[dest_key] = scored
        elif "cross_silo_blocked" in blocked_reasons:
            diagnostics.append((
                dest_key[0],
                dest_key[1],
                "cross_silo_blocked",
                {
                    "mode": silo_settings.mode,
                    "destination_silo_group_id": destination.silo_group_id,
                    "destination_silo_group_name": destination.silo_group_name,
                },
            ))
        elif "max_links_reached" in blocked_reasons:
            diagnostics.append((dest_key[0], dest_key[1], "max_links_reached", None))
        elif "anchor_too_long" in blocked_reasons:
            diagnostics.append((dest_key[0], dest_key[1], "anchor_too_long", None))
        else:
            diagnostics.append((dest_key[0], dest_key[1], "all_candidates_filtered", None))

        if dest_idx % 100 == 0 and dest_idx > 0:
            pct = 0.50 + 0.35 * (dest_idx / items_in_scope)
            _progress(pct, f"Scored {dest_idx}/{items_in_scope} destinations...")

    # Build embedding lookup before freeing the numpy arrays (used by FR-015)
    embedding_lookup: dict[ContentKey, np.ndarray] = {
        dest_key: dest_embeddings[i]
        for i, dest_key in enumerate(destination_keys)
    }

    del dest_embeddings, sentence_embeddings
    gc.collect()

    if slate_diversity_settings.enabled:
        _progress(0.87, "FR-015: applying slate diversity reranking...")
        selected_candidates = apply_slate_diversity(
            candidates_by_destination=candidates_by_destination,
            embedding_lookup=embedding_lookup,
            settings=slate_diversity_settings,
            max_per_host=max_host_reuse,
        )
    else:
        _progress(0.87, "Resolving host-reuse, circular-pair, and paragraph-cluster filters...")
        blocked_diagnostics: dict[ContentKey, str] = {}
        selected_candidates = select_final_candidates(
            candidates_by_destination,
            max_host_reuse=max_host_reuse,
            sentence_records=sentence_records,
            paragraph_window=paragraph_window,
            blocked_diagnostics=blocked_diagnostics,
        )
        for dest_key, reason in blocked_diagnostics.items():
            diagnostics.append((dest_key[0], dest_key[1], reason, None))

    _progress(0.92, "Persisting suggestions...")
    suggestions_created = _persist_suggestions(
        run_id=run_id,
        selected_candidates=selected_candidates,
        content_records=content_records,
        sentence_records=sentence_records,
        rerun_mode=rerun_mode,
    )

    _persist_diagnostics(run_id=run_id, diagnostics=diagnostics)

    _progress(1.0, f"Pipeline complete — {suggestions_created} suggestions created.")
    return PipelineResult(
        run_id=run_id,
        items_in_scope=items_in_scope,
        suggestions_created=suggestions_created,
        destinations_skipped=items_in_scope - suggestions_created,
    )


# ---------------------------------------------------------------------------
# Data loaders
# ---------------------------------------------------------------------------

def _load_weights() -> dict[str, float]:
    try:
        from apps.core.models import AppSetting
        qs = AppSetting.objects.filter(
            key__in=["w_semantic", "w_keyword", "w_node", "w_quality"]
        ).values_list("key", "value")
        overrides = {k: float(v) for k, v in qs}
        return {**DEFAULT_WEIGHTS, **overrides}
    except Exception:
        logger.exception("Failed to load pipeline weights; using defaults.")
        return dict(DEFAULT_WEIGHTS)


def _get_max_host_reuse() -> int:
    try:
        from apps.core.models import AppSetting
        setting = AppSetting.objects.filter(key="max_host_reuse").first()
        if setting:
            return int(setting.value)
    except Exception:
        logger.exception("Failed to load max host reuse; using default.")
    return 3


def _get_max_existing_links_per_host() -> int:
    """Maximum number of existing outgoing body links a host page may already
    have before the pipeline stops adding new suggestions to it.

    Configurable via AppSetting key ``spam_guards.max_existing_links_per_host``.
    Default: 2 — Ntoulas et al. (US20060184500A1) anchor-word fraction research
    and the 2024 Google API leak findings support this as a conservative cap.
    """
    try:
        from apps.core.models import AppSetting
        setting = AppSetting.objects.filter(key="spam_guards.max_existing_links_per_host").first()
        if setting:
            return int(setting.value)
    except Exception:
        logger.exception("Failed to load spam_guards.max_existing_links_per_host; using default.")
    return 2


def _get_max_anchor_words() -> int:
    """Maximum number of words allowed in suggested anchor text.

    Configurable via AppSetting key ``spam_guards.max_anchor_words``.
    Default: 4 — Google recommends 2–5 words (link best-practices docs);
    US8380722B2 states anchors are "usually short and descriptive";
    empirical average of natural anchor text is ~4.85 words (seo.ai, 23M links).
    """
    try:
        from apps.core.models import AppSetting
        setting = AppSetting.objects.filter(key="spam_guards.max_anchor_words").first()
        if setting:
            return int(setting.value)
    except Exception:
        logger.exception("Failed to load spam_guards.max_anchor_words; using default.")
    return 4


def _get_paragraph_window() -> int:
    """Sentence-position window used to detect paragraph-level link clustering.

    Two suggested links on the same host page are considered to be in the same
    paragraph when their sentence positions are within this many positions of
    each other. Only the higher-scoring suggestion is kept.

    Configurable via AppSetting key ``spam_guards.paragraph_window``.
    Default: 3 — backed by US8577893B1 (Google ±5-word context window per link)
    and Google's documented guidance against placing multiple links close together.
    """
    try:
        from apps.core.models import AppSetting
        setting = AppSetting.objects.filter(key="spam_guards.paragraph_window").first()
        if setting:
            return int(setting.value)
    except Exception:
        logger.exception("Failed to load spam_guards.paragraph_window; using default.")
    return 3


def _load_silo_settings() -> SiloSettings:
    try:
        from apps.core.views import get_silo_settings

        config = get_silo_settings()
        return SiloSettings(
            mode=str(config.get("mode", recommended_str("silo.mode"))),
            same_silo_boost=float(config.get("same_silo_boost", recommended_float("silo.same_silo_boost"))),
            cross_silo_penalty=float(config.get("cross_silo_penalty", recommended_float("silo.cross_silo_penalty"))),
        )
    except Exception:
        logger.exception("Failed to load silo settings; using defaults.")
        return SiloSettings()


def _load_weighted_authority_settings() -> dict[str, float]:
    try:
        from apps.core.views import get_weighted_authority_settings

        config = get_weighted_authority_settings()
        return {
            "ranking_weight": float(config.get("ranking_weight", recommended_float("weighted_authority.ranking_weight"))),
        }
    except Exception:
        logger.exception("Failed to load weighted authority settings; using defaults.")
        return {
            "ranking_weight": recommended_float("weighted_authority.ranking_weight"),
        }


def _load_link_freshness_settings() -> dict[str, float]:
    try:
        from apps.core.views import get_link_freshness_settings

        config = get_link_freshness_settings()
        return {
            "ranking_weight": float(config.get("ranking_weight", recommended_float("link_freshness.ranking_weight"))),
        }
    except Exception:
        logger.exception("Failed to load link freshness settings; using defaults.")
        return {
            "ranking_weight": recommended_float("link_freshness.ranking_weight"),
        }


def _load_phrase_matching_settings() -> PhraseMatchingSettings:
    try:
        from apps.core.views import get_phrase_matching_settings

        config = get_phrase_matching_settings()
        return PhraseMatchingSettings(
            ranking_weight=float(config.get("ranking_weight", recommended_float("phrase_matching.ranking_weight"))),
            enable_anchor_expansion=bool(config.get("enable_anchor_expansion", True)),
            enable_partial_matching=bool(config.get("enable_partial_matching", True)),
            context_window_tokens=int(config.get("context_window_tokens", recommended_float("phrase_matching.context_window_tokens"))),
        )
    except Exception:
        logger.exception("Failed to load phrase matching settings; using defaults.")
        return PhraseMatchingSettings()


def _load_learned_anchor_settings() -> LearnedAnchorSettings:
    try:
        from apps.core.views import get_learned_anchor_settings

        config = get_learned_anchor_settings()
        return LearnedAnchorSettings(
            ranking_weight=float(config.get("ranking_weight", recommended_float("learned_anchor.ranking_weight"))),
            minimum_anchor_sources=int(config.get("minimum_anchor_sources", recommended_float("learned_anchor.minimum_anchor_sources"))),
            minimum_family_support_share=float(config.get("minimum_family_support_share", recommended_float("learned_anchor.minimum_family_support_share"))),
            enable_noise_filter=bool(config.get("enable_noise_filter", True)),
        )
    except Exception:
        logger.exception("Failed to load learned anchor settings; using defaults.")
        return LearnedAnchorSettings()


def _load_rare_term_propagation_settings() -> RareTermPropagationSettings:
    try:
        from apps.core.views import get_rare_term_propagation_settings

        config = get_rare_term_propagation_settings()
        return RareTermPropagationSettings(
            enabled=bool(config.get("enabled", True)),
            ranking_weight=float(config.get("ranking_weight", recommended_float("rare_term_propagation.ranking_weight"))),
            max_document_frequency=int(config.get("max_document_frequency", recommended_float("rare_term_propagation.max_document_frequency"))),
            minimum_supporting_related_pages=int(config.get("minimum_supporting_related_pages", recommended_float("rare_term_propagation.minimum_supporting_related_pages"))),
        )
    except Exception:
        logger.exception("Failed to load rare-term propagation settings; using defaults.")
        return RareTermPropagationSettings()


def _load_field_aware_relevance_settings() -> FieldAwareRelevanceSettings:
    try:
        from apps.core.views import get_field_aware_relevance_settings

        config = get_field_aware_relevance_settings()
        return FieldAwareRelevanceSettings(
            ranking_weight=float(config.get("ranking_weight", recommended_float("field_aware_relevance.ranking_weight"))),
            title_field_weight=float(config.get("title_field_weight", recommended_float("field_aware_relevance.title_field_weight"))),
            body_field_weight=float(config.get("body_field_weight", recommended_float("field_aware_relevance.body_field_weight"))),
            scope_field_weight=float(config.get("scope_field_weight", recommended_float("field_aware_relevance.scope_field_weight"))),
            learned_anchor_field_weight=float(config.get("learned_anchor_field_weight", recommended_float("field_aware_relevance.learned_anchor_field_weight"))),
        )
    except Exception:
        logger.exception("Failed to load field-aware relevance settings; using defaults.")
        return FieldAwareRelevanceSettings()


def _load_ga4_gsc_settings() -> dict[str, float]:
    try:
        from apps.core.views import get_ga4_gsc_settings

        config = get_ga4_gsc_settings()
        return {
            "ranking_weight": float(config.get("ranking_weight", recommended_float("ga4_gsc.ranking_weight"))),
        }
    except Exception:
        logger.exception("Failed to load GA4/GSC settings; using defaults.")
        return {
            "ranking_weight": recommended_float("ga4_gsc.ranking_weight"),
        }


def _load_click_distance_settings() -> dict[str, float]:
    try:
        from apps.core.views import get_click_distance_settings

        config = get_click_distance_settings()
        return {
            "ranking_weight": float(config.get("ranking_weight", recommended_float("click_distance.ranking_weight"))),
        }
    except Exception:
        logger.exception("Failed to load click-distance settings; using defaults.")
        return {
            "ranking_weight": recommended_float("click_distance.ranking_weight"),
        }


def _load_feedback_rerank_settings() -> FeedbackRerankSettings:
    """Load feedback-driven explore/exploit settings from the DB."""
    try:
        from apps.core.views import get_feedback_rerank_settings
        raw = get_feedback_rerank_settings()
        return FeedbackRerankSettings(
            enabled=raw["enabled"],
            ranking_weight=raw["ranking_weight"],
            exploration_rate=raw["exploration_rate"],
        )
    except Exception:
        logger.exception("Failed to load feedback rerank settings; using defaults.")
        return FeedbackRerankSettings()


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
    for ci in qs.iterator(chunk_size=500):
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
            rows = cursor.fetchmany(2000)
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
        "from_content_item__pk", "from_content_item__content_type",
        "to_content_item__pk", "to_content_item__content_type",
    )
    return {
        (
            (from_pk, from_type),
            (to_pk, to_type),
        )
        for from_pk, from_type, to_pk, to_type in qs
    }


def _load_learned_anchor_rows_by_destination() -> dict[ContentKey, list[LearnedAnchorInputRow]]:
    from apps.graph.models import ExistingLink

    rows_by_destination: dict[ContentKey, list[LearnedAnchorInputRow]] = defaultdict(list)
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
        key for key in content_records
        if key not in pending_destinations
        and (destination_content_item_ids is None or key[0] in destination_content_item_ids)
    ]
    if not candidate_keys:
        return (), np.empty((0, EMBEDDING_DIM), dtype=np.float32)

    pks = [pk for pk, _ in candidate_keys]
    qs = ContentItem.objects.filter(
        pk__in=pks,
        embedding__isnull=False,
    ).values_list("pk", "content_type", "embedding")

    found: dict[ContentKey, np.ndarray] = {}
    for pk, ct, emb in qs:
        if emb is not None:
            found[(pk, ct)] = _coerce_embedding_vector(emb)

    valid_keys = [key for key in candidate_keys if key in found]
    if not valid_keys:
        return (), np.empty((0, EMBEDDING_DIM), dtype=np.float32)

    matrix = np.vstack([found[key] for key in valid_keys]).astype(np.float32, copy=False)
    return tuple(valid_keys), matrix


def _load_sentence_embeddings(
    content_keys: set[ContentKey],
) -> tuple[list[int], np.ndarray]:
    """Load sentence embeddings from pgvector with bounded memory use."""
    from django.db import connection

    content_pks = sorted({pk for pk, _ in content_keys})
    if not content_pks:
        return [], np.empty((0, EMBEDDING_DIM), dtype=np.float32)

    in_clause, params = _sql_in_clause_params(content_pks)
    query = f"""
        SELECT id, embedding
        FROM content_sentence
        WHERE content_item_id IN ({in_clause})
          AND word_position <= %s
          AND embedding IS NOT NULL
        ORDER BY id
    """
    ids: list[int] = []
    vectors: list[list[float]] = []

    with connection.cursor() as cursor:
        cursor.execute(query, [*params, settings.HOST_SCAN_WORD_LIMIT])
        while True:
            rows = cursor.fetchmany(1000)
            if not rows:
                break
            for sentence_id, embedding in rows:
                ids.append(sentence_id)
                vectors.append(_coerce_embedding_vector(embedding))

    if not ids:
        return [], np.empty((0, EMBEDDING_DIM), dtype=np.float32)

    return ids, np.vstack(vectors).astype(np.float32, copy=False)


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
) -> dict[ContentKey, list[int]]:
    """Stage 1: find top-K host content items per destination via cosine similarity.

    Returns a mapping from destination_key -> flat list of candidate sentence IDs
    (all sentences from the top-K host content items).
    """
    # Build a host embedding matrix from content items that have sentence embeddings
    host_keys = [
        key for key in content_records
        if key in content_to_sentence_ids and content_to_sentence_ids[key]
    ]
    if not host_keys:
        return {}

    from .faiss_index import is_faiss_gpu_active, faiss_search, build_faiss_index, HAS_FAISS

    host_pk_set = {pk for pk, _ in host_keys}

    use_faiss = is_faiss_gpu_active()

    if not use_faiss and HAS_FAISS:
        # JIT build: FAISS is installed but index not yet populated in this process.
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
        logger.warning("FAISS installed but no embeddings in DB — returning empty Stage 1 results")
        return {}

    # NumPy fallback path — faiss package not installed -------------------------
    from apps.content.models import ContentItem
    host_pks_list = [pk for pk, _ in host_keys]
    host_emb_qs = ContentItem.objects.filter(
        pk__in=host_pks_list,
        embedding__isnull=False,
    ).values_list("pk", "content_type", "embedding")

    host_emb_map: dict[ContentKey, np.ndarray] = {
        (pk, ct): _coerce_embedding_vector(emb) for pk, ct, emb in host_emb_qs if emb is not None
    }
    valid_host_keys = [k for k in host_keys if k in host_emb_map]
    if not valid_host_keys:
        return {}

    host_matrix = np.vstack([host_emb_map[k] for k in valid_host_keys]).astype(np.float32, copy=False)

    result: dict[ContentKey, list[int]] = {}
    n_dest = len(destination_keys)

    for block_start in range(0, n_dest, block_size):
        block_end = min(block_start + block_size, n_dest)
        dest_block = dest_embeddings[block_start:block_end]
        dest_keys_block = destination_keys[block_start:block_end]

        # cosine similarity: dest_block (B, D) @ host_matrix.T (D, H) -> (B, H)
        sims = dest_block @ host_matrix.T

        for b_idx, dest_key in enumerate(dest_keys_block):
            row = sims[b_idx]
            # Get top-K host indices (excluding self)
            top_indices = np.argpartition(row, -min(top_k, len(valid_host_keys)))[-top_k:]
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
            sentence_id: index
            for index, sentence_id in enumerate(sentence_ids_ordered)
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
        scores = candidate_matrix @ destination_embedding  # cosine similarity (normalized)

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
        matches.append(SentenceSemanticMatch(
            host_content_id=record.content_id,
            host_content_type=record.content_type,
            sentence_id=sid,
            score_semantic=float(score),
        ))

    return matches


# ---------------------------------------------------------------------------
# Persist suggestions
# ---------------------------------------------------------------------------

def _persist_suggestions(
    *,
    run_id: str,
    selected_candidates: list[ScoredCandidate],
    content_records: dict[ContentKey, ContentRecord],
    sentence_records: dict[int, SentenceRecord],
    rerun_mode: str,
) -> int:
    """Create Suggestion records for the selected candidates.

    For full_regenerate mode, deletes existing pending/superseded suggestions
    for the same destination before inserting new ones.
    """
    from apps.content.models import ContentItem, Sentence
    from apps.suggestions.models import PipelineRun, Suggestion

    try:
        run = PipelineRun.objects.get(run_id=run_id)
    except PipelineRun.DoesNotExist:
        run = None

    valid_candidates: list[ScoredCandidate] = []
    content_item_ids: set[int] = set()
    sentence_ids: set[int] = set()
    destination_ids_to_replace: set[int] = set()

    for candidate in selected_candidates:
        dest_key = candidate.destination_key
        dest_record = content_records.get(dest_key)
        sentence_record = sentence_records.get(candidate.host_sentence_id)
        if dest_record is None or sentence_record is None:
            continue
        valid_candidates.append(candidate)
        content_item_ids.add(candidate.destination_content_id)
        content_item_ids.add(candidate.host_content_id)
        sentence_ids.add(candidate.host_sentence_id)
        if rerun_mode == "full_regenerate":
            destination_ids_to_replace.add(candidate.destination_content_id)

    if not valid_candidates:
        return 0

    content_items = ContentItem.objects.in_bulk(content_item_ids)
    sentences = Sentence.objects.in_bulk(sentence_ids)

    if destination_ids_to_replace:
        Suggestion.objects.filter(
            destination_id__in=destination_ids_to_replace,
            status__in=["pending", "superseded"],
        ).delete()

    to_create: list[Suggestion] = []
    for candidate in valid_candidates:
        dest_ci = content_items.get(candidate.destination_content_id)
        host_ci = content_items.get(candidate.host_content_id)
        host_sentence = sentences.get(candidate.host_sentence_id)
        if dest_ci is None or host_ci is None or host_sentence is None:
            continue

        to_create.append(
            Suggestion(
                pipeline_run=run,
                destination=dest_ci,
                host=host_ci,
                host_sentence=host_sentence,
                destination_title=dest_ci.title,
                host_sentence_text=host_sentence.text,
                anchor_phrase=candidate.anchor_phrase,
                anchor_start=candidate.anchor_start,
                anchor_end=candidate.anchor_end,
                anchor_confidence=candidate.anchor_confidence,
                score_semantic=candidate.score_semantic,
                score_keyword=candidate.score_keyword,
                score_node_affinity=candidate.score_node_affinity,
                score_quality=candidate.score_quality,
                score_march_2026_pagerank=dest_ci.march_2026_pagerank_score,
                score_velocity=dest_ci.velocity_score,
                score_link_freshness=dest_ci.link_freshness_score,
                score_phrase_relevance=candidate.score_phrase_relevance,
                score_learned_anchor_corroboration=candidate.score_learned_anchor_corroboration,
                score_rare_term_propagation=candidate.score_rare_term_propagation,
                score_field_aware_relevance=candidate.score_field_aware_relevance,
                score_ga4_gsc=candidate.score_ga4_gsc,
                score_click_distance=candidate.score_click_distance,
                score_explore_exploit=candidate.score_explore_exploit,
                score_cluster_suppression=candidate.score_cluster_suppression,
                score_slate_diversity=candidate.score_slate_diversity,
                slate_diversity_diagnostics=candidate.slate_diversity_diagnostics or {},
                phrase_match_diagnostics=candidate.phrase_match_diagnostics,
                learned_anchor_diagnostics=candidate.learned_anchor_diagnostics,
                rare_term_diagnostics=candidate.rare_term_diagnostics,
                field_aware_diagnostics=candidate.field_aware_diagnostics,
                click_distance_diagnostics=candidate.click_distance_diagnostics,
                explore_exploit_diagnostics=candidate.explore_exploit_diagnostics,
                cluster_diagnostics=candidate.cluster_diagnostics,
                score_final=candidate.score_final,
                status="pending",
            )
        )

    if to_create:
        Suggestion.objects.bulk_create(to_create)

    return len(to_create)


def _persist_diagnostics(
    *,
    run_id: str,
    diagnostics: list[tuple[int, str, str, dict[str, Any] | None]],
) -> None:
    """Persist pipeline diagnostics (why-no-suggestion records)."""
    from apps.suggestions.models import PipelineDiagnostic, PipelineRun
    from apps.content.models import ContentItem

    try:
        run = PipelineRun.objects.get(run_id=run_id)
    except PipelineRun.DoesNotExist:
        return

    content_items = {
        (content_item.pk, content_item.content_type): content_item
        for content_item in ContentItem.objects.filter(
            pk__in={content_id for content_id, _, _, _ in diagnostics}
        )
    }

    to_create = []
    for content_id, content_type, reason, detail in diagnostics:
        ci = content_items.get((content_id, content_type))
        if ci is None:
            continue
        to_create.append(PipelineDiagnostic(
            pipeline_run=run,
            destination=ci,
            skip_reason=reason,
            detail=detail or {},
        ))

    if to_create:
        PipelineDiagnostic.objects.bulk_create(to_create, ignore_conflicts=True)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _destination_text(title: str, distilled_text: str) -> str:
    title_clean = (title or "").strip()
    distilled_clean = (distilled_text or "").strip()
    if distilled_clean:
        return f"{title_clean}\n\n{distilled_clean}".strip()
    return title_clean


def _load_clustering_settings() -> ClusteringSettings:
    """Load near-duplicate clustering settings from the DB."""
    try:
        from apps.core.views import get_clustering_settings
        raw = get_clustering_settings()
        return ClusteringSettings(
            enabled=raw["enabled"],
            similarity_threshold=raw["similarity_threshold"],
            suppression_penalty=raw["suppression_penalty"],
        )
    except Exception:
        logger.exception("Failed to load clustering settings; using defaults.")
        return ClusteringSettings()


def _load_slate_diversity_settings() -> SlateDiversitySettings:
    """Load FR-015 slate diversity settings from the DB."""
    try:
        from apps.core.views import get_slate_diversity_settings
        raw = get_slate_diversity_settings()
        return SlateDiversitySettings(
            enabled=raw["enabled"],
            diversity_lambda=raw["diversity_lambda"],
            score_window=raw["score_window"],
            similarity_cap=raw["similarity_cap"],
        )
    except Exception:
        logger.exception("Failed to load slate diversity settings; using defaults.")
        return SlateDiversitySettings()


try:
    from .embeddings import EMBEDDING_DIM
except ImportError:
    EMBEDDING_DIM = 1024
