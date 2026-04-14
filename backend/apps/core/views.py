"""
Core views — health check, appearance settings, dashboard, and site-asset endpoints.

GET    /api/health/             → {"status": "ok", "version": "2.0.0"}
GET    /api/settings/appearance/ → full appearance config JSON
PUT    /api/settings/appearance/ → merge-update appearance config, returns updated config
POST   /api/settings/logo/      → upload logo image, returns {"logo_url": "..."}
DELETE /api/settings/logo/      → remove logo, clears logoUrl in config
POST   /api/settings/favicon/   → upload favicon image, returns {"favicon_url": "..."}
DELETE /api/settings/favicon/   → remove favicon, clears faviconUrl in config
GET    /api/dashboard/           → aggregated stats for the dashboard
"""

import json
import logging
import math
import uuid
from urllib.parse import urlparse

from django.conf import settings as django_settings
from django.http import JsonResponse
from django.views import View
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

logger = logging.getLogger(__name__)

from apps.api.throttles import (
    GraphRebuildThrottle as _GraphRebuildThrottle,
    WeightRecalcThrottle as _WeightRecalcThrottle,
    ChallengerEvalThrottle as _ChallengerEvalThrottle,
)

from apps.suggestions.recommended_weights import (
    recommended_bool,
    recommended_float,
    recommended_int,
    recommended_str,
)


DEFAULT_APPEARANCE = {
    "primaryColor": "#1a73e8",
    "accentColor": "#f4b400",
    "fontSize": "medium",
    "layoutWidth": "standard",
    "sidebarWidth": "standard",
    "density": "comfortable",
    "headerBg": "#ffffff",
    "siteName": "XF Internal Linker",
    "showScrollToTop": True,
    "footerText": "XF Internal Linker V2",
    "showFooter": True,
    "footerBg": "#fafafa",
    "logoUrl": "",
    "faviconUrl": "",
    "presets": [],
}

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
    # FR-024 engagement signal
    "engagement_signal_enabled": recommended_bool(
        "value_model.engagement_signal_enabled"
    ),
    "w_engagement": recommended_float("value_model.w_engagement"),
    "engagement_lookback_days": recommended_int("value_model.engagement_lookback_days"),
    "engagement_words_per_minute": recommended_int(
        "value_model.engagement_words_per_minute"
    ),
    "engagement_cap_ratio": recommended_float("value_model.engagement_cap_ratio"),
    "engagement_fallback_value": recommended_float(
        "value_model.engagement_fallback_value"
    ),
    # FR-023 hot decay signal
    "hot_decay_enabled": recommended_bool("value_model.hot_decay_enabled"),
    "hot_gravity": recommended_float("value_model.hot_gravity"),
    "hot_clicks_weight": recommended_float("value_model.hot_clicks_weight"),
    "hot_impressions_weight": recommended_float("value_model.hot_impressions_weight"),
    "hot_lookback_days": recommended_int("value_model.hot_lookback_days"),
    # FR-025 co-occurrence signal
    "co_occurrence_signal_enabled": recommended_bool(
        "value_model.co_occurrence_signal_enabled"
    ),
    "w_cooccurrence": recommended_float("value_model.w_cooccurrence"),
    "co_occurrence_fallback_value": recommended_float(
        "value_model.co_occurrence_fallback_value"
    ),
    "co_occurrence_min_co_sessions": recommended_int(
        "value_model.co_occurrence_min_co_sessions"
    ),
}

# Allowed MIME types for site asset uploads
_LOGO_ALLOWED = frozenset({"image/png", "image/svg+xml", "image/webp", "image/jpeg"})
_FAVICON_ALLOWED = frozenset(
    {
        "image/png",
        "image/svg+xml",
        "image/x-icon",
        "image/vnd.microsoft.icon",
    }
)
_ASSET_MAX_BYTES = 2 * 1024 * 1024  # 2 MB


def _get_app_setting_value(key: str, default: str | None = None) -> str | None:
    from apps.core.models import AppSetting

    setting = AppSetting.objects.filter(key=key).first()
    if setting is None:
        return default
    return setting.value


def get_silo_settings() -> dict[str, float | str]:
    """Load persisted silo settings with defensive defaults."""
    mode = (
        _get_app_setting_value("silo.mode", DEFAULT_SILO_SETTINGS["mode"])
        or DEFAULT_SILO_SETTINGS["mode"]
    )
    if mode not in {"disabled", "prefer_same_silo", "strict_same_silo"}:
        mode = DEFAULT_SILO_SETTINGS["mode"]

    def _read_float(key: str, default: float) -> float:
        raw = _get_app_setting_value(key)
        try:
            return float(raw) if raw is not None else default
        except (TypeError, ValueError):
            return default

    return {
        "mode": mode,
        "same_silo_boost": _read_float(
            "silo.same_silo_boost", DEFAULT_SILO_SETTINGS["same_silo_boost"]
        ),
        "cross_silo_penalty": _read_float(
            "silo.cross_silo_penalty", DEFAULT_SILO_SETTINGS["cross_silo_penalty"]
        ),
    }


def _validate_silo_settings(payload: dict) -> dict[str, float | str]:
    mode = payload.get("mode", DEFAULT_SILO_SETTINGS["mode"])
    if mode not in {"disabled", "prefer_same_silo", "strict_same_silo"}:
        raise ValueError(
            "mode must be one of disabled, prefer_same_silo, strict_same_silo."
        )

    def _coerce_float(key: str) -> float:
        value = payload.get(key, DEFAULT_SILO_SETTINGS[key])
        try:
            return float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{key} must be numeric.") from exc

    same_silo_boost = _coerce_float("same_silo_boost")
    cross_silo_penalty = _coerce_float("cross_silo_penalty")
    if same_silo_boost < 0:
        raise ValueError("same_silo_boost must be >= 0.")
    if cross_silo_penalty < 0:
        raise ValueError("cross_silo_penalty must be >= 0.")

    return {
        "mode": mode,
        "same_silo_boost": same_silo_boost,
        "cross_silo_penalty": cross_silo_penalty,
    }


def get_wordpress_settings() -> dict[str, object]:
    """Load persisted WordPress sync settings with environment fallbacks."""
    base_url = (
        (
            _get_app_setting_value(
                "wordpress.base_url", django_settings.WORDPRESS_BASE_URL
            )
            or ""
        )
        .strip()
        .rstrip("/")
    )
    username = (
        _get_app_setting_value("wordpress.username", django_settings.WORDPRESS_USERNAME)
        or ""
    ).strip()
    app_password = (
        _get_app_setting_value(
            "wordpress.app_password", django_settings.WORDPRESS_APP_PASSWORD
        )
        or ""
    )

    def _read_int(key: str, default: int) -> int:
        raw = _get_app_setting_value(key)
        try:
            return int(raw) if raw is not None else default
        except (TypeError, ValueError):
            return default

    sync_enabled = (
        _get_app_setting_value("wordpress.sync_enabled") or ""
    ).strip().lower() in {"1", "true", "yes", "on"}

    from apps.health.services import get_service_health_status

    health = get_service_health_status("wordpress")

    return {
        "base_url": base_url,
        "username": username,
        "app_password_configured": bool(app_password.strip()),
        "sync_enabled": sync_enabled,
        "sync_hour": _read_int(
            "wordpress.sync_hour", DEFAULT_WORDPRESS_SETTINGS["sync_hour"]
        ),
        "sync_minute": _read_int(
            "wordpress.sync_minute", DEFAULT_WORDPRESS_SETTINGS["sync_minute"]
        ),
        "health": health,
    }


def get_wordpress_runtime_config() -> dict[str, str]:
    """Return WordPress connection settings including the stored secret."""
    return {
        "base_url": (
            _get_app_setting_value(
                "wordpress.base_url", django_settings.WORDPRESS_BASE_URL
            )
            or ""
        )
        .strip()
        .rstrip("/"),
        "username": (
            _get_app_setting_value(
                "wordpress.username", django_settings.WORDPRESS_USERNAME
            )
            or ""
        ).strip(),
        "app_password": (
            _get_app_setting_value(
                "wordpress.app_password", django_settings.WORDPRESS_APP_PASSWORD
            )
            or ""
        ).strip(),
    }


def get_weighted_authority_settings() -> dict[str, float]:
    """Load persisted weighted-authority settings with defensive defaults."""
    settings = _read_weighted_authority_settings()
    try:
        return _validate_weighted_authority_settings(
            settings,
            current=dict(DEFAULT_WEIGHTED_AUTHORITY_SETTINGS),
        )
    except ValueError:
        return dict(DEFAULT_WEIGHTED_AUTHORITY_SETTINGS)


def get_link_freshness_settings() -> dict[str, float | int]:
    """Load persisted link-freshness settings with defensive defaults."""
    settings = _read_link_freshness_settings()
    try:
        return _validate_link_freshness_settings(
            settings,
            current=dict(DEFAULT_LINK_FRESHNESS_SETTINGS),
        )
    except ValueError:
        return dict(DEFAULT_LINK_FRESHNESS_SETTINGS)


def get_phrase_matching_settings() -> dict[str, float | int | bool]:
    """Load persisted phrase-matching settings with defensive defaults."""
    settings = _read_phrase_matching_settings()
    try:
        return _validate_phrase_matching_settings(
            settings,
            current=dict(DEFAULT_PHRASE_MATCHING_SETTINGS),
        )
    except ValueError:
        return dict(DEFAULT_PHRASE_MATCHING_SETTINGS)


def get_learned_anchor_settings() -> dict[str, float | int | bool]:
    """Load persisted learned-anchor settings with defensive defaults."""
    settings = _read_learned_anchor_settings()
    try:
        return _validate_learned_anchor_settings(
            settings,
            current=dict(DEFAULT_LEARNED_ANCHOR_SETTINGS),
        )
    except ValueError:
        return dict(DEFAULT_LEARNED_ANCHOR_SETTINGS)


def get_rare_term_propagation_settings() -> dict[str, float | int | bool]:
    """Load persisted FR-010 rare-term settings with defensive defaults."""
    settings = _read_rare_term_propagation_settings()
    try:
        return _validate_rare_term_propagation_settings(
            settings,
            current=dict(DEFAULT_RARE_TERM_PROPAGATION_SETTINGS),
        )
    except ValueError:
        return dict(DEFAULT_RARE_TERM_PROPAGATION_SETTINGS)


def get_field_aware_relevance_settings() -> dict[str, float]:
    """Load persisted FR-011 field-aware settings with defensive defaults."""
    settings = _read_field_aware_relevance_settings()
    try:
        return _validate_field_aware_relevance_settings(
            settings,
            current=dict(DEFAULT_FIELD_AWARE_RELEVANCE_SETTINGS),
        )
    except ValueError:
        return dict(DEFAULT_FIELD_AWARE_RELEVANCE_SETTINGS)


def get_graph_candidate_settings() -> dict[str, float | int | bool]:
    """Load persisted FR-021 graph-walk settings with defensive defaults."""
    settings = _read_graph_candidate_settings()
    try:
        return _validate_graph_candidate_settings(
            settings,
            current=dict(DEFAULT_GRAPH_CANDIDATE_SETTINGS),
        )
    except Exception:
        return dict(DEFAULT_GRAPH_CANDIDATE_SETTINGS)


def get_value_model_settings() -> dict[str, float | int | bool]:
    """Load persisted FR-021 value-model settings with defensive defaults."""
    settings = _read_value_model_settings()
    try:
        return _validate_value_model_settings(
            settings,
            current=dict(DEFAULT_VALUE_MODEL_SETTINGS),
        )
    except Exception:
        return dict(DEFAULT_VALUE_MODEL_SETTINGS)


def get_ga4_gsc_settings() -> dict[str, object]:
    """Load persisted GA4/GSC settings with defensive defaults and health status."""
    settings = _read_ga4_gsc_settings()
    if not isinstance(settings.get("ranking_weight"), (float, int)):
        settings["ranking_weight"] = DEFAULT_GA4_GSC_SETTINGS["ranking_weight"]

    from apps.health.services import get_service_health_status

    settings["ga4_health"] = get_service_health_status("ga4")
    settings["gsc_health"] = get_service_health_status("gsc")

    return settings


def get_click_distance_settings() -> dict[str, float]:
    """Load persisted FR-012 click-distance settings with defensive defaults."""
    settings = _read_click_distance_settings()
    try:
        return _validate_click_distance_settings(
            settings,
            current=dict(DEFAULT_CLICK_DISTANCE_SETTINGS),
        )
    except ValueError:
        return dict(DEFAULT_CLICK_DISTANCE_SETTINGS)


def get_feedback_rerank_settings() -> dict[str, float | bool]:
    """Load persisted feedback-driven explore/exploit settings with defensive defaults."""
    settings = _read_feedback_rerank_settings()
    try:
        return _validate_feedback_rerank_settings(
            settings,
            current=dict(DEFAULT_FEEDBACK_RERANK_SETTINGS),
        )
    except ValueError:
        return dict(DEFAULT_FEEDBACK_RERANK_SETTINGS)


def get_clustering_settings() -> dict[str, float | bool]:
    """Load persisted FR-014 clustering settings with defensive defaults."""
    settings = _read_clustering_settings()
    try:
        return _validate_clustering_settings(
            settings,
            current=dict(DEFAULT_CLUSTERING_SETTINGS),
        )
    except Exception:
        return dict(DEFAULT_CLUSTERING_SETTINGS)


def _read_clustering_settings() -> dict[str, float | bool]:
    """Read near-duplicate clustering settings from AppSetting without applying bounds."""

    def _read_float(key: str, default: float) -> float:
        raw = _get_app_setting_value(key)
        try:
            value = float(raw) if raw is not None else default
        except (TypeError, ValueError):
            return default
        if not math.isfinite(value):
            return default
        return value

    def _read_bool(key: str, default: bool) -> bool:
        raw = _get_app_setting_value(key)
        if raw is None:
            return default
        if isinstance(raw, str):
            return raw.strip().lower() in {"1", "true", "yes", "on"}
        return bool(raw)

    return {
        "enabled": _read_bool(
            "clustering.enabled", DEFAULT_CLUSTERING_SETTINGS["enabled"]
        ),
        "similarity_threshold": _read_float(
            "clustering.similarity_threshold",
            DEFAULT_CLUSTERING_SETTINGS["similarity_threshold"],
        ),
        "suppression_penalty": _read_float(
            "clustering.suppression_penalty",
            DEFAULT_CLUSTERING_SETTINGS["suppression_penalty"],
        ),
    }


def _read_weighted_authority_settings() -> dict[str, float]:
    """Read weighted-authority settings from AppSetting without applying bounds."""

    def _read_float(key: str, default: float) -> float:
        raw = _get_app_setting_value(key)
        try:
            value = float(raw) if raw is not None else default
        except (TypeError, ValueError):
            return default
        if not math.isfinite(value):
            return default
        return value

    return {
        "ranking_weight": _read_float(
            "weighted_authority.ranking_weight",
            DEFAULT_WEIGHTED_AUTHORITY_SETTINGS["ranking_weight"],
        ),
        "position_bias": _read_float(
            "weighted_authority.position_bias",
            DEFAULT_WEIGHTED_AUTHORITY_SETTINGS["position_bias"],
        ),
        "empty_anchor_factor": _read_float(
            "weighted_authority.empty_anchor_factor",
            DEFAULT_WEIGHTED_AUTHORITY_SETTINGS["empty_anchor_factor"],
        ),
        "bare_url_factor": _read_float(
            "weighted_authority.bare_url_factor",
            DEFAULT_WEIGHTED_AUTHORITY_SETTINGS["bare_url_factor"],
        ),
        "weak_context_factor": _read_float(
            "weighted_authority.weak_context_factor",
            DEFAULT_WEIGHTED_AUTHORITY_SETTINGS["weak_context_factor"],
        ),
        "isolated_context_factor": _read_float(
            "weighted_authority.isolated_context_factor",
            DEFAULT_WEIGHTED_AUTHORITY_SETTINGS["isolated_context_factor"],
        ),
    }


def _read_link_freshness_settings() -> dict[str, float | int]:
    """Read link-freshness settings from AppSetting without applying bounds."""

    def _read_float(key: str, default: float) -> float:
        raw = _get_app_setting_value(key)
        try:
            value = float(raw) if raw is not None else default
        except (TypeError, ValueError):
            return default
        if not math.isfinite(value):
            return default
        return value

    def _read_int(key: str, default: int) -> int:
        raw = _get_app_setting_value(key)
        try:
            value = int(raw) if raw is not None else default
        except (TypeError, ValueError):
            return default
        return value

    return {
        "ranking_weight": _read_float(
            "link_freshness.ranking_weight",
            DEFAULT_LINK_FRESHNESS_SETTINGS["ranking_weight"],
        ),
        "recent_window_days": _read_int(
            "link_freshness.recent_window_days",
            DEFAULT_LINK_FRESHNESS_SETTINGS["recent_window_days"],
        ),
        "newest_peer_percent": _read_float(
            "link_freshness.newest_peer_percent",
            DEFAULT_LINK_FRESHNESS_SETTINGS["newest_peer_percent"],
        ),
        "min_peer_count": _read_int(
            "link_freshness.min_peer_count",
            DEFAULT_LINK_FRESHNESS_SETTINGS["min_peer_count"],
        ),
        "w_recent": _read_float(
            "link_freshness.w_recent", DEFAULT_LINK_FRESHNESS_SETTINGS["w_recent"]
        ),
        "w_growth": _read_float(
            "link_freshness.w_growth", DEFAULT_LINK_FRESHNESS_SETTINGS["w_growth"]
        ),
        "w_cohort": _read_float(
            "link_freshness.w_cohort", DEFAULT_LINK_FRESHNESS_SETTINGS["w_cohort"]
        ),
        "w_loss": _read_float(
            "link_freshness.w_loss", DEFAULT_LINK_FRESHNESS_SETTINGS["w_loss"]
        ),
    }


def _read_phrase_matching_settings() -> dict[str, float | int | bool]:
    """Read phrase-matching settings from AppSetting without applying bounds."""

    def _read_float(key: str, default: float) -> float:
        raw = _get_app_setting_value(key)
        try:
            value = float(raw) if raw is not None else default
        except (TypeError, ValueError):
            return default
        if not math.isfinite(value):
            return default
        return value

    def _read_int(key: str, default: int) -> int:
        raw = _get_app_setting_value(key)
        try:
            value = int(raw) if raw is not None else default
        except (TypeError, ValueError):
            return default
        return value

    def _read_bool(key: str, default: bool) -> bool:
        raw = _get_app_setting_value(key)
        if raw is None:
            return default
        return str(raw).strip().lower() in {"1", "true", "yes", "on"}

    return {
        "ranking_weight": _read_float(
            "phrase_matching.ranking_weight",
            DEFAULT_PHRASE_MATCHING_SETTINGS["ranking_weight"],
        ),
        "enable_anchor_expansion": _read_bool(
            "phrase_matching.enable_anchor_expansion",
            DEFAULT_PHRASE_MATCHING_SETTINGS["enable_anchor_expansion"],
        ),
        "enable_partial_matching": _read_bool(
            "phrase_matching.enable_partial_matching",
            DEFAULT_PHRASE_MATCHING_SETTINGS["enable_partial_matching"],
        ),
        "context_window_tokens": _read_int(
            "phrase_matching.context_window_tokens",
            DEFAULT_PHRASE_MATCHING_SETTINGS["context_window_tokens"],
        ),
    }


def _read_learned_anchor_settings() -> dict[str, float | int | bool]:
    """Read learned-anchor settings from AppSetting without applying bounds."""

    def _read_float(key: str, default: float) -> float:
        raw = _get_app_setting_value(key)
        try:
            value = float(raw) if raw is not None else default
        except (TypeError, ValueError):
            return default
        if not math.isfinite(value):
            return default
        return value


def _read_click_distance_settings() -> dict[str, float]:
    """Read click-distance settings from AppSetting without applying bounds."""

    def _read_float(key: str, default: float) -> float:
        raw = _get_app_setting_value(key)
        try:
            value = float(raw) if raw is not None else default
        except (TypeError, ValueError):
            return default
        if not math.isfinite(value):
            return default
        return value

    return {
        "ranking_weight": _read_float(
            "click_distance.ranking_weight",
            DEFAULT_CLICK_DISTANCE_SETTINGS["ranking_weight"],
        ),
        "k_cd": _read_float(
            "click_distance.k_cd", DEFAULT_CLICK_DISTANCE_SETTINGS["k_cd"]
        ),
        "b_cd": _read_float(
            "click_distance.b_cd", DEFAULT_CLICK_DISTANCE_SETTINGS["b_cd"]
        ),
        "b_ud": _read_float(
            "click_distance.b_ud", DEFAULT_CLICK_DISTANCE_SETTINGS["b_ud"]
        ),
    }


def _read_feedback_rerank_settings() -> dict[str, float | bool]:
    """Read feedback-driven explore/exploit settings from AppSetting without applying bounds."""

    def _read_float(key: str, default: float) -> float:
        raw = _get_app_setting_value(key)
        try:
            value = float(raw) if raw is not None else default
        except (TypeError, ValueError):
            return default
        if not math.isfinite(value):
            return default
        return value

    def _read_bool(key: str, default: bool) -> bool:
        raw = _get_app_setting_value(key)
        if raw is None:
            return default
        return raw.lower() == "true"

    return {
        "enabled": _read_bool(
            "explore_exploit.enabled", DEFAULT_FEEDBACK_RERANK_SETTINGS["enabled"]
        ),
        "ranking_weight": _read_float(
            "explore_exploit.ranking_weight",
            DEFAULT_FEEDBACK_RERANK_SETTINGS["ranking_weight"],
        ),
        "exploration_rate": _read_float(
            "explore_exploit.exploration_rate",
            DEFAULT_FEEDBACK_RERANK_SETTINGS["exploration_rate"],
        ),
    }


def _read_slate_diversity_settings() -> dict:
    """Read FR-015 slate diversity settings from AppSetting without applying bounds."""

    def _read_float(key: str, default: float) -> float:
        raw = _get_app_setting_value(key)
        try:
            value = float(raw) if raw is not None else default
        except (TypeError, ValueError):
            return default
        if not math.isfinite(value):
            return default
        return value

    def _read_bool(key: str, default: bool) -> bool:
        raw = _get_app_setting_value(key)
        if raw is None:
            return default
        return str(raw).strip().lower() in {"1", "true", "yes", "on"}

    return {
        "enabled": _read_bool(
            "slate_diversity.enabled", DEFAULT_SLATE_DIVERSITY_SETTINGS["enabled"]
        ),
        "diversity_lambda": _read_float(
            "slate_diversity.diversity_lambda",
            DEFAULT_SLATE_DIVERSITY_SETTINGS["diversity_lambda"],
        ),
        "score_window": _read_float(
            "slate_diversity.score_window",
            DEFAULT_SLATE_DIVERSITY_SETTINGS["score_window"],
        ),
        "similarity_cap": _read_float(
            "slate_diversity.similarity_cap",
            DEFAULT_SLATE_DIVERSITY_SETTINGS["similarity_cap"],
        ),
        "algorithm_version": DEFAULT_SLATE_DIVERSITY_SETTINGS["algorithm_version"],
    }


def get_slate_diversity_settings() -> dict:
    """Return current FR-015 slate diversity settings with defaults applied."""
    try:
        return _read_slate_diversity_settings()
    except Exception:
        return dict(DEFAULT_SLATE_DIVERSITY_SETTINGS)


def _validate_slate_diversity_settings(payload: dict, current: dict) -> dict:
    """Validate and clamp slate diversity settings."""

    def _get_float(key: str) -> float:
        val = payload.get(key, current.get(key))
        try:
            return float(val)
        except (TypeError, ValueError):
            return float(current.get(key, DEFAULT_SLATE_DIVERSITY_SETTINGS[key]))

    def _get_bool(key: str) -> bool:
        val = payload.get(key, current.get(key))
        if isinstance(val, bool):
            return val
        return str(val).strip().lower() in {"1", "true", "yes", "on"}

    return {
        "enabled": _get_bool("enabled"),
        "diversity_lambda": max(0.0, min(1.0, _get_float("diversity_lambda"))),
        "score_window": max(0.05, min(1.0, _get_float("score_window"))),
        "similarity_cap": max(0.70, min(0.99, _get_float("similarity_cap"))),
        "algorithm_version": DEFAULT_SLATE_DIVERSITY_SETTINGS["algorithm_version"],
    }


def _validate_click_distance_settings(payload: dict, current: dict) -> dict[str, float]:
    """Validate and clamp click-distance settings."""

    def _get_float(key: str) -> float:
        val = payload.get(key, current.get(key))
        try:
            return float(val)
        except (TypeError, ValueError):
            return float(current.get(key, 0.0))

    ranking_weight = max(0.0, min(0.10, _get_float("ranking_weight")))
    k_cd = max(0.5, min(12.0, _get_float("k_cd")))
    b_cd = max(0.0, min(1.0, _get_float("b_cd")))
    b_ud = max(0.0, min(1.0, _get_float("b_ud")))

    if b_cd + b_ud <= 0:
        b_cd = DEFAULT_CLICK_DISTANCE_SETTINGS["b_cd"]
        b_ud = DEFAULT_CLICK_DISTANCE_SETTINGS["b_ud"]

    return {
        "ranking_weight": ranking_weight,
        "k_cd": k_cd,
        "b_cd": b_cd,
        "b_ud": b_ud,
    }


def _read_learned_anchor_settings() -> dict[str, float | int | bool]:
    """Read learned-anchor settings from AppSetting without applying bounds."""

    def _read_float(key: str, default: float) -> float:
        raw = _get_app_setting_value(key)
        try:
            value = float(raw) if raw is not None else default
        except (TypeError, ValueError):
            return default
        if not math.isfinite(value):
            return default
        return value

    def _read_int(key: str, default: int) -> int:
        raw = _get_app_setting_value(key)
        try:
            value = int(raw) if raw is not None else default
        except (TypeError, ValueError):
            return default
        return value

    def _read_bool(key: str, default: bool) -> bool:
        raw = _get_app_setting_value(key)
        if raw is None:
            return default
        return str(raw).strip().lower() in {"1", "true", "yes", "on"}

    return {
        "ranking_weight": _read_float(
            "learned_anchor.ranking_weight",
            DEFAULT_LEARNED_ANCHOR_SETTINGS["ranking_weight"],
        ),
        "minimum_anchor_sources": _read_int(
            "learned_anchor.minimum_anchor_sources",
            DEFAULT_LEARNED_ANCHOR_SETTINGS["minimum_anchor_sources"],
        ),
        "minimum_family_support_share": _read_float(
            "learned_anchor.minimum_family_support_share",
            DEFAULT_LEARNED_ANCHOR_SETTINGS["minimum_family_support_share"],
        ),
        "enable_noise_filter": _read_bool(
            "learned_anchor.enable_noise_filter",
            DEFAULT_LEARNED_ANCHOR_SETTINGS["enable_noise_filter"],
        ),
    }


def _read_rare_term_propagation_settings() -> dict[str, float | int | bool]:
    """Read FR-010 rare-term settings from AppSetting without applying bounds."""

    def _read_float(key: str, default: float) -> float:
        raw = _get_app_setting_value(key)
        try:
            value = float(raw) if raw is not None else default
        except (TypeError, ValueError):
            return default
        if not math.isfinite(value):
            return default
        return value

    def _read_int(key: str, default: int) -> int:
        raw = _get_app_setting_value(key)
        try:
            value = int(raw) if raw is not None else default
        except (TypeError, ValueError):
            return default
        return value

    def _read_bool(key: str, default: bool) -> bool:
        raw = _get_app_setting_value(key)
        if raw is None:
            return default
        return str(raw).strip().lower() in {"1", "true", "yes", "on"}

    return {
        "enabled": _read_bool(
            "rare_term_propagation.enabled",
            DEFAULT_RARE_TERM_PROPAGATION_SETTINGS["enabled"],
        ),
        "ranking_weight": _read_float(
            "rare_term_propagation.ranking_weight",
            DEFAULT_RARE_TERM_PROPAGATION_SETTINGS["ranking_weight"],
        ),
        "max_document_frequency": _read_int(
            "rare_term_propagation.max_document_frequency",
            DEFAULT_RARE_TERM_PROPAGATION_SETTINGS["max_document_frequency"],
        ),
        "minimum_supporting_related_pages": _read_int(
            "rare_term_propagation.minimum_supporting_related_pages",
            DEFAULT_RARE_TERM_PROPAGATION_SETTINGS["minimum_supporting_related_pages"],
        ),
    }


def _read_field_aware_relevance_settings() -> dict[str, float]:
    """Read FR-011 field-aware settings from AppSetting without applying bounds."""

    def _read_float(key: str, default: float) -> float:
        raw = _get_app_setting_value(key)
        try:
            value = float(raw) if raw is not None else default
        except (TypeError, ValueError):
            return default
        if not math.isfinite(value):
            return default
        return value

    return {
        "ranking_weight": _read_float(
            "field_aware_relevance.ranking_weight",
            DEFAULT_FIELD_AWARE_RELEVANCE_SETTINGS["ranking_weight"],
        ),
        "title_field_weight": _read_float(
            "field_aware_relevance.title_field_weight",
            DEFAULT_FIELD_AWARE_RELEVANCE_SETTINGS["title_field_weight"],
        ),
        "body_field_weight": _read_float(
            "field_aware_relevance.body_field_weight",
            DEFAULT_FIELD_AWARE_RELEVANCE_SETTINGS["body_field_weight"],
        ),
        "scope_field_weight": _read_float(
            "field_aware_relevance.scope_field_weight",
            DEFAULT_FIELD_AWARE_RELEVANCE_SETTINGS["scope_field_weight"],
        ),
        "learned_anchor_field_weight": _read_float(
            "field_aware_relevance.learned_anchor_field_weight",
            DEFAULT_FIELD_AWARE_RELEVANCE_SETTINGS["learned_anchor_field_weight"],
        ),
    }


def _validate_clustering_settings(
    payload: dict, current: dict
) -> dict[str, float | bool]:
    """Validate and clamp near-duplicate clustering settings."""

    def _get_float(key: str) -> float:
        val = payload.get(key, current.get(key))
        try:
            return float(val)
        except (TypeError, ValueError):
            return float(current.get(key, 0.0))

    enabled = bool(payload.get("enabled", current.get("enabled")))
    similarity_threshold = max(0.01, min(0.20, _get_float("similarity_threshold")))
    suppression_penalty = max(0.0, min(100.0, _get_float("suppression_penalty")))

    return {
        "enabled": enabled,
        "similarity_threshold": similarity_threshold,
        "suppression_penalty": suppression_penalty,
    }


def _read_ga4_gsc_settings() -> dict[str, object]:
    """Read GA4/GSC settings from AppSetting without applying bounds."""

    def _read_float(key: str, default: float) -> float:
        raw = _get_app_setting_value(key)
        try:
            value = float(raw) if raw is not None else default
        except (TypeError, ValueError):
            return default
        if not math.isfinite(value):
            return default
        return value

    def _read_bool(key: str, default: bool) -> bool:
        raw = _get_app_setting_value(key)
        if raw is None:
            return default
        return str(raw).strip().lower() in {"1", "true", "yes", "on"}

    def _read_int(key: str, default: int) -> int:
        raw = _get_app_setting_value(key)
        try:
            value = int(raw) if raw is not None else default
        except (TypeError, ValueError):
            return default
        return value

    property_url = (
        (_get_app_setting_value("ga4_gsc.property_url", "") or "").strip().rstrip("/")
    )
    service_account_email = (
        _get_app_setting_value("ga4_gsc.service_account_email", "") or ""
    ).strip()
    private_key = (_get_app_setting_value("ga4_gsc.private_key", "") or "").strip()
    connection_status = "not_configured"
    connection_message = (
        "Fill in the Search Console property URL and service-account credentials."
    )
    if property_url and service_account_email and private_key:
        connection_status = "saved"
        connection_message = "Search Console credentials are saved. Run Test Connection to confirm access."

    return {
        "ranking_weight": _read_float(
            "ga4_gsc.ranking_weight", DEFAULT_GA4_GSC_SETTINGS["ranking_weight"]
        ),
        "property_url": property_url,
        "service_account_email": service_account_email,
        "private_key_configured": bool(private_key),
        "sync_enabled": _read_bool(
            "ga4_gsc.sync_enabled", DEFAULT_GA4_GSC_SETTINGS["sync_enabled"]
        ),
        "sync_lookback_days": _read_int(
            "ga4_gsc.sync_lookback_days", DEFAULT_GA4_GSC_SETTINGS["sync_lookback_days"]
        ),
        "connection_status": connection_status,
        "connection_message": connection_message,
    }


def _validate_wordpress_settings(payload: dict) -> dict[str, object]:
    current = get_wordpress_settings()

    base_url = str(payload.get("base_url", current["base_url"])).strip().rstrip("/")
    username = str(payload.get("username", current["username"])).strip()

    if base_url:
        parsed = urlparse(base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("base_url must be a valid http(s) URL.")

    app_password_provided = "app_password" in payload
    app_password = None
    if app_password_provided:
        app_password = str(payload.get("app_password", "")).strip()

    effective_has_password = bool(current["app_password_configured"])
    if app_password_provided:
        effective_has_password = bool(app_password)

    def _coerce_bool(value: object, default: bool) -> bool:
        if value is None:
            return default
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in {"1", "true", "yes", "on"}

    def _coerce_int(key: str, minimum: int, maximum: int) -> int:
        raw = payload.get(key, current[key])
        try:
            value = int(raw)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{key} must be an integer.") from exc
        if value < minimum or value > maximum:
            raise ValueError(f"{key} must be between {minimum} and {maximum}.")
        return value

    sync_enabled = _coerce_bool(
        payload.get("sync_enabled"), bool(current["sync_enabled"])
    )
    sync_hour = _coerce_int("sync_hour", 0, 23)
    sync_minute = _coerce_int("sync_minute", 0, 59)

    if username and not effective_has_password:
        raise ValueError(
            "Application Password is required when a WordPress username is configured."
        )
    if effective_has_password and not username:
        raise ValueError(
            "username is required when an Application Password is configured."
        )
    if sync_enabled and not base_url:
        raise ValueError(
            "base_url is required when scheduled WordPress sync is enabled."
        )

    return {
        "base_url": base_url,
        "username": username,
        "app_password": app_password,
        "app_password_provided": app_password_provided,
        "app_password_configured": effective_has_password,
        "sync_enabled": sync_enabled,
        "sync_hour": sync_hour,
        "sync_minute": sync_minute,
    }


def _validate_weighted_authority_settings(
    payload: dict,
    *,
    current: dict[str, float] | None = None,
) -> dict[str, float]:
    current = current or _read_weighted_authority_settings()

    def _coerce_float(key: str) -> float:
        value = payload.get(key, current[key])
        try:
            coerced = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{key} must be numeric.") from exc
        if not math.isfinite(coerced):
            raise ValueError(f"{key} must be finite.")
        return coerced

    validated = {
        "ranking_weight": _coerce_float("ranking_weight"),
        "position_bias": _coerce_float("position_bias"),
        "empty_anchor_factor": _coerce_float("empty_anchor_factor"),
        "bare_url_factor": _coerce_float("bare_url_factor"),
        "weak_context_factor": _coerce_float("weak_context_factor"),
        "isolated_context_factor": _coerce_float("isolated_context_factor"),
    }

    bounds = {
        "ranking_weight": (0.0, 0.25),
        "position_bias": (0.0, 1.0),
        "empty_anchor_factor": (0.1, 1.0),
        "bare_url_factor": (0.1, 1.0),
        "weak_context_factor": (0.1, 1.0),
        "isolated_context_factor": (0.1, 1.0),
    }
    for key, (minimum, maximum) in bounds.items():
        value = validated[key]
        if value < minimum or value > maximum:
            raise ValueError(f"{key} must be between {minimum} and {maximum}.")

    if validated["isolated_context_factor"] > validated["weak_context_factor"]:
        raise ValueError("isolated_context_factor must be <= weak_context_factor.")
    if validated["weak_context_factor"] > 1.0:
        raise ValueError("weak_context_factor must be <= 1.0.")
    if validated["bare_url_factor"] > 1.0:
        raise ValueError("bare_url_factor must be <= 1.0.")

    return validated


def _validate_link_freshness_settings(
    payload: dict,
    *,
    current: dict[str, float | int] | None = None,
) -> dict[str, float | int]:
    current = current or _read_link_freshness_settings()

    def _coerce_float(key: str) -> float:
        value = payload.get(key, current[key])
        try:
            coerced = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{key} must be numeric.") from exc
        if not math.isfinite(coerced):
            raise ValueError(f"{key} must be finite.")
        return coerced

    def _coerce_int(key: str) -> int:
        value = payload.get(key, current[key])
        try:
            coerced = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{key} must be an integer.") from exc
        return coerced

    validated = {
        "ranking_weight": _coerce_float("ranking_weight"),
        "recent_window_days": _coerce_int("recent_window_days"),
        "newest_peer_percent": _coerce_float("newest_peer_percent"),
        "min_peer_count": _coerce_int("min_peer_count"),
        "w_recent": _coerce_float("w_recent"),
        "w_growth": _coerce_float("w_growth"),
        "w_cohort": _coerce_float("w_cohort"),
        "w_loss": _coerce_float("w_loss"),
    }

    bounds = {
        "ranking_weight": (0.0, 0.15),
        "recent_window_days": (7, 90),
        "newest_peer_percent": (0.10, 0.50),
        "min_peer_count": (1, 20),
        "w_recent": (0.0, 1.0),
        "w_growth": (0.0, 1.0),
        "w_cohort": (0.0, 1.0),
        "w_loss": (0.0, 1.0),
    }
    for key, (minimum, maximum) in bounds.items():
        value = validated[key]
        if value < minimum or value > maximum:
            raise ValueError(f"{key} must be between {minimum} and {maximum}.")

    weight_total = (
        float(validated["w_recent"])
        + float(validated["w_growth"])
        + float(validated["w_cohort"])
        + float(validated["w_loss"])
    )
    if not math.isclose(weight_total, 1.0, rel_tol=0.0, abs_tol=1e-6):
        raise ValueError("w_recent + w_growth + w_cohort + w_loss must equal 1.0.")

    return validated


def _validate_phrase_matching_settings(
    payload: dict,
    *,
    current: dict[str, float | int | bool] | None = None,
) -> dict[str, float | int | bool]:
    current = current or _read_phrase_matching_settings()

    def _coerce_float(key: str) -> float:
        value = payload.get(key, current[key])
        try:
            coerced = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{key} must be numeric.") from exc
        if not math.isfinite(coerced):
            raise ValueError(f"{key} must be finite.")
        return coerced

    def _coerce_int(key: str) -> int:
        value = payload.get(key, current[key])
        try:
            return int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{key} must be an integer.") from exc

    def _coerce_bool(key: str) -> bool:
        value = payload.get(key, current[key])
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in {"1", "true", "yes", "on"}

    validated = {
        "ranking_weight": _coerce_float("ranking_weight"),
        "enable_anchor_expansion": _coerce_bool("enable_anchor_expansion"),
        "enable_partial_matching": _coerce_bool("enable_partial_matching"),
        "context_window_tokens": _coerce_int("context_window_tokens"),
    }

    if validated["ranking_weight"] < 0.0 or validated["ranking_weight"] > 0.10:
        raise ValueError("ranking_weight must be between 0.0 and 0.10.")
    if (
        validated["context_window_tokens"] < 4
        or validated["context_window_tokens"] > 12
    ):
        raise ValueError("context_window_tokens must be between 4 and 12.")

    return validated


def _validate_learned_anchor_settings(
    payload: dict,
    *,
    current: dict[str, float | int | bool] | None = None,
) -> dict[str, float | int | bool]:
    current = current or _read_learned_anchor_settings()

    def _coerce_float(key: str) -> float:
        value = payload.get(key, current[key])
        try:
            coerced = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{key} must be numeric.") from exc
        if not math.isfinite(coerced):
            raise ValueError(f"{key} must be finite.")
        return coerced

    def _coerce_int(key: str) -> int:
        value = payload.get(key, current[key])
        try:
            return int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{key} must be an integer.") from exc

    def _coerce_bool(key: str) -> bool:
        value = payload.get(key, current[key])
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in {"1", "true", "yes", "on"}

    validated = {
        "ranking_weight": _coerce_float("ranking_weight"),
        "minimum_anchor_sources": _coerce_int("minimum_anchor_sources"),
        "minimum_family_support_share": _coerce_float("minimum_family_support_share"),
        "enable_noise_filter": _coerce_bool("enable_noise_filter"),
    }

    if validated["ranking_weight"] < 0.0 or validated["ranking_weight"] > 0.10:
        raise ValueError("ranking_weight must be between 0.0 and 0.10.")
    if (
        validated["minimum_anchor_sources"] < 1
        or validated["minimum_anchor_sources"] > 10
    ):
        raise ValueError("minimum_anchor_sources must be between 1 and 10.")
    if (
        validated["minimum_family_support_share"] < 0.05
        or validated["minimum_family_support_share"] > 0.50
    ):
        raise ValueError("minimum_family_support_share must be between 0.05 and 0.50.")

    return validated


def _validate_rare_term_propagation_settings(
    payload: dict,
    *,
    current: dict[str, float | int | bool] | None = None,
) -> dict[str, float | int | bool]:
    current = current or _read_rare_term_propagation_settings()

    def _coerce_float(key: str) -> float:
        value = payload.get(key, current[key])
        try:
            coerced = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{key} must be numeric.") from exc
        if not math.isfinite(coerced):
            raise ValueError(f"{key} must be finite.")
        return coerced

    def _coerce_int(key: str) -> int:
        value = payload.get(key, current[key])
        try:
            return int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{key} must be an integer.") from exc

    def _coerce_bool(key: str) -> bool:
        value = payload.get(key, current[key])
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in {"1", "true", "yes", "on"}

    validated = {
        "enabled": _coerce_bool("enabled"),
        "ranking_weight": _coerce_float("ranking_weight"),
        "max_document_frequency": _coerce_int("max_document_frequency"),
        "minimum_supporting_related_pages": _coerce_int(
            "minimum_supporting_related_pages"
        ),
    }

    if validated["ranking_weight"] < 0.0 or validated["ranking_weight"] > 0.10:
        raise ValueError("ranking_weight must be between 0.0 and 0.10.")
    if (
        validated["max_document_frequency"] < 1
        or validated["max_document_frequency"] > 10
    ):
        raise ValueError("max_document_frequency must be between 1 and 10.")
    if (
        validated["minimum_supporting_related_pages"] < 1
        or validated["minimum_supporting_related_pages"] > 5
    ):
        raise ValueError("minimum_supporting_related_pages must be between 1 and 5.")

    return validated


def _validate_field_aware_relevance_settings(
    payload: dict,
    *,
    current: dict[str, float] | None = None,
) -> dict[str, float]:
    current = current or _read_field_aware_relevance_settings()

    def _coerce_float(key: str) -> float:
        value = payload.get(key, current[key])
        try:
            coerced = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{key} must be numeric.") from exc
        if not math.isfinite(coerced):
            raise ValueError(f"{key} must be finite.")
        return coerced

    validated = {
        "ranking_weight": _coerce_float("ranking_weight"),
        "title_field_weight": _coerce_float("title_field_weight"),
        "body_field_weight": _coerce_float("body_field_weight"),
        "scope_field_weight": _coerce_float("scope_field_weight"),
        "learned_anchor_field_weight": _coerce_float("learned_anchor_field_weight"),
    }

    if validated["ranking_weight"] < 0.0 or validated["ranking_weight"] > 0.15:
        raise ValueError("ranking_weight must be between 0.0 and 0.15.")

    field_weight_sum = 0.0
    for key in (
        "title_field_weight",
        "body_field_weight",
        "scope_field_weight",
        "learned_anchor_field_weight",
    ):
        if validated[key] < 0.0 or validated[key] > 1.0:
            raise ValueError(f"{key} must be between 0.0 and 1.0.")
        field_weight_sum += validated[key]

    if not math.isclose(field_weight_sum, 1.0, abs_tol=1e-6):
        raise ValueError(
            "title/body/scope/learned-anchor field weights must sum to 1.0."
        )

    return validated


def _validate_ga4_gsc_settings(  # noqa: C901 — pre-existing complexity, safe to keep
    payload: dict,
    *,
    current: dict[str, object] | None = None,
) -> dict[str, object]:
    current = current or _read_ga4_gsc_settings()

    def _coerce_float(key: str) -> float:
        value = payload.get(key, current[key])
        try:
            coerced = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{key} must be numeric.") from exc
        if not math.isfinite(coerced):
            raise ValueError(f"{key} must be finite.")
        return coerced

    def _coerce_bool(key: str) -> bool:
        value = payload.get(key, current[key])
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in {"1", "true", "yes", "on"}:
                return True
            if lowered in {"0", "false", "no", "off"}:
                return False
        raise ValueError(f"{key} must be true or false.")

    def _coerce_int(key: str, minimum: int, maximum: int) -> int:
        value = payload.get(key, current[key])
        try:
            coerced = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{key} must be a whole number.") from exc
        if coerced < minimum or coerced > maximum:
            raise ValueError(f"{key} must be between {minimum} and {maximum}.")
        return coerced

    validated = {
        "ranking_weight": _coerce_float("ranking_weight"),
        "property_url": str(payload.get("property_url", current["property_url"]))
        .strip()
        .rstrip("/"),
        "service_account_email": str(
            payload.get("service_account_email", current["service_account_email"])
        ).strip(),
        "sync_enabled": _coerce_bool("sync_enabled"),
        "sync_lookback_days": _coerce_int("sync_lookback_days", 1, 30),
    }
    private_key_provided = "private_key" in payload
    private_key = (
        str(payload.get("private_key", "")).strip() if private_key_provided else None
    )

    if validated["ranking_weight"] < 0.0 or validated["ranking_weight"] > 1.0:
        raise ValueError("ranking_weight must be between 0.0 and 1.0.")
    if validated["property_url"]:
        parsed = urlparse(validated["property_url"])
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("property_url must be a valid http(s) URL.")
    if (
        validated["service_account_email"]
        and "@" not in validated["service_account_email"]
    ):
        raise ValueError("service_account_email must look like an email address.")
    has_private_key = bool(current.get("private_key_configured")) or bool(private_key)
    if validated["sync_enabled"] and (
        not validated["property_url"]
        or not validated["service_account_email"]
        or not has_private_key
    ):
        raise ValueError(
            "Search Console sync needs property_url, service_account_email, and private_key."
        )

    validated["private_key"] = private_key
    validated["private_key_provided"] = private_key_provided

    return validated


def _validate_feedback_rerank_settings(
    payload: dict,
    *,
    current: dict[str, float | bool] | None = None,
) -> dict[str, float | bool]:
    """Validate and clamp feedback-driven explore/exploit settings."""
    current = current or _read_feedback_rerank_settings()

    def _coerce_float(key: str) -> float:
        value = payload.get(key, current[key])
        try:
            coerced = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{key} must be numeric.") from exc
        if not math.isfinite(coerced):
            raise ValueError(f"{key} must be finite.")
        return coerced

    def _coerce_bool(key: str) -> bool:
        value = payload.get(key, current[key])
        if isinstance(value, str):
            return value.lower() in {"1", "true", "yes", "on"}
        return bool(value)

    validated = {
        "enabled": _coerce_bool("enabled"),
        "ranking_weight": _coerce_float("ranking_weight"),
        "exploration_rate": _coerce_float("exploration_rate"),
    }

    if validated["ranking_weight"] < 0.0 or validated["ranking_weight"] > 0.5:
        raise ValueError("ranking_weight must be between 0.0 and 0.5.")
    if validated["exploration_rate"] < 0.1 or validated["exploration_rate"] > 2.0:
        raise ValueError("exploration_rate must be between 0.1 and 2.0.")

    return validated


def _sync_wordpress_periodic_task(config: dict[str, object]) -> None:
    """Keep the stored periodic schedule aligned with the saved WordPress sync settings."""
    from django_celery_beat.models import CrontabSchedule, PeriodicTask

    schedule, _ = CrontabSchedule.objects.get_or_create(
        minute=str(config["sync_minute"]),
        hour=str(config["sync_hour"]),
        day_of_week="*",
        day_of_month="*",
        month_of_year="*",
        timezone="UTC",
    )
    PeriodicTask.objects.update_or_create(
        name="wordpress-content-sync",
        defaults={
            "task": "pipeline.import_content",
            "crontab": schedule,
            "kwargs": json.dumps({"source": "wp", "mode": "full"}),
            "queue": "pipeline",
            "enabled": bool(config["sync_enabled"]) and bool(config["base_url"]),
            "description": "Scheduled WordPress content sync for cross-link indexing.",
        },
    )


class HealthCheckView(View):
    """
    Simple health check endpoint.
    Used by Docker Compose and load balancers to verify the backend is alive.
    """

    def get(self, request):
        """Return a simple JSON response confirming the backend is running."""
        return JsonResponse({"status": "ok", "version": "2.0.0"})


class AppearanceSettingsView(APIView):
    """
    GET  /api/settings/appearance/ — returns current appearance config (or defaults)
    PUT  /api/settings/appearance/ — merge-updates the config, returns updated config
    """

    permission_classes = [IsAuthenticated]

    def _get_config(self) -> dict:
        from apps.core.models import AppSetting

        try:
            setting = AppSetting.objects.get(key="appearance.config")
            stored = json.loads(setting.value)
        except AppSetting.DoesNotExist:
            stored = {}
        # Merge stored values over defaults.  Keys that are not in
        # DEFAULT_APPEARANCE are silently dropped — this cleans up legacy
        # keys such as "theme" that were removed from the schema.
        result = dict(DEFAULT_APPEARANCE)
        for k in DEFAULT_APPEARANCE:
            if k in stored:
                result[k] = stored[k]
        return result

    def get(self, request):
        return Response(self._get_config())

    def put(self, request):
        from apps.core.models import AppSetting

        current = self._get_config()
        # Shallow merge — client sends only the keys it wants to change
        for k, v in request.data.items():
            if k in DEFAULT_APPEARANCE:
                current[k] = v
        AppSetting.objects.update_or_create(
            key="appearance.config",
            defaults={
                "value": json.dumps(current),
                "value_type": "json",
                "category": "appearance",
                "description": "Theme customizer appearance configuration (managed by UI).",
                "is_secret": False,
            },
        )
        return Response(current)


class SiloSettingsView(APIView):
    """
    GET  /api/settings/silos/ - returns persisted silo-ranking configuration
    PUT  /api/settings/silos/ - validates and persists silo-ranking configuration
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(get_silo_settings())

    def put(self, request):
        from apps.core.models import AppSetting

        try:
            validated = _validate_silo_settings(request.data)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=400)

        rows = {
            "silo.mode": {
                "value": validated["mode"],
                "value_type": "str",
                "description": "Topical silo enforcement mode for the suggestion pipeline.",
            },
            "silo.same_silo_boost": {
                "value": str(validated["same_silo_boost"]),
                "value_type": "float",
                "description": "Score bonus applied to same-silo candidates in prefer_same_silo mode.",
            },
            "silo.cross_silo_penalty": {
                "value": str(validated["cross_silo_penalty"]),
                "value_type": "float",
                "description": "Score penalty applied to cross-silo candidates in prefer_same_silo mode.",
            },
        }

        for key, row in rows.items():
            AppSetting.objects.update_or_create(
                key=key,
                defaults={
                    "value": row["value"],
                    "value_type": row["value_type"],
                    "category": "ml",
                    "description": row["description"],
                    "is_secret": False,
                },
            )
        return Response(validated)


class WeightedAuthoritySettingsView(APIView):
    """
    GET  /api/settings/weighted-authority/ - returns March 2026 PageRank settings
    PUT  /api/settings/weighted-authority/ - validates and persists those settings
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(get_weighted_authority_settings())

    def put(self, request):
        from apps.core.models import AppSetting

        try:
            validated = _validate_weighted_authority_settings(request.data)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=400)

        rows = {
            "weighted_authority.ranking_weight": {
                "value": str(validated["ranking_weight"]),
                "description": "Ranking weight applied to the normalized March 2026 PageRank signal.",
            },
            "weighted_authority.position_bias": {
                "value": str(validated["position_bias"]),
                "description": "How much later links are down-weighted within a source page.",
            },
            "weighted_authority.empty_anchor_factor": {
                "value": str(validated["empty_anchor_factor"]),
                "description": "Multiplier applied when a non-bare link has blank anchor text.",
            },
            "weighted_authority.bare_url_factor": {
                "value": str(validated["bare_url_factor"]),
                "description": "Multiplier applied to naked URL links.",
            },
            "weighted_authority.weak_context_factor": {
                "value": str(validated["weak_context_factor"]),
                "description": "Multiplier applied to links with prose on only one side.",
            },
            "weighted_authority.isolated_context_factor": {
                "value": str(validated["isolated_context_factor"]),
                "description": "Multiplier applied to isolated or list-like links.",
            },
        }

        for key, row in rows.items():
            AppSetting.objects.update_or_create(
                key=key,
                defaults={
                    "value": row["value"],
                    "value_type": "float",
                    "category": "ml",
                    "description": row["description"],
                    "is_secret": False,
                },
            )
        return Response(validated)


class WeightedAuthorityRecalculateView(APIView):
    """POST /api/settings/weighted-authority/recalculate/ - recalculate March 2026 PageRank."""

    throttle_classes = [_WeightRecalcThrottle]

    def post(self, request):
        from apps.pipeline.tasks import recalculate_weighted_authority

        job_id = str(uuid.uuid4())
        recalculate_weighted_authority.delay(job_id=job_id)
        return Response({"job_id": job_id}, status=202)


class LinkFreshnessSettingsView(APIView):
    """
    GET  /api/settings/link-freshness/ - returns Link Freshness settings
    PUT  /api/settings/link-freshness/ - validates and persists those settings
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(get_link_freshness_settings())

    def put(self, request):
        from apps.core.models import AppSetting

        try:
            validated = _validate_link_freshness_settings(request.data)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=400)

        rows = {
            "link_freshness.ranking_weight": {
                "value": str(validated["ranking_weight"]),
                "value_type": "float",
                "description": "Ranking weight applied to the centered Link Freshness component.",
            },
            "link_freshness.recent_window_days": {
                "value": str(validated["recent_window_days"]),
                "value_type": "int",
                "description": "Day window used to compare recent link growth vs. the prior window.",
            },
            "link_freshness.newest_peer_percent": {
                "value": str(validated["newest_peer_percent"]),
                "value_type": "float",
                "description": "Share of newest inbound peers used for cohort freshness.",
            },
            "link_freshness.min_peer_count": {
                "value": str(validated["min_peer_count"]),
                "value_type": "int",
                "description": "Minimum inbound peer history rows required before Link Freshness stops being neutral.",
            },
            "link_freshness.w_recent": {
                "value": str(validated["w_recent"]),
                "value_type": "float",
                "description": "Weight for the recent-new-links share component.",
            },
            "link_freshness.w_growth": {
                "value": str(validated["w_growth"]),
                "value_type": "float",
                "description": "Weight for the recent-vs-previous growth delta component.",
            },
            "link_freshness.w_cohort": {
                "value": str(validated["w_cohort"]),
                "value_type": "float",
                "description": "Weight for the newest-cohort freshness component.",
            },
            "link_freshness.w_loss": {
                "value": str(validated["w_loss"]),
                "value_type": "float",
                "description": "Weight for recent inbound-link disappearance pressure.",
            },
        }

        for key, row in rows.items():
            AppSetting.objects.update_or_create(
                key=key,
                defaults={
                    "value": row["value"],
                    "value_type": row["value_type"],
                    "category": "link_freshness",
                    "description": row["description"],
                    "is_secret": False,
                },
            )
        return Response(validated)


class LinkFreshnessRecalculateView(APIView):
    """POST /api/settings/link-freshness/recalculate/ - recalculate Link Freshness."""

    throttle_classes = [_WeightRecalcThrottle]

    def post(self, request):
        from apps.pipeline.tasks import recalculate_link_freshness

        job_id = str(uuid.uuid4())
        recalculate_link_freshness.delay(job_id=job_id)
        return Response({"job_id": job_id}, status=202)


class PhraseMatchingSettingsView(APIView):
    """
    GET  /api/settings/phrase-matching/ - returns FR-008 phrase-matching settings
    PUT  /api/settings/phrase-matching/ - validates and persists those settings
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(get_phrase_matching_settings())

    def put(self, request):
        from apps.core.models import AppSetting

        try:
            validated = _validate_phrase_matching_settings(request.data)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=400)

        rows = {
            "phrase_matching.ranking_weight": {
                "value": str(validated["ranking_weight"]),
                "value_type": "float",
                "description": "Ranking weight applied to the centered FR-008 phrase relevance component.",
            },
            "phrase_matching.enable_anchor_expansion": {
                "value": "true" if validated["enable_anchor_expansion"] else "false",
                "value_type": "bool",
                "description": "Whether anchor extraction can expand beyond the current exact title fallback.",
            },
            "phrase_matching.enable_partial_matching": {
                "value": "true" if validated["enable_partial_matching"] else "false",
                "value_type": "bool",
                "description": "Whether bounded partial phrase matches are allowed when local context supports them.",
            },
            "phrase_matching.context_window_tokens": {
                "value": str(validated["context_window_tokens"]),
                "value_type": "int",
                "description": "Same-sentence token window used for FR-008 local corroboration.",
            },
        }

        for key, row in rows.items():
            AppSetting.objects.update_or_create(
                key=key,
                defaults={
                    "value": row["value"],
                    "value_type": row["value_type"],
                    "category": "anchor",
                    "description": row["description"],
                    "is_secret": False,
                },
            )
        return Response(validated)


class LearnedAnchorSettingsView(APIView):
    """
    GET  /api/settings/learned-anchor/ - returns FR-009 learned-anchor settings
    PUT  /api/settings/learned-anchor/ - validates and persists those settings
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(get_learned_anchor_settings())

    def put(self, request):
        from apps.core.models import AppSetting

        try:
            validated = _validate_learned_anchor_settings(request.data)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=400)

        rows = {
            "learned_anchor.ranking_weight": {
                "value": str(validated["ranking_weight"]),
                "value_type": "float",
                "description": "Ranking weight applied to the positive-only FR-009 learned-anchor corroboration component.",
            },
            "learned_anchor.minimum_anchor_sources": {
                "value": str(validated["minimum_anchor_sources"]),
                "value_type": "int",
                "description": "Minimum usable inbound anchor sources required before learned anchors stop being neutral.",
            },
            "learned_anchor.minimum_family_support_share": {
                "value": str(validated["minimum_family_support_share"]),
                "value_type": "float",
                "description": "Minimum support share a learned anchor family needs before it can corroborate the chosen anchor.",
            },
            "learned_anchor.enable_noise_filter": {
                "value": "true" if validated["enable_noise_filter"] else "false",
                "value_type": "bool",
                "description": "Whether generic live anchor text like click here is filtered out before learned-anchor grouping.",
            },
        }

        for key, row in rows.items():
            AppSetting.objects.update_or_create(
                key=key,
                defaults={
                    "value": row["value"],
                    "value_type": row["value_type"],
                    "category": "anchor",
                    "description": row["description"],
                    "is_secret": False,
                },
            )
        return Response(validated)


class RareTermPropagationSettingsView(APIView):
    """
    GET  /api/settings/rare-term-propagation/ - returns FR-010 rare-term settings
    PUT  /api/settings/rare-term-propagation/ - validates and persists those settings
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(get_rare_term_propagation_settings())

    def put(self, request):
        from apps.core.models import AppSetting

        try:
            validated = _validate_rare_term_propagation_settings(request.data)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=400)

        rows = {
            "rare_term_propagation.enabled": {
                "value": "true" if validated["enabled"] else "false",
                "value_type": "bool",
                "description": "Whether FR-010 rare-term propagation profiles are built during suggestion scoring.",
            },
            "rare_term_propagation.ranking_weight": {
                "value": str(validated["ranking_weight"]),
                "value_type": "float",
                "description": "Ranking weight applied to the positive-only FR-010 rare-term propagation component.",
            },
            "rare_term_propagation.max_document_frequency": {
                "value": str(validated["max_document_frequency"]),
                "value_type": "int",
                "description": "Highest site-wide document frequency a token can have and still count as a propagated rare term.",
            },
            "rare_term_propagation.minimum_supporting_related_pages": {
                "value": str(validated["minimum_supporting_related_pages"]),
                "value_type": "int",
                "description": "Minimum number of eligible related pages that must support a propagated rare term before it stops being neutral.",
            },
        }

        for key, row in rows.items():
            AppSetting.objects.update_or_create(
                key=key,
                defaults={
                    "value": row["value"],
                    "value_type": row["value_type"],
                    "category": "ml",
                    "description": row["description"],
                    "is_secret": False,
                },
            )
        return Response(validated)


class FieldAwareRelevanceSettingsView(APIView):
    """
    GET  /api/settings/field-aware-relevance/ - returns FR-011 field-aware settings
    PUT  /api/settings/field-aware-relevance/ - validates and persists those settings
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(get_field_aware_relevance_settings())

    def put(self, request):
        from apps.core.models import AppSetting

        try:
            validated = _validate_field_aware_relevance_settings(request.data)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=400)

        rows = {
            "field_aware_relevance.ranking_weight": {
                "value": str(validated["ranking_weight"]),
                "value_type": "float",
                "description": "Ranking weight applied to the centered FR-011 field-aware relevance component.",
            },
            "field_aware_relevance.title_field_weight": {
                "value": str(validated["title_field_weight"]),
                "value_type": "float",
                "description": "Share of FR-011 field-aware relevance assigned to destination title matches.",
            },
            "field_aware_relevance.body_field_weight": {
                "value": str(validated["body_field_weight"]),
                "value_type": "float",
                "description": "Share of FR-011 field-aware relevance assigned to destination body-text matches.",
            },
            "field_aware_relevance.scope_field_weight": {
                "value": str(validated["scope_field_weight"]),
                "value_type": "float",
                "description": "Share of FR-011 field-aware relevance assigned to scope-label matches.",
            },
            "field_aware_relevance.learned_anchor_field_weight": {
                "value": str(validated["learned_anchor_field_weight"]),
                "value_type": "float",
                "description": "Share of FR-011 field-aware relevance assigned to learned-anchor vocabulary matches.",
            },
        }

        for key, row in rows.items():
            AppSetting.objects.update_or_create(
                key=key,
                defaults={
                    "value": row["value"],
                    "value_type": row["value_type"],
                    "category": "ml",
                    "description": row["description"],
                    "is_secret": False,
                },
            )
        return Response(validated)


class GA4GSCSettingsView(APIView):
    """
    GET  /api/settings/ga4-gsc/ - returns GA4/GSC settings including GSC credentials
    PUT  /api/settings/ga4-gsc/ - validates and persists those settings
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(get_ga4_gsc_settings())

    def put(self, request):
        from apps.core.models import AppSetting

        try:
            validated = _validate_ga4_gsc_settings(request.data)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=400)

        rows = {
            "ga4_gsc.ranking_weight": {
                "value": str(validated["ranking_weight"]),
                "value_type": "float",
                "description": "Ranking weight for the GA4/GSC content-value signal.",
                "category": "ml",
                "is_secret": False,
            },
            "ga4_gsc.property_url": {
                "value": str(validated["property_url"]),
                "value_type": "str",
                "description": "Google Search Console property URL for read access.",
                "category": "analytics",
                "is_secret": False,
            },
            "ga4_gsc.service_account_email": {
                "value": str(validated["service_account_email"]),
                "value_type": "str",
                "description": "Service-account email used for Search Console read access.",
                "category": "analytics",
                "is_secret": False,
            },
            "ga4_gsc.sync_enabled": {
                "value": "true" if validated["sync_enabled"] else "false",
                "value_type": "bool",
                "description": "Whether Search Console sync is enabled when the importer is added.",
                "category": "analytics",
                "is_secret": False,
            },
            "ga4_gsc.sync_lookback_days": {
                "value": str(validated["sync_lookback_days"]),
                "value_type": "int",
                "description": "How many days the future Search Console sync should reread.",
                "category": "analytics",
                "is_secret": False,
            },
        }
        if validated["private_key_provided"]:
            rows["ga4_gsc.private_key"] = {
                "value": str(validated["private_key"] or ""),
                "value_type": "str",
                "description": "Service-account private key for Search Console read access.",
                "category": "analytics",
                "is_secret": True,
            }

        for key, row in rows.items():
            AppSetting.objects.update_or_create(
                key=key,
                defaults={
                    "value": row["value"],
                    "value_type": row["value_type"],
                    "category": row["category"],
                    "description": row["description"],
                    "is_secret": row["is_secret"],
                },
            )
        return Response(get_ga4_gsc_settings())


def _gsc_private_key() -> str:
    return (_get_app_setting_value("ga4_gsc.private_key", "") or "").strip()


def _build_gsc_service(*, service_account_email: str, private_key: str):
    from google.oauth2 import service_account
    from googleapiclient.discovery import build

    credentials = service_account.Credentials.from_service_account_info(
        {
            "type": "service_account",
            "client_email": service_account_email,
            "private_key": private_key.replace("\\n", "\n"),
            "token_uri": "https://oauth2.googleapis.com/token",
        },
        scopes=["https://www.googleapis.com/auth/webmasters.readonly"],
    )
    return build("searchconsole", "v1", credentials=credentials, cache_discovery=False)


class GSCConnectionTestView(APIView):
    """POST /api/settings/ga4-gsc/test-connection/ - validate Search Console credentials."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        current = get_ga4_gsc_settings()
        property_url = (
            str(request.data.get("property_url") or current["property_url"] or "")
            .strip()
            .rstrip("/")
        )
        service_account_email = str(
            request.data.get("service_account_email")
            or current["service_account_email"]
            or ""
        ).strip()
        private_key = str(request.data.get("private_key") or _gsc_private_key()).strip()
        if not property_url or not service_account_email or not private_key:
            return Response(
                {
                    "status": "not_configured",
                    "message": "Save the property URL, service-account email, and private key first.",
                },
                status=400,
            )

        try:
            service = _build_gsc_service(
                service_account_email=service_account_email, private_key=private_key
            )
            response = service.sites().list().execute()
        except Exception as exc:
            return Response(
                {
                    "status": "error",
                    "message": f"Search Console connection failed: {exc}",
                },
                status=400,
            )

        site_entries = (
            response.get("siteEntry", []) if isinstance(response, dict) else []
        )
        property_match = any(
            str(entry.get("siteUrl") or "").rstrip("/") == property_url
            for entry in site_entries
        )
        message = "Search Console credentials worked and the property is visible."
        if not property_match:
            message = "Search Console credentials worked, but this property URL was not listed for the service account."
        return Response(
            {"status": "connected" if property_match else "saved", "message": message}
        )


class WordPressSettingsView(APIView):
    """
    GET  /api/settings/wordpress/ - returns saved WordPress sync settings
    PUT  /api/settings/wordpress/ - validates and persists WordPress sync settings
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(get_wordpress_settings())

    def put(self, request):
        from apps.core.models import AppSetting

        try:
            validated = _validate_wordpress_settings(request.data)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=400)

        rows = {
            "wordpress.base_url": {
                "value": str(validated["base_url"]),
                "value_type": "str",
                "description": "Base URL for the read-only WordPress REST API.",
                "category": "sync",
                "is_secret": False,
            },
            "wordpress.username": {
                "value": str(validated["username"]),
                "value_type": "str",
                "description": "WordPress username used for Application Password authentication.",
                "category": "api",
                "is_secret": False,
            },
            "wordpress.sync_enabled": {
                "value": "true" if validated["sync_enabled"] else "false",
                "value_type": "bool",
                "description": "Whether scheduled WordPress sync is enabled for the active scheduler lane.",
                "category": "sync",
                "is_secret": False,
            },
            "wordpress.sync_hour": {
                "value": str(validated["sync_hour"]),
                "value_type": "int",
                "description": "UTC hour for the scheduled WordPress sync.",
                "category": "sync",
                "is_secret": False,
            },
            "wordpress.sync_minute": {
                "value": str(validated["sync_minute"]),
                "value_type": "int",
                "description": "UTC minute for the scheduled WordPress sync.",
                "category": "sync",
                "is_secret": False,
            },
        }
        if validated["app_password_provided"]:
            rows["wordpress.app_password"] = {
                "value": str(validated["app_password"] or ""),
                "value_type": "str",
                "description": "WordPress Application Password for private-content reads.",
                "category": "api",
                "is_secret": True,
            }

        for key, row in rows.items():
            AppSetting.objects.update_or_create(
                key=key,
                defaults={
                    "value": row["value"],
                    "value_type": row["value_type"],
                    "category": row["category"],
                    "description": row["description"],
                    "is_secret": row["is_secret"],
                },
            )

        _sync_wordpress_periodic_task(validated)
        return Response(get_wordpress_settings())


class WordPressSyncRunView(APIView):
    """POST /api/sync/wordpress/run/ - enqueue a manual WordPress sync job."""

    def post(self, request):
        from django.utils import timezone

        from apps.pipeline.tasks import dispatch_import_content
        from apps.sync.models import SyncJob

        config = get_wordpress_settings()
        if not config["base_url"]:
            return Response(
                {"detail": "Configure a WordPress base URL before starting a sync."},
                status=400,
            )

        job = SyncJob.objects.create(
            source="wp",
            mode="full",
            status="pending",
            message="Queued WordPress sync.",
            started_at=timezone.now(),
        )

        dispatch_import_content(
            mode="full",
            source="wp",
            job_id=str(job.job_id),
            force_reembed=bool(request.data.get("force_reembed") or False),
        )

        return Response(
            {
                "job_id": str(job.job_id),
                "source": "wp",
                "mode": "full",
            },
            status=202,
        )


class XenForoSettingsView(APIView):
    """
    GET  /api/settings/xenforo/ - returns saved XenForo connection settings
    PUT  /api/settings/xenforo/ - validates and persists XenForo credentials
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        from apps.health.services import get_service_health_status

        base_url = (
            _get_app_setting_value(
                "xenforo.base_url", getattr(django_settings, "XENFORO_BASE_URL", "")
            )
            or ""
        ).strip()
        api_key = (
            _get_app_setting_value(
                "xenforo.api_key", getattr(django_settings, "XENFORO_API_KEY", "")
            )
            or ""
        ).strip()

        # Get actual connectivity health
        health = get_service_health_status("xenforo")

        return Response(
            {
                "base_url": base_url,
                "api_key_configured": bool(api_key),
                "health": health,
            }
        )

    def put(self, request):
        from apps.core.models import AppSetting

        base_url = (request.data.get("base_url") or "").strip().rstrip("/")
        api_key = (request.data.get("api_key") or "").strip()

        if not base_url:
            return Response({"detail": "base_url is required."}, status=400)

        AppSetting.objects.update_or_create(
            key="xenforo.base_url",
            defaults={
                "value": base_url,
                "value_type": "str",
                "category": "api",
                "is_secret": False,
            },
        )
        if api_key:
            AppSetting.objects.update_or_create(
                key="xenforo.api_key",
                defaults={
                    "value": api_key,
                    "value_type": "str",
                    "category": "api",
                    "is_secret": True,
                },
            )

        return Response({"status": "saved"})


class XenForoTestConnectionView(APIView):
    """POST /api/settings/xenforo/test-connection/ — verify XenForo API credentials."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        import requests as http_requests

        base_url = (
            (
                request.data.get("base_url")
                or _get_app_setting_value(
                    "xenforo.base_url", getattr(django_settings, "XENFORO_BASE_URL", "")
                )
                or ""
            )
            .strip()
            .rstrip("/")
        )
        api_key = (
            request.data.get("api_key")
            or _get_app_setting_value(
                "xenforo.api_key", getattr(django_settings, "XENFORO_API_KEY", "")
            )
            or ""
        ).strip()

        if not base_url or not api_key:
            return Response(
                {
                    "status": "not_configured",
                    "message": "Both Forum URL and API Key are required.",
                },
                status=400,
            )

        try:
            resp = http_requests.get(
                f"{base_url}/api/me",
                headers={"XF-Api-Key": api_key},
                timeout=10,
            )
            payload = resp.json()
        except Exception as exc:
            return Response(
                {"status": "error", "message": f"Could not reach XenForo: {exc}"},
                status=502,
            )

        if resp.status_code != 200:
            errors = payload.get("errors", [])
            detail = (
                errors[0].get("message", "Authentication failed.")
                if errors
                else f"HTTP {resp.status_code}"
            )
            return Response({"status": "error", "message": detail}, status=400)

        username = payload.get("me", {}).get("username", "unknown")
        return Response(
            {"status": "connected", "message": f"Connected to XenForo as '{username}'."}
        )


class WordPressTestConnectionView(APIView):
    """POST /api/settings/wordpress/test-connection/ — verify WordPress REST API credentials."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        import requests as http_requests

        base_url = (
            (
                request.data.get("base_url")
                or _get_app_setting_value(
                    "wordpress.base_url",
                    getattr(django_settings, "WORDPRESS_BASE_URL", ""),
                )
                or ""
            )
            .strip()
            .rstrip("/")
        )
        username = (
            request.data.get("username")
            or _get_app_setting_value(
                "wordpress.username", getattr(django_settings, "WORDPRESS_USERNAME", "")
            )
            or ""
        ).strip()
        app_password = (
            request.data.get("app_password")
            or _get_app_setting_value(
                "wordpress.app_password",
                getattr(django_settings, "WORDPRESS_APP_PASSWORD", ""),
            )
            or ""
        ).strip()

        if not base_url or not username or not app_password:
            return Response(
                {
                    "status": "not_configured",
                    "message": "Site URL, username, and app password are all required.",
                },
                status=400,
            )

        try:
            resp = http_requests.get(
                f"{base_url}/wp-json/wp/v2/users/me",
                auth=(username, app_password),
                timeout=10,
            )
            payload = resp.json()
        except Exception as exc:
            return Response(
                {"status": "error", "message": f"Could not reach WordPress: {exc}"},
                status=502,
            )

        if resp.status_code != 200:
            detail = payload.get("message", f"HTTP {resp.status_code}")
            return Response({"status": "error", "message": detail}, status=400)

        display_name = payload.get("name", "unknown")
        return Response(
            {
                "status": "connected",
                "message": f"Connected to WordPress as '{display_name}'.",
            }
        )


class WebhookTestView(APIView):
    """POST /api/settings/webhooks/test/ — verify internal webhook receiver endpoints are alive."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        from django.test import RequestFactory

        from apps.sync.views import WordPressWebhookView, XenForoWebhookView

        factory = RequestFactory()
        results = {}

        # Test XenForo webhook endpoint
        try:
            xf_request = factory.post(
                "/api/sync/webhooks/xenforo/",
                data={"event": "connection_test"},
                content_type="application/json",
            )
            xf_response = XenForoWebhookView.as_view()(xf_request)
            results["xenforo"] = {
                "status": "ok" if xf_response.status_code in (200, 403) else "error",
                "http_status": xf_response.status_code,
                "message": "Endpoint reachable."
                if xf_response.status_code == 200
                else "Endpoint reachable but webhook secret mismatch — check XENFORO_WEBHOOK_SECRET."
                if xf_response.status_code == 403
                else f"Unexpected response: HTTP {xf_response.status_code}",
            }
        except Exception as exc:
            results["xenforo"] = {"status": "error", "message": str(exc)}

        # Test WordPress webhook endpoint
        try:
            wp_request = factory.post(
                "/api/sync/webhooks/wordpress/",
                data={"event": "connection_test"},
                content_type="application/json",
            )
            wp_response = WordPressWebhookView.as_view()(wp_request)
            results["wordpress"] = {
                "status": "ok" if wp_response.status_code in (200, 403) else "error",
                "http_status": wp_response.status_code,
                "message": "Endpoint reachable."
                if wp_response.status_code == 200
                else "Endpoint reachable but webhook secret mismatch — check WORDPRESS_WEBHOOK_SECRET."
                if wp_response.status_code == 403
                else f"Unexpected response: HTTP {wp_response.status_code}",
            }
        except Exception as exc:
            results["wordpress"] = {"status": "error", "message": str(exc)}

        all_ok = all(r.get("status") == "ok" for r in results.values())
        return Response(
            {
                "status": "connected" if all_ok else "partial",
                "message": "All webhook endpoints are reachable."
                if all_ok
                else "Some webhook endpoints have issues.",
                "details": results,
            }
        )


class WebhookSettingsView(APIView):
    """
    GET  /api/settings/webhooks/ — returns whether each webhook secret is configured
    PUT  /api/settings/webhooks/ — saves webhook secrets to AppSetting
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        xf = (
            _get_app_setting_value(
                "webhook.xenforo_secret",
                getattr(django_settings, "XENFORO_WEBHOOK_SECRET", ""),
            )
            or ""
        ).strip()
        wp = (
            _get_app_setting_value(
                "webhook.wordpress_secret",
                getattr(django_settings, "WORDPRESS_WEBHOOK_SECRET", ""),
            )
            or ""
        ).strip()
        return Response(
            {
                "xf_secret_configured": bool(xf),
                "wp_secret_configured": bool(wp),
            }
        )

    def put(self, request):
        from apps.core.models import AppSetting

        xf_secret = (request.data.get("xf_webhook_secret") or "").strip()
        wp_secret = (request.data.get("wp_webhook_secret") or "").strip()

        if xf_secret:
            AppSetting.objects.update_or_create(
                key="webhook.xenforo_secret",
                defaults={
                    "value": xf_secret,
                    "value_type": "str",
                    "category": "api",
                    "description": "XenForo webhook secret",
                    "is_secret": True,
                },
            )
        if wp_secret:
            AppSetting.objects.update_or_create(
                key="webhook.wordpress_secret",
                defaults={
                    "value": wp_secret,
                    "value_type": "str",
                    "category": "api",
                    "description": "WordPress webhook secret",
                    "is_secret": True,
                },
            )

        xf = (
            _get_app_setting_value(
                "webhook.xenforo_secret",
                getattr(django_settings, "XENFORO_WEBHOOK_SECRET", ""),
            )
            or ""
        ).strip()
        wp = (
            _get_app_setting_value(
                "webhook.wordpress_secret",
                getattr(django_settings, "WORDPRESS_WEBHOOK_SECRET", ""),
            )
            or ""
        ).strip()
        return Response(
            {
                "xf_secret_configured": bool(xf),
                "wp_secret_configured": bool(wp),
            }
        )


def _save_appearance_key(key: str, value) -> None:
    """Persist a single key into the appearance config AppSetting blob."""
    from apps.core.models import AppSetting

    try:
        setting = AppSetting.objects.get(key="appearance.config")
        stored = json.loads(setting.value)
    except AppSetting.DoesNotExist:
        stored = {}
    stored[key] = value
    AppSetting.objects.update_or_create(
        key="appearance.config",
        defaults={
            "value": json.dumps(stored),
            "value_type": "json",
            "category": "appearance",
            "description": "Theme customizer appearance configuration (managed by UI).",
            "is_secret": False,
        },
    )


class _SiteAssetUploadView(APIView):
    """
    Base class for logo and favicon upload views.

    Subclasses set:
        asset_key      — the key in DEFAULT_APPEARANCE (e.g. 'logoUrl')
        allowed_types  — frozenset of permitted MIME types
        url_field      — the key returned in the JSON response (e.g. 'logo_url')
        subfolder      — directory inside MEDIA_ROOT/site-assets/ (e.g. 'logos')
    """

    asset_key: str = ""
    allowed_types: frozenset = frozenset()
    url_field: str = ""
    subfolder: str = ""

    def post(self, request):
        upload = request.FILES.get("file")
        if not upload:
            return Response(
                {"error": "No file uploaded. Use field name 'file'."}, status=400
            )

        # Size check
        if upload.size > _ASSET_MAX_BYTES:
            return Response({"error": "File exceeds 2 MB limit."}, status=400)

        # MIME-type check (uses the browser-reported content type)
        if upload.content_type not in self.allowed_types:
            return Response(
                {
                    "error": (
                        f"Unsupported file type '{upload.content_type}'. "
                        f"Allowed: {', '.join(sorted(self.allowed_types))}"
                    )
                },
                status=400,
            )

        # Derive safe extension from MIME type
        ext_map = {
            "image/png": ".png",
            "image/svg+xml": ".svg",
            "image/webp": ".webp",
            "image/jpeg": ".jpg",
            "image/x-icon": ".ico",
            "image/vnd.microsoft.icon": ".ico",
        }
        ext = ext_map.get(upload.content_type, ".bin")

        # Build destination path using UUID filename — never use the original name
        dest_dir = django_settings.MEDIA_ROOT / "site-assets" / self.subfolder
        dest_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{uuid.uuid4()}{ext}"
        dest_path = dest_dir / filename

        with open(dest_path, "wb") as f:
            for chunk in upload.chunks():
                f.write(chunk)

        asset_url = (
            f"{django_settings.MEDIA_URL}site-assets/{self.subfolder}/{filename}"
        )
        _save_appearance_key(self.asset_key, asset_url)

        return Response({self.url_field: asset_url}, status=201)

    def delete(self, request):
        _save_appearance_key(self.asset_key, "")
        return Response(status=204)


class LogoUploadView(_SiteAssetUploadView):
    """POST /api/settings/logo/ — upload site logo (PNG, SVG, WEBP, JPEG ≤ 2 MB)."""

    asset_key = "logoUrl"
    allowed_types = _LOGO_ALLOWED
    url_field = "logo_url"
    subfolder = "logos"


class FaviconUploadView(_SiteAssetUploadView):
    """POST /api/settings/favicon/ — upload site favicon (PNG, SVG, ICO ≤ 2 MB)."""

    asset_key = "faviconUrl"
    allowed_types = _FAVICON_ALLOWED
    url_field = "favicon_url"
    subfolder = "favicons"


class DashboardView(APIView):
    """
    GET /api/dashboard/

    Returns aggregated stats for the dashboard:
    - suggestion counts by status
    - total content items
    - last completed sync job
    - recent pipeline runs (last 5)
    - recent import jobs (last 5)
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        from apps.suggestions.models import Suggestion, PipelineRun
        from apps.content.models import ContentItem
        from apps.sync.models import SyncJob
        from apps.graph.models import BrokenLink
        from django.db.models import Count

        # Suggestion counts by status
        status_rows = Suggestion.objects.values("status").annotate(count=Count("pk"))
        suggestion_counts = {row["status"]: row["count"] for row in status_rows}

        # Total content items
        content_count = ContentItem.objects.count()

        open_broken_links = BrokenLink.objects.filter(status="open").count()

        # Last completed sync
        last_sync = (
            SyncJob.objects.filter(status="completed")
            .values("completed_at", "source", "mode", "items_synced")
            .order_by("-completed_at")
            .first()
        )

        # Recent pipeline runs (last 5)
        pipeline_runs = list(
            PipelineRun.objects.values(
                "run_id",
                "run_state",
                "rerun_mode",
                "suggestions_created",
                "destinations_processed",
                "duration_seconds",
                "created_at",
            ).order_by("-created_at")[:5]
        )
        for run in pipeline_runs:
            run["run_id"] = str(run["run_id"])
            if run["created_at"]:
                run["created_at"] = run["created_at"].isoformat()
            ds = run.pop("duration_seconds")
            if ds is not None:
                minutes, seconds = divmod(int(ds), 60)
                run["duration_display"] = (
                    f"{minutes}m {seconds}s" if minutes else f"{seconds}s"
                )
            else:
                run["duration_display"] = None

        # Recent import jobs (last 5)
        recent_imports = list(
            SyncJob.objects.values(
                "job_id",
                "status",
                "source",
                "mode",
                "items_synced",
                "created_at",
                "completed_at",
            ).order_by("-created_at")[:5]
        )
        for job in recent_imports:
            job["job_id"] = str(job["job_id"])
            if job["created_at"]:
                job["created_at"] = job["created_at"].isoformat()
            if job["completed_at"]:
                job["completed_at"] = job["completed_at"].isoformat()

        # System Health Summary
        from apps.health.models import ServiceHealthRecord

        health_records = ServiceHealthRecord.objects.all()
        status_counts = health_records.values("status").annotate(count=Count("status"))
        summary = {row["status"]: row["count"] for row in status_counts}

        # Determine overall system state
        overall_status = ServiceHealthRecord.STATUS_HEALTHY
        if any(r.status == ServiceHealthRecord.STATUS_DOWN for r in health_records):
            overall_status = ServiceHealthRecord.STATUS_DOWN
        elif any(
            r.status
            in (ServiceHealthRecord.STATUS_ERROR, ServiceHealthRecord.STATUS_STALE)
            for r in health_records
        ):
            overall_status = ServiceHealthRecord.STATUS_ERROR
        elif any(
            r.status == ServiceHealthRecord.STATUS_WARNING for r in health_records
        ):
            overall_status = ServiceHealthRecord.STATUS_WARNING

        # Freshness ribbon timestamps
        last_sync_at = (
            SyncJob.objects.filter(status="completed")
            .values_list("completed_at", flat=True)
            .order_by("-completed_at")
            .first()
        )
        last_pipeline_at = (
            PipelineRun.objects.filter(run_state="completed")
            .values_list("updated_at", flat=True)
            .order_by("-updated_at")
            .first()
        )

        # Analytics freshness — check for most recent GSC sync if model exists
        last_analytics_at = None
        try:
            from apps.analytics.models import GSCSyncRun

            last_analytics_at = (
                GSCSyncRun.objects.filter(status="completed")
                .values_list("completed_at", flat=True)
                .order_by("-completed_at")
                .first()
            )
        except Exception:
            logger.debug("GSCSyncRun model not available, skipping analytics freshness")

        # Runtime mode from AppSetting
        runtime_mode = "CPU"
        try:
            from apps.core.models import AppSetting

            mode_setting = (
                AppSetting.objects.filter(key="system.runtime_mode")
                .values_list("value", flat=True)
                .first()
            )
            if mode_setting:
                runtime_mode = mode_setting
        except Exception:
            logger.debug("AppSetting table not available, using default runtime_mode")

        return Response(
            {
                "suggestion_counts": {
                    "pending": suggestion_counts.get("pending", 0),
                    "approved": suggestion_counts.get("approved", 0),
                    "rejected": suggestion_counts.get("rejected", 0),
                    "applied": suggestion_counts.get("applied", 0),
                    "total": sum(suggestion_counts.values()),
                },
                "content_count": content_count,
                "open_broken_links": open_broken_links,
                "last_sync": last_sync,
                "pipeline_runs": pipeline_runs,
                "recent_imports": recent_imports,
                "system_health": {
                    "status": overall_status,
                    "summary": summary,
                    "total_monitored": health_records.count(),
                },
                # Freshness ribbon
                "last_sync_at": last_sync_at.isoformat() if last_sync_at else None,
                "last_analytics_at": last_analytics_at.isoformat()
                if last_analytics_at
                else None,
                "last_pipeline_at": last_pipeline_at.isoformat()
                if last_pipeline_at
                else None,
                "runtime_mode": runtime_mode,
            }
        )


# ---------------------------------------------------------------------------
# Dashboard operating desk endpoints (Stage 3)
# ---------------------------------------------------------------------------


class TodayActionsView(APIView):
    """GET /api/dashboard/today-actions/

    Returns up to 5 priority-ranked action items for the current day.
    Priority waterfall: blocking alert > stale sync > pending review > idle.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        from apps.notifications.models import OperatorAlert
        from apps.suggestions.models import PipelineRun, Suggestion
        from apps.sync.models import SyncJob
        from django.utils import timezone

        actions: list[dict] = []
        now = timezone.now()

        # 1. Unacknowledged urgent/error alerts
        urgent_alerts = OperatorAlert.objects.filter(
            status="unread", severity__in=["urgent", "error"]
        ).order_by("-first_seen_at")[:3]
        for alert in urgent_alerts:
            actions.append(
                {
                    "title": alert.title,
                    "reason": f"Unresolved {alert.severity} alert since {alert.first_seen_at:%b %d}",
                    "route": f"/alerts/{alert.alert_id}",
                    "severity": alert.severity,
                    "isBlocking": alert.severity == "urgent",
                }
            )

        # 2. Stale sync (no sync in 48h)
        last_sync = (
            SyncJob.objects.filter(status="completed").order_by("-completed_at").first()
        )
        if last_sync and last_sync.completed_at:
            hours_since = (now - last_sync.completed_at).total_seconds() / 3600
            if hours_since > 48:
                days = int(hours_since // 24)
                actions.append(
                    {
                        "title": "Content is getting stale",
                        "reason": f"Last sync was {days} days ago. Run a fresh sync to catch new content.",
                        "route": "/jobs",
                        "severity": "warning",
                        "isBlocking": False,
                    }
                )
        elif not last_sync:
            actions.append(
                {
                    "title": "No content synced yet",
                    "reason": "Run your first content sync to get started.",
                    "route": "/jobs",
                    "severity": "warning",
                    "isBlocking": False,
                }
            )

        # 3. Pending suggestions waiting for review
        pending_count = Suggestion.objects.filter(status="pending").count()
        if pending_count > 20:
            actions.append(
                {
                    "title": f"{pending_count} suggestions waiting for review",
                    "reason": "Review and approve link suggestions to improve your internal linking.",
                    "route": "/review",
                    "severity": "info",
                    "isBlocking": False,
                }
            )

        # 4. Pipeline stale (no run in 14 days)
        last_run = (
            PipelineRun.objects.filter(run_state="completed")
            .order_by("-updated_at")
            .first()
        )
        if last_run and last_run.updated_at:
            days_since = (now - last_run.updated_at).days
            if days_since > 14:
                actions.append(
                    {
                        "title": "Pipeline hasn't run in a while",
                        "reason": f"Last pipeline run was {days_since} days ago. Run it to generate fresh suggestions.",
                        "route": "/jobs",
                        "severity": "info",
                        "isBlocking": False,
                    }
                )

        # 5. Zero suggestions on last run
        if last_run and last_run.suggestions_created == 0:
            actions.append(
                {
                    "title": "Last pipeline produced no suggestions",
                    "reason": "Check your settings — the pipeline may need tuning.",
                    "route": "/settings",
                    "deepLinkTarget": "ranking-weights",
                    "severity": "warning",
                    "isBlocking": False,
                }
            )

        return Response(actions[:5])


class WhatChangedView(APIView):
    """GET /api/dashboard/what-changed/

    Returns counts of changes in the last 24 hours plus autotuner outcomes.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        from apps.suggestions.models import PipelineRun, Suggestion
        from apps.sync.models import SyncJob
        from django.utils import timezone
        from datetime import timedelta

        since = timezone.now() - timedelta(hours=24)

        # Counts
        new_suggestions = Suggestion.objects.filter(created_at__gte=since).count()
        reviewed = Suggestion.objects.filter(reviewed_at__gte=since).count()
        synced_items = SyncJob.objects.filter(
            status="completed", completed_at__gte=since
        ).values_list("items_synced", flat=True)
        total_synced = sum(synced_items)
        pipeline_runs = PipelineRun.objects.filter(created_at__gte=since).count()

        # Autotuner outcomes (if any challenger was promoted/rolled back)
        autotuner_outcome = None
        try:
            from apps.suggestions.models import RankingChallenger

            recent_challenger = (
                RankingChallenger.objects.filter(updated_at__gte=since)
                .exclude(status="pending")
                .order_by("-updated_at")
                .first()
            )
            if recent_challenger:
                autotuner_outcome = {
                    "status": recent_challenger.status,
                    "label": recent_challenger.label
                    if hasattr(recent_challenger, "label")
                    else str(recent_challenger.pk),
                    "updated_at": recent_challenger.updated_at.isoformat(),
                }
        except Exception:
            logger.debug(
                "RankingChallenger model not available, skipping autotuner outcome"
            )

        return Response(
            {
                "period_hours": 24,
                "new_suggestions": new_suggestions,
                "reviewed": reviewed,
                "items_synced": total_synced,
                "pipeline_runs": pipeline_runs,
                "autotuner_outcome": autotuner_outcome,
            }
        )


class ResumeStateView(APIView):
    """GET /api/dashboard/resume-state/

    Returns interrupted pipeline runs, last review position, and missed
    tasks from the catch-up registry.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        from apps.suggestions.models import PipelineRun
        from apps.sync.models import SyncJob
        from django.utils import timezone

        # Interrupted pipeline runs
        interrupted_runs = list(
            PipelineRun.objects.filter(run_state="running")
            .values("run_id", "run_state", "created_at", "updated_at")
            .order_by("-created_at")[:3]
        )
        for run in interrupted_runs:
            run["run_id"] = str(run["run_id"])
            if run["created_at"]:
                run["created_at"] = run["created_at"].isoformat()
            if run["updated_at"]:
                run["updated_at"] = run["updated_at"].isoformat()

        # Resumable sync jobs
        resumable_syncs = list(
            SyncJob.objects.filter(is_resumable=True)
            .exclude(status="completed")
            .values(
                "job_id",
                "status",
                "source",
                "mode",
                "checkpoint_stage",
                "checkpoint_items_processed",
            )
            .order_by("-created_at")[:3]
        )
        for job in resumable_syncs:
            job["job_id"] = str(job["job_id"])

        # Missed tasks from catch-up registry
        missed_tasks: list[dict] = []
        try:
            from config.catchup_registry import CATCHUP_REGISTRY
            from django_celery_beat.models import PeriodicTask

            now = timezone.now()
            for task_name, entry in CATCHUP_REGISTRY.items():
                periodic = PeriodicTask.objects.filter(name=task_name).first()
                if periodic is None:
                    continue
                if periodic.last_run_at is None:
                    missed_tasks.append(
                        {
                            "task_name": task_name,
                            "weight_class": entry.weight_class,
                            "hours_overdue": None,
                            "reason": "Never ran",
                        }
                    )
                else:
                    hours_since = (now - periodic.last_run_at).total_seconds() / 3600
                    if hours_since > entry.threshold_hours:
                        missed_tasks.append(
                            {
                                "task_name": task_name,
                                "weight_class": entry.weight_class,
                                "hours_overdue": round(
                                    hours_since - entry.threshold_hours, 1
                                ),
                                "reason": f"Last ran {int(hours_since)}h ago (threshold: {int(entry.threshold_hours)}h)",
                            }
                        )
        except Exception:
            logger.debug("Catch-up registry unavailable, skipping missed tasks check")

        return Response(
            {
                "interrupted_runs": interrupted_runs,
                "resumable_syncs": resumable_syncs,
                "missed_tasks": missed_tasks,
            }
        )


class RuntimeSettingsView(APIView):
    """GET /api/settings/runtime/ — current runtime mode and state."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        from apps.core.models import AppSetting

        mode = "cpu"
        perf_mode = "balanced"
        try:
            mode_val = (
                AppSetting.objects.filter(key="system.runtime_mode")
                .values_list("value", flat=True)
                .first()
            )
            if mode_val:
                mode = mode_val
            perf_val = (
                AppSetting.objects.filter(key="system.performance_mode")
                .values_list("value", flat=True)
                .first()
            )
            if perf_val:
                perf_mode = perf_val
        except Exception:
            logger.debug(
                "AppSetting table not available, using default runtime and performance modes"
            )

        return Response(
            {
                "runtime_mode": mode,
                "performance_mode": perf_mode,
            }
        )


class RuntimeSwitchView(APIView):
    """POST /api/settings/runtime/switch/ — switch performance mode."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        from apps.core.models import AppSetting

        new_mode = request.data.get("mode")
        if new_mode not in ("safe", "balanced", "high"):
            return Response(
                {"error": "Invalid mode. Use 'safe', 'balanced', or 'high'."},
                status=400,
            )

        AppSetting.objects.update_or_create(
            key="system.performance_mode",
            defaults={
                "value": new_mode,
                "value_type": "str",
                "category": "performance",
            },
        )
        return Response({"performance_mode": new_mode})


class SystemMetricsView(APIView):
    """GET /api/system/metrics/ — live CPU, RAM, and GPU sampling for the dashboard.

    Combines psutil (CPU + RAM) and pynvml (GPU) into one lightweight call so
    the frontend can poll a single endpoint every 10 seconds. All fields are
    fail-soft: if a sampler is unavailable, the field is null rather than
    raising an error.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        cpu_percent = None
        ram_used_mb = None
        ram_total_mb = None
        ram_percent = None
        try:
            import psutil

            # Non-blocking CPU sample (0s interval avoids a 1s delay per request).
            cpu_percent = psutil.cpu_percent(interval=None)
            vm = psutil.virtual_memory()
            ram_used_mb = round(vm.used / (1024 * 1024))
            ram_total_mb = round(vm.total / (1024 * 1024))
            ram_percent = vm.percent
        except Exception:
            logger.debug("psutil unavailable; CPU/RAM fields returned as null")

        gpu = {
            "available": False,
            "temp_c": None,
            "vram_used_mb": None,
            "vram_total_mb": None,
            "vram_percent": None,
            "utilization_pct": None,
        }
        try:
            import pynvml

            pynvml.nvmlInit()
            handle = pynvml.nvmlDeviceGetHandleByIndex(0)
            temp = pynvml.nvmlDeviceGetTemperature(handle, pynvml.NVML_TEMPERATURE_GPU)
            mem_info = pynvml.nvmlDeviceGetMemoryInfo(handle)
            util = pynvml.nvmlDeviceGetUtilizationRates(handle)
            pynvml.nvmlShutdown()

            vram_total_mb = round(mem_info.total / (1024 * 1024))
            vram_used_mb = round(mem_info.used / (1024 * 1024))
            gpu = {
                "available": True,
                "temp_c": temp,
                "vram_used_mb": vram_used_mb,
                "vram_total_mb": vram_total_mb,
                "vram_percent": round(100.0 * vram_used_mb / vram_total_mb, 1)
                if vram_total_mb
                else None,
                "utilization_pct": util.gpu,
            }
        except Exception:
            logger.debug("pynvml unavailable or GPU missing; returning available=False")

        return Response(
            {
                "cpu_percent": cpu_percent,
                "ram_used_mb": ram_used_mb,
                "ram_total_mb": ram_total_mb,
                "ram_percent": ram_percent,
                "gpu": gpu,
            }
        )


class RuntimeConfigView(APIView):
    """GET/POST /api/settings/runtime-config/ — runtime tunables that a noob user may safely adjust.

    Currently exposes:
      - system.embedding_batch_size  (int, 8..128)  — live; read at each pipeline run.
      - system.celery_concurrency    (int, 1..8)    — stored; applies after container restart.

    Stored in AppSetting (category="performance"). The performance-mode switch lives at
    /api/settings/runtime/ — this endpoint is a separate namespace for tunables.
    """

    permission_classes = [IsAuthenticated]

    BATCH_SIZE_MIN = 8
    BATCH_SIZE_MAX = 128
    CONCURRENCY_MIN = 1
    CONCURRENCY_MAX = 8

    def _read_int(self, key, default):
        from apps.core.models import AppSetting

        val = (
            AppSetting.objects.filter(key=key).values_list("value", flat=True).first()
        )
        if val is None:
            return default
        try:
            return int(val)
        except (TypeError, ValueError):
            return default

    def get(self, request):
        from django.conf import settings as django_conf

        default_batch = int(getattr(django_conf, "EMBEDDING_BATCH_SIZE", 32) or 32)
        default_conc = int(getattr(django_conf, "CELERY_WORKER_CONCURRENCY", 2) or 2)
        return Response(
            {
                "embedding_batch_size": self._read_int(
                    "system.embedding_batch_size", default_batch
                ),
                "celery_concurrency": self._read_int(
                    "system.celery_concurrency", default_conc
                ),
                "embedding_batch_size_range": [
                    self.BATCH_SIZE_MIN,
                    self.BATCH_SIZE_MAX,
                ],
                "celery_concurrency_range": [
                    self.CONCURRENCY_MIN,
                    self.CONCURRENCY_MAX,
                ],
                "celery_concurrency_requires_restart": True,
            }
        )

    def post(self, request):
        from apps.core.models import AppSetting

        updated = {}
        errors = {}
        data = request.data or {}

        if "embedding_batch_size" in data:
            try:
                bs = int(data["embedding_batch_size"])
            except (TypeError, ValueError):
                errors["embedding_batch_size"] = "Must be an integer."
            else:
                if not (self.BATCH_SIZE_MIN <= bs <= self.BATCH_SIZE_MAX):
                    errors["embedding_batch_size"] = (
                        f"Must be between {self.BATCH_SIZE_MIN} and {self.BATCH_SIZE_MAX}."
                    )
                else:
                    AppSetting.objects.update_or_create(
                        key="system.embedding_batch_size",
                        defaults={
                            "value": str(bs),
                            "value_type": "int",
                            "category": "performance",
                        },
                    )
                    updated["embedding_batch_size"] = bs

        if "celery_concurrency" in data:
            try:
                cc = int(data["celery_concurrency"])
            except (TypeError, ValueError):
                errors["celery_concurrency"] = "Must be an integer."
            else:
                if not (self.CONCURRENCY_MIN <= cc <= self.CONCURRENCY_MAX):
                    errors["celery_concurrency"] = (
                        f"Must be between {self.CONCURRENCY_MIN} and {self.CONCURRENCY_MAX}."
                    )
                else:
                    AppSetting.objects.update_or_create(
                        key="system.celery_concurrency",
                        defaults={
                            "value": str(cc),
                            "value_type": "int",
                            "category": "performance",
                        },
                    )
                    updated["celery_concurrency"] = cc

        if errors:
            return Response({"errors": errors, "updated": updated}, status=400)
        return Response({"updated": updated})


class SafeModeBootView(APIView):
    """POST /api/system/safe-mode-boot/ — arm a flag that forces 'safe' mode on next backend startup.

    Use case: the app is misbehaving under High Performance mode and the user wants a
    one-shot recovery. Reading & clearing happens in apps.core.apps.CoreConfig.ready().
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        from apps.core.models import AppSetting

        AppSetting.objects.update_or_create(
            key="system.boot_safe_once",
            defaults={
                "value": "true",
                "value_type": "bool",
                "category": "performance",
            },
        )
        return Response({"armed": True, "applies_on": "next_backend_restart"})

    def get(self, request):
        from apps.core.models import AppSetting

        val = (
            AppSetting.objects.filter(key="system.boot_safe_once")
            .values_list("value", flat=True)
            .first()
        )
        return Response({"armed": str(val).lower() == "true"})

    def delete(self, request):
        from apps.core.models import AppSetting

        AppSetting.objects.filter(key="system.boot_safe_once").delete()
        return Response({"armed": False})


class JobQueueView(APIView):
    """GET /api/jobs/queue/ — active and queued tasks with ETA and lock status."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        from apps.suggestions.models import PipelineRun
        from apps.sync.models import SyncJob
        from apps.pipeline.services.task_lock import get_active_locks
        from apps.pipeline.services.eta_estimator import estimate_eta

        locks = get_active_locks()

        # Active pipeline runs
        active_runs = list(
            PipelineRun.objects.filter(run_state__in=["queued", "running"])
            .values(
                "run_id",
                "run_state",
                "rerun_mode",
                "suggestions_created",
                "destinations_processed",
                "phase_log",
                "celery_task_id",
                "created_at",
                "updated_at",
            )
            .order_by("created_at")[:20]
        )
        for run in active_runs:
            run["run_id"] = str(run["run_id"])
            run["type"] = "pipeline"
            if run["created_at"]:
                run["created_at"] = run["created_at"].isoformat()
            if run["updated_at"]:
                run["updated_at"] = run["updated_at"].isoformat()
            eta = estimate_eta("pipeline.run_pipeline")
            run["estimated_remaining_seconds"] = eta.total_seconds() if eta else None

        # Active sync jobs
        active_syncs = list(
            SyncJob.objects.filter(status__in=["pending", "running"])
            .values(
                "job_id",
                "status",
                "source",
                "mode",
                "progress",
                "items_synced",
                "checkpoint_stage",
                "is_resumable",
                "created_at",
                "started_at",
            )
            .order_by("created_at")[:20]
        )
        for job in active_syncs:
            job["job_id"] = str(job["job_id"])
            job["type"] = "sync"
            if job["created_at"]:
                job["created_at"] = job["created_at"].isoformat()
            if job["started_at"]:
                job["started_at"] = job["started_at"].isoformat()
            eta = estimate_eta("nightly-xenforo-sync", mode=job.get("mode"))
            job["estimated_remaining_seconds"] = eta.total_seconds() if eta else None

        return Response(
            {
                "items": active_runs + active_syncs,
                "locks": locks,
            }
        )


class JobQuarantineView(APIView):
    """GET /api/jobs/quarantine/ — quarantined pipeline runs."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        from apps.suggestions.models import PipelineRun

        quarantined = list(
            PipelineRun.objects.filter(is_quarantined=True)
            .values(
                "run_id",
                "run_state",
                "rerun_mode",
                "error_message",
                "phase_log",
                "created_at",
                "updated_at",
            )
            .order_by("-updated_at")[:50]
        )
        for run in quarantined:
            run["run_id"] = str(run["run_id"])
            if run["created_at"]:
                run["created_at"] = run["created_at"].isoformat()
            if run["updated_at"]:
                run["updated_at"] = run["updated_at"].isoformat()

        return Response(quarantined)


class HelperNodeListView(APIView):
    """GET/POST /api/settings/helpers/ — list and register helper nodes."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        from apps.core.models import HelperNode

        nodes = HelperNode.objects.all()
        data = [
            {
                "id": n.id,
                "name": n.name,
                "role": n.role,
                "status": n.status,
                "capabilities": n.capabilities,
                "allowed_queues": n.allowed_queues,
                "allowed_job_types": n.allowed_job_types,
                "time_policy": n.time_policy,
                "max_concurrency": n.max_concurrency,
                "cpu_cap_pct": n.cpu_cap_pct,
                "ram_cap_pct": n.ram_cap_pct,
                "last_heartbeat": n.last_heartbeat.isoformat()
                if n.last_heartbeat
                else None,
            }
            for n in nodes
        ]
        return Response(data)

    def post(self, request):
        import hashlib

        from apps.core.models import HelperNode

        name = request.data.get("name")
        token = request.data.get("token")
        if not name or not token:
            return Response({"error": "name and token are required"}, status=400)

        token_hash = hashlib.sha256(token.encode()).hexdigest()
        node, created = HelperNode.objects.get_or_create(
            name=name,
            defaults={
                "token_hash": token_hash,
                "role": request.data.get("role", "worker"),
                "capabilities": request.data.get("capabilities", {}),
                "allowed_queues": request.data.get("allowed_queues", []),
                "allowed_job_types": request.data.get("allowed_job_types", []),
                "time_policy": request.data.get("time_policy", "anytime"),
                "max_concurrency": request.data.get("max_concurrency", 2),
                "cpu_cap_pct": request.data.get("cpu_cap_pct", 60),
                "ram_cap_pct": request.data.get("ram_cap_pct", 60),
            },
        )
        if not created:
            return Response(
                {"error": "A node with this name already exists"}, status=409
            )

        return Response({"id": node.id, "name": node.name}, status=201)


class HelperNodeDetailView(APIView):
    """PATCH/DELETE /api/settings/helpers/<id>/ — update or remove a helper node."""

    permission_classes = [IsAuthenticated]

    def patch(self, request, pk):
        from apps.core.models import HelperNode

        try:
            node = HelperNode.objects.get(pk=pk)
        except HelperNode.DoesNotExist:
            return Response({"error": "Not found"}, status=404)

        for field in (
            "role",
            "status",
            "time_policy",
            "max_concurrency",
            "cpu_cap_pct",
            "ram_cap_pct",
        ):
            if field in request.data:
                setattr(node, field, request.data[field])
        for json_field in ("capabilities", "allowed_queues", "allowed_job_types"):
            if json_field in request.data:
                setattr(node, json_field, request.data[json_field])
        node.save()
        return Response({"id": node.id, "name": node.name, "status": node.status})

    def delete(self, request, pk):
        from apps.core.models import HelperNode

        deleted, _ = HelperNode.objects.filter(pk=pk).delete()
        if not deleted:
            return Response({"error": "Not found"}, status=404)
        return Response(status=204)


class ClickDistanceSettingsView(APIView):
    """
    GET /api/settings/click-distance/
    PUT /api/settings/click-distance/
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(get_click_distance_settings())

    def put(self, request):
        from apps.core.models import AppSetting

        current = get_click_distance_settings()
        try:
            validated = _validate_click_distance_settings(request.data, current)
        except ValueError as exc:
            return Response({"error": str(exc)}, status=400)

        for key, value in validated.items():
            AppSetting.objects.update_or_create(
                key=f"click_distance.{key}", defaults={"value": str(value)}
            )

        return Response(validated)


class ClickDistanceRecalculateView(APIView):
    """
    POST /api/settings/click-distance/recalculate/
    """

    throttle_classes = [_WeightRecalcThrottle]

    def post(self, request):
        """Trigger bulk recalculation of click distance scores."""
        from apps.pipeline.tasks import recalculate_click_distance_task

        task = recalculate_click_distance_task.delay()
        return Response({"status": "queued", "job_id": task.id})


class FeedbackRerankSettingsView(APIView):
    """
    GET  /api/settings/explore-exploit/ - returns FR-013 explore/exploit settings
    PUT  /api/settings/explore-exploit/ - validates and persists those settings
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(get_feedback_rerank_settings())

    def put(self, request):
        from apps.core.models import AppSetting

        current = get_feedback_rerank_settings()
        try:
            validated = _validate_feedback_rerank_settings(
                request.data, current=current
            )
        except ValueError as exc:
            return Response({"error": str(exc)}, status=400)

        rows = {
            "explore_exploit.enabled": {
                "value": "true" if validated["enabled"] else "false",
                "value_type": "bool",
                "description": "Whether feedback-driven explore/exploit reranking is active.",
            },
            "explore_exploit.ranking_weight": {
                "value": str(validated["ranking_weight"]),
                "value_type": "float",
                "description": "Multiplier weight for the feedback-driven score component.",
            },
            "explore_exploit.exploration_rate": {
                "value": str(validated["exploration_rate"]),
                "value_type": "float",
                "description": "k factor for the UCB1 exploration boost.",
            },
        }

        for key, row in rows.items():
            AppSetting.objects.update_or_create(
                key=key,
                defaults={
                    "value": row["value"],
                    "value_type": row["value_type"],
                    "category": "ml",
                    "description": row["description"],
                    "is_secret": False,
                },
            )

        return Response(validated)


class ClusteringSettingsView(APIView):
    """
    GET  /api/settings/clustering/ - returns FR-014 clustering configuration
    PUT  /api/settings/clustering/ - validates and persists clustering configuration
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(get_clustering_settings())

    def put(self, request):
        from apps.core.models import AppSetting

        current = get_clustering_settings()
        try:
            validated = _validate_clustering_settings(request.data, current)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=400)

        rows = {
            "clustering.enabled": {
                "value": "true" if validated["enabled"] else "false",
                "value_type": "bool",
                "description": "Whether to cluster near-duplicate destinations and suppress non-canonicals.",
            },
            "clustering.similarity_threshold": {
                "value": str(validated["similarity_threshold"]),
                "value_type": "float",
                "description": "Cosine distance threshold for near-duplicate grouping (lower = stricter).",
            },
            "clustering.suppression_penalty": {
                "value": str(validated["suppression_penalty"]),
                "value_type": "float",
                "description": "Fixed score penalty applied to non-canonical cluster members.",
            },
        }

        for key, row in rows.items():
            AppSetting.objects.update_or_create(
                key=key,
                defaults={
                    "value": row["value"],
                    "value_type": row["value_type"],
                    "category": "ml",
                    "description": row["description"],
                    "is_secret": False,
                },
            )
        return Response(validated)


class ClusteringRecalculateView(APIView):
    """POST /api/settings/clustering/recalculate/ - run batch clustering pass."""

    throttle_classes = [_WeightRecalcThrottle]

    def post(self, request):
        from apps.pipeline.tasks import run_clustering_pass

        job_id = str(uuid.uuid4())
        run_clustering_pass.delay(job_id=job_id)
        return Response({"job_id": job_id}, status=202)


class SlateDiversitySettingsView(APIView):
    """
    GET  /api/settings/slate-diversity/ - returns FR-015 slate diversity settings
    PUT  /api/settings/slate-diversity/ - validates and persists those settings
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(get_slate_diversity_settings())

    def put(self, request):
        from apps.core.models import AppSetting

        current = get_slate_diversity_settings()
        try:
            validated = _validate_slate_diversity_settings(request.data, current)
        except ValueError as exc:
            return Response({"error": str(exc)}, status=400)

        rows = {
            "slate_diversity.enabled": {
                "value": "true" if validated["enabled"] else "false",
                "value_type": "bool",
                "description": "Whether FR-015 MMR slate diversity reranking is active.",
            },
            "slate_diversity.diversity_lambda": {
                "value": str(validated["diversity_lambda"]),
                "value_type": "float",
                "description": "MMR lambda: 1.0 = pure relevance, 0.0 = pure diversity.",
            },
            "slate_diversity.score_window": {
                "value": str(validated["score_window"]),
                "value_type": "float",
                "description": "Max score gap from top candidate for MMR eligibility.",
            },
            "slate_diversity.similarity_cap": {
                "value": str(validated["similarity_cap"]),
                "value_type": "float",
                "description": "Cosine similarity above which two destinations are flagged as redundant.",
            },
        }

        for key, row in rows.items():
            AppSetting.objects.update_or_create(
                key=key,
                defaults={
                    "value": row["value"],
                    "value_type": row["value_type"],
                    "category": "ml",
                    "description": row["description"],
                    "is_secret": False,
                },
            )

        return Response(validated)


class WeightTuneTriggerView(APIView):
    """POST /api/settings/weight-tune/trigger/ — manually trigger a FR-018 weight-tune run."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        from apps.pipeline.tasks import monthly_weight_tune

        task = monthly_weight_tune.delay()
        return Response(
            {"detail": "Weight-tune task queued.", "task_id": task.id}, status=202
        )


class ChallengerEvaluateView(APIView):
    """POST /api/settings/weight-tune/evaluate/<run_id>/ — manually evaluate a pending challenger."""

    permission_classes = [IsAuthenticated]
    throttle_classes = [_ChallengerEvalThrottle]

    def post(self, request, run_id):
        from apps.pipeline.tasks import evaluate_weight_challenger
        from apps.suggestions.models import RankingChallenger

        if not RankingChallenger.objects.filter(
            run_id=run_id, status="pending"
        ).exists():
            return Response(
                {"detail": f"No pending challenger with run_id '{run_id}'."},
                status=404,
            )

        task = evaluate_weight_challenger.delay(run_id=run_id)
        return Response(
            {"detail": "Evaluation queued.", "task_id": task.id}, status=202
        )


class GraphCandidateSettingsView(APIView):
    """
    GET  /api/settings/graph-candidate/ - returns FR-021 graph-walk settings
    PUT  /api/settings/graph-candidate/ - validates and persists those settings
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(get_graph_candidate_settings())

    def put(self, request):
        from apps.core.models import AppSetting

        current = get_graph_candidate_settings()
        try:
            validated = _validate_graph_candidate_settings(request.data, current)
        except ValueError as exc:
            return Response({"error": str(exc)}, status=400)

        rows = {
            "graph_candidate.enabled": {
                "value": "true" if validated["enabled"] else "false",
                "value_type": "bool",
                "description": "Whether FR-021 Pixie walk candidate generation is active.",
            },
            "graph_candidate.walk_steps_per_entity": {
                "value": str(validated["walk_steps_per_entity"]),
                "value_type": "int",
                "description": "Number of Pixie random walk steps to perform per query entity.",
            },
            "graph_candidate.min_stable_candidates": {
                "value": str(validated["min_stable_candidates"]),
                "value_type": "int",
                "description": "Minimum number of stable candidates to find before early stopping.",
            },
            "graph_candidate.min_visit_threshold": {
                "value": str(validated["min_visit_threshold"]),
                "value_type": "int",
                "description": "Minimum walk visits required for a node to be considered stable.",
            },
            "graph_candidate.top_k_candidates": {
                "value": str(validated["top_k_candidates"]),
                "value_type": "int",
                "description": "Max number of top-visited candidates to return to the pipeline.",
            },
            "graph_candidate.top_n_entities_per_article": {
                "value": str(validated["top_n_entities_per_article"]),
                "value_type": "int",
                "description": "Max number of top entities to extract per article for graph linking.",
            },
        }

        for key, row in rows.items():
            AppSetting.objects.update_or_create(
                key=key,
                defaults={
                    "value": row["value"],
                    "value_type": row["value_type"],
                    "category": "ml",
                    "description": row["description"],
                    "is_secret": False,
                },
            )
        return Response(validated)


class ValueModelSettingsView(APIView):
    """
    GET  /api/settings/value-model/ - returns FR-021 value model settings
    PUT  /api/settings/value-model/ - validates and persists those settings
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(get_value_model_settings())

    def put(self, request):
        from apps.core.models import AppSetting

        current = get_value_model_settings()
        try:
            validated = _validate_value_model_settings(request.data, current)
        except ValueError as exc:
            return Response({"error": str(exc)}, status=400)

        rows = {
            "value_model.enabled": {
                "value": "true" if validated["enabled"] else "false",
                "value_type": "bool",
                "description": "Whether FR-021 Instagram-style value pre-scoring is active.",
            },
            "value_model.w_relevance": {
                "value": str(validated["w_relevance"]),
                "value_type": "float",
                "description": "Value component weight: semantic relevance.",
            },
            "value_model.w_traffic": {
                "value": str(validated["w_traffic"]),
                "value_type": "float",
                "description": "Value component weight: historical traffic.",
            },
            "value_model.w_freshness": {
                "value": str(validated["w_freshness"]),
                "value_type": "float",
                "description": "Value component weight: content freshness.",
            },
            "value_model.w_authority": {
                "value": str(validated["w_authority"]),
                "value_type": "float",
                "description": "Value component weight: content authority.",
            },
            "value_model.w_penalty": {
                "value": str(validated["w_penalty"]),
                "value_type": "float",
                "description": "Value component weight: blocklist/penalty sink.",
            },
            "value_model.traffic_lookback_days": {
                "value": str(validated["traffic_lookback_days"]),
                "value_type": "int",
                "description": "Number of days of traffic history to look back.",
            },
            "value_model.traffic_fallback_value": {
                "value": str(validated["traffic_fallback_value"]),
                "value_type": "float",
                "description": "Default traffic score to use if no data exists.",
            },
            "value_model.engagement_signal_enabled": {
                "value": "true" if validated["engagement_signal_enabled"] else "false",
                "value_type": "bool",
                "description": "Whether FR-024 engagement (read-through rate) signal is active.",
            },
            "value_model.w_engagement": {
                "value": str(validated["w_engagement"]),
                "value_type": "float",
                "description": "Value component weight: engagement / read-through rate signal.",
            },
            "value_model.engagement_lookback_days": {
                "value": str(validated["engagement_lookback_days"]),
                "value_type": "int",
                "description": "Rolling window (days) for averaging SearchMetric engagement rows.",
            },
            "value_model.engagement_words_per_minute": {
                "value": str(validated["engagement_words_per_minute"]),
                "value_type": "int",
                "description": "WPM constant used to estimate article read time.",
            },
            "value_model.engagement_cap_ratio": {
                "value": str(validated["engagement_cap_ratio"]),
                "value_type": "float",
                "description": "Cap applied to raw read-through rate before site-wide normalization.",
            },
            "value_model.engagement_fallback_value": {
                "value": str(validated["engagement_fallback_value"]),
                "value_type": "float",
                "description": "Fallback signal value when no SearchMetric rows exist for a destination.",
            },
            # FR-023 hot decay signal
            "value_model.hot_decay_enabled": {
                "value": "true" if validated["hot_decay_enabled"] else "false",
                "value_type": "bool",
                "description": "Whether FR-023 Reddit Hot decay replaces flat traffic averaging.",
            },
            "value_model.hot_gravity": {
                "value": str(validated["hot_gravity"]),
                "value_type": "float",
                "description": "Time-decay gravity factor for the Reddit Hot formula.",
            },
            "value_model.hot_clicks_weight": {
                "value": str(validated["hot_clicks_weight"]),
                "value_type": "float",
                "description": "Weight applied to click volume in hot score calculation.",
            },
            "value_model.hot_impressions_weight": {
                "value": str(validated["hot_impressions_weight"]),
                "value_type": "float",
                "description": "Weight applied to impression volume in hot score calculation.",
            },
            "value_model.hot_lookback_days": {
                "value": str(validated["hot_lookback_days"]),
                "value_type": "int",
                "description": "Number of days of daily traffic data to feed into hot scoring.",
            },
            # FR-025 co-occurrence signal
            "value_model.co_occurrence_signal_enabled": {
                "value": "true"
                if validated["co_occurrence_signal_enabled"]
                else "false",
                "value_type": "bool",
                "description": "Whether the FR-025 session co-occurrence signal is active.",
            },
            "value_model.w_cooccurrence": {
                "value": str(validated["w_cooccurrence"]),
                "value_type": "float",
                "description": "Value component weight: session co-occurrence signal.",
            },
            "value_model.co_occurrence_fallback_value": {
                "value": str(validated["co_occurrence_fallback_value"]),
                "value_type": "float",
                "description": "Fallback signal value when no co-occurrence pair exists.",
            },
            "value_model.co_occurrence_min_co_sessions": {
                "value": str(validated["co_occurrence_min_co_sessions"]),
                "value_type": "int",
                "description": "Minimum co-session count for a pair to be used in scoring.",
            },
        }

        for key, row in rows.items():
            AppSetting.objects.update_or_create(
                key=key,
                defaults={
                    "value": row["value"],
                    "value_type": row["value_type"],
                    "category": "ml",
                    "description": row["description"],
                    "is_secret": False,
                },
            )
        return Response(validated)


DEFAULT_SPAM_GUARD_SETTINGS: dict[str, int] = {
    "max_existing_links_per_host": 2,
    "max_anchor_words": 4,
    "paragraph_window": 3,
}


def get_spam_guard_settings() -> dict[str, int]:
    """Return current spam-guard limits, falling back to patent-backed defaults."""

    def _read_int(key: str, default: int) -> int:
        raw = _get_app_setting_value(key)
        try:
            return int(raw) if raw is not None else default
        except (TypeError, ValueError):
            return default

    return {
        "max_existing_links_per_host": _read_int(
            "spam_guards.max_existing_links_per_host",
            DEFAULT_SPAM_GUARD_SETTINGS["max_existing_links_per_host"],
        ),
        "max_anchor_words": _read_int(
            "spam_guards.max_anchor_words",
            DEFAULT_SPAM_GUARD_SETTINGS["max_anchor_words"],
        ),
        "paragraph_window": _read_int(
            "spam_guards.paragraph_window",
            DEFAULT_SPAM_GUARD_SETTINGS["paragraph_window"],
        ),
    }


def _validate_spam_guard_settings(payload: dict, current: dict) -> dict[str, int]:
    """Validate and clamp spam-guard settings."""

    def _get_int(key: str, lo: int, hi: int) -> int:
        val = payload.get(key, current.get(key))
        try:
            return max(lo, min(hi, int(val)))
        except (TypeError, ValueError):
            return current.get(key, DEFAULT_SPAM_GUARD_SETTINGS[key])

    return {
        "max_existing_links_per_host": _get_int("max_existing_links_per_host", 1, 20),
        "max_anchor_words": _get_int("max_anchor_words", 1, 10),
        "paragraph_window": _get_int("paragraph_window", 1, 10),
    }


class SpamGuardSettingsView(APIView):
    """
    GET  /api/settings/spam-guards/  — returns current spam-guard limits
    PUT  /api/settings/spam-guards/  — validates and persists new limits

    Controls three pipeline guards that prevent the tool from producing
    spammy internal-link suggestions (backed by Ntoulas et al., US8380722B2,
    US8577893B1, and the 2024 Google API leak findings):

    * max_existing_links_per_host — skip a host page if it already has this
      many outgoing body links (default 3).
    * max_anchor_words — reject anchor text longer than this many words
      (default 4, matching Google's 2–5 word recommendation).
    * paragraph_window — block a second suggestion within this many sentence
      positions of an already-selected one on the same host (default 3).
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(get_spam_guard_settings())

    def put(self, request):
        from apps.core.models import AppSetting

        current = get_spam_guard_settings()
        try:
            validated = _validate_spam_guard_settings(request.data, current)
        except ValueError as exc:
            return Response({"error": str(exc)}, status=400)

        rows = {
            "spam_guards.max_existing_links_per_host": {
                "value": str(validated["max_existing_links_per_host"]),
                "value_type": "int",
                "description": (
                    "Maximum number of existing outgoing body links a host page may "
                    "already carry before the pipeline skips it. "
                    "Default 3 — Ntoulas et al. anchor-word fraction research (US20060184500A1)."
                ),
            },
            "spam_guards.max_anchor_words": {
                "value": str(validated["max_anchor_words"]),
                "value_type": "int",
                "description": (
                    "Maximum number of words allowed in a suggested anchor phrase. "
                    "Default 4 — Google recommends 2–5 words; US8380722B2 confirms "
                    "anchors are 'usually short and descriptive'."
                ),
            },
            "spam_guards.paragraph_window": {
                "value": str(validated["paragraph_window"]),
                "value_type": "int",
                "description": (
                    "Sentence-position window for paragraph-cluster detection. "
                    "Two suggestions within this many sentences of each other on "
                    "the same host are treated as the same paragraph — only the "
                    "higher-scoring one is kept. Default 3 — US8577893B1."
                ),
            },
        }

        for key, row in rows.items():
            AppSetting.objects.update_or_create(
                key=key,
                defaults={
                    "value": row["value"],
                    "value_type": row["value_type"],
                    "category": "anchor",
                    "description": row["description"],
                    "is_secret": False,
                },
            )
        return Response(validated)


class GraphRebuildView(APIView):
    """POST /api/settings/graph/rebuild/ - manual trigger for bipartite graph refresh."""

    permission_classes = [IsAuthenticated]
    throttle_classes = [_GraphRebuildThrottle]

    def post(self, request):
        from apps.pipeline.tasks import dispatch_graph_rebuild

        job_id = str(uuid.uuid4())
        payload = dispatch_graph_rebuild(job_id=job_id)
        return Response(payload, status=202)


def _read_graph_candidate_settings() -> dict[str, float | int | bool]:
    def _read_float(key: str, default: float) -> float:
        raw = _get_app_setting_value(key)
        try:
            return float(raw) if raw is not None else default
        except (TypeError, ValueError):
            return default

    def _read_int(key: str, default: int) -> int:
        raw = _get_app_setting_value(key)
        try:
            return int(raw) if raw is not None else default
        except (TypeError, ValueError):
            return default

    def _read_bool(key: str, default: bool) -> bool:
        raw = _get_app_setting_value(key)
        if raw is None:
            return default
        return str(raw).strip().lower() in {"1", "true", "yes", "on"}

    return {
        "enabled": _read_bool(
            "graph_candidate.enabled", DEFAULT_GRAPH_CANDIDATE_SETTINGS["enabled"]
        ),
        "walk_steps_per_entity": _read_int(
            "graph_candidate.walk_steps_per_entity",
            DEFAULT_GRAPH_CANDIDATE_SETTINGS["walk_steps_per_entity"],
        ),
        "min_stable_candidates": _read_int(
            "graph_candidate.min_stable_candidates",
            DEFAULT_GRAPH_CANDIDATE_SETTINGS["min_stable_candidates"],
        ),
        "min_visit_threshold": _read_int(
            "graph_candidate.min_visit_threshold",
            DEFAULT_GRAPH_CANDIDATE_SETTINGS["min_visit_threshold"],
        ),
        "top_k_candidates": _read_int(
            "graph_candidate.top_k_candidates",
            DEFAULT_GRAPH_CANDIDATE_SETTINGS["top_k_candidates"],
        ),
        "top_n_entities_per_article": _read_int(
            "graph_candidate.top_n_entities_per_article",
            DEFAULT_GRAPH_CANDIDATE_SETTINGS["top_n_entities_per_article"],
        ),
    }


def _validate_graph_candidate_settings(payload: dict, current: dict) -> dict:
    def _get_float(key: str) -> float:
        val = payload.get(key, current.get(key))
        try:
            return float(val)
        except (TypeError, ValueError):
            return float(current.get(key, 0.0))

    def _get_int(key: str) -> int:
        val = payload.get(key, current.get(key))
        try:
            return int(val)
        except (TypeError, ValueError):
            return int(current.get(key, 0))

    def _get_bool(key: str) -> bool:
        val = payload.get(key, current.get(key))
        if isinstance(val, bool):
            return val
        return str(val).strip().lower() in {"1", "true", "yes", "on"}

    return {
        "enabled": _get_bool("enabled"),
        "walk_steps_per_entity": max(10, min(10000, _get_int("walk_steps_per_entity"))),
        "min_stable_candidates": max(5, min(500, _get_int("min_stable_candidates"))),
        "min_visit_threshold": max(1, min(20, _get_int("min_visit_threshold"))),
        "top_k_candidates": max(10, min(1000, _get_int("top_k_candidates"))),
        "top_n_entities_per_article": max(
            1, min(100, _get_int("top_n_entities_per_article"))
        ),
    }


def _read_value_model_settings() -> dict[str, float | int | bool]:
    def _read_float(key: str, default: float) -> float:
        raw = _get_app_setting_value(key)
        try:
            return float(raw) if raw is not None else default
        except (TypeError, ValueError):
            return default

    def _read_int(key: str, default: int) -> int:
        raw = _get_app_setting_value(key)
        try:
            return int(raw) if raw is not None else default
        except (TypeError, ValueError):
            return default

    def _read_bool(key: str, default: bool) -> bool:
        raw = _get_app_setting_value(key)
        if raw is None:
            return default
        return str(raw).strip().lower() in {"1", "true", "yes", "on"}

    return {
        "enabled": _read_bool(
            "value_model.enabled", DEFAULT_VALUE_MODEL_SETTINGS["enabled"]
        ),
        "w_relevance": _read_float(
            "value_model.w_relevance", DEFAULT_VALUE_MODEL_SETTINGS["w_relevance"]
        ),
        "w_traffic": _read_float(
            "value_model.w_traffic", DEFAULT_VALUE_MODEL_SETTINGS["w_traffic"]
        ),
        "w_freshness": _read_float(
            "value_model.w_freshness", DEFAULT_VALUE_MODEL_SETTINGS["w_freshness"]
        ),
        "w_authority": _read_float(
            "value_model.w_authority", DEFAULT_VALUE_MODEL_SETTINGS["w_authority"]
        ),
        "w_penalty": _read_float(
            "value_model.w_penalty", DEFAULT_VALUE_MODEL_SETTINGS["w_penalty"]
        ),
        "traffic_lookback_days": _read_int(
            "value_model.traffic_lookback_days",
            DEFAULT_VALUE_MODEL_SETTINGS["traffic_lookback_days"],
        ),
        "traffic_fallback_value": _read_float(
            "value_model.traffic_fallback_value",
            DEFAULT_VALUE_MODEL_SETTINGS["traffic_fallback_value"],
        ),
        "engagement_signal_enabled": _read_bool(
            "value_model.engagement_signal_enabled",
            DEFAULT_VALUE_MODEL_SETTINGS["engagement_signal_enabled"],
        ),
        "w_engagement": _read_float(
            "value_model.w_engagement", DEFAULT_VALUE_MODEL_SETTINGS["w_engagement"]
        ),
        "engagement_lookback_days": _read_int(
            "value_model.engagement_lookback_days",
            DEFAULT_VALUE_MODEL_SETTINGS["engagement_lookback_days"],
        ),
        "engagement_words_per_minute": _read_int(
            "value_model.engagement_words_per_minute",
            DEFAULT_VALUE_MODEL_SETTINGS["engagement_words_per_minute"],
        ),
        "engagement_cap_ratio": _read_float(
            "value_model.engagement_cap_ratio",
            DEFAULT_VALUE_MODEL_SETTINGS["engagement_cap_ratio"],
        ),
        "engagement_fallback_value": _read_float(
            "value_model.engagement_fallback_value",
            DEFAULT_VALUE_MODEL_SETTINGS["engagement_fallback_value"],
        ),
        # FR-023 hot decay signal
        "hot_decay_enabled": _read_bool(
            "value_model.hot_decay_enabled",
            DEFAULT_VALUE_MODEL_SETTINGS["hot_decay_enabled"],
        ),
        "hot_gravity": _read_float(
            "value_model.hot_gravity", DEFAULT_VALUE_MODEL_SETTINGS["hot_gravity"]
        ),
        "hot_clicks_weight": _read_float(
            "value_model.hot_clicks_weight",
            DEFAULT_VALUE_MODEL_SETTINGS["hot_clicks_weight"],
        ),
        "hot_impressions_weight": _read_float(
            "value_model.hot_impressions_weight",
            DEFAULT_VALUE_MODEL_SETTINGS["hot_impressions_weight"],
        ),
        "hot_lookback_days": _read_int(
            "value_model.hot_lookback_days",
            DEFAULT_VALUE_MODEL_SETTINGS["hot_lookback_days"],
        ),
        # FR-025 co-occurrence signal
        "co_occurrence_signal_enabled": _read_bool(
            "value_model.co_occurrence_signal_enabled",
            DEFAULT_VALUE_MODEL_SETTINGS["co_occurrence_signal_enabled"],
        ),
        "w_cooccurrence": _read_float(
            "value_model.w_cooccurrence", DEFAULT_VALUE_MODEL_SETTINGS["w_cooccurrence"]
        ),
        "co_occurrence_fallback_value": _read_float(
            "value_model.co_occurrence_fallback_value",
            DEFAULT_VALUE_MODEL_SETTINGS["co_occurrence_fallback_value"],
        ),
        "co_occurrence_min_co_sessions": _read_int(
            "value_model.co_occurrence_min_co_sessions",
            DEFAULT_VALUE_MODEL_SETTINGS["co_occurrence_min_co_sessions"],
        ),
    }


def _validate_value_model_settings(payload: dict, current: dict) -> dict:
    def _get_float(key: str) -> float:
        val = payload.get(key, current.get(key))
        try:
            return float(val)
        except (TypeError, ValueError):
            return float(current.get(key, 0.0))

    def _get_int(key: str) -> int:
        val = payload.get(key, current.get(key))
        try:
            return int(val)
        except (TypeError, ValueError):
            return int(current.get(key, 0))

    def _get_bool(key: str) -> bool:
        val = payload.get(key, current.get(key))
        if isinstance(val, bool):
            return val
        return str(val).strip().lower() in {"1", "true", "yes", "on"}

    return {
        "enabled": _get_bool("enabled"),
        "w_relevance": max(0.0, min(1.0, _get_float("w_relevance"))),
        "w_traffic": max(0.0, min(1.0, _get_float("w_traffic"))),
        "w_freshness": max(0.0, min(1.0, _get_float("w_freshness"))),
        "w_authority": max(0.0, min(1.0, _get_float("w_authority"))),
        "w_penalty": max(0.0, min(1.0, _get_float("w_penalty"))),
        "traffic_lookback_days": max(1, min(365, _get_int("traffic_lookback_days"))),
        "traffic_fallback_value": max(
            0.0, min(1.0, _get_float("traffic_fallback_value"))
        ),
        "engagement_signal_enabled": _get_bool("engagement_signal_enabled"),
        "w_engagement": max(0.0, min(1.0, _get_float("w_engagement"))),
        "engagement_lookback_days": max(
            1, min(365, _get_int("engagement_lookback_days"))
        ),
        "engagement_words_per_minute": max(
            50, min(600, _get_int("engagement_words_per_minute"))
        ),
        "engagement_cap_ratio": max(1.0, min(5.0, _get_float("engagement_cap_ratio"))),
        "engagement_fallback_value": max(
            0.0, min(1.0, _get_float("engagement_fallback_value"))
        ),
        # FR-023 hot decay signal
        "hot_decay_enabled": _get_bool("hot_decay_enabled"),
        "hot_gravity": max(0.001, min(0.5, _get_float("hot_gravity"))),
        "hot_clicks_weight": max(0.0, min(5.0, _get_float("hot_clicks_weight"))),
        "hot_impressions_weight": max(
            0.0, min(5.0, _get_float("hot_impressions_weight"))
        ),
        "hot_lookback_days": max(7, min(365, _get_int("hot_lookback_days"))),
        # FR-025 co-occurrence signal
        "co_occurrence_signal_enabled": _get_bool("co_occurrence_signal_enabled"),
        "w_cooccurrence": max(0.0, min(1.0, _get_float("w_cooccurrence"))),
        "co_occurrence_fallback_value": max(
            0.0, min(1.0, _get_float("co_occurrence_fallback_value"))
        ),
        "co_occurrence_min_co_sessions": max(
            1, min(100, _get_int("co_occurrence_min_co_sessions"))
        ),
    }


class UserMeView(APIView):
    """
    Returns the currently authenticated user's profile.
    Returns 401 when no valid token is provided.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(
            {
                "id": request.user.id,
                "username": request.user.username,
                "email": request.user.email,
                "is_staff": request.user.is_staff,
                "date_joined": request.user.date_joined,
            }
        )


class UserLogoutView(APIView):
    """
    Deletes the user's auth token, invalidating all future requests with it.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            request.user.auth_token.delete()
        except Exception:
            logger.debug("Auth token delete failed or already gone", exc_info=True)
        return Response({"status": "success"})
