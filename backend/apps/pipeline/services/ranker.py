"""Composite scoring and anti-junk selection for link suggestions.

This module is pure Python — no database access. All DB loading is done
by the pipeline service which passes pre-built records into these functions.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
import heapq
import logging
import math
import warnings
import numpy as np
from typing import Mapping, TypeAlias

logger = logging.getLogger(__name__)

try:
    from extensions import scoring

    HAS_CPP_EXT = True
except ImportError as _ext_err:
    HAS_CPP_EXT = False
    _msg = (
        "C++ scoring extension not found — ranker using slow Python fallback. "
        "Run 'make build-ext' to compile."
    )
    warnings.warn(_msg, RuntimeWarning)
    logging.getLogger(__name__).warning(_msg)
    # Write to ErrorLog so the failure is visible in the dashboard.
    try:
        import traceback
        from apps.audit.models import ErrorLog

        ErrorLog.objects.create(
            job_type="cpp_extension",
            step="import_scoring",
            error_message=_msg,
            raw_exception=traceback.format_exc(),
            why=(
                "The compiled C++ scoring extension (.so on Linux, .pyd on Windows) "
                "could not be imported. This means the ranker is using the slow Python "
                "fallback which is 50-100x slower. Rebuild with: "
                "cd backend/extensions && pip install -e ."
            ),
        )
    except Exception:
        pass  # ErrorLog itself may not be available during early startup

HAS_CPP_FULL_BATCH = HAS_CPP_EXT and hasattr(
    scoring, "calculate_composite_scores_full_batch"
)

# Default character-length bounds for host sentences selected as
# anchor context. A sentence shorter than ``_DEFAULT_MIN_SENTENCE_CHARS``
# is usually a title/caption and lacks enough surrounding text to
# corroborate a link; one longer than ``_DEFAULT_MAX_SENTENCE_CHARS``
# is usually a paragraph run-on and dilutes the signal.
_DEFAULT_MIN_SENTENCE_CHARS = 30
_DEFAULT_MAX_SENTENCE_CHARS = 300

# Minimum character count the host page itself must have for its body
# to be considered substantive enough to link FROM. Set by the FR-006
# / FR-011 spec at 300 chars ~= 50 words.
_DEFAULT_MIN_HOST_CHARS = 300

# Thin-content word-count thresholds applied as a penalty multiplier
# during final scoring. Below ``_THIN_WORD_HARD_THRESHOLD`` the
# penalty is 30% of score_final; below ``_THIN_WORD_SOFT_THRESHOLD``
# it is 15%; at or above, no thin-content penalty applies.
_THIN_WORD_HARD_THRESHOLD = 100
_THIN_WORD_SOFT_THRESHOLD = 200

from .field_aware_relevance import (
    FieldAwareRelevanceSettings,
    evaluate_field_aware_relevance,
)
from .graph_signal_ranker import GraphSignalRanker
from .anchor_diversity import (
    AnchorDiversitySettings,
    evaluate_anchor_diversity,
)
from .keyword_stuffing import KeywordStuffingEvaluation, KeywordStuffingSettings
from .learned_anchor import (
    LearnedAnchorInputRow,
    LearnedAnchorSettings,
    evaluate_learned_anchor_corroboration,
)
from .link_farm import LinkFarmEvaluation, LinkFarmSettings
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
    # Pick #21 — Snowball/Porter2 stems of the same surface tokens.
    # Populated by ``pipeline_data._load_content_records`` when the
    # ``parse.stemmer.enabled`` setting is on (default off — empty).
    # Consumers that opt in (e.g. rare-term propagation) read this
    # for stem-based comparison; everyone else keeps using ``tokens``.
    stemmed_tokens: frozenset[str] = frozenset()

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
    position: int = 0  # zero-based sentence index within the post (Sentence.position)
    # Pick #21 — Snowball stems of ``tokens``. See ``ContentRecord.stemmed_tokens``.
    stemmed_tokens: frozenset[str] = frozenset()

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
    score_anchor_diversity: float = 0.5
    score_keyword_stuffing: float = 0.5
    score_link_farm: float = 0.5
    repeated_anchor: bool = False
    anchor_diversity_diagnostics: dict[str, object] = field(default_factory=dict)
    keyword_stuffing_diagnostics: dict[str, object] = field(default_factory=dict)
    link_farm_diagnostics: dict[str, object] = field(default_factory=dict)
    score_slate_diversity: float | None = field(default=None)
    slate_diversity_diagnostics: dict[str, object] = field(default_factory=dict)
    # FR-099 through FR-105 — graph-topology signals (default 0.0 = neutral).
    # See docs/specs/fr099-*.md through docs/specs/fr105-*.md.
    score_darb: float = 0.0
    score_kmig: float = 0.0
    score_tapb: float = 0.0
    score_kcib: float = 0.0
    score_berp: float = 0.0
    score_hgte: float = 0.0
    score_rsqva: float = 0.0
    darb_diagnostics: dict[str, object] = field(default_factory=dict)
    kmig_diagnostics: dict[str, object] = field(default_factory=dict)
    tapb_diagnostics: dict[str, object] = field(default_factory=dict)
    kcib_diagnostics: dict[str, object] = field(default_factory=dict)
    berp_diagnostics: dict[str, object] = field(default_factory=dict)
    hgte_diagnostics: dict[str, object] = field(default_factory=dict)
    rsqva_diagnostics: dict[str, object] = field(default_factory=dict)

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
    """Return dot(row, weights) + silo using the per-candidate component vector."""
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
    existing_outgoing_counts: Mapping[ContentKey, int] | None = None,
    max_existing_links_per_host: int = 2,
    max_anchor_words: int = 4,
    learned_anchor_rows_by_destination: Mapping[ContentKey, list[LearnedAnchorInputRow]]
    | None = None,
    anchor_history_by_destination: Mapping[ContentKey, object] | None = None,
    rare_term_profiles: Mapping[ContentKey, RareTermProfile] | None = None,
    keyword_stuffing_by_destination: Mapping[ContentKey, KeywordStuffingEvaluation]
    | None = None,
    link_farm_by_destination: Mapping[ContentKey, LinkFarmEvaluation] | None = None,
    weights: Mapping[str, float],
    march_2026_pagerank_bounds: tuple[float, float],
    weighted_authority_ranking_weight: float = 0.0,
    link_freshness_ranking_weight: float = 0.0,
    ga4_gsc_ranking_weight: float = 0.0,
    click_distance_ranking_weight: float = 0.0,
    anchor_diversity_settings: AnchorDiversitySettings = AnchorDiversitySettings(),
    keyword_stuffing_settings: KeywordStuffingSettings = KeywordStuffingSettings(),
    link_farm_settings: LinkFarmSettings = LinkFarmSettings(),
    phrase_matching_settings: PhraseMatchingSettings = PhraseMatchingSettings(),
    learned_anchor_settings: LearnedAnchorSettings = LearnedAnchorSettings(),
    rare_term_settings: RareTermPropagationSettings = RareTermPropagationSettings(),
    field_aware_settings: FieldAwareRelevanceSettings = FieldAwareRelevanceSettings(),
    silo_settings: SiloSettings = SiloSettings(),
    clustering_settings: ClusteringSettings = ClusteringSettings(),
    blocked_reasons: set[str] | None = None,
    min_semantic_score: float = 0.25,
    fr099_fr105_caches: object = None,
    fr099_fr105_settings: object = None,
    graph_signal_ranker: GraphSignalRanker | None = None,
    phase6_contribution: object = None,
    anchor_garbage_dispatcher: object = None,
    min_sentence_chars: int = _DEFAULT_MIN_SENTENCE_CHARS,
    max_sentence_chars: int = _DEFAULT_MAX_SENTENCE_CHARS,
    min_host_chars: int = _DEFAULT_MIN_HOST_CHARS,
) -> list[ScoredCandidate]:
    """Apply composite scoring plus local anti-junk filters for one destination."""
    march_2026_pagerank_min, march_2026_pagerank_max = march_2026_pagerank_bounds
    learned_anchor_rows_by_destination = learned_anchor_rows_by_destination or {}
    anchor_history_by_destination = anchor_history_by_destination or {}
    rare_term_profiles = rare_term_profiles or {}
    keyword_stuffing_by_destination = keyword_stuffing_by_destination or {}
    link_farm_by_destination = link_farm_by_destination or {}
    ranked: list[ScoredCandidate] = []
    pending_candidates: list[dict[str, object]] = []
    # Pre-allocate fixed-size arrays: avoids repeated list.append + np.asarray copy on every candidate.
    # Upper bound is len(sentence_matches); sliced down to row_idx after the loop.
    component_scores = np.empty((len(sentence_matches), 15), dtype=np.float32)
    silo_array = np.empty(len(sentence_matches), dtype=np.float32)
    row_idx = 0
    destination_learned_anchor_rows = learned_anchor_rows_by_destination.get(
        destination.key, []
    )
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
            float(anchor_diversity_settings.ranking_weight),
            float(keyword_stuffing_settings.ranking_weight),
            float(link_farm_settings.ranking_weight),
        ],
        dtype=np.float32,
    )
    keyword_stuffing_eval = keyword_stuffing_by_destination.get(
        destination.key,
        _neutral_keyword_stuffing_eval(keyword_stuffing_settings),
    )
    link_farm_eval = link_farm_by_destination.get(
        destination.key,
        _neutral_link_farm_eval(link_farm_settings),
    )

    for match in sentence_matches:
        if match.score_semantic < min_semantic_score:
            continue

        host_key = match.host_key
        if host_key == destination.key:
            continue

        if (host_key, destination.key) in existing_links:
            continue

        # Guard 1 — skip hosts that already carry too many outgoing body links.
        # Research basis: Ntoulas et al. anchor-word fraction (US20060184500A1);
        # Google droppedLocalAnchorCount (2024 API leak). Adding more links to a
        # page that already has 3+ raises the anchor-word fraction into the range
        # where spam probability climbs sharply.
        if existing_outgoing_counts is not None:
            if existing_outgoing_counts.get(host_key, 0) >= max_existing_links_per_host:
                if blocked_reasons is not None:
                    blocked_reasons.add("max_links_reached")
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

        # Guard 2 — reject anchors that are too long (long-tail keyword stuffing).
        # Research basis: Google recommends 2–5 words (link best-practices docs);
        # US8380722B2 states anchors are "usually short and descriptive";
        # Google's phraseAnchorSpamFraq field (2024 leak) specifically targets
        # recurring long-phrase anchors. A 4-word cap sits inside the safe zone.
        if (
            phrase_match.anchor_phrase
            and len(phrase_match.anchor_phrase.split()) > max_anchor_words
        ):
            if blocked_reasons is not None:
                blocked_reasons.add("anchor_too_long")
            continue
        anchor_diversity_eval = evaluate_anchor_diversity(
            destination_key=destination.key,
            candidate_anchor_text=phrase_match.anchor_phrase or "",
            history_by_destination=anchor_history_by_destination,
            settings=anchor_diversity_settings,
        )
        if anchor_diversity_eval.blocked:
            if blocked_reasons is not None:
                blocked_reasons.add("anchor_diversity_blocked")
            continue

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
        score_anchor_diversity_component = anchor_diversity_eval.score_component
        score_keyword_stuffing_component = keyword_stuffing_eval.score_component
        score_link_farm_component = link_farm_eval.score_component
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
                # Audit bug A2 fix — Phase 6 FM adapter needs this on
                # the per-candidate dict so the feature vector matches
                # the W1 trainer's vocabulary.
                "score_link_freshness": score_link_freshness,
                "anchor_diversity_eval": anchor_diversity_eval,
                "keyword_stuffing_eval": keyword_stuffing_eval,
                "link_farm_eval": link_farm_eval,
                "phrase_match": phrase_match,
                "learned_anchor_match": learned_anchor_match,
                "rare_term_match": rare_term_match,
                "field_aware_match": field_aware_match,
            }
        )
        component_scores[row_idx] = [
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
            float(score_anchor_diversity_component),
            float(score_keyword_stuffing_component),
            float(score_link_farm_component),
        ]
        silo_array[row_idx] = float(score_silo)
        row_idx += 1

    component_scores = component_scores[:row_idx]
    silo_array = silo_array[:row_idx]

    if pending_candidates:
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

    # Lazy import to keep the module dependency-light when FR-099..105 is
    # disabled. Dispatcher is a pure-Python additive layer on top of the
    # existing 15-component composite — see docs/specs/fr099-*.md through
    # docs/specs/fr105-*.md.
    _fr099_dispatcher = None
    if fr099_fr105_settings is not None and fr099_fr105_caches is not None:
        from .fr099_fr105_signals import evaluate_all_fr099_fr105 as _fr099_dispatcher

    # W3c graph-signal contribution (picks #29 / #30 / #36).
    # The HITS-authority / PPR / TrustRank scores are properties of the
    # *destination* node, so the contribution is constant across every
    # match for this destination — compute once outside the per-candidate
    # loop. Cold-start safe: if no W1 job has populated the store yet,
    # ``build_graph_signal_ranker`` returns None upstream and this stays 0.
    graph_signal_contribution = (
        graph_signal_ranker.contribution(destination.key)
        if graph_signal_ranker is not None
        else 0.0
    )

    for pending_candidate, raw_score_final in zip(pending_candidates, score_finals):
        match = pending_candidate["match"]
        phrase_match = pending_candidate["phrase_match"]
        learned_anchor_match = pending_candidate["learned_anchor_match"]
        rare_term_match = pending_candidate["rare_term_match"]
        field_aware_match = pending_candidate["field_aware_match"]
        anchor_diversity_eval = pending_candidate["anchor_diversity_eval"]
        keyword_stuffing_eval = pending_candidate["keyword_stuffing_eval"]
        link_farm_eval = pending_candidate["link_farm_eval"]
        score_click_distance = float(pending_candidate["score_click_distance"])
        score_click_distance_component = float(
            pending_candidate["score_click_distance_component"]
        )
        score_final = float(raw_score_final)

        # FR-099 through FR-105 — graph-topology signals.
        # Dispatcher returns weighted_contribution (already multiplied by each
        # signal's ranking_weight), per_signal_scores (raw [0, 1] for
        # Suggestion.score_<signal>), and per_signal_diagnostics.
        fr099_contribution = 0.0
        fr099_scores: dict[str, float] = {
            "score_darb": 0.0,
            "score_kmig": 0.0,
            "score_tapb": 0.0,
            "score_kcib": 0.0,
            "score_berp": 0.0,
            "score_hgte": 0.0,
            "score_rsqva": 0.0,
        }
        fr099_diags: dict[str, dict[str, object]] = {
            "darb_diagnostics": {},
            "kmig_diagnostics": {},
            "tapb_diagnostics": {},
            "kcib_diagnostics": {},
            "berp_diagnostics": {},
            "hgte_diagnostics": {},
            "rsqva_diagnostics": {},
        }
        if _fr099_dispatcher is not None:
            host_record = content_records.get(match.host_key)
            host_content_value = (
                float(host_record.content_value_score)
                if host_record is not None
                and getattr(host_record, "content_value_score", None) is not None
                else None
            )
            dest_silo_id = getattr(destination, "silo_group_id", None)
            fr099_eval = _fr099_dispatcher(
                host_key=match.host_key,
                destination_key=destination.key,
                host_content_value=host_content_value,
                dest_silo_id=dest_silo_id,
                existing_outgoing_counts=existing_outgoing_counts,
                caches=fr099_fr105_caches,
                settings=fr099_fr105_settings,
            )
            fr099_contribution = float(fr099_eval.weighted_contribution)
            fr099_scores = fr099_eval.per_signal_scores
            fr099_diags = fr099_eval.per_signal_diagnostics
        score_final += fr099_contribution
        score_final += graph_signal_contribution

        # Slice 5 — Phase 6 ranker-time contribution dispatcher.
        # Adds the operator-tunable contribution from each enabled
        # Phase 6 pick (VADER #22, KenLM #23, LDA #18, Node2Vec #37,
        # BPR #38, FM #39) via the
        # apps.pipeline.services.phase6_ranker_contribution dispatcher.
        # Cold-start safe: when phase6_contribution is None, every
        # adapter returns 0.0 for missing models, this stays at 0.0.
        #
        # Audit bug A2 fix: pass the live ``score_components`` dict +
        # ``anchor_confidence`` so the FM adapter can build feature
        # vectors that match the W1 trainer's vocabulary. Without
        # them, the FM DictVectorizer sees zero overlap and the
        # adapter is inert.
        if phase6_contribution is not None:
            try:
                from .phase6_ranker_contribution import AdapterContext

                sentence_record = sentence_records.get(match.sentence_id)
                host_text = ""
                if sentence_record is not None:
                    host_text = getattr(sentence_record, "text", "") or ""
                dest_text = getattr(destination, "title", "") or ""
                # Mirror the FM trainer's nine score columns (see
                # ``run_factorization_machines_refit``). Field-name
                # parity is mandatory — DictVectorizer's vocab is
                # built from the trainer's keys.
                phase6_score_components = {
                    "score_semantic": float(match.score_semantic),
                    "score_keyword": float(pending_candidate["score_keyword"]),
                    "score_node_affinity": float(pending_candidate["score_node"]),
                    "score_quality": float(pending_candidate["score_quality"]),
                    "score_link_freshness": float(
                        pending_candidate.get("score_link_freshness", 0.0)
                    ),
                    "score_phrase_relevance": float(
                        phrase_match.score_phrase_relevance
                    ),
                    "score_field_aware_relevance": float(
                        field_aware_match.score_field_aware_relevance
                    ),
                    "score_rare_term_propagation": float(
                        rare_term_match.score_rare_term_propagation
                    ),
                    "score_anchor_diversity": float(
                        anchor_diversity_eval.score_anchor_diversity
                    ),
                }
                phase6_ctx = AdapterContext(
                    host_sentence_text=host_text,
                    destination_text=dest_text,
                    host_key=host_key,
                    destination_key=destination.key,
                    score_components=phase6_score_components,
                    anchor_confidence=getattr(
                        phrase_match, "anchor_confidence", None
                    ),
                )
                score_final += float(
                    phase6_contribution.contribute_total(phase6_ctx)
                )
            except Exception as exc:  # pragma: no cover — defensive
                logger.warning(
                    "phase6_contribution.contribute_total raised: %s",
                    exc,
                )

        # PR-Anchor — anti-generic / pro-descriptive anchor signals.
        # Three composable algos via apps.pipeline.services.
        # anchor_garbage_signals: Aho-Corasick blacklist (Aho 1975
        # CACM), Damerau-Levenshtein + char-trigram Jaccard
        # (Damerau 1964 + Broder 1997), and Shannon bigram entropy
        # + Iglewicz-Hoaglin modified z-score (Shannon 1948 + IH
        # 1993). Cold-start safe: when the dispatcher is None,
        # contribution is exactly 0.0.
        if anchor_garbage_dispatcher is not None:
            try:
                anchor_text = phrase_match.anchor_phrase or ""
                dest_title_for_anchor = (
                    getattr(destination, "title", "") or ""
                )
                # URL slug: parse from the destination's URL when
                # available; defaults to "" so the descriptiveness
                # algorithm short-circuits the slug check.
                dest_url = getattr(destination, "url", "") or ""
                dest_slug = ""
                if dest_url:
                    # Slug is the last non-empty segment of the URL
                    # path. Cheap; no urllib.parse import on the hot
                    # path.
                    for segment in reversed(dest_url.rstrip("/").split("/")):
                        if segment:
                            dest_slug = segment
                            break
                score_final += float(
                    anchor_garbage_dispatcher.contribution(
                        anchor_text,
                        dest_title_for_anchor,
                        dest_slug,
                    )
                )
            except Exception as exc:  # pragma: no cover — defensive
                logger.warning(
                    "anchor_garbage_dispatcher.contribution raised: %s",
                    exc,
                )

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
                    "penalty": clustering_settings.suppression_penalty,
                }
            else:
                cluster_diagnostics = {
                    "cluster_id": destination.cluster_id,
                    "is_canonical": True,
                    "penalty": 0.0,
                }

        # Thin content penalty (Panda-based, US Patent 8,682,892).
        # Pages with fewer words are penalised but NOT excluded — they
        # remain valid fallback destinations.  Empty pages (0 words) are
        # fully suppressed.
        thin_penalty = 0.0
        crawled_meta = getattr(destination, "_crawled_word_count", None)
        if crawled_meta is not None:
            wc = crawled_meta
        else:
            wc = getattr(destination, "word_count", None)
        if wc is not None:
            if wc == 0:
                thin_penalty = -score_final  # fully suppress
            elif wc < _THIN_WORD_HARD_THRESHOLD:
                thin_penalty = score_final * -0.30
            elif wc < _THIN_WORD_SOFT_THRESHOLD:
                thin_penalty = score_final * -0.15
        score_final += thin_penalty

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
                score_learned_anchor_corroboration=float(
                    learned_anchor_match.score_learned_anchor_corroboration
                ),
                score_rare_term_propagation=float(
                    rare_term_match.score_rare_term_propagation
                ),
                score_field_aware_relevance=float(
                    field_aware_match.score_field_aware_relevance
                ),
                score_ga4_gsc=float(pending_candidate["score_ga4_gsc"]),
                score_click_distance=score_click_distance,
                score_explore_exploit=0.0,  # Will be updated by feedback reranker later
                score_cluster_suppression=float(score_cluster_suppression),
                score_anchor_diversity=float(
                    anchor_diversity_eval.score_anchor_diversity
                ),
                score_keyword_stuffing=float(
                    keyword_stuffing_eval.score_keyword_stuffing
                ),
                score_link_farm=float(link_farm_eval.score_link_farm),
                score_final=float(score_final),
                anchor_phrase=phrase_match.anchor_phrase or "",
                anchor_start=phrase_match.anchor_start,
                anchor_end=phrase_match.anchor_end,
                anchor_confidence=phrase_match.anchor_confidence,
                repeated_anchor=anchor_diversity_eval.repeated_anchor,
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
                anchor_diversity_diagnostics=anchor_diversity_eval.diagnostics,
                keyword_stuffing_diagnostics=keyword_stuffing_eval.diagnostics,
                link_farm_diagnostics=link_farm_eval.diagnostics,
                # FR-099 through FR-105 — graph-topology signals.
                score_darb=float(fr099_scores.get("score_darb", 0.0)),
                score_kmig=float(fr099_scores.get("score_kmig", 0.0)),
                score_tapb=float(fr099_scores.get("score_tapb", 0.0)),
                score_kcib=float(fr099_scores.get("score_kcib", 0.0)),
                score_berp=float(fr099_scores.get("score_berp", 0.0)),
                score_hgte=float(fr099_scores.get("score_hgte", 0.0)),
                score_rsqva=float(fr099_scores.get("score_rsqva", 0.0)),
                darb_diagnostics=dict(fr099_diags.get("darb_diagnostics", {})),
                kmig_diagnostics=dict(fr099_diags.get("kmig_diagnostics", {})),
                tapb_diagnostics=dict(fr099_diags.get("tapb_diagnostics", {})),
                kcib_diagnostics=dict(fr099_diags.get("kcib_diagnostics", {})),
                berp_diagnostics=dict(fr099_diags.get("berp_diagnostics", {})),
                hgte_diagnostics=dict(fr099_diags.get("hgte_diagnostics", {})),
                rsqva_diagnostics=dict(fr099_diags.get("rsqva_diagnostics", {})),
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


def _neutral_keyword_stuffing_eval(
    settings: KeywordStuffingSettings,
) -> KeywordStuffingEvaluation:
    return KeywordStuffingEvaluation(
        score_keyword_stuffing=0.5,
        score_component=0.0,
        diagnostics={
            "stuffing_state": "neutral",
            "stuff_score": 0.0,
            "stuff_penalty": 0.0,
            "score_keyword_stuffing": 0.5,
            "algorithm_version": settings.algorithm_version,
        },
    )


def _neutral_link_farm_eval(settings: LinkFarmSettings) -> LinkFarmEvaluation:
    return LinkFarmEvaluation(
        score_link_farm=0.5,
        score_component=0.0,
        diagnostics={
            "link_farm_state": "neutral",
            "ring_score": 0.0,
            "ring_penalty": 0.0,
            "score_link_farm": 0.5,
            "algorithm_version": settings.algorithm_version,
        },
    )


def _is_paragraph_collision(
    candidate: ScoredCandidate,
    host_para_positions: dict[ContentKey, list[int]],
    sentence_records: Mapping[int, SentenceRecord],
    paragraph_window: int,
) -> bool:
    """Return True if *candidate*'s sentence falls within *paragraph_window*
    positions of any sentence already selected for the same host page.

    Research basis: US8577893B1 models a ±5-word context window per link;
    adjacent links pollute each other's context signals. Google's own link
    best-practices docs warn against placing many links close together in the
    same text block. A window of ±3 sentences is a conservative but safe proxy
    for "same paragraph" in typical forum post content.
    """
    sent = sentence_records.get(candidate.host_sentence_id)
    if sent is None:
        return False
    used = host_para_positions.get(candidate.host_key, [])
    return any(abs(sent.position - p) <= paragraph_window for p in used)


def select_final_candidates(
    candidates_by_destination: Mapping[ContentKey, list[ScoredCandidate]],
    *,
    max_host_reuse: int = 3,
    sentence_records: Mapping[int, SentenceRecord] | None = None,
    paragraph_window: int = 3,
    blocked_diagnostics: dict[ContentKey, str] | None = None,
) -> list[ScoredCandidate]:
    """Resolve host-reuse, circular-direction, and paragraph-cluster conflicts.

    If *blocked_diagnostics* is provided, destinations whose candidates are
    all blocked will be recorded with their last blocking reason
    (``"host_reuse_cap"``, ``"circular_suppressed"``, or
    ``"paragraph_cluster"``).

    *sentence_records* enables the paragraph guard. When provided, a second
    suggestion targeting a sentence within *paragraph_window* positions of an
    already-selected sentence on the same host is rejected and the next-best
    candidate tried instead.
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
    # Guard 3 — tracks which sentence positions are already "occupied" per host.
    host_para_positions: dict[ContentKey, list[int]] = {}
    last_block_reason: dict[ContentKey, str] = {}

    while heap:
        _neg_final, _neg_semantic, destination_id, destination_type, candidate_idx = (
            heapq.heappop(heap)
        )
        destination_key = (destination_id, destination_type)
        if destination_key in selected_by_destination:
            continue

        candidates = candidates_by_destination.get(destination_key, [])
        if candidate_idx >= len(candidates):
            continue

        candidate = candidates[candidate_idx]
        is_host_reuse = host_reuse_counts[candidate.host_key] >= max_host_reuse
        is_circular = (
            candidate.host_key,
            candidate.destination_key,
        ) in selected_directions
        is_para_collision = sentence_records is not None and _is_paragraph_collision(
            candidate, host_para_positions, sentence_records, paragraph_window
        )
        blocked = is_host_reuse or is_circular or is_para_collision
        if blocked:
            if is_circular:
                last_block_reason[destination_key] = "circular_suppressed"
            elif is_host_reuse:
                last_block_reason[destination_key] = "host_reuse_cap"
            else:
                last_block_reason[destination_key] = "paragraph_cluster"
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
        # Record the sentence position used by this host so the paragraph guard
        # can reject suggestions that land too close to it.
        if sentence_records is not None:
            sent = sentence_records.get(candidate.host_sentence_id)
            if sent is not None:
                host_para_positions.setdefault(candidate.host_key, []).append(
                    sent.position
                )
        last_block_reason.pop(destination_key, None)

    if blocked_diagnostics is not None:
        for dest_key, reason in last_block_reason.items():
            if dest_key not in selected_by_destination:
                blocked_diagnostics[dest_key] = reason

    return sorted(
        selected_by_destination.values(),
        key=lambda c: (-c.score_final, -c.score_semantic),
    )
