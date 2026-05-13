"""Internal settings readers and PUT-payload validators.

Split from settings_helpers.py on 2026-05-10.
This module houses the _read_* and _validate_* functions.
"""

from __future__ import annotations

import math
from urllib.parse import urlparse

from apps.api.query_params import coerce_bool
from apps.core.services.settings_base import (
    _coerce_bool_strict,
    _coerce_float_strict,
    _coerce_int_strict,
    _get_app_setting_value,
    _read_operator,
    coerce_lenient_bool,
    coerce_clamp_float,
    coerce_clamp_int,
    coerce_setting_bool,
    coerce_setting_float,
    coerce_setting_int,
    enforce_bounds,
    read_app_setting_bool,
    read_app_setting_float,
    read_app_setting_int,
)
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
    DEFAULT_SLATE_DIVERSITY_SETTINGS,
    DEFAULT_VALUE_MODEL_SETTINGS,
    DEFAULT_WEIGHTED_AUTHORITY_SETTINGS,
)

# ── Silo ──────────────────────────────────────────────────────────

def _validate_silo_settings(payload: dict) -> dict[str, float | str]:
    from apps.core.services.settings_defaults import DEFAULT_SILO_SETTINGS
    mode = payload.get("mode", DEFAULT_SILO_SETTINGS["mode"])
    if mode not in {"disabled", "prefer_same_silo", "strict_same_silo"}:
        raise ValueError("mode must be one of disabled, prefer_same_silo, strict_same_silo.")
    same_silo_boost = coerce_setting_float(payload, DEFAULT_SILO_SETTINGS, "same_silo_boost", require_finite=False)
    cross_silo_penalty = coerce_setting_float(payload, DEFAULT_SILO_SETTINGS, "cross_silo_penalty", require_finite=False)
    if same_silo_boost < 0: raise ValueError("same_silo_boost must be >= 0.")
    if cross_silo_penalty < 0: raise ValueError("cross_silo_penalty must be >= 0.")
    return {"mode": mode, "same_silo_boost": same_silo_boost, "cross_silo_penalty": cross_silo_penalty}

# ── Weighted Authority ─────────────────────────────────────────────

_WEIGHTED_AUTHORITY_KEYS = ("ranking_weight", "position_bias", "empty_anchor_factor", "bare_url_factor", "weak_context_factor", "isolated_context_factor")
_WEIGHTED_AUTHORITY_BOUNDS = {
    "ranking_weight": (0.0, 0.25), "position_bias": (0.0, 1.0), "empty_anchor_factor": (0.1, 1.0),
    "bare_url_factor": (0.1, 1.0), "weak_context_factor": (0.1, 1.0), "isolated_context_factor": (0.1, 1.0)
}

def _read_weighted_authority_settings() -> dict[str, float]:
    return {key: read_app_setting_float(f"weighted_authority.{key}", DEFAULT_WEIGHTED_AUTHORITY_SETTINGS[key]) for key in _WEIGHTED_AUTHORITY_KEYS}

def _validate_weighted_authority_settings(payload: dict, *, current: dict[str, float] | None = None) -> dict[str, float]:
    current = current or _read_weighted_authority_settings()
    validated = {key: coerce_setting_float(payload, current, key) for key in _WEIGHTED_AUTHORITY_BOUNDS}
    enforce_bounds(validated, _WEIGHTED_AUTHORITY_BOUNDS)
    if validated["isolated_context_factor"] > validated["weak_context_factor"]:
        raise ValueError("isolated_context_factor must be <= weak_context_factor.")
    return validated

# ── Link Freshness ────────────────────────────────────────────────

_LINK_FRESHNESS_BOUNDS = {
    "ranking_weight": (0.0, 0.15), "recent_window_days": (7, 90), "newest_peer_percent": (0.10, 0.50),
    "min_peer_count": (1, 20), "w_recent": (0.0, 1.0), "w_growth": (0.0, 1.0), "w_cohort": (0.0, 1.0), "w_loss": (0.0, 1.0)
}
_LINK_FRESHNESS_FLOAT_KEYS = ("ranking_weight", "newest_peer_percent", "w_recent", "w_growth", "w_cohort", "w_loss")
_LINK_FRESHNESS_INT_KEYS = ("recent_window_days", "min_peer_count")

def _read_link_freshness_settings() -> dict[str, float | int]:
    out = {key: read_app_setting_float(f"link_freshness.{key}", DEFAULT_LINK_FRESHNESS_SETTINGS[key]) for key in _LINK_FRESHNESS_FLOAT_KEYS}
    for key in _LINK_FRESHNESS_INT_KEYS:
        out[key] = read_app_setting_int(f"link_freshness.{key}", DEFAULT_LINK_FRESHNESS_SETTINGS[key])
    return out

def _validate_link_freshness_settings(payload: dict, *, current: dict[str, float | int] | None = None) -> dict[str, float | int]:
    current = current or _read_link_freshness_settings()
    validated = {key: coerce_setting_float(payload, current, key) for key in _LINK_FRESHNESS_FLOAT_KEYS}
    for key in _LINK_FRESHNESS_INT_KEYS: validated[key] = coerce_setting_int(payload, current, key)
    enforce_bounds(validated, _LINK_FRESHNESS_BOUNDS)
    weight_total = sum(float(validated[k]) for k in ("w_recent", "w_growth", "w_cohort", "w_loss"))
    if not math.isclose(weight_total, 1.0, abs_tol=1e-6):
        raise ValueError("w_recent + w_growth + w_cohort + w_loss must equal 1.0.")
    return validated

# ── Phrase Matching ───────────────────────────────────────────────

_PHRASE_MATCHING_BOUNDS = {"ranking_weight": (0.0, 0.10), "context_window_tokens": (4, 12)}

def _read_phrase_matching_settings() -> dict[str, float | int | bool]:
    return {
        "ranking_weight": read_app_setting_float("phrase_matching.ranking_weight", DEFAULT_PHRASE_MATCHING_SETTINGS["ranking_weight"]),
        "enable_anchor_expansion": read_app_setting_bool("phrase_matching.enable_anchor_expansion", DEFAULT_PHRASE_MATCHING_SETTINGS["enable_anchor_expansion"]),
        "enable_partial_matching": read_app_setting_bool("phrase_matching.enable_partial_matching", DEFAULT_PHRASE_MATCHING_SETTINGS["enable_partial_matching"]),
        "context_window_tokens": read_app_setting_int("phrase_matching.context_window_tokens", DEFAULT_PHRASE_MATCHING_SETTINGS["context_window_tokens"]),
    }

def _validate_phrase_matching_settings(payload: dict, *, current: dict[str, float | int | bool] | None = None) -> dict[str, float | int | bool]:
    current = current or _read_phrase_matching_settings()
    validated = {
        "ranking_weight": coerce_setting_float(payload, current, "ranking_weight"),
        "enable_anchor_expansion": coerce_setting_bool(payload, current, "enable_anchor_expansion"),
        "enable_partial_matching": coerce_setting_bool(payload, current, "enable_partial_matching"),
        "context_window_tokens": coerce_setting_int(payload, current, "context_window_tokens"),
    }
    enforce_bounds(validated, _PHRASE_MATCHING_BOUNDS)
    return validated

# ── Click Distance ───────────────────────────────────────────────

def _read_click_distance_settings() -> dict[str, float]:
    return {key: read_app_setting_float(f"click_distance.{key}", DEFAULT_CLICK_DISTANCE_SETTINGS[key]) for key in ("ranking_weight", "k_cd", "b_cd", "b_ud")}

def _validate_click_distance_settings(payload: dict, current: dict) -> dict[str, float]:
    ranking_weight = max(0.0, min(0.10, coerce_clamp_float(payload, current, "ranking_weight", 0.0, 0.10)))
    k_cd = max(0.5, min(12.0, coerce_clamp_float(payload, current, "k_cd", 0.5, 12.0)))
    b_cd = max(0.0, min(1.0, coerce_clamp_float(payload, current, "b_cd", 0.0, 1.0)))
    b_ud = max(0.0, min(1.0, coerce_clamp_float(payload, current, "b_ud", 0.0, 1.0)))
    if b_cd + b_ud <= 0:
        b_cd, b_ud = DEFAULT_CLICK_DISTANCE_SETTINGS["b_cd"], DEFAULT_CLICK_DISTANCE_SETTINGS["b_ud"]
    return {"ranking_weight": ranking_weight, "k_cd": k_cd, "b_cd": b_cd, "b_ud": b_ud}

# ── Learned Anchor ────────────────────────────────────────────────

_LEARNED_ANCHOR_BOUNDS = {"ranking_weight": (0.0, 0.10), "minimum_anchor_sources": (1, 10), "minimum_family_support_share": (0.05, 0.50)}

def _read_learned_anchor_settings() -> dict[str, float | int | bool]:
    return {
        "ranking_weight": read_app_setting_float("learned_anchor.ranking_weight", DEFAULT_LEARNED_ANCHOR_SETTINGS["ranking_weight"]),
        "minimum_anchor_sources": read_app_setting_int("learned_anchor.minimum_anchor_sources", DEFAULT_LEARNED_ANCHOR_SETTINGS["minimum_anchor_sources"]),
        "minimum_family_support_share": read_app_setting_float("learned_anchor.minimum_family_support_share", DEFAULT_LEARNED_ANCHOR_SETTINGS["minimum_family_support_share"]),
        "enable_noise_filter": read_app_setting_bool("learned_anchor.enable_noise_filter", DEFAULT_LEARNED_ANCHOR_SETTINGS["enable_noise_filter"]),
    }

def _validate_learned_anchor_settings(payload: dict, *, current: dict[str, float | int | bool] | None = None) -> dict[str, float | int | bool]:
    current = current or _read_learned_anchor_settings()
    validated = {
        "ranking_weight": coerce_setting_float(payload, current, "ranking_weight"),
        "minimum_anchor_sources": coerce_setting_int(payload, current, "minimum_anchor_sources"),
        "minimum_family_support_share": coerce_setting_float(payload, current, "minimum_family_support_share"),
        "enable_noise_filter": coerce_setting_bool(payload, current, "enable_noise_filter"),
    }
    enforce_bounds(validated, _LEARNED_ANCHOR_BOUNDS)
    return validated

# ── Rare Term Propagation ─────────────────────────────────────────

_RARE_TERM_PROPAGATION_BOUNDS = {"ranking_weight": (0.0, 0.10), "max_document_frequency": (1, 10), "minimum_supporting_related_pages": (1, 5)}

def _read_rare_term_propagation_settings() -> dict[str, float | int | bool]:
    return {
        "enabled": read_app_setting_bool("rare_term_propagation.enabled", DEFAULT_RARE_TERM_PROPAGATION_SETTINGS["enabled"]),
        "ranking_weight": read_app_setting_float("rare_term_propagation.ranking_weight", DEFAULT_RARE_TERM_PROPAGATION_SETTINGS["ranking_weight"]),
        "max_document_frequency": read_app_setting_int("rare_term_propagation.max_document_frequency", DEFAULT_RARE_TERM_PROPAGATION_SETTINGS["max_document_frequency"]),
        "minimum_supporting_related_pages": read_app_setting_int("rare_term_propagation.minimum_supporting_related_pages", DEFAULT_RARE_TERM_PROPAGATION_SETTINGS["minimum_supporting_related_pages"]),
    }

def _validate_rare_term_propagation_settings(payload: dict, *, current: dict[str, float | int | bool] | None = None) -> dict[str, float | int | bool]:
    current = current or _read_rare_term_propagation_settings()
    validated = {
        "enabled": coerce_setting_bool(payload, current, "enabled"),
        "ranking_weight": coerce_setting_float(payload, current, "ranking_weight"),
        "max_document_frequency": coerce_setting_int(payload, current, "max_document_frequency"),
        "minimum_supporting_related_pages": coerce_setting_int(payload, current, "minimum_supporting_related_pages"),
    }
    enforce_bounds(validated, _RARE_TERM_PROPAGATION_BOUNDS)
    return validated

# ── Field-Aware Relevance ─────────────────────────────────────────

_FIELD_AWARE_RELEVANCE_KEYS = (
    "ranking_weight",
    "title_field_weight",
    "heading_field_weight",
    "intro_field_weight",
    "body_field_weight",
    "scope_field_weight",
    "learned_anchor_field_weight",
)
_FIELD_AWARE_RELEVANCE_WEIGHT_KEYS = _FIELD_AWARE_RELEVANCE_KEYS[1:]
_FIELD_AWARE_RELEVANCE_BOUNDS = {
    "ranking_weight": (0.0, 0.15),
    "title_field_weight": (0.0, 1.0),
    "heading_field_weight": (0.0, 1.0),
    "intro_field_weight": (0.0, 1.0),
    "body_field_weight": (0.0, 1.0),
    "scope_field_weight": (0.0, 1.0),
    "learned_anchor_field_weight": (0.0, 1.0),
}

def _read_field_aware_relevance_settings() -> dict[str, float]:
    return {key: read_app_setting_float(f"field_aware_relevance.{key}", DEFAULT_FIELD_AWARE_RELEVANCE_SETTINGS[key]) for key in _FIELD_AWARE_RELEVANCE_KEYS}

def _validate_field_aware_relevance_settings(payload: dict, *, current: dict[str, float] | None = None) -> dict[str, float]:
    current = current or _read_field_aware_relevance_settings()
    validated = {key: coerce_setting_float(payload, current, key) for key in _FIELD_AWARE_RELEVANCE_KEYS}
    enforce_bounds(validated, _FIELD_AWARE_RELEVANCE_BOUNDS)
    if not math.isclose(
        sum(validated[k] for k in _FIELD_AWARE_RELEVANCE_WEIGHT_KEYS),
        1.0,
        abs_tol=1e-6,
    ):
        raise ValueError(
            "title/heading/intro/body/scope/learned-anchor field weights must sum to 1.0."
        )
    return validated

# ── Clustering ────────────────────────────────────────────────────

def _read_clustering_settings() -> dict[str, float | bool]:
    return {
        "enabled": read_app_setting_bool("clustering.enabled", DEFAULT_CLUSTERING_SETTINGS["enabled"]),
        "similarity_threshold": read_app_setting_float("clustering.similarity_threshold", DEFAULT_CLUSTERING_SETTINGS["similarity_threshold"]),
        "suppression_penalty": read_app_setting_float("clustering.suppression_penalty", DEFAULT_CLUSTERING_SETTINGS["suppression_penalty"]),
    }

def _validate_clustering_settings(payload: dict, current: dict) -> dict[str, float | bool]:
    enabled = bool(payload.get("enabled", current.get("enabled")))
    similarity_threshold = max(0.01, min(0.20, coerce_clamp_float(payload, current, "similarity_threshold", 0.01, 0.20)))
    suppression_penalty = max(0.0, min(100.0, coerce_clamp_float(payload, current, "suppression_penalty", 0.0, 100.0)))
    return {"enabled": enabled, "similarity_threshold": similarity_threshold, "suppression_penalty": suppression_penalty}

# ── Feedback Rerank ───────────────────────────────────────────────

def _read_feedback_rerank_settings() -> dict[str, float | bool]:
    return {
        "enabled": read_app_setting_bool("explore_exploit.enabled", DEFAULT_FEEDBACK_RERANK_SETTINGS["enabled"]),
        "ranking_weight": read_app_setting_float("explore_exploit.ranking_weight", DEFAULT_FEEDBACK_RERANK_SETTINGS["ranking_weight"]),
        "exploration_rate": read_app_setting_float("explore_exploit.exploration_rate", DEFAULT_FEEDBACK_RERANK_SETTINGS["exploration_rate"]),
    }

def _validate_feedback_rerank_settings(payload: dict, *, current: dict[str, float | bool] | None = None) -> dict[str, float | bool]:
    current = current or _read_feedback_rerank_settings()
    validated = {
        "enabled": coerce_setting_bool(payload, current, "enabled"),
        "ranking_weight": coerce_setting_float(payload, current, "ranking_weight"),
        "exploration_rate": coerce_setting_float(payload, current, "exploration_rate"),
    }
    enforce_bounds(validated, {"ranking_weight": (0.0, 0.5), "exploration_rate": (0.1, 2.0)})
    return validated

# ── Slate Diversity ───────────────────────────────────────────────

def _read_slate_diversity_settings() -> dict:
    return {
        "enabled": read_app_setting_bool("slate_diversity.enabled", DEFAULT_SLATE_DIVERSITY_SETTINGS["enabled"]),
        "diversity_lambda": read_app_setting_float("slate_diversity.diversity_lambda", DEFAULT_SLATE_DIVERSITY_SETTINGS["diversity_lambda"]),
        "score_window": read_app_setting_float("slate_diversity.score_window", DEFAULT_SLATE_DIVERSITY_SETTINGS["score_window"]),
        "similarity_cap": read_app_setting_float("slate_diversity.similarity_cap", DEFAULT_SLATE_DIVERSITY_SETTINGS["similarity_cap"]),
        "algorithm_version": DEFAULT_SLATE_DIVERSITY_SETTINGS["algorithm_version"],
    }

# ── GA4 / GSC ─────────────────────────────────────────────────────

def _ga4_gsc_connection_status(property_url: str, email: str, private_key_configured: bool) -> tuple[str, str]:
    """Phase 2.18 — centralized connection-status logic for the UI."""
    if property_url and email and private_key_configured:
        return "saved", "Search Console credentials are saved. Run Test Connection to confirm access."
    return "not_configured", "Fill in the Search Console property URL and service-account credentials."


def _read_ga4_gsc_settings() -> dict[str, object]:
    property_url = (_get_app_setting_value("ga4_gsc.property_url", "") or "").strip().rstrip("/")
    service_account_email = (_get_app_setting_value("ga4_gsc.service_account_email", "") or "").strip()
    private_key_configured = bool(_get_app_setting_value("ga4_gsc.private_key", ""))

    status, msg = _ga4_gsc_connection_status(property_url, service_account_email, private_key_configured)

    return {
        "ranking_weight": read_app_setting_float("ga4_gsc.ranking_weight", DEFAULT_GA4_GSC_SETTINGS["ranking_weight"]),
        "property_url": property_url,
        "service_account_email": service_account_email,
        "private_key_configured": private_key_configured,
        "sync_enabled": read_app_setting_bool("ga4_gsc.sync_enabled", DEFAULT_GA4_GSC_SETTINGS["sync_enabled"]),
        "sync_lookback_days": read_app_setting_int("ga4_gsc.sync_lookback_days", DEFAULT_GA4_GSC_SETTINGS["sync_lookback_days"]),
        "connection_status": status,
        "connection_message": msg,
    }


def _validate_ga4_gsc_consistency(validated: dict) -> None:
    """Raise ValueError if the combination of GA4/GSC settings is invalid."""
    if validated["sync_enabled"] and (not validated["property_url"] or not validated["service_account_email"]):
        raise ValueError("Search Console sync needs property_url and service_account_email.")

def _validate_ga4_gsc_settings(payload: dict, *, current: dict[str, object] | None = None) -> dict[str, object]:
    current = current or _read_ga4_gsc_settings()
    validated = {
        "ranking_weight": _coerce_float_strict(payload.get("ranking_weight", current["ranking_weight"]), key="ranking_weight"),
        "property_url": str(payload.get("property_url", current["property_url"])).strip().rstrip("/"),
        "service_account_email": str(payload.get("service_account_email", current["service_account_email"])).strip(),
        "sync_enabled": _coerce_bool_strict(payload.get("sync_enabled", current["sync_enabled"]), key="sync_enabled"),
        "sync_lookback_days": _coerce_int_strict(payload.get("sync_lookback_days", current["sync_lookback_days"]), key="sync_lookback_days", minimum=1, maximum=30),
    }
    if validated["ranking_weight"] < 0.0 or validated["ranking_weight"] > 1.0: raise ValueError("ranking_weight must be between 0.0 and 1.0.")
    if validated["property_url"]:
        parsed = urlparse(validated["property_url"])
        if parsed.scheme not in {"http", "https"} or not parsed.netloc: raise ValueError("property_url must be a valid http(s) URL.")
    if validated["service_account_email"] and "@" not in validated["service_account_email"]: raise ValueError("service_account_email must look like an email address.")
    
    private_key_provided = "private_key" in payload
    private_key = str(payload.get("private_key", "")).strip() if private_key_provided else None
    has_private_key = bool(current.get("private_key_configured")) or bool(private_key)
    
    if validated["sync_enabled"] and (not validated["property_url"] or not validated["service_account_email"] or not has_private_key):
        raise ValueError("Search Console sync needs property_url, service_account_email, and private_key.")
    
    validated["private_key"] = private_key
    validated["private_key_provided"] = private_key_provided
    return validated

# ── Graph Candidate ────────────────────────────────────────────────

_GRAPH_CANDIDATE_INT_BOUNDS = {"walk_steps_per_entity": (10, 10000), "min_stable_candidates": (5, 500), "min_visit_threshold": (1, 20), "top_k_candidates": (10, 1000), "top_n_entities_per_article": (1, 100)}

def _read_graph_candidate_settings() -> dict[str, float | int | bool]:
    out = {"enabled": read_app_setting_bool("graph_candidate.enabled", DEFAULT_GRAPH_CANDIDATE_SETTINGS["enabled"])}
    for key in _GRAPH_CANDIDATE_INT_BOUNDS:
        out[key] = read_app_setting_int(f"graph_candidate.{key}", DEFAULT_GRAPH_CANDIDATE_SETTINGS[key])
    return out

def _validate_graph_candidate_settings(payload: dict, current: dict) -> dict:
    out = {"enabled": coerce_lenient_bool(payload, current, "enabled")}
    for key, (lo, hi) in _GRAPH_CANDIDATE_INT_BOUNDS.items():
        out[key] = coerce_clamp_int(payload, current, key, lo, hi)
    return out

# ── Value Model ───────────────────────────────────────────────────

def _vm_read_bool(key: str, default: bool) -> bool: return read_app_setting_bool(f"value_model.{key}", default)
def _vm_read_float(key: str, default: float) -> float: return read_app_setting_float(f"value_model.{key}", default)
def _vm_read_int(key: str, default: int) -> int: return read_app_setting_int(f"value_model.{key}", default)


_vm_settings_core = ("enabled", "w_relevance", "w_traffic", "w_freshness", "w_authority", "w_penalty", "traffic_lookback_days", "traffic_fallback_value")
_vm_settings_engagement = ("engagement_signal_enabled", "w_engagement", "engagement_lookback_days", "engagement_words_per_minute", "engagement_cap_ratio", "engagement_fallback_value")
_vm_settings_hot_decay = ("hot_decay_enabled", "hot_gravity", "hot_clicks_weight", "hot_impressions_weight", "hot_lookback_days")
_vm_settings_co_occurrence = ("co_occurrence_signal_enabled", "w_cooccurrence", "co_occurrence_fallback_value", "co_occurrence_min_co_sessions")


def _read_value_model_settings() -> dict[str, float | int | bool]:
    d = DEFAULT_VALUE_MODEL_SETTINGS
    
    return {
        "enabled": _vm_read_bool("enabled", d["enabled"]),
        "w_relevance": _vm_read_float("w_relevance", d["w_relevance"]),
        "w_traffic": _vm_read_float("w_traffic", d["w_traffic"]),
        "w_freshness": _vm_read_float("w_freshness", d["w_freshness"]),
        "w_authority": _vm_read_float("w_authority", d["w_authority"]),
        "w_penalty": _vm_read_float("w_penalty", d["w_penalty"]),
        "traffic_lookback_days": _vm_read_int("traffic_lookback_days", d["traffic_lookback_days"]),
        "traffic_fallback_value": _vm_read_float("traffic_fallback_value", d["traffic_fallback_value"]),
        "engagement_signal_enabled": _vm_read_bool("engagement_signal_enabled", d["engagement_signal_enabled"]),
        "w_engagement": _vm_read_float("w_engagement", d["w_engagement"]),
        "engagement_lookback_days": _vm_read_int("engagement_lookback_days", d["engagement_lookback_days"]),
        "engagement_words_per_minute": _vm_read_int("engagement_words_per_minute", d["engagement_words_per_minute"]),
        "engagement_cap_ratio": _vm_read_float("engagement_cap_ratio", d["engagement_cap_ratio"]),
        "engagement_fallback_value": _vm_read_float("engagement_fallback_value", d["engagement_fallback_value"]),
        "hot_decay_enabled": _vm_read_bool("hot_decay_enabled", d["hot_decay_enabled"]),
        "hot_gravity": _vm_read_float("hot_gravity", d["hot_gravity"]),
        "hot_clicks_weight": _vm_read_float("hot_clicks_weight", d["hot_clicks_weight"]),
        "hot_impressions_weight": _vm_read_float("hot_impressions_weight", d["hot_impressions_weight"]),
        "hot_lookback_days": _vm_read_int("hot_lookback_days", d["hot_lookback_days"]),
        "co_occurrence_signal_enabled": _vm_read_bool("co_occurrence_signal_enabled", d["co_occurrence_signal_enabled"]),
        "w_cooccurrence": _vm_read_float("w_cooccurrence", d["w_cooccurrence"]),
        "co_occurrence_fallback_value": _vm_read_float("co_occurrence_fallback_value", d["co_occurrence_fallback_value"]),
        "co_occurrence_min_co_sessions": _vm_read_int("co_occurrence_min_co_sessions", d["co_occurrence_min_co_sessions"]),
    }

_VALUE_MODEL_FLOAT_BOUNDS = {"w_relevance": (0.0, 1.0), "w_traffic": (0.0, 1.0), "w_freshness": (0.0, 1.0), "w_authority": (0.0, 1.0), "w_penalty": (0.0, 1.0), "traffic_fallback_value": (0.0, 1.0), "w_engagement": (0.0, 1.0), "engagement_cap_ratio": (1.0, 5.0), "engagement_fallback_value": (0.0, 1.0), "hot_gravity": (0.001, 0.5), "hot_clicks_weight": (0.0, 5.0), "hot_impressions_weight": (0.0, 5.0), "w_cooccurrence": (0.0, 1.0), "co_occurrence_fallback_value": (0.0, 1.0)}
_VALUE_MODEL_INT_BOUNDS = {"traffic_lookback_days": (1, 365), "engagement_lookback_days": (1, 365), "engagement_words_per_minute": (50, 600), "hot_lookback_days": (7, 365), "co_occurrence_min_co_sessions": (1, 100)}
_VALUE_MODEL_BOOL_KEYS = ("enabled", "engagement_signal_enabled", "hot_decay_enabled", "co_occurrence_signal_enabled")

def _validate_value_model_settings(payload: dict, current: dict) -> dict:
    validated = {key: coerce_lenient_bool(payload, current, key) for key in _VALUE_MODEL_BOOL_KEYS}
    for key, (lo, hi) in _VALUE_MODEL_FLOAT_BOUNDS.items(): validated[key] = coerce_clamp_float(payload, current, key, lo, hi)
    for key, (lo_i, hi_i) in _VALUE_MODEL_INT_BOUNDS.items(): validated[key] = coerce_clamp_int(payload, current, key, lo_i, hi_i)
    return validated

# ── WordPress ─────────────────────────────────────────────────────

def _read_wp_string(key: str, default: str) -> str:
    """Read a WordPress AppSetting string with trimming."""
    return (_get_app_setting_value(key, default) or "").strip()


def _resolve_wp_app_password(data: dict) -> str:
    """Resolve WordPress app-password: body > stored."""
    provided = (data.get("app_password") or "").strip()
    if provided:
        return provided
    return (_get_app_setting_value("wordpress.app_password", "") or "").strip()


def _validate_wp_credentials_consistency(username: str, has_password: bool) -> None:
    """Raise ValueError if username/password are partially set."""
    if username and not has_password:
        raise ValueError("Application Password is required when a WordPress username is configured.")
    if has_password and not username:
        raise ValueError("username is required when an Application Password is configured.")


def _validate_wordpress_settings(payload: dict) -> dict[str, object]:
    from apps.core.services.settings_accessors import get_wordpress_settings
    current = get_wordpress_settings()
    base_url = str(payload.get("base_url", current["base_url"])).strip().rstrip("/")
    username = str(payload.get("username", current["username"])).strip()
    if base_url:
        parsed = urlparse(base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc: raise ValueError("base_url must be a valid http(s) URL.")
    
    app_password_provided = "app_password" in payload
    app_password = str(payload.get("app_password", "")).strip() if app_password_provided else None
    effective_has_password = bool(current["app_password_configured"])
    if app_password_provided: effective_has_password = bool(app_password)
    
    sync_enabled = coerce_bool(payload.get("sync_enabled"), default=bool(current["sync_enabled"]))
    validated_sync = {"sync_hour": coerce_setting_int(payload, current, "sync_hour"), "sync_minute": coerce_setting_int(payload, current, "sync_minute")}
    enforce_bounds(validated_sync, {"sync_hour": (0, 23), "sync_minute": (0, 59)})
    
    _validate_wp_credentials_consistency(username, effective_has_password)
    if sync_enabled and not base_url: raise ValueError("base_url is required when scheduled WordPress sync is enabled.")
    
    return {"base_url": base_url, "username": username, "app_password": app_password, "app_password_provided": app_password_provided, "app_password_configured": effective_has_password, "sync_enabled": sync_enabled, **validated_sync}

# ── Spam Guard ────────────────────────────────────────────────────

def _validate_spam_guard_settings(payload: dict, current: dict) -> dict[str, int]:
    from apps.core.services.settings_defaults import DEFAULT_SPAM_GUARD_SETTINGS
    def _get_int(key: str, lo: int, hi: int) -> int:
        val = payload.get(key, current.get(key))
        try: return max(lo, min(hi, int(val)))
        except (TypeError, ValueError): return current.get(key, DEFAULT_SPAM_GUARD_SETTINGS[key])
    return {k: _get_int(k, 1, 20 if k == "max_existing_links_per_host" else 10) for k in ("max_existing_links_per_host", "max_anchor_words", "paragraph_window")}
