"""Composite scoring and anti-junk selection for link suggestions.

This module is pure Python — no database access. All DB loading is done
by the pipeline service which passes pre-built records into these functions.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
import heapq
import math
import numpy as np
from typing import Mapping, TypeAlias
 
try:
    from extensions import scoring
    HAS_CPP_EXT = True
except ImportError:
    HAS_CPP_EXT = False

HAS_CPP_FULL_BATCH = HAS_CPP_EXT and hasattr(scoring, "calculate_composite_scores_full_batch")

from .field_aware_relevance import (
    FieldAwareRelevanceSettings,
    evaluate_field_aware_relevance,
)
from .learned_anchor import (
    LearnedAnchorInputRow,
    LearnedAnchorSettings,
    evaluate_learned_anchor_corroboration,
)
from .link_freshness import score_link_freshness_component
from .phrase_matching import PhraseMatchingSettings, evaluate_phrase_match
from .rare_term_propagation import (
    RareTermProfile,
    RareTermPropagationSettings,
    evaluate_rare_term_propagation,
)
from apps.suggestions.recommended_weights import recommended_float, recommended_str


ContentKey: TypeAlias = tuple[int, str]
ExistingLinkKey: TypeAlias = tuple[ContentKey, ContentKey]

@dataclass(frozen=True, slots=True)
class ContentRecord:
    """Pipeline metadata for a content item."""

    content_id: int
    content_type: str
    title: str
    distilled_text: str
    scope_id: int
    scope_type: str
    parent_id: int | None
    parent_type: str
    grandparent_id: int | None
    grandparent_type: str
    silo_group_id: int | None
    silo_group_name: str
    reply_count: int
    march_2026_pagerank_score: float
    link_freshness_score: float
    primary_post_char_count: int
    tokens: frozenset[str]
    content_value_score: float = 0.0
    click_distance_score: float = 0.5
    scope_title: str = ""
    parent_scope_title: str = ""
    grandparent_scope_title: str = ""
    cluster_id: int | None = None
    is_canonical: bool = False

    @property
    def key(self) -> ContentKey:
        return (self.content_id, self.content_type)


@dataclass(frozen=True, slots=True)
class SentenceRecord:
    """Sentence metadata used during ranking."""

    sentence_id: int
    content_id: int
    content_type: str
    text: str
    char_count: int
    tokens: frozenset[str]

    @property
    def content_key(self) -> ContentKey:
        return (self.content_id, self.content_type)


@dataclass(frozen=True, slots=True)
class SentenceSemanticMatch:
    """Sentence-level semantic score produced by Stage 2."""

    host_content_id: int
    host_content_type: str
    sentence_id: int
    score_semantic: float

    @property
    def host_key(self) -> ContentKey:
        return (self.host_content_id, self.host_content_type)


@dataclass(frozen=True, slots=True)
class ScoredCandidate:
    """Fully scored candidate suggestion."""

    destination_content_id: int
    destination_content_type: str
    host_content_id: int
    host_content_type: str
    host_sentence_id: int
    score_semantic: float
    score_keyword: float
    score_node_affinity: float
    score_quality: float
    score_silo_affinity: float
    score_phrase_relevance: float
    score_learned_anchor_corroboration: float
    score_rare_term_propagation: float
    score_field_aware_relevance: float
    score_ga4_gsc: float
    score_click_distance: float
    score_explore_exploit: float
    score_cluster_suppression: float
    score_final: float
    anchor_phrase: str
    anchor_start: int | None
    anchor_end: int | None
    anchor_confidence: str
    phrase_match_diagnostics: dict[str, object]
    learned_anchor_diagnostics: dict[str, object]
    rare_term_diagnostics: dict[str, object]
    field_aware_diagnostics: dict[str, object]
    cluster_diagnostics: dict[str, object]
    explore_exploit_diagnostics: dict[str, object]
    click_distance_diagnostics: dict[str, object]
    score_slate_diversity: float | None = field(default=None)
    slate_diversity_diagnostics: dict[str, object] = field(default_factory=dict)

    @property
    def destination_key(self) -> ContentKey:
        return (self.destination_content_id, self.destination_content_type)

    @property
    def host_key(self) -> ContentKey:
        return (self.host_content_id, self.host_content_type)


@dataclass(frozen=True, slots=True)
class ClusteringSettings:
    enabled: bool = False
    similarity_threshold: float = 0.04
    suppression_penalty: float = 20.0


@dataclass(frozen=True, slots=True)
class SiloSettings:
    """Persisted controls for silo-aware ranking."""

    mode: str = recommended_str("silo.mode")
    same_silo_boost: float = recommended_float("silo.same_silo_boost")
    cross_silo_penalty: float = recommended_float("silo.cross_silo_penalty")


def classify_silo_relationship(destination: ContentRecord, host: ContentRecord) -> str:
    """Return same, cross, or unassigned for host/destination silo relationship."""
    if destination.silo_group_id is None or host.silo_group_id is None:
        return "unassigned"
    if destination.silo_group_id == host.silo_group_id:
        return "same"
    return "cross"


def score_silo_affinity(
    destination: ContentRecord,
    host: ContentRecord,
    settings: SiloSettings,
) -> float:
    """Calculate the additive silo adjustment for a candidate."""
    if settings.mode != "prefer_same_silo":
        return 0.0

    relationship = classify_silo_relationship(destination, host)
    if relationship == "same":
        return settings.same_silo_boost
    if relationship == "cross":
        return -settings.cross_silo_penalty
    return 0.0


def is_strict_same_silo_blocked(
    destination: ContentRecord,
    host: ContentRecord,
    settings: SiloSettings,
) -> bool:
    """Return True when strict mode should reject a cross-silo candidate."""
    return (
        settings.mode == "strict_same_silo"
        and classify_silo_relationship(destination, host) == "cross"
    )


def keyword_jaccard_similarity(
    destination_tokens: frozenset[str],
    sentence_tokens: frozenset[str],
) -> float:
    """Calculate Jaccard similarity across pre-tokenized destination/sentence sets."""
    if not destination_tokens or not sentence_tokens:
        return 0.0
    union = destination_tokens | sentence_tokens
    if not union:
        return 0.0
    return len(destination_tokens & sentence_tokens) / len(union)


def score_node_affinity(destination: ContentRecord, host: ContentRecord) -> float:
    """Score host/destination proximity in the scope tree."""
    if (
        destination.scope_id == host.scope_id
        and destination.scope_type == host.scope_type
    ):
        return 1.0

    if (
        destination.parent_id is not None
        and host.parent_id is not None
        and destination.parent_id == host.parent_id
        and destination.parent_type == host.parent_type
    ):
        return 0.6

    if (
        destination.grandparent_id is not None
        and host.grandparent_id is not None
        and destination.grandparent_id == host.grandparent_id
        and destination.grandparent_type == host.grandparent_type
    ):
        return 0.3

    return 0.0


def log_minmax_normalize_march_2026_pagerank(
    march_2026_pagerank_score: float,
    march_2026_pagerank_min: float,
    march_2026_pagerank_max: float,
) -> float:
    """Logarithmic min-max normalization for March 2026 PageRank-based scoring."""
    return log_minmax_normalize_score(
        march_2026_pagerank_score,
        march_2026_pagerank_min,
        march_2026_pagerank_max,
    )


def log_minmax_normalize_score(
    score: float,
    score_min: float,
    score_max: float,
) -> float:
    """Logarithmic min-max normalization for positive authority-like scores."""
    if score_min == score_max:
        return 0.5

    epsilon = 1e-9
    min_log = math.log(score_min + epsilon)
    max_log = math.log(score_max + epsilon)
    if min_log == max_log:
        return 0.5

    score_log = math.log(score + epsilon)
    normalized = (score_log - min_log) / (max_log - min_log)
    return max(0.0, min(1.0, normalized))


def derive_march_2026_pagerank_bounds(
    content_records: Mapping[ContentKey, ContentRecord],
) -> tuple[float, float]:
    """Return the global min/max March 2026 PageRank used by scoring."""
    if not content_records:
        return (0.0, 0.0)
    scores = [record.march_2026_pagerank_score for record in content_records.values()]
    return (min(scores), max(scores))


def _calculate_composite_scores_full_batch_py(
    component_scores: np.ndarray,
    weights: np.ndarray,
    silo: np.ndarray,
) -> np.ndarray:
    """Return dot(row, weights) + silo using columns: semantic, keyword, node, quality, pagerank, freshness, phrase, learned_anchor, rare_term, field_aware, ga4_gsc, click_distance."""
    component_scores = np.asarray(component_scores, dtype=np.float32)
    weights = np.asarray(weights, dtype=np.float32)
    silo = np.asarray(silo, dtype=np.float32)

    if component_scores.ndim != 2:
        raise ValueError("component_scores must be a 2D array")
    if weights.ndim != 1:
        raise ValueError("weights must be a 1D array")
    if silo.ndim != 1:
        raise ValueError("silo must be a 1D array")
    if component_scores.shape[1] != weights.shape[0]:
        raise ValueError("weights length must match component_scores.shape[1]")
    if component_scores.shape[0] != silo.shape[0]:
        raise ValueError("silo length must match component_scores.shape[0]")

    results = np.empty(component_scores.shape[0], dtype=np.float32)
    for row_index, row in enumerate(component_scores):
        total = float(silo[row_index])
        for component, weight in zip(row, weights):
            total += float(component) * float(weight)
        results[row_index] = total
    return results


def score_destination_matches(
    destination: ContentRecord,
    sentence_matches: list[SentenceSemanticMatch],
    *,
    content_records: Mapping[ContentKey, ContentRecord],
    sentence_records: Mapping[int, SentenceRecord],
    existing_links: set[ExistingLinkKey],
    learned_anchor_rows_by_destination: Mapping[ContentKey, list[LearnedAnchorInputRow]] | None = None,
    rare_term_profiles: Mapping[ContentKey, RareTermProfile] | None = None,
    weights: Mapping[str, float],
    march_2026_pagerank_bounds: tuple[float, float],
    weighted_authority_ranking_weight: float = 0.0,
    link_freshness_ranking_weight: float = 0.0,
    ga4_gsc_ranking_weight: float = 0.0,
    click_distance_ranking_weight: float = 0.0,
    phrase_matching_settings: PhraseMatchingSettings = PhraseMatchingSettings(),
    learned_anchor_settings: LearnedAnchorSettings = LearnedAnchorSettings(),
    rare_term_settings: RareTermPropagationSettings = RareTermPropagationSettings(),
    field_aware_settings: FieldAwareRelevanceSettings = FieldAwareRelevanceSettings(),
    silo_settings: SiloSettings = SiloSettings(),
    clustering_settings: ClusteringSettings = ClusteringSettings(),
    blocked_reasons: set[str] | None = None,
    min_semantic_score: float = 0.25,
    min_sentence_chars: int = 30,
    max_sentence_chars: int = 300,
    min_host_chars: int = 300,
) -> list[ScoredCandidate]:
    """Apply composite scoring plus local anti-junk filters for one destination."""
    march_2026_pagerank_min, march_2026_pagerank_max = march_2026_pagerank_bounds
    learned_anchor_rows_by_destination = learned_anchor_rows_by_destination or {}
    rare_term_profiles = rare_term_profiles or {}
    ranked: list[ScoredCandidate] = []
    pending_candidates: list[dict[str, object]] = []
    component_rows: list[list[float]] = []
    silo_scores: list[float] = []
    destination_learned_anchor_rows = learned_anchor_rows_by_destination.get(destination.key, [])
    batch_weights = np.asarray(
        [
            float(weights.get("w_semantic", 0.0)),
            float(weights.get("w_keyword", 0.0)),
            float(weights.get("w_node", 0.0)),
            float(weights.get("w_quality", 0.0)),
            float(weighted_authority_ranking_weight),
            float(link_freshness_ranking_weight),
            float(phrase_matching_settings.ranking_weight),
            float(learned_anchor_settings.ranking_weight),
            float(rare_term_settings.ranking_weight),
            float(field_aware_settings.ranking_weight),
            float(ga4_gsc_ranking_weight),
            float(click_distance_ranking_weight),
        ],
        dtype=np.float32,
    )

    for match in sentence_matches:
        if match.score_semantic < min_semantic_score:
            continue

        host_key = match.host_key
        if host_key == destination.key:
            continue

        if (host_key, destination.key) in existing_links:
            continue

        host_record = content_records.get(host_key)
        sentence_record = sentence_records.get(match.sentence_id)
        if host_record is None or sentence_record is None:
            continue

        if is_strict_same_silo_blocked(destination, host_record, silo_settings):
            if blocked_reasons is not None:
                blocked_reasons.add("cross_silo_blocked")
            continue

        if sentence_record.char_count < min_sentence_chars:
            continue
        if sentence_record.char_count > max_sentence_chars:
            continue

        if (
            host_record.reply_count <= 0
            and host_record.primary_post_char_count <= min_host_chars
        ):
            continue

        score_keyword = keyword_jaccard_similarity(
            destination.tokens,
            sentence_record.tokens,
        )
        phrase_match = evaluate_phrase_match(
            host_sentence_text=sentence_record.text,
            destination_title=destination.title,
            destination_distilled_text=destination.distilled_text,
            settings=phrase_matching_settings,
        )
        learned_anchor_match = evaluate_learned_anchor_corroboration(
            candidate_anchor_text=phrase_match.anchor_phrase,
            host_sentence_text=sentence_record.text,
            inbound_anchor_rows=destination_learned_anchor_rows,
            settings=learned_anchor_settings,
        )
        rare_term_match = evaluate_rare_term_propagation(
            destination=destination,
            host_sentence_tokens=sentence_record.tokens,
            profiles=rare_term_profiles,
            settings=rare_term_settings,
        )
        field_aware_match = evaluate_field_aware_relevance(
            destination=destination,
            host_sentence_text=sentence_record.text,
            inbound_anchor_rows=destination_learned_anchor_rows,
            settings=field_aware_settings,
        )
        score_node = score_node_affinity(destination, host_record)
        score_quality = log_minmax_normalize_march_2026_pagerank(
            host_record.march_2026_pagerank_score,
            march_2026_pagerank_min,
            march_2026_pagerank_max,
        )
        score_march_2026_pagerank_component = (
            log_minmax_normalize_score(
                destination.march_2026_pagerank_score,
                march_2026_pagerank_min,
                march_2026_pagerank_max,
            )
            if weighted_authority_ranking_weight > 0.0
            else 0.0
        )
        score_link_freshness = (
            score_link_freshness_component(destination.link_freshness_score)
            if link_freshness_ranking_weight > 0.0
            else 0.0
        )
        score_ga4_gsc = (
            float(destination.content_value_score)
            if ga4_gsc_ranking_weight > 0.0
            else 0.0
        )
        score_phrase_relevance = phrase_match.score_phrase_component
        score_learned_anchor = learned_anchor_match.learned_anchor_component
        score_rare_term = rare_term_match.rare_term_component
        score_field_aware = field_aware_match.field_aware_component
        score_click_distance = destination.click_distance_score
        score_click_distance_component = 2 * (score_click_distance - 0.5)
        score_silo = score_silo_affinity(destination, host_record, silo_settings)
        pending_candidates.append(
            {
                "match": match,
                "score_keyword": score_keyword,
                "score_node": score_node,
                "score_quality": score_quality,
                "score_silo": score_silo,
                "score_phrase_relevance": score_phrase_relevance,
                "score_learned_anchor": score_learned_anchor,
                "score_rare_term": score_rare_term,
                "score_field_aware": score_field_aware,
                "score_ga4_gsc": score_ga4_gsc,
                "score_click_distance": score_click_distance,
                "score_click_distance_component": score_click_distance_component,
                "phrase_match": phrase_match,
                "learned_anchor_match": learned_anchor_match,
                "rare_term_match": rare_term_match,
                "field_aware_match": field_aware_match,
            }
        )
        component_rows.append(
            [
                float(match.score_semantic),
                float(score_keyword),
                float(score_node),
                float(score_quality),
                float(score_march_2026_pagerank_component),
                float(score_link_freshness),
                float(score_phrase_relevance),
                float(score_learned_anchor),
                float(score_rare_term),
                float(score_field_aware),
                float(score_ga4_gsc),
                float(score_click_distance_component),
            ]
        )
        silo_scores.append(float(score_silo))

    if pending_candidates:
        component_scores = np.asarray(component_rows, dtype=np.float32)
        silo_array = np.asarray(silo_scores, dtype=np.float32)
        if HAS_CPP_FULL_BATCH:
            score_finals = scoring.calculate_composite_scores_full_batch(
                component_scores,
                batch_weights,
                silo_array,
            )
        else:
            score_finals = _calculate_composite_scores_full_batch_py(
                component_scores,
                batch_weights,
                silo_array,
            )
    else:
        score_finals = np.empty(0, dtype=np.float32)

    for pending_candidate, raw_score_final in zip(pending_candidates, score_finals):
        match = pending_candidate["match"]
        phrase_match = pending_candidate["phrase_match"]
        learned_anchor_match = pending_candidate["learned_anchor_match"]
        rare_term_match = pending_candidate["rare_term_match"]
        field_aware_match = pending_candidate["field_aware_match"]
        score_click_distance = float(pending_candidate["score_click_distance"])
        score_click_distance_component = float(pending_candidate["score_click_distance_component"])
        score_final = float(raw_score_final)

        # FR-014 Clustering Suppression
        score_cluster_suppression = 0.0
        cluster_diagnostics = {}
        if clustering_settings.enabled and destination.cluster_id:
            if not destination.is_canonical:
                # Soft suppression
                score_cluster_suppression = -clustering_settings.suppression_penalty
                score_final += score_cluster_suppression
                cluster_diagnostics = {
                    "cluster_id": destination.cluster_id,
                    "is_canonical": False,
                    "penalty": clustering_settings.suppression_penalty
                }
            else:
                cluster_diagnostics = {
                    "cluster_id": destination.cluster_id,
                    "is_canonical": True,
                    "penalty": 0.0
                }

        ranked.append(
            ScoredCandidate(
                destination_content_id=destination.content_id,
                destination_content_type=destination.content_type,
                host_content_id=match.host_content_id,
                host_content_type=match.host_content_type,
                host_sentence_id=match.sentence_id,
                score_semantic=float(match.score_semantic),
                score_keyword=float(pending_candidate["score_keyword"]),
                score_node_affinity=float(pending_candidate["score_node"]),
                score_quality=float(pending_candidate["score_quality"]),
                score_silo_affinity=float(pending_candidate["score_silo"]),
                score_phrase_relevance=float(phrase_match.score_phrase_relevance),
                score_learned_anchor_corroboration=float(learned_anchor_match.score_learned_anchor_corroboration),
                score_rare_term_propagation=float(rare_term_match.score_rare_term_propagation),
                score_field_aware_relevance=float(field_aware_match.score_field_aware_relevance),
                score_ga4_gsc=float(pending_candidate["score_ga4_gsc"]),
                score_click_distance=score_click_distance,
                score_explore_exploit=0.0, # Will be updated by feedback reranker later
                score_cluster_suppression=float(score_cluster_suppression),
                score_final=float(score_final),
                anchor_phrase=phrase_match.anchor_phrase or "",
                anchor_start=phrase_match.anchor_start,
                anchor_end=phrase_match.anchor_end,
                anchor_confidence=phrase_match.anchor_confidence,
                phrase_match_diagnostics=phrase_match.phrase_match_diagnostics,
                learned_anchor_diagnostics=learned_anchor_match.learned_anchor_diagnostics,
                rare_term_diagnostics=rare_term_match.rare_term_diagnostics,
                field_aware_diagnostics=field_aware_match.field_aware_diagnostics,
                cluster_diagnostics=cluster_diagnostics,
                explore_exploit_diagnostics={},
                click_distance_diagnostics={
                    "click_distance_score": round(score_click_distance, 4),
                    "click_distance_ranking_weight": click_distance_ranking_weight,
                    "score_component": round(score_click_distance_component, 4),
                },
            )
        )

    ranked.sort(
        key=lambda candidate: (
            -candidate.score_final,
            -candidate.score_semantic,
            candidate.host_content_id,
            candidate.host_content_type,
            candidate.host_sentence_id,
        )
    )
    return ranked


def select_final_candidates(
    candidates_by_destination: Mapping[ContentKey, list[ScoredCandidate]],
    *,
    max_host_reuse: int = 3,
    blocked_diagnostics: dict[ContentKey, str] | None = None,
) -> list[ScoredCandidate]:
    """Resolve host-reuse and circular-direction conflicts across destinations.

    If *blocked_diagnostics* is provided, destinations whose candidates are
    all blocked will be recorded with their last blocking reason
    (``"host_reuse_cap"`` or ``"circular_suppressed"``).
    """
    heap: list[tuple[float, float, int, str, int]] = []
    destination_cursor: dict[ContentKey, int] = {}

    for destination_key, candidates in candidates_by_destination.items():
        if not candidates:
            continue
        destination_cursor[destination_key] = 0
        heapq.heappush(
            heap,
            (
                -candidates[0].score_final,
                -candidates[0].score_semantic,
                candidates[0].destination_content_id,
                candidates[0].destination_content_type,
                0,
            ),
        )

    selected_by_destination: dict[ContentKey, ScoredCandidate] = {}
    host_reuse_counts: Counter[ContentKey] = Counter()
    selected_directions: set[tuple[ContentKey, ContentKey]] = set()
    last_block_reason: dict[ContentKey, str] = {}

    while heap:
        _neg_final, _neg_semantic, destination_id, destination_type, candidate_idx = heapq.heappop(heap)
        destination_key = (destination_id, destination_type)
        if destination_key in selected_by_destination:
            continue

        candidates = candidates_by_destination.get(destination_key, [])
        if candidate_idx >= len(candidates):
            continue

        candidate = candidates[candidate_idx]
        is_host_reuse = host_reuse_counts[candidate.host_key] >= max_host_reuse
        is_circular = (candidate.host_key, candidate.destination_key) in selected_directions
        blocked = is_host_reuse or is_circular
        if blocked:
            if is_circular:
                last_block_reason[destination_key] = "circular_suppressed"
            else:
                last_block_reason[destination_key] = "host_reuse_cap"
            next_idx = candidate_idx + 1
            if next_idx < len(candidates):
                next_candidate = candidates[next_idx]
                heapq.heappush(
                    heap,
                    (
                        -next_candidate.score_final,
                        -next_candidate.score_semantic,
                        next_candidate.destination_content_id,
                        next_candidate.destination_content_type,
                        next_idx,
                    ),
                )
            continue

        selected_by_destination[destination_key] = candidate
        host_reuse_counts[candidate.host_key] += 1
        selected_directions.add((candidate.destination_key, candidate.host_key))
        last_block_reason.pop(destination_key, None)

    if blocked_diagnostics is not None:
        for dest_key, reason in last_block_reason.items():
            if dest_key not in selected_by_destination:
                blocked_diagnostics[dest_key] = reason

    return sorted(
        selected_by_destination.values(),
        key=lambda c: (-c.score_final, -c.score_semantic),
    )
