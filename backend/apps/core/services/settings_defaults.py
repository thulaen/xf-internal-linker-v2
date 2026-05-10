"""Canonical default values and bounds for per-feature settings.

Split from settings_helpers.py on 2026-05-10.
Each DEFAULT_* dict is the "first start" value for the feature.
"""

from __future__ import annotations

from apps.suggestions.recommended_weights import (
    recommended_bool,
    recommended_float,
    recommended_int,
    recommended_str,
)

DEFAULT_SILO_SETTINGS = {
    "mode": recommended_str("silo.mode"),
    "same_silo_boost": recommended_float("silo.same_silo_boost"),
    "cross_silo_penalty": recommended_float("silo.cross_silo_penalty"),
}

DEFAULT_WORDPRESS_SETTINGS = {
    "base_url": "",
    "username": "",
    "sync_enabled": False,
    "sync_hour": 3,
    "sync_minute": 0,
}

DEFAULT_WEIGHTED_AUTHORITY_SETTINGS = {
    "ranking_weight": recommended_float("weighted_authority.ranking_weight"),
    "position_bias": recommended_float("weighted_authority.position_bias"),
    "empty_anchor_factor": recommended_float("weighted_authority.empty_anchor_factor"),
    "bare_url_factor": recommended_float("weighted_authority.bare_url_factor"),
    "weak_context_factor": recommended_float("weighted_authority.weak_context_factor"),
    "isolated_context_factor": recommended_float(
        "weighted_authority.isolated_context_factor"
    ),
}

DEFAULT_LINK_FRESHNESS_SETTINGS = {
    "ranking_weight": recommended_float("link_freshness.ranking_weight"),
    "recent_window_days": recommended_int("link_freshness.recent_window_days"),
    "newest_peer_percent": recommended_float("link_freshness.newest_peer_percent"),
    "min_peer_count": recommended_int("link_freshness.min_peer_count"),
    "w_recent": recommended_float("link_freshness.w_recent"),
    "w_growth": recommended_float("link_freshness.w_growth"),
    "w_cohort": recommended_float("link_freshness.w_cohort"),
    "w_loss": recommended_float("link_freshness.w_loss"),
}

DEFAULT_PHRASE_MATCHING_SETTINGS = {
    "ranking_weight": recommended_float("phrase_matching.ranking_weight"),
    "enable_anchor_expansion": recommended_bool(
        "phrase_matching.enable_anchor_expansion"
    ),
    "enable_partial_matching": recommended_bool(
        "phrase_matching.enable_partial_matching"
    ),
    "context_window_tokens": recommended_int("phrase_matching.context_window_tokens"),
}

DEFAULT_LEARNED_ANCHOR_SETTINGS = {
    "ranking_weight": recommended_float("learned_anchor.ranking_weight"),
    "minimum_anchor_sources": recommended_int("learned_anchor.minimum_anchor_sources"),
    "minimum_family_support_share": recommended_float(
        "learned_anchor.minimum_family_support_share"
    ),
    "enable_noise_filter": recommended_bool("learned_anchor.enable_noise_filter"),
}

DEFAULT_RARE_TERM_PROPAGATION_SETTINGS = {
    "enabled": recommended_bool("rare_term_propagation.enabled"),
    "ranking_weight": recommended_float("rare_term_propagation.ranking_weight"),
    "max_document_frequency": recommended_int(
        "rare_term_propagation.max_document_frequency"
    ),
    "minimum_supporting_related_pages": recommended_int(
        "rare_term_propagation.minimum_supporting_related_pages"
    ),
}

DEFAULT_FIELD_AWARE_RELEVANCE_SETTINGS = {
    "ranking_weight": recommended_float("field_aware_relevance.ranking_weight"),
    "title_field_weight": recommended_float("field_aware_relevance.title_field_weight"),
    "body_field_weight": recommended_float("field_aware_relevance.body_field_weight"),
    "scope_field_weight": recommended_float("field_aware_relevance.scope_field_weight"),
    "learned_anchor_field_weight": recommended_float(
        "field_aware_relevance.learned_anchor_field_weight"
    ),
}

DEFAULT_GA4_GSC_SETTINGS = {
    "ranking_weight": recommended_float("ga4_gsc.ranking_weight"),
    "property_url": "",
    "service_account_email": "",
    "private_key_configured": False,
    "sync_enabled": False,
    "sync_lookback_days": 7,
    "connection_status": "not_configured",
    "connection_message": "Fill in the Search Console property URL and service-account credentials.",
}

DEFAULT_CLICK_DISTANCE_SETTINGS = {
    "ranking_weight": recommended_float("click_distance.ranking_weight"),
    "k_cd": recommended_float("click_distance.k_cd"),
    "b_cd": recommended_float("click_distance.b_cd"),
    "b_ud": recommended_float("click_distance.b_ud"),
}

DEFAULT_FEEDBACK_RERANK_SETTINGS = {
    "enabled": recommended_bool("explore_exploit.enabled"),
    "ranking_weight": recommended_float("explore_exploit.ranking_weight"),
    "exploration_rate": recommended_float("explore_exploit.exploration_rate"),
}

DEFAULT_CLUSTERING_SETTINGS = {
    "enabled": recommended_bool("clustering.enabled"),
    "similarity_threshold": recommended_float("clustering.similarity_threshold"),
    "suppression_penalty": recommended_float("clustering.suppression_penalty"),
}

DEFAULT_SLATE_DIVERSITY_SETTINGS = {
    "enabled": recommended_bool("slate_diversity.enabled"),
    "diversity_lambda": recommended_float("slate_diversity.diversity_lambda"),
    "score_window": recommended_float("slate_diversity.score_window"),
    "similarity_cap": recommended_float("slate_diversity.similarity_cap"),
    "algorithm_version": "fr015-v1",
}

DEFAULT_GRAPH_CANDIDATE_SETTINGS = {
    "enabled": recommended_bool("graph_candidate.enabled"),
    "walk_steps_per_entity": recommended_int("graph_candidate.walk_steps_per_entity"),
    "min_stable_candidates": recommended_int("graph_candidate.min_stable_candidates"),
    "min_visit_threshold": recommended_int("graph_candidate.min_visit_threshold"),
    "top_k_candidates": recommended_int("graph_candidate.top_k_candidates"),
    "top_n_entities_per_article": recommended_int(
        "graph_candidate.top_n_entities_per_article"
    ),
}

DEFAULT_VALUE_MODEL_SETTINGS = {
    "enabled": recommended_bool("value_model.enabled"),
    "w_relevance": recommended_float("value_model.w_relevance"),
    "w_traffic": recommended_float("value_model.w_traffic"),
    "w_freshness": recommended_float("value_model.w_freshness"),
    "w_authority": recommended_float("value_model.w_authority"),
    "w_penalty": recommended_float("value_model.w_penalty"),
    "traffic_lookback_days": recommended_int("value_model.traffic_lookback_days"),
    "traffic_fallback_value": recommended_float("value_model.traffic_fallback_value"),
    "engagement_signal_enabled": recommended_bool("value_model.engagement_signal_enabled"),
    "w_engagement": recommended_float("value_model.w_engagement"),
    "engagement_lookback_days": recommended_int("value_model.engagement_lookback_days"),
    "engagement_words_per_minute": recommended_int("value_model.engagement_words_per_minute"),
    "engagement_cap_ratio": recommended_float("value_model.engagement_cap_ratio"),
    "engagement_fallback_value": recommended_float("value_model.engagement_fallback_value"),
    "hot_decay_enabled": recommended_bool("value_model.hot_decay_enabled"),
    "hot_gravity": recommended_float("value_model.hot_gravity"),
    "hot_clicks_weight": recommended_float("value_model.hot_clicks_weight"),
    "hot_impressions_weight": recommended_float("value_model.hot_impressions_weight"),
    "hot_lookback_days": recommended_int("value_model.hot_lookback_days"),
    "co_occurrence_signal_enabled": recommended_bool("value_model.co_occurrence_signal_enabled"),
    "w_cooccurrence": recommended_float("value_model.w_cooccurrence"),
    "co_occurrence_fallback_value": recommended_float("value_model.co_occurrence_fallback_value"),
    "co_occurrence_min_co_sessions": recommended_int("value_model.co_occurrence_min_co_sessions"),
}

DEFAULT_SPAM_GUARD_SETTINGS: dict[str, int] = {
    "max_existing_links_per_host": 2,
    "max_anchor_words": 4,
    "paragraph_window": 3,
}
