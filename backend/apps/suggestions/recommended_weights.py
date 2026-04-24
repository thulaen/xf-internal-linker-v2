"""Canonical research-backed starting weights for the Recommended preset.

These values are the single backend source of truth for the default ranking
starting point shown in Settings and used when older presets are missing newer
keys.
"""

from __future__ import annotations

from .recommended_weights_forward_settings import FORWARD_DECLARED_WEIGHTS

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
    # ── FR-099 through FR-105: 7 complementary graph-topology ranking signals ──
    # Addresses the Reddit-post topology errors: dangling nodes, duplicate lines,
    # misaligned boundaries, gaps between polygons, overlapping polygons.
    # Full specs in docs/specs/fr099-*.md through docs/specs/fr105-*.md.
    # Gate A + Gate B in docs/RANKING-GATES.md applied to every default below.

    # FR-099 — Dangling Authority Redistribution Bonus (DARB)
    # Baseline: Page, Brin, Motwani, Winograd 1999, Stanford InfoLab 1999-66
    # §2.5 "Dangling Links" + §3.2 eq. 1. Weight 0.04 ≈ 40% of weighted_authority
    # (0.10) split across DARB + KCIB as complementary authority signals.
    "darb.enabled": "true",
    "darb.ranking_weight": "0.04",
    "darb.out_degree_saturation": "5",
    "darb.min_host_value": "0.5",

    # FR-100 — Katz Marginal Information Gain (KMIG)
    # Baseline: Katz 1953, Psychometrika 18(1) §2 eq. 2 + §3 attenuation β < 1/λ₁.
    # β=0.5 from Pigueiral 2017 EuroCG'17 truncated-Katz default.
    # Weight 0.05 matches ga4_gsc.ranking_weight magnitude (both additive bonuses).
    "kmig.enabled": "true",
    "kmig.ranking_weight": "0.05",
    "kmig.attenuation": "0.5",
    "kmig.max_hops": "2",

    # FR-101 — Tarjan Articulation Point Boost (TAPB)
    # Baseline: Tarjan 1972, SIAM J. Computing 1(2) §3 articulation-point DFS.
    # Weight 0.03 matches link_farm.ranking_weight (another rare-event structural
    # signal). AP density ~5-8% per Newman 2010 §7.4.1 Table 7.1.
    "tapb.enabled": "true",
    "tapb.ranking_weight": "0.03",
    "tapb.apply_to_articulation_node_only": "true",

    # FR-102 — K-Core Integration Boost (KCIB)
    # Baseline: Seidman 1983, Social Networks 5(3) §2 eq. 1 k-core definition.
    # Modern impl: Batagelj & Zaversnik 2003 O(m) algorithm via networkx.
    # Weight 0.03 matches link_farm magnitude band.
    "kcib.enabled": "true",
    "kcib.ranking_weight": "0.03",
    "kcib.min_kcore_spread": "1",

    # FR-103 — Bridge-Edge Redundancy Penalty (BERP)
    # Baseline: Hopcroft & Tarjan 1973, CACM 16(6) §2 Algorithm 3 bridge-detection.
    # Weight 0.04 penalty matches keyword_stuffing.ranking_weight penalty band.
    # Bridge density ~2% per Newman 2010 §7.4.1 Table 7.1.
    "berp.enabled": "true",
    "berp.ranking_weight": "0.04",
    "berp.min_component_size": "5",

    # FR-104 — Host-Graph Topic Entropy Boost (HGTE)
    # Baseline: Shannon 1948, BSTJ 27(3) §6 eq. 4 entropy formula.
    # Weight 0.04 matches rare_term_propagation.ranking_weight (another
    # diversity-oriented additive bonus). min_host_out_degree=3 follows
    # Shannon §12 asymptotic reliability discussion.
    "hgte.enabled": "true",
    "hgte.ranking_weight": "0.04",
    "hgte.min_host_out_degree": "3",

    # FR-105 — Reverse Search-Query Vocabulary Alignment (RSQVA)
    # Baseline: Salton & Buckley 1988, IP&M 24(5) §3 eq. 1 + §4 cosine similarity.
    # Click-weighting from Järvelin & Kekäläinen 2002 ACM TOIS 20(4) §2.1.
    # Weight 0.05 matches ga4_gsc (both GSC/GA4-derived). Min 5 queries per page
    # per Salton-Buckley §3.2 reliability threshold.
    "rsqva.enabled": "true",
    "rsqva.ranking_weight": "0.05",
    "rsqva.min_queries_per_page": "5",
    "rsqva.min_query_clicks": "1",
    "rsqva.max_vocab_size": "10000",
}

# Merge forward-declared FR keys into the main dict.
RECOMMENDED_PRESET_WEIGHTS.update(FORWARD_DECLARED_WEIGHTS)


def recommended_bool(key: str) -> bool:
    return RECOMMENDED_PRESET_WEIGHTS[key].strip().lower() == "true"


def recommended_float(key: str) -> float:
    return float(RECOMMENDED_PRESET_WEIGHTS[key])


def recommended_int(key: str) -> int:
    return int(float(RECOMMENDED_PRESET_WEIGHTS[key]))


def recommended_str(key: str) -> str:
    return RECOMMENDED_PRESET_WEIGHTS[key]
