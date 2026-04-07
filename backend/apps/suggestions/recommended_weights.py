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
    # FR-040 - Multimedia Boost
    # Forward-declared: inert until FR-040 is implemented and reads these keys.
    # Research basis: Google image/video quality guidance, alt-text usage, and
    # multimedia-engagement studies. Starting weight is 0.10 because FR-040
    # belongs to the value-model family and should be material enough to reward
    # richer destinations without overpowering semantic fit or authority.
    "multimedia_signal_enabled": "true",
    "w_multimedia": "0.10",
    "multimedia_fallback_value": "0.5",
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
    # FR-045 — Anchor Diversity & Exact-Match Reuse Guard
    # Forward-declared: inert until FR-045 is implemented and reads these keys.
    # Research basis: Google over-optimization penalty (Penguin) and anchor text
    # diversity best practices. Starting weight is 0.0 (guard-only mode) because
    # this signal is subtractive — it penalises repetitive anchors rather than
    # boosting diverse ones. Raise to 0.03 after confirming exact_match_share
    # thresholds are well-calibrated on the target site.
    "anchor_diversity.enabled": "true",
    "anchor_diversity.ranking_weight": "0.0",
    "anchor_diversity.min_history_count": "2",
    "anchor_diversity.max_exact_match_share": "0.40",
    "anchor_diversity.max_exact_match_count": "3",
    "anchor_diversity.hard_cap_enabled": "false",
    # FR-046 — Multi-Query Fan-Out for Stage 1 Candidate Retrieval
    # Forward-declared: inert until FR-046 is implemented and reads these keys.
    # Research basis: Cormack et al. 2009 reciprocal rank fusion and multi-query
    # decomposition for long-form documents. This FR modifies Stage 1 retrieval
    # (not scoring), so there is no ranking_weight — it affects which candidates
    # enter the pipeline, not how they are scored.
    "fan_out.enabled": "true",
    "fan_out.max_sub_queries": "3",
    "fan_out.min_segment_words": "50",
    "fan_out.rrf_k": "60",
    # FR-047 — Navigation Path Prediction
    # Forward-declared: inert until FR-047 is implemented and reads these keys.
    # Research basis: US7584181B2 (implicit links from user access patterns) plus
    # first-order Markov transition models on GA4 page_view sequences. Starting
    # weight is 0.04 because directional navigation data is a strong behavioural
    # signal, but it depends on sufficient GA4 session volume to be reliable.
    # Raise to 0.06 after validating that transition counts are stable across
    # pipeline runs on a live site with >50 sessions per source page.
    "navigation_path.enabled": "true",
    "navigation_path.ranking_weight": "0.04",
    "navigation_path.lookback_days": "90",
    "navigation_path.min_sessions": "50",
    "navigation_path.min_transition_count": "5",
    "navigation_path.w_direct": "0.6",
    "navigation_path.w_shortcut": "0.4",
    # FR-048 — Topical Authority Cluster Density
    # Forward-declared: inert until FR-048 is implemented and reads these keys.
    # Research basis: HITS hub/authority scoring, Majestic Topical Trust Flow,
    # HDBSCAN clustering on existing bge-m3 embeddings. Starting weight is 0.04
    # because topical depth is a well-established SEO signal but the cluster
    # quality depends on site size and content diversity. min_cluster_size=5
    # prevents noise clusters from inflating scores. Raise to 0.06 after
    # verifying that HDBSCAN produces stable, meaningful clusters on the target
    # site's embedding space.
    "topical_cluster.enabled": "true",
    "topical_cluster.ranking_weight": "0.04",
    "topical_cluster.min_cluster_size": "5",
    "topical_cluster.min_site_pages": "20",
    "topical_cluster.max_staleness_days": "14",
    "topical_cluster.fallback_value": "0.5",
    # FR-049 — Query Intent Funnel Alignment
    # Forward-declared: inert until FR-049 is implemented and reads these keys.
    # Research basis: WO2015200404A1 (query intent identification) and
    # US20110289063A1 (determining query intent). Starting weight is 0.03
    # because keyword-pattern intent classification is a coarse heuristic in v1
    # and the funnel model assumes a linear journey that not all content follows.
    # Raise to 0.05 after validating that GSC-based intent classification
    # produces stable, sensible stage assignments across a live site.
    "intent_funnel.enabled": "true",
    "intent_funnel.ranking_weight": "0.03",
    "intent_funnel.optimal_offset": "1",
    "intent_funnel.sigma": "1.2",
    "intent_funnel.min_confidence": "0.25",
    "intent_funnel.navigational_confidence_threshold": "0.6",
    # FR-050 — Seasonality & Temporal Demand Matching
    # Forward-declared: inert until FR-050 is implemented and reads these keys.
    # Research basis: US9081857B1 (freshness and seasonality-based content
    # determinations) plus classical seasonal decomposition. Starting weight is
    # 0.03 because seasonal scoring requires 12+ months of clean GA4/GSC data
    # and the signal is inherently noisy for sites with weak seasonal patterns.
    # Raise to 0.05 after confirming that seasonal_strength correctly separates
    # seasonal from perennial pages on a live site.
    "seasonality.enabled": "true",
    "seasonality.ranking_weight": "0.03",
    "seasonality.min_history_months": "12",
    "seasonality.min_seasonal_strength": "0.3",
    "seasonality.anticipation_window_months": "3",
    "seasonality.w_current": "0.7",
    "seasonality.w_anticipation": "0.3",
    "seasonality.index_cap": "3.0",
    # FR-021 - Graph-Based Link Candidate Generation
    "graph_candidate.enabled": "true",
    "graph_candidate.walk_steps_per_entity": "1000",
    "graph_candidate.min_stable_candidates": "50",
    "graph_candidate.min_visit_threshold": "3",
    "graph_candidate.top_k_candidates": "100",
    "graph_candidate.top_n_entities_per_article": "20",
    "value_model.enabled": "true",
    # Additive signal weights must sum to 1.0.
    # Rebalanced after FR-024 (engagement) and FR-025 (co-occurrence) were added.
    "value_model.w_relevance": "0.35",
    "value_model.w_traffic": "0.25",
    "value_model.w_freshness": "0.1",
    "value_model.w_authority": "0.1",
    "value_model.w_penalty": "0.5",
    "value_model.traffic_lookback_days": "90",
    "value_model.traffic_fallback_value": "0.5",
    # FR-024 - TikTok Read-Through Rate Engagement Signal
    "value_model.engagement_signal_enabled": "true",
    "value_model.w_engagement": "0.08",
    "value_model.engagement_lookback_days": "30",
    "value_model.engagement_words_per_minute": "200",
    "value_model.engagement_cap_ratio": "1.5",
    "value_model.engagement_fallback_value": "0.5",
    # FR-023 - Reddit Hot Decay
    # Forward-declared in C# HttpWorker (TrafficDecayService.cs) but was missing
    # from Django settings. Adapted from Reddit's Hot algorithm: recent traffic
    # momentum matters more than stale volume. gravity=0.05 is conservative;
    # raise to 0.08 after verifying that hot_score rankings are stable across
    # 7-day windows on a site with >100 daily active pages.
    "value_model.hot_decay_enabled": "true",
    "value_model.hot_gravity": "0.05",
    "value_model.hot_clicks_weight": "1.0",
    "value_model.hot_impressions_weight": "0.05",
    "value_model.hot_lookback_days": "90",
    # FR-025 - Session Co-Occurrence Signal
    "value_model.co_occurrence_signal_enabled": "true",
    "value_model.w_cooccurrence": "0.12",
    "value_model.co_occurrence_fallback_value": "0.5",
    "value_model.co_occurrence_min_co_sessions": "5",
}


def recommended_bool(key: str) -> bool:
    return RECOMMENDED_PRESET_WEIGHTS[key].strip().lower() == "true"


def recommended_float(key: str) -> float:
    return float(RECOMMENDED_PRESET_WEIGHTS[key])


def recommended_int(key: str) -> int:
    return int(float(RECOMMENDED_PRESET_WEIGHTS[key]))


def recommended_str(key: str) -> str:
    return RECOMMENDED_PRESET_WEIGHTS[key]
