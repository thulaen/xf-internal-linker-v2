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
import math
import uuid
from urllib.parse import urlparse

from django.conf import settings as django_settings
from django.http import JsonResponse
from django.views import View
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

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
    "isolated_context_factor": recommended_float("weighted_authority.isolated_context_factor"),
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
    "enable_anchor_expansion": recommended_bool("phrase_matching.enable_anchor_expansion"),
    "enable_partial_matching": recommended_bool("phrase_matching.enable_partial_matching"),
    "context_window_tokens": recommended_int("phrase_matching.context_window_tokens"),
}

DEFAULT_LEARNED_ANCHOR_SETTINGS = {
    "ranking_weight": recommended_float("learned_anchor.ranking_weight"),
    "minimum_anchor_sources": recommended_int("learned_anchor.minimum_anchor_sources"),
    "minimum_family_support_share": recommended_float("learned_anchor.minimum_family_support_share"),
    "enable_noise_filter": recommended_bool("learned_anchor.enable_noise_filter"),
}

DEFAULT_RARE_TERM_PROPAGATION_SETTINGS = {
    "enabled": recommended_bool("rare_term_propagation.enabled"),
    "ranking_weight": recommended_float("rare_term_propagation.ranking_weight"),
    "max_document_frequency": recommended_int("rare_term_propagation.max_document_frequency"),
    "minimum_supporting_related_pages": recommended_int("rare_term_propagation.minimum_supporting_related_pages"),
}

DEFAULT_FIELD_AWARE_RELEVANCE_SETTINGS = {
    "ranking_weight": recommended_float("field_aware_relevance.ranking_weight"),
    "title_field_weight": recommended_float("field_aware_relevance.title_field_weight"),
    "body_field_weight": recommended_float("field_aware_relevance.body_field_weight"),
    "scope_field_weight": recommended_float("field_aware_relevance.scope_field_weight"),
    "learned_anchor_field_weight": recommended_float("field_aware_relevance.learned_anchor_field_weight"),
}

DEFAULT_GA4_GSC_SETTINGS = {
    "ranking_weight": recommended_float("ga4_gsc.ranking_weight"),
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

# Allowed MIME types for site asset uploads
_LOGO_ALLOWED = frozenset({"image/png", "image/svg+xml", "image/webp", "image/jpeg"})
_FAVICON_ALLOWED = frozenset({
    "image/png", "image/svg+xml",
    "image/x-icon", "image/vnd.microsoft.icon",
})
_ASSET_MAX_BYTES = 2 * 1024 * 1024  # 2 MB


def _get_app_setting_value(key: str, default: str | None = None) -> str | None:
    from apps.core.models import AppSetting

    setting = AppSetting.objects.filter(key=key).first()
    if setting is None:
        return default
    return setting.value


def get_silo_settings() -> dict[str, float | str]:
    """Load persisted silo settings with defensive defaults."""
    mode = _get_app_setting_value("silo.mode", DEFAULT_SILO_SETTINGS["mode"]) or DEFAULT_SILO_SETTINGS["mode"]
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
        "same_silo_boost": _read_float("silo.same_silo_boost", DEFAULT_SILO_SETTINGS["same_silo_boost"]),
        "cross_silo_penalty": _read_float("silo.cross_silo_penalty", DEFAULT_SILO_SETTINGS["cross_silo_penalty"]),
    }


def _validate_silo_settings(payload: dict) -> dict[str, float | str]:
    mode = payload.get("mode", DEFAULT_SILO_SETTINGS["mode"])
    if mode not in {"disabled", "prefer_same_silo", "strict_same_silo"}:
        raise ValueError("mode must be one of disabled, prefer_same_silo, strict_same_silo.")

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
    base_url = (_get_app_setting_value("wordpress.base_url", django_settings.WORDPRESS_BASE_URL) or "").strip().rstrip("/")
    username = (_get_app_setting_value("wordpress.username", django_settings.WORDPRESS_USERNAME) or "").strip()
    app_password = _get_app_setting_value("wordpress.app_password", django_settings.WORDPRESS_APP_PASSWORD) or ""

    def _read_int(key: str, default: int) -> int:
        raw = _get_app_setting_value(key)
        try:
            return int(raw) if raw is not None else default
        except (TypeError, ValueError):
            return default

    sync_enabled = (_get_app_setting_value("wordpress.sync_enabled") or "").strip().lower() in {"1", "true", "yes", "on"}

    return {
        "base_url": base_url,
        "username": username,
        "app_password_configured": bool(app_password.strip()),
        "sync_enabled": sync_enabled,
        "sync_hour": _read_int("wordpress.sync_hour", DEFAULT_WORDPRESS_SETTINGS["sync_hour"]),
        "sync_minute": _read_int("wordpress.sync_minute", DEFAULT_WORDPRESS_SETTINGS["sync_minute"]),
    }


def get_wordpress_runtime_config() -> dict[str, str]:
    """Return WordPress connection settings including the stored secret."""
    return {
        "base_url": (_get_app_setting_value("wordpress.base_url", django_settings.WORDPRESS_BASE_URL) or "").strip().rstrip("/"),
        "username": (_get_app_setting_value("wordpress.username", django_settings.WORDPRESS_USERNAME) or "").strip(),
        "app_password": (_get_app_setting_value("wordpress.app_password", django_settings.WORDPRESS_APP_PASSWORD) or "").strip(),
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


def get_ga4_gsc_settings() -> dict[str, float]:
    """Load persisted GA4/GSC settings with defensive defaults."""
    settings = _read_ga4_gsc_settings()
    try:
        return _validate_ga4_gsc_settings(
            settings,
            current=dict(DEFAULT_GA4_GSC_SETTINGS),
        )
    except ValueError:
        return dict(DEFAULT_GA4_GSC_SETTINGS)


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
        "enabled": _read_bool("clustering.enabled", DEFAULT_CLUSTERING_SETTINGS["enabled"]),
        "similarity_threshold": _read_float("clustering.similarity_threshold", DEFAULT_CLUSTERING_SETTINGS["similarity_threshold"]),
        "suppression_penalty": _read_float("clustering.suppression_penalty", DEFAULT_CLUSTERING_SETTINGS["suppression_penalty"]),
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
        "ranking_weight": _read_float("weighted_authority.ranking_weight", DEFAULT_WEIGHTED_AUTHORITY_SETTINGS["ranking_weight"]),
        "position_bias": _read_float("weighted_authority.position_bias", DEFAULT_WEIGHTED_AUTHORITY_SETTINGS["position_bias"]),
        "empty_anchor_factor": _read_float("weighted_authority.empty_anchor_factor", DEFAULT_WEIGHTED_AUTHORITY_SETTINGS["empty_anchor_factor"]),
        "bare_url_factor": _read_float("weighted_authority.bare_url_factor", DEFAULT_WEIGHTED_AUTHORITY_SETTINGS["bare_url_factor"]),
        "weak_context_factor": _read_float("weighted_authority.weak_context_factor", DEFAULT_WEIGHTED_AUTHORITY_SETTINGS["weak_context_factor"]),
        "isolated_context_factor": _read_float("weighted_authority.isolated_context_factor", DEFAULT_WEIGHTED_AUTHORITY_SETTINGS["isolated_context_factor"]),
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
        "ranking_weight": _read_float("link_freshness.ranking_weight", DEFAULT_LINK_FRESHNESS_SETTINGS["ranking_weight"]),
        "recent_window_days": _read_int("link_freshness.recent_window_days", DEFAULT_LINK_FRESHNESS_SETTINGS["recent_window_days"]),
        "newest_peer_percent": _read_float("link_freshness.newest_peer_percent", DEFAULT_LINK_FRESHNESS_SETTINGS["newest_peer_percent"]),
        "min_peer_count": _read_int("link_freshness.min_peer_count", DEFAULT_LINK_FRESHNESS_SETTINGS["min_peer_count"]),
        "w_recent": _read_float("link_freshness.w_recent", DEFAULT_LINK_FRESHNESS_SETTINGS["w_recent"]),
        "w_growth": _read_float("link_freshness.w_growth", DEFAULT_LINK_FRESHNESS_SETTINGS["w_growth"]),
        "w_cohort": _read_float("link_freshness.w_cohort", DEFAULT_LINK_FRESHNESS_SETTINGS["w_cohort"]),
        "w_loss": _read_float("link_freshness.w_loss", DEFAULT_LINK_FRESHNESS_SETTINGS["w_loss"]),
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
        "ranking_weight": _read_float("phrase_matching.ranking_weight", DEFAULT_PHRASE_MATCHING_SETTINGS["ranking_weight"]),
        "enable_anchor_expansion": _read_bool("phrase_matching.enable_anchor_expansion", DEFAULT_PHRASE_MATCHING_SETTINGS["enable_anchor_expansion"]),
        "enable_partial_matching": _read_bool("phrase_matching.enable_partial_matching", DEFAULT_PHRASE_MATCHING_SETTINGS["enable_partial_matching"]),
        "context_window_tokens": _read_int("phrase_matching.context_window_tokens", DEFAULT_PHRASE_MATCHING_SETTINGS["context_window_tokens"]),
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
        "ranking_weight": _read_float("click_distance.ranking_weight", DEFAULT_CLICK_DISTANCE_SETTINGS["ranking_weight"]),
        "k_cd": _read_float("click_distance.k_cd", DEFAULT_CLICK_DISTANCE_SETTINGS["k_cd"]),
        "b_cd": _read_float("click_distance.b_cd", DEFAULT_CLICK_DISTANCE_SETTINGS["b_cd"]),
        "b_ud": _read_float("click_distance.b_ud", DEFAULT_CLICK_DISTANCE_SETTINGS["b_ud"]),
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
        "enabled": _read_bool("explore_exploit.enabled", DEFAULT_FEEDBACK_RERANK_SETTINGS["enabled"]),
        "ranking_weight": _read_float("explore_exploit.ranking_weight", DEFAULT_FEEDBACK_RERANK_SETTINGS["ranking_weight"]),
        "exploration_rate": _read_float("explore_exploit.exploration_rate", DEFAULT_FEEDBACK_RERANK_SETTINGS["exploration_rate"]),
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
        "enabled": _read_bool("slate_diversity.enabled", DEFAULT_SLATE_DIVERSITY_SETTINGS["enabled"]),
        "diversity_lambda": _read_float("slate_diversity.diversity_lambda", DEFAULT_SLATE_DIVERSITY_SETTINGS["diversity_lambda"]),
        "score_window": _read_float("slate_diversity.score_window", DEFAULT_SLATE_DIVERSITY_SETTINGS["score_window"]),
        "similarity_cap": _read_float("slate_diversity.similarity_cap", DEFAULT_SLATE_DIVERSITY_SETTINGS["similarity_cap"]),
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
        "ranking_weight": _read_float("learned_anchor.ranking_weight", DEFAULT_LEARNED_ANCHOR_SETTINGS["ranking_weight"]),
        "minimum_anchor_sources": _read_int("learned_anchor.minimum_anchor_sources", DEFAULT_LEARNED_ANCHOR_SETTINGS["minimum_anchor_sources"]),
        "minimum_family_support_share": _read_float("learned_anchor.minimum_family_support_share", DEFAULT_LEARNED_ANCHOR_SETTINGS["minimum_family_support_share"]),
        "enable_noise_filter": _read_bool("learned_anchor.enable_noise_filter", DEFAULT_LEARNED_ANCHOR_SETTINGS["enable_noise_filter"]),
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
        "enabled": _read_bool("rare_term_propagation.enabled", DEFAULT_RARE_TERM_PROPAGATION_SETTINGS["enabled"]),
        "ranking_weight": _read_float("rare_term_propagation.ranking_weight", DEFAULT_RARE_TERM_PROPAGATION_SETTINGS["ranking_weight"]),
        "max_document_frequency": _read_int("rare_term_propagation.max_document_frequency", DEFAULT_RARE_TERM_PROPAGATION_SETTINGS["max_document_frequency"]),
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


def _validate_clustering_settings(payload: dict, current: dict) -> dict[str, float | bool]:
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



def _read_ga4_gsc_settings() -> dict[str, float]:
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

    return {
        "ranking_weight": _read_float("ga4_gsc.ranking_weight", DEFAULT_GA4_GSC_SETTINGS["ranking_weight"]),
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

    sync_enabled = _coerce_bool(payload.get("sync_enabled"), bool(current["sync_enabled"]))
    sync_hour = _coerce_int("sync_hour", 0, 23)
    sync_minute = _coerce_int("sync_minute", 0, 59)

    if username and not effective_has_password:
        raise ValueError("Application Password is required when a WordPress username is configured.")
    if effective_has_password and not username:
        raise ValueError("username is required when an Application Password is configured.")
    if sync_enabled and not base_url:
        raise ValueError("base_url is required when scheduled WordPress sync is enabled.")

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
    if validated["context_window_tokens"] < 4 or validated["context_window_tokens"] > 12:
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
    if validated["minimum_anchor_sources"] < 1 or validated["minimum_anchor_sources"] > 10:
        raise ValueError("minimum_anchor_sources must be between 1 and 10.")
    if validated["minimum_family_support_share"] < 0.05 or validated["minimum_family_support_share"] > 0.50:
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
        "minimum_supporting_related_pages": _coerce_int("minimum_supporting_related_pages"),
    }

    if validated["ranking_weight"] < 0.0 or validated["ranking_weight"] > 0.10:
        raise ValueError("ranking_weight must be between 0.0 and 0.10.")
    if validated["max_document_frequency"] < 1 or validated["max_document_frequency"] > 10:
        raise ValueError("max_document_frequency must be between 1 and 10.")
    if validated["minimum_supporting_related_pages"] < 1 or validated["minimum_supporting_related_pages"] > 5:
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
        raise ValueError("title/body/scope/learned-anchor field weights must sum to 1.0.")

    return validated


def _validate_ga4_gsc_settings(
    payload: dict,
    *,
    current: dict[str, float] | None = None,
) -> dict[str, float]:
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

    validated = {
        "ranking_weight": _coerce_float("ranking_weight"),
    }

    if validated["ranking_weight"] < 0.0 or validated["ranking_weight"] > 1.0:
        raise ValueError("ranking_weight must be between 0.0 and 1.0.")

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
    """Keep the Celery Beat schedule aligned with the saved WordPress sync settings."""
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
    permission_classes = [AllowAny]

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
    permission_classes = [AllowAny]

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
    permission_classes = [AllowAny]

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
    permission_classes = [AllowAny]

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
    permission_classes = [AllowAny]

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
    permission_classes = [AllowAny]

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
    permission_classes = [AllowAny]

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
    permission_classes = [AllowAny]

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
    GET  /api/settings/ga4-gsc/ - returns GA4/GSC placeholder settings
    PUT  /api/settings/ga4-gsc/ - validates and persists those settings
    """
    permission_classes = [AllowAny]

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


class WordPressSettingsView(APIView):
    """
    GET  /api/settings/wordpress/ - returns saved WordPress sync settings
    PUT  /api/settings/wordpress/ - validates and persists WordPress sync settings
    """
    permission_classes = [AllowAny]

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
                "description": "Whether scheduled WordPress sync is enabled via Celery Beat.",
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

        from apps.pipeline.tasks import import_content
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

        import_content.delay(
            mode="full",
            source="wp",
            job_id=str(job.job_id),
        )

        return Response(
            {
                "job_id": str(job.job_id),
                "source": "wp",
                "mode": "full",
            },
            status=202,
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
            return Response({"error": "No file uploaded. Use field name 'file'."}, status=400)

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

        asset_url = f"{django_settings.MEDIA_URL}site-assets/{self.subfolder}/{filename}"
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
    permission_classes = [AllowAny]

    def get(self, request):
        from apps.suggestions.models import Suggestion, PipelineRun
        from apps.content.models import ContentItem
        from apps.sync.models import SyncJob
        from apps.graph.models import BrokenLink
        from django.db.models import Count

        # Suggestion counts by status
        status_rows = (
            Suggestion.objects.values("status")
            .annotate(count=Count("pk"))
        )
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
                "run_id", "run_state", "rerun_mode",
                "suggestions_created", "destinations_processed",
                "duration_seconds", "created_at",
            ).order_by("-created_at")[:5]
        )
        for run in pipeline_runs:
            run["run_id"] = str(run["run_id"])
            if run["created_at"]:
                run["created_at"] = run["created_at"].isoformat()
            ds = run.pop("duration_seconds")
            if ds is not None:
                minutes, seconds = divmod(int(ds), 60)
                run["duration_display"] = f"{minutes}m {seconds}s" if minutes else f"{seconds}s"
            else:
                run["duration_display"] = None

        # Recent import jobs (last 5)
        recent_imports = list(
            SyncJob.objects.values(
                "job_id", "status", "source", "mode",
                "items_synced", "created_at", "completed_at",
            ).order_by("-created_at")[:5]
        )
        for job in recent_imports:
            job["job_id"] = str(job["job_id"])
            if job["created_at"]:
                job["created_at"] = job["created_at"].isoformat()
            if job["completed_at"]:
                job["completed_at"] = job["completed_at"].isoformat()

        return Response({
            "suggestion_counts": {
                "pending":  suggestion_counts.get("pending", 0),
                "approved": suggestion_counts.get("approved", 0),
                "rejected": suggestion_counts.get("rejected", 0),
                "applied":  suggestion_counts.get("applied", 0),
                "total":    sum(suggestion_counts.values()),
            },
            "content_count": content_count,
            "open_broken_links": open_broken_links,
            "last_sync": last_sync,
            "pipeline_runs": pipeline_runs,
            "recent_imports": recent_imports,
        })


class ClickDistanceSettingsView(APIView):
    """
    GET /api/settings/click-distance/
    PUT /api/settings/click-distance/
    """
    permission_classes = [AllowAny]

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
                key=f"click_distance.{key}",
                defaults={"value": str(value)}
            )

        return Response(validated)


class ClickDistanceRecalculateView(APIView):
    """
    POST /api/settings/click-distance/recalculate/
    """
    def post(self, request):
        """Trigger bulk recalculation of click distance scores."""
        from apps.pipeline.tasks import recalculate_click_distance_task
        
        task = recalculate_click_distance_task.delay()
        return Response({
            "status": "queued",
            "job_id": task.id
        })


class FeedbackRerankSettingsView(APIView):
    """
    GET  /api/settings/explore-exploit/ - returns FR-013 explore/exploit settings
    PUT  /api/settings/explore-exploit/ - validates and persists those settings
    """
    permission_classes = [AllowAny]

    def get(self, request):
        return Response(get_feedback_rerank_settings())

    def put(self, request):
        from apps.core.models import AppSetting
        
        current = get_feedback_rerank_settings()
        try:
            validated = _validate_feedback_rerank_settings(request.data, current=current)
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
    permission_classes = [AllowAny]

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
    permission_classes = [AllowAny]

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



class RTuneTriggerView(APIView):
    """POST /api/settings/r-tune/trigger/ — manually queue the monthly R auto-tune task."""

    def post(self, request):
        from apps.pipeline.tasks import monthly_r_auto_tune

        task = monthly_r_auto_tune.delay()
        return Response({"detail": "R auto-tune task queued.", "task_id": task.id}, status=202)
