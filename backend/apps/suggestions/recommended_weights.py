"""Canonical research-backed starting weights for the Recommended preset.

These values are the single backend source of truth for the default ranking
starting point shown in Settings and used when older presets are missing newer
keys.
"""

from __future__ import annotations

from .recommended_weights_forward_settings import FORWARD_DECLARED_WEIGHTS
from .recommended_weights_phase2_metas_p1_p6 import (
    FORWARD_DECLARED_WEIGHTS_PHASE2_METAS_P1_P6,
)
from .recommended_weights_phase2_metas_p7_p12 import (
    FORWARD_DECLARED_WEIGHTS_PHASE2_METAS_P7_P12,
)
from .recommended_weights_phase2_metas_q1_q8 import (
    FORWARD_DECLARED_WEIGHTS_PHASE2_METAS_Q1_Q8,
)
from .recommended_weights_phase2_metas_q9_q16 import (
    FORWARD_DECLARED_WEIGHTS_PHASE2_METAS_Q9_Q16,
)
from .recommended_weights_phase2_metas_q17_q24 import (
    FORWARD_DECLARED_WEIGHTS_PHASE2_METAS_Q17_Q24,
)

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
    # Runtime anti-spam signals (also seeded into DB by migration 0032).
    # Both signals are live and read by pipeline/services/pipeline_loaders.py.
    "keyword_stuffing.enabled": "true",
    "keyword_stuffing.ranking_weight": "0.04",
    "keyword_stuffing.alpha": "6.0",
    "keyword_stuffing.tau": "0.30",
    "keyword_stuffing.dirichlet_mu": "2000",
    "keyword_stuffing.top_k_stuff_terms": "5",
    "link_farm.enabled": "true",
    "link_farm.ranking_weight": "0.03",
    "link_farm.min_scc_size": "3",
    "link_farm.density_threshold": "0.6",
    "link_farm.lambda": "0.8",
    # Pipeline recall thresholds — tunable to trade recall vs. speed.
    # Research basis: Bruch et al. 2024 and Cormack et al. 2009 recommend
    # tunable fan-out over fixed budgets. These defaults match the original
    # hardcoded values but can now be adjusted per-site.
    "pipeline.stage1_top_k": "50",
    "pipeline.stage2_top_k": "10",
    "pipeline.min_semantic_score": "0.25",
}

# Merge forward-declared FR keys into the main dict.
RECOMMENDED_PRESET_WEIGHTS.update(FORWARD_DECLARED_WEIGHTS)
# Merge Phase 2 forward-declared meta hyperparameters (META-40 through META-249).
# Each meta carries researched hyperparameters; roster members default
# enabled=true, others default enabled=false.
RECOMMENDED_PRESET_WEIGHTS.update(FORWARD_DECLARED_WEIGHTS_PHASE2_METAS_P1_P6)
RECOMMENDED_PRESET_WEIGHTS.update(FORWARD_DECLARED_WEIGHTS_PHASE2_METAS_P7_P12)
RECOMMENDED_PRESET_WEIGHTS.update(FORWARD_DECLARED_WEIGHTS_PHASE2_METAS_Q1_Q8)
RECOMMENDED_PRESET_WEIGHTS.update(FORWARD_DECLARED_WEIGHTS_PHASE2_METAS_Q9_Q16)
RECOMMENDED_PRESET_WEIGHTS.update(FORWARD_DECLARED_WEIGHTS_PHASE2_METAS_Q17_Q24)


def recommended_bool(key: str) -> bool:
    return RECOMMENDED_PRESET_WEIGHTS[key].strip().lower() == "true"


def recommended_float(key: str) -> float:
    return float(RECOMMENDED_PRESET_WEIGHTS[key])


def recommended_int(key: str) -> int:
    return int(float(RECOMMENDED_PRESET_WEIGHTS[key]))


def recommended_str(key: str) -> str:
    return RECOMMENDED_PRESET_WEIGHTS[key]
