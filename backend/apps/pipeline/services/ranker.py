"""Composite scoring and anti-junk selection for link suggestions.

This module is pure Python — no database access. All DB loading is done
by the pipeline service which passes pre-built records into these functions.
"""

from __future__ import annotations

from collections import Counter
import dataclasses
import heapq
import logging
import math
import numpy as np
from rapidfuzz import fuzz
from typing import Any, Mapping

from .rust_kernels import KernelUnavailableError, load_kernel

logger = logging.getLogger(__name__)

# The ranker's final composite-score kernel was ported from C++ to Rust
# (rust/extensions/scoring) and is loaded through the shared `load_kernel`
# helper (RUST-FIRST.md zero-fallback — there is no Python copy of the hot
# path). Loading at module level inside a try/except is a boot-safety shim: if
# the native `.so` is not yet staged, the import still succeeds so the rest of
# the module is usable, and the actual call (below) raises loudly through
# `load_kernel`. `_calculate_composite_scores_full_batch_py` is retained ONLY as
# the cross-language parity oracle the acceptance tests drive — it is NOT a
# silent runtime fallback.
try:
    scoring = load_kernel("extensions.scoring", "calculate_composite_scores_full_batch")
    HAS_CPP_FULL_BATCH = True
except KernelUnavailableError:
    scoring = None
    HAS_CPP_FULL_BATCH = False

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
from .phrase_matching import (
    PhraseMatchingSettings,
    evaluate_phrase_match,
    score_phrase_relevance_component,
)
from .rare_term_propagation import (
    RareTermProfile,
    RareTermPropagationSettings,
    evaluate_rare_term_propagation,
)
from .ranker_types import (
    ClusteringSettings,
    ContentKey,
    ContentRecord,
    ExistingLinkKey,
    ScoredCandidate,
    SentenceRecord,
    SentenceSemanticMatch,
    SiloSettings,
    _NEUTRAL_SCORE,
)


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


def _score_fuzzy_match(anchor: str, target: str) -> float:
    """Pick #62 — Fuzzy string matching score [0, 1] via RapidFuzz.

    Uses Token Set Ratio to handle reordering and partial matches.
     रिसर्च basis: Joachims 2007 §3 typo-tolerance in anchor text.
    """
    if not anchor or not target:
        return 0.0
    # ratio is [0, 100]
    ratio = fuzz.token_set_ratio(anchor, target)
    if ratio < 85:  # Research threshold gate (US8380722B2 §5)
        return 0.0
    return ratio / 100.0


def _compute_jsd(p_tokens: list[str], q_tokens: list[str]) -> float:
    """Pick #64 — Jensen-Shannon Divergence [0, 1] between token distributions.

    Measure alignment between query distribution (source) and document
    distribution (destination). 0.0 = identical distributions (max boost).
    Citation: Lin, J. (1991). "Divergence measures based on the Shannon entropy."
    """
    if not p_tokens or not q_tokens:
        return 1.0  # Max divergence

    from collections import Counter

    p_counts = Counter(p_tokens)
    q_counts = Counter(q_tokens)

    total_p = sum(p_counts.values())
    total_q = sum(q_counts.values())

    vocab = set(p_counts.keys()) | set(q_counts.keys())
    p = {w: p_counts.get(w, 0) / total_p for w in vocab}
    q = {w: q_counts.get(w, 0) / total_q for w in vocab}

    # Mixture distribution
    m = {w: 0.5 * (p[w] + q[w]) for w in vocab}

    def kl_div(dist, ref):
        res = 0.0
        for w in vocab:
            if dist[w] > 0:
                res += dist[w] * math.log2(dist[w] / ref[w])
        return res

    jsd = 0.5 * kl_div(p, m) + 0.5 * kl_div(q, m)
    return jsd


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
        return _NEUTRAL_SCORE

    epsilon = 1e-9
    min_log = math.log(score_min + epsilon)
    max_log = math.log(score_max + epsilon)
    if min_log == max_log:
        return _NEUTRAL_SCORE

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


def _build_min_semantic_predicate(min_semantic_score: float):
    """Return a ``score -> bool`` predicate for the Stage-2 cutoff.

    FR-245 — when ``pipeline.calibration_enabled`` is true (default),
    the predicate is ``passes_calibrated_threshold`` reading
    ``pipeline.min_calibrated_probability`` (default 0.5). When false
    (or any read fails), falls back to the legacy raw cosine cutoff
    so behaviour is identical to pre-FR-245 code. Sources of truth:
    Platt 1999 §2 (sigmoid decision boundary); cold-start params in
    ``score_calibration.COLD_START_PARAMS`` target σ(0)=0.5 at
    cosine=0.25 so the legacy behaviour is roughly preserved.
    """
    try:
        from apps.suggestions.recommended_weights import (
            recommended_bool,
            recommended_float as _recommended_float,
        )

        if not recommended_bool("pipeline.calibration_enabled"):
            return lambda score: score >= min_semantic_score
        threshold = float(_recommended_float("pipeline.min_calibrated_probability"))
    except Exception:  # noqa: BLE001 — cold-start safe.
        return lambda score: score >= min_semantic_score
    try:
        from .score_calibration import (
            load_active_params,
            passes_calibrated_threshold,
        )
    except Exception:  # noqa: BLE001
        return lambda score: score >= min_semantic_score
    active_params = load_active_params()  # None → cold-start fallback used
    return lambda score: passes_calibrated_threshold(
        score,
        threshold=threshold,
        params=active_params,
    )


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

    # FR-053 bug-fix follow-up — prefetch host sentence embeddings.
    # The original ranker hook (Group E V1) tried to read ``embedding``
    # off ``SentenceRecord``, which doesn't carry the vector. The
    # passage-relevance signal therefore never fired in production.
    # One bulk query here gives the ranker hook the actual
    # ``Sentence.embedding`` payload it needs, indexed by sentence_id.
    # Empty dict on any failure → ``passage_relevance.score`` falls
    # back to its neutral path, so the ranker stays defensive.
    sentence_embedding_by_id: dict[int, Any] = {}
    # The destination's underlying ``ContentItem`` ORM row is also
    # needed for FR-053 — ``ContentRecord`` is a frozen dataclass and
    # doesn't carry the ``duplicate_of`` FK or the ``passage_embeddings``
    # related-name. One lookup per destination is fine because this
    # function runs per-destination already.
    destination_content_item: Any = None
    try:
        from apps.content.models import ContentItem as _ContentItemModel
        from apps.content.models import Sentence as _SentenceModel

        needed_ids = {match.sentence_id for match in sentence_matches}
        if needed_ids:
            sentence_embedding_by_id = {
                pk: emb
                for pk, emb in _SentenceModel.objects.filter(
                    pk__in=needed_ids,
                    embedding__isnull=False,
                ).values_list("pk", "embedding")
            }
        destination_content_item = (
            _ContentItemModel.objects.filter(
                content_id=destination.content_id,
                content_type=destination.content_type,
            )
            .only("pk", "duplicate_of_id")
            .first()
        )
    except Exception as exc:
        logger.warning(
            "score_destination_matches: failed to prefetch sentence "
            "embeddings or destination ContentItem for FR-053 — passage "
            "relevance will return neutral for this run",
            exc_info=True,
        )
        # Phase 0.2 — surface to /error-log so the operator sees the
        # silent neutral-fallback instead of it being buried in worker
        # logs. ingest_error() is dedup-by-fingerprint and never raises.
        from apps.audit.error_ingest import ingest_error
        from apps.audit.models import ErrorLog

        ingest_error(
            job_type="ranker_signal",
            step="prefetch_passage_relevance",
            error_message=str(exc),
            raw_exception=repr(exc),
            why="FR-053 passage relevance returned neutral 0.5 for this run.",
            severity=ErrorLog.SEVERITY_MEDIUM,
        )
        sentence_embedding_by_id = {}
        destination_content_item = None

    nk_node_signal = None
    nk_link_candidates_by_host = {}
    if destination_content_item:
        try:
            from apps.graph.api import latest_node_signal, link_prediction_candidates
            nk_node_signal = latest_node_signal(destination_content_item)
            nk_candidates = link_prediction_candidates(destination_content_item, as_destination=True)
            nk_link_candidates_by_host = {
                (c.from_item.content_id, c.from_item.content_type): c for c in nk_candidates
            }
        except Exception as exc:
            logger.warning("Failed to fetch NetworKit graph signals", exc_info=True)

    # FR-245 — when calibration is enabled (default true), use the
    # Platt-calibrated probability instead of the raw cosine cutoff.
    # Cold-start params target σ(0)=0.5 at cosine=0.25 so behaviour is
    # roughly equivalent to the legacy 0.25 cutoff during the no-fit
    # interim. See docs/specs/fr245-platt-calibrated-thresholds.md.
    fr245_predicate = _build_min_semantic_predicate(min_semantic_score)
    for match in sentence_matches:
        if not fr245_predicate(match.score_semantic):
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
            host_nlp_metadata=sentence_record.nlp_metadata,
            destination_nlp_metadata=destination.nlp_metadata,
        )
        # Bug fix 2026-05-05: PhraseMatchResult is a frozen dataclass; the
        # original code assigned to `.score_phrase_relevance` directly which
        # raised FrozenInstanceError. Compute boosts into a local then
        # rebuild the dataclass once via `replace()`.
        relevance = phrase_match.score_phrase_relevance

        # Pick #55 — Noun-chunk boost.
        if (
            phrase_match.anchor_phrase
            and sentence_record.nlp_metadata
            and any(
                phrase_match.anchor_phrase == chunk["text"]
                for chunk in sentence_record.nlp_metadata.get("noun_chunks", [])
            )
        ):
            relevance = min(
                1.0, relevance + phrase_matching_settings.noun_chunk_boost_weight
            )

        # Pick #57 — Lexical Richness boost.
        if sentence_record.nlp_metadata:
            richness = sentence_record.nlp_metadata.get("lexical_richness", {})
            ttr = richness.get("ttr", 0.0)
            if ttr > 0.4:  # Only boost substantive sentences
                relevance = min(
                    1.0, relevance + phrase_matching_settings.lexical_richness_weight
                )

        # Pick #62 — Fuzzy Match (RapidFuzz).
        if phrase_match.anchor_phrase:
            fuzzy_score = _score_fuzzy_match(
                phrase_match.anchor_phrase, destination.title
            )
            if fuzzy_score > 0:
                relevance = min(
                    1.0,
                    relevance
                    + fuzzy_score * phrase_matching_settings.fuzzy_match_weight,
                )

        # Pick #61 — Phonetic Boost (Double Metaphone).
        if sentence_record.nlp_metadata and destination.nlp_metadata:
            host_keys = set(sentence_record.nlp_metadata.get("phonetic_keys", []))
            dest_keys = set(destination.nlp_metadata.get("phonetic_keys", []))
            if host_keys & dest_keys:
                relevance = min(
                    1.0, relevance + phrase_matching_settings.phonetic_boost_weight
                )

        # Pick #64 — JSD alignment boost.
        jsd = _compute_jsd(destination.tokens, sentence_record.tokens)
        if jsd < 0.5:  # Lower divergence = better alignment
            jsd_boost = (1.0 - jsd) * phrase_matching_settings.jsd_boost_weight
            relevance = min(1.0, relevance + jsd_boost)

        # Re-center the component score after all NLP boosts.
        phrase_match = dataclasses.replace(
            phrase_match,
            score_phrase_relevance=relevance,
            score_phrase_component=score_phrase_relevance_component(relevance),
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
        # RUST-FIRST.md zero-fallback: the Rust kernel is authoritative and is
        # called unconditionally. `load_kernel` raises a loud
        # `KernelUnavailableError` if the native `.so` is missing, instead of
        # silently dropping to the slow Python path. The Rust kernel's typed
        # numpy extractor (`PyReadonlyArray2<f32>`) requires C-contiguous
        # float32 inputs, so coerce here exactly like the parity oracle does.
        kernel = load_kernel(
            "extensions.scoring", "calculate_composite_scores_full_batch"
        )
        component_scores_f32 = np.ascontiguousarray(component_scores, dtype=np.float32)
        batch_weights_f32 = np.ascontiguousarray(batch_weights, dtype=np.float32)
        silo_array_f32 = np.ascontiguousarray(silo_array, dtype=np.float32)
        score_finals = kernel.calculate_composite_scores_full_batch(
            component_scores_f32,
            batch_weights_f32,
            silo_array_f32,
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

    nk_node_contribution = 0.0
    if nk_node_signal:
        def _get_nk(val): return float(val) - 0.5 if val is not None else 0.0
        nk_node_contribution += float(weights.get("graph.nk_centrality.ranking_weight", 0.0)) * _get_nk(nk_node_signal.eigenvector)
        nk_node_contribution += float(weights.get("graph.nk_betweenness.ranking_weight", 0.0)) * _get_nk(nk_node_signal.betweenness)
        nk_node_contribution += float(weights.get("graph.nk_reach.ranking_weight", 0.0)) * (0.5 if nk_node_signal.inbound_reachable else -0.5)
        nk_node_contribution += float(weights.get("graph.nk_kcore.ranking_weight", 0.0)) * _get_nk(nk_node_signal.core_number)
        nk_node_contribution += float(weights.get("graph.nk_components.ranking_weight", 0.0)) * (0.5 if nk_node_signal.is_main_component else -0.5)
        nk_node_contribution += float(weights.get("graph.nk_local_clustering.ranking_weight", 0.0)) * _get_nk(nk_node_signal.local_clustering)
        nk_node_contribution += float(weights.get("graph.nk_group_seed_rank.ranking_weight", 0.0)) * _get_nk(nk_node_signal.group_seed_rank)

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

        nk_link_contribution = 0.0
        nk_cand = nk_link_candidates_by_host.get(match.host_key)
        if nk_cand:
            def _get_nk(val): return float(val) - 0.5 if val is not None else 0.0
            nk_link_contribution += float(weights.get("graph.nk_link_prediction.ranking_weight", 0.0)) * _get_nk(nk_cand.adamic_adar)
            nk_link_contribution += float(weights.get("graph.nk_communities.ranking_weight", 0.0)) * (0.5 if nk_cand.same_community else -0.5)
            nk_link_contribution += float(weights.get("graph.nk_node2vec.ranking_weight", 0.0)) * _get_nk(nk_cand.embed_cosine)
        
        score_final += nk_node_contribution + nk_link_contribution

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

        # FR-249 — Embedding age decay component. Source: Liu 2009 *Learning
        # to Rank for IR* §1.5.4 (DOI 10.1561/1500000016) — freshness as a
        # ranking feature. Newton's law of cooling with default 365-day
        # half-life. The decay is in [0, 1]; we multiply by the configured
        # weight (default 0.05) so a fresh embedding gains up to +0.05 and
        # a 1-year-old embedding gains +0.025. Cold-start safe: when
        # ``destination.updated_at`` is None, decay returns 1.0 (no
        # penalty for unknown age). See docs/specs/fr249-embedding-age-decay.md.
        from .embedding_age import (
            compute_embedding_age_decay as _fr249_decay,
            get_age_decay_settings as _fr249_settings,
        )

        _fr249_half_life, _fr249_weight = _fr249_settings()
        score_embedding_age = _fr249_decay(
            getattr(destination, "updated_at", None),
            half_life_days=_fr249_half_life,
        )
        score_final += float(_fr249_weight) * score_embedding_age

        # FR-053 — Passage-Level Relevance Scoring (masterplan Group E).
        # Read the destination's best-passage similarity to the host
        # sentence embedding and add the centred component to score_final.
        # Plain English: if any single paragraph in the destination is a
        # very strong match for the host sentence, lift this candidate
        # above destinations whose match was averaged out across the
        # whole page. Patent US 9,940,367 B1 (Google 2018).
        #
        # Defensive: ``passage_relevance.score`` never raises into here;
        # any failure path returns the neutral 0.5 score whose centred
        # component is 0.0 (no contribution).
        passage_relevance_score = _NEUTRAL_SCORE
        passage_relevance_diags: dict[str, Any] = {}
        passage_relevance_contribution = 0.0
        try:
            from . import passage_relevance as passage_relevance_svc

            # Look up the prefetched ``Sentence.embedding`` payload via the
            # dict built above. Falls through to None when the sentence
            # has no embedding yet (cold start) — score() handles None
            # via the ``neutral_no_query_embedding`` state. Same for
            # destination_content_item being None (prefetch failure) —
            # score() returns the neutral_no_destination diagnostic.
            host_q = sentence_embedding_by_id.get(match.sentence_id)
            passage_relevance_score, passage_relevance_diags = (
                passage_relevance_svc.score(host_q, destination_content_item)
            )
            passage_relevance_weight = passage_relevance_svc.ranking_weight()
            passage_relevance_contribution = (
                passage_relevance_weight
                * passage_relevance_svc.score_component(passage_relevance_score)
            )
        except Exception as exc:
            logger.warning(
                "passage_relevance contribution failed for sentence=%s destination=%s; "
                "treating as neutral",
                getattr(match, "sentence_id", None),
                getattr(destination, "pk", None),
                exc_info=True,
            )
            # Phase 0.2 — fingerprinted dedup so a recurring failure
            # rolls into one /error-log row with occurrence_count++.
            from apps.audit.error_ingest import ingest_error
            from apps.audit.models import ErrorLog

            ingest_error(
                job_type="ranker_signal",
                step="passage_relevance_contribution",
                error_message=str(exc),
                raw_exception=repr(exc),
                why="FR-053 contribution suppressed; ranker continues with score_final unchanged.",
                severity=ErrorLog.SEVERITY_MEDIUM,
            )
        score_final += passage_relevance_contribution

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
                    anchor_confidence=getattr(phrase_match, "anchor_confidence", None),
                )
                score_final += float(phase6_contribution.contribute_total(phase6_ctx))
            except Exception as exc:  # pragma: no cover — defensive
                logger.warning(
                    "phase6_contribution.contribute_total raised: %s",
                    exc,
                )
                # Phase 0.2 — surface to deduped error log.
                from apps.audit.error_ingest import ingest_error
                from apps.audit.models import ErrorLog

                ingest_error(
                    job_type="ranker_signal",
                    step="phase6_contribution",
                    error_message=str(exc),
                    raw_exception=repr(exc),
                    why="Phase 6 picks (VADER/KenLM/LDA/Node2Vec/BPR/FM) returned no contribution.",
                    severity=ErrorLog.SEVERITY_LOW,
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
                dest_title_for_anchor = getattr(destination, "title", "") or ""
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
                # Phase 0.2 — surface to deduped error log so an
                # anchor-classifier regression isn't silently lost.
                from apps.audit.error_ingest import ingest_error
                from apps.audit.models import ErrorLog

                ingest_error(
                    job_type="ranker_signal",
                    step="anchor_garbage_dispatcher",
                    error_message=str(exc),
                    raw_exception=repr(exc),
                    why="PR-Anchor anti-generic / pro-descriptive contribution skipped for this candidate.",
                    severity=ErrorLog.SEVERITY_LOW,
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
                # FR-053 Passage-Level Relevance (masterplan Group E).
                score_passage_relevance=float(passage_relevance_score),
                passage_relevance_diagnostics=dict(passage_relevance_diags),
                # FR-249 — embedding age decay; persisted to Suggestion
                # so the FR-018 WeightTuner can read it as a 5th
                # tunable feature alongside score_semantic / score_
                # keyword / score_node_affinity / score_quality.
                score_embedding_age=float(score_embedding_age),
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
        score_keyword_stuffing=_NEUTRAL_SCORE,
        score_component=0.0,
        diagnostics={
            "stuffing_state": "neutral",
            "stuff_score": 0.0,
            "stuff_penalty": 0.0,
            "score_keyword_stuffing": _NEUTRAL_SCORE,
            "algorithm_version": settings.algorithm_version,
        },
    )


def _neutral_link_farm_eval(settings: LinkFarmSettings) -> LinkFarmEvaluation:
    return LinkFarmEvaluation(
        score_link_farm=_NEUTRAL_SCORE,
        score_component=0.0,
        diagnostics={
            "link_farm_state": "neutral",
            "ring_score": 0.0,
            "ring_penalty": 0.0,
            "score_link_farm": _NEUTRAL_SCORE,
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
