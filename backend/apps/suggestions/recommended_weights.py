"""Canonical research-backed starting weights for the Recommended preset.

These values are the single backend source of truth for the default ranking
starting point shown in Settings and used when older presets are missing newer
keys.
"""

from __future__ import annotations

RECOMMENDED_PRESET_WEIGHTS: dict[str, str] = {
    "w_semantic": "0.40",
    "w_keyword": "0.25",
    "w_node": "0.20",
    "w_quality": "0.15",
    "silo.mode": "prefer_same_silo",
    "silo.same_silo_boost": "0.05",
    "silo.cross_silo_penalty": "0.05",
    "weighted_authority.ranking_weight": "0.10",
    "weighted_authority.position_bias": "0.5",
    "weighted_authority.empty_anchor_factor": "0.6",
    "weighted_authority.bare_url_factor": "0.35",
    "weighted_authority.weak_context_factor": "0.75",
    "weighted_authority.isolated_context_factor": "0.45",
    "rare_term_propagation.enabled": "true",
    "rare_term_propagation.ranking_weight": "0.05",
    "rare_term_propagation.max_document_frequency": "3",
    "rare_term_propagation.minimum_supporting_related_pages": "2",
    "field_aware_relevance.ranking_weight": "0.10",
    "field_aware_relevance.title_field_weight": "0.40",
    "field_aware_relevance.body_field_weight": "0.30",
    "field_aware_relevance.scope_field_weight": "0.15",
    "field_aware_relevance.learned_anchor_field_weight": "0.15",
    "ga4_gsc.ranking_weight": "0.05",
    "click_distance.ranking_weight": "0.07",
    "click_distance.k_cd": "4.0",
    "click_distance.b_cd": "0.75",
    "click_distance.b_ud": "0.25",
    "explore_exploit.enabled": "true",
    "explore_exploit.ranking_weight": "0.08",
    "explore_exploit.exploration_rate": "1.41421356237",
    "clustering.enabled": "true",
    "clustering.similarity_threshold": "0.04",
    "clustering.suppression_penalty": "20.0",
    "slate_diversity.enabled": "true",
    "slate_diversity.diversity_lambda": "0.65",
    "slate_diversity.score_window": "0.30",
    "slate_diversity.similarity_cap": "0.90",
    "link_freshness.ranking_weight": "0.05",
    "link_freshness.recent_window_days": "30",
    "link_freshness.newest_peer_percent": "0.25",
    "link_freshness.min_peer_count": "3",
    "link_freshness.w_recent": "0.35",
    "link_freshness.w_growth": "0.35",
    "link_freshness.w_cohort": "0.20",
    "link_freshness.w_loss": "0.10",
    "phrase_matching.ranking_weight": "0.08",
    "phrase_matching.enable_anchor_expansion": "true",
    "phrase_matching.enable_partial_matching": "true",
    "phrase_matching.context_window_tokens": "8",
    "learned_anchor.ranking_weight": "0.05",
    "learned_anchor.minimum_anchor_sources": "2",
    "learned_anchor.minimum_family_support_share": "0.15",
    "learned_anchor.enable_noise_filter": "true",
    # FR-038 — Information Gain Scoring
    # Forward-declared: these keys are inert until FR-038 is implemented and reads them.
    # A new migration (or manual DB update) is needed to push these into the seeded preset.
    # Research basis: US11354342B2. Starting weight is conservative (0.03) because this
    # signal is unvalidated on real content. Run diagnostics first, then raise to 0.05
    # once sample_novel_tokens look sensible across a live pipeline run.
    "information_gain.enabled": "true",
    "information_gain.ranking_weight": "0.03",
    "information_gain.min_source_chars": "200",
    # FR-039 — Entity Salience Match
    # Forward-declared: same note as FR-038 above — inert until FR-039 is implemented.
    # Research basis: US9251473B2. Starting weight is 0.04 — slightly higher than FR-038
    # because entity salience is a well-established IR signal and TF-IDF arithmetic is
    # deterministic and easy to inspect. max_site_document_frequency=20 allows moderately
    # common terms to qualify as salient, which is appropriate for a forum site where even
    # product names can appear on 10–15 pages.
    "entity_salience.enabled": "true",
    "entity_salience.ranking_weight": "0.04",
    "entity_salience.max_salient_terms": "10",
    "entity_salience.max_site_document_frequency": "20",
    "entity_salience.min_source_term_frequency": "2",
    # FR-041 - Originality Provenance Scoring
    # Forward-declared: inert until FR-041 is implemented and reads these keys.
    # Research basis: US8707459B2 plus lexical near-duplicate provenance math
    # using shingles, resemblance, and containment. Starting weight is 0.03
    # because the signal is narrow by design: it should gently prefer the
    # earliest, most source-like page within a near-copy family, not override
    # broader relevance or authority signals across unrelated pages.
    "originality_provenance.enabled": "true",
    "originality_provenance.ranking_weight": "0.03",
    "originality_provenance.resemblance_threshold": "0.55",
    "originality_provenance.containment_threshold": "0.80",
    # FR-042 - Fact Density Scoring
    # Forward-declared: inert until FR-042 is implemented and reads these keys.
    # Research basis: factual-density literature plus US9286379B2 document-quality
    # framing. Starting weight is 0.04 because this is a broadly useful quality
    # signal, but it still relies on heuristic fact-like sentence detection and
    # may be noisy on conversational forum content until calibrated on live data.
    "fact_density.enabled": "true",
    "fact_density.ranking_weight": "0.04",
    "fact_density.min_word_count": "120",
    "fact_density.density_cap_per_100_words": "8.0",
    "fact_density.filler_penalty_weight": "0.35",
    # FR-043 - Semantic Drift Penalty
    # Forward-declared: inert until FR-043 is implemented and reads these keys.
    # Research basis: Hearst TextTiling segmentation plus US8185378B2 text-
    # coherence ideas. Starting weight is 0.03 because this is a subtractive
    # quality guardrail and should begin conservatively to avoid over-penalizing
    # long forum pages, compilations, or pages with legitimate multi-section flow.
    "semantic_drift.enabled": "true",
    "semantic_drift.ranking_weight": "0.03",
    "semantic_drift.tokens_per_sequence": "20",
    "semantic_drift.block_size_in_sequences": "6",
    "semantic_drift.anchor_similarity_threshold": "0.18",
    "semantic_drift.min_word_count": "180",
    # FR-044 - Internal Search Intensity Signal
    # Forward-declared: inert until FR-044 is implemented and reads these keys.
    # Research basis: Matomo Site Search aggregates, burst-style trend math, and
    # US20050102259A1 query-trend analysis. Starting weight is 0.02 because this
    # signal is temporally noisy and query matching can overfire before operators
    # validate that active internal-search topics map cleanly onto destination pages.
    "internal_search.enabled": "true",
    "internal_search.ranking_weight": "0.02",
    "internal_search.recent_days": "3",
    "internal_search.baseline_days": "28",
    "internal_search.max_active_queries": "200",
    "internal_search.min_recent_count": "3",
}


def recommended_bool(key: str) -> bool:
    return RECOMMENDED_PRESET_WEIGHTS[key].strip().lower() == "true"


def recommended_float(key: str) -> float:
    return float(RECOMMENDED_PRESET_WEIGHTS[key])


def recommended_int(key: str) -> int:
    return int(float(RECOMMENDED_PRESET_WEIGHTS[key]))


def recommended_str(key: str) -> str:
    return RECOMMENDED_PRESET_WEIGHTS[key]
