"""Facade for core settings helpers.

Refactored on 2026-05-10: implementation split into 4 modules to stay
under the 1500-line cap:
1. settings_base.py (Layer 1-3 readers/coercers)
2. settings_defaults.py (DEFAULT_* dicts)
3. settings_validators.py (Internal readers and PUT validators)
4. settings_accessors.py (Public get_* accessors)
"""

from __future__ import annotations

# Re-export Layer 1-3 readers and coercers
from apps.core.services.settings_base import (
    _coerce_bool_strict,
    _coerce_float_strict,
    _coerce_int_strict,
    _get_app_setting_value,
    _read_operator,
    coerce_clamp_float,
    coerce_clamp_int,
    coerce_lenient_bool,
    coerce_setting_bool,
    coerce_setting_float,
    coerce_setting_int,
    enforce_bounds,
    read_app_setting_bool,
    read_app_setting_float,
    read_app_setting_int,
    setting_bool,
    setting_float,
    setting_int,
    setting_str,
)

# Re-export DEFAULT dicts
from apps.core.services.settings_defaults import (
    DEFAULT_CLICK_DISTANCE_SETTINGS,
    DEFAULT_CLUSTERING_SETTINGS,
    DEFAULT_FEEDBACK_RERANK_SETTINGS,
    DEFAULT_FIELD_AWARE_RELEVANCE_SETTINGS,
    DEFAULT_GA4_GSC_SETTINGS,
    DEFAULT_GRAPH_CANDIDATE_SETTINGS,
    DEFAULT_LEARNED_ANCHOR_SETTINGS,
    DEFAULT_LINK_FRESHNESS_SETTINGS,
    DEFAULT_PHRASE_MATCHING_SETTINGS,
    DEFAULT_RARE_TERM_PROPAGATION_SETTINGS,
    DEFAULT_SILO_SETTINGS,
    DEFAULT_SLATE_DIVERSITY_SETTINGS,
    DEFAULT_SPAM_GUARD_SETTINGS,
    DEFAULT_VALUE_MODEL_SETTINGS,
    DEFAULT_WEIGHTED_AUTHORITY_SETTINGS,
    DEFAULT_WORDPRESS_SETTINGS,
)

# Re-export Public Accessors
from apps.core.services.settings_accessors import (
    _sync_wordpress_periodic_task,
    get_click_distance_settings,
    get_clustering_settings,
    get_feedback_rerank_settings,
    get_field_aware_relevance_settings,
    get_ga4_gsc_settings,
    get_graph_candidate_settings,
    get_learned_anchor_settings,
    get_link_freshness_settings,
    get_phrase_matching_settings,
    get_rare_term_propagation_settings,
    get_silo_settings,
    get_slate_diversity_settings,
    get_spam_guard_settings,
    get_value_model_settings,
    get_weighted_authority_settings,
    get_wordpress_runtime_config,
    get_wordpress_settings,
)

# Re-export Validators (internal, but often used by views)
from apps.core.services.settings_validators import (
    _ga4_gsc_connection_status,
    _read_click_distance_settings,
    _read_clustering_settings,
    _read_feedback_rerank_settings,
    _read_field_aware_relevance_settings,
    _read_ga4_gsc_settings,
    _read_graph_candidate_settings,
    _read_learned_anchor_settings,
    _read_link_freshness_settings,
    _read_phrase_matching_settings,
    _read_rare_term_propagation_settings,
    _read_slate_diversity_settings,
    _read_value_model_settings,
    _read_weighted_authority_settings,
    _read_wp_string,
    _resolve_wp_app_password,
    _validate_click_distance_settings,
    _validate_clustering_settings,
    _validate_feedback_rerank_settings,
    _validate_field_aware_relevance_settings,
    _validate_ga4_gsc_consistency,
    _validate_ga4_gsc_settings,
    _validate_graph_candidate_settings,
    _validate_learned_anchor_settings,
    _validate_link_freshness_settings,
    _validate_phrase_matching_settings,
    _validate_rare_term_propagation_settings,
    _validate_silo_settings,
    _validate_spam_guard_settings,
    _validate_value_model_settings,
    _validate_weighted_authority_settings,
    _validate_wordpress_settings,
    _validate_wp_credentials_consistency,
    _vm_read_bool,
    _vm_read_float,
    _vm_read_int,
    _vm_settings_co_occurrence,
    _vm_settings_core,
    _vm_settings_engagement,
    _vm_settings_hot_decay,
)
