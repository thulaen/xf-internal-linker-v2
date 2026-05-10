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
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

logger = logging.getLogger(__name__)

from apps.api.query_params import coerce_bool, coerce_float, coerce_int
from apps.core.services.settings_helpers import (
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
)
from apps.api.throttles import (
    ChallengerEvalThrottle as _ChallengerEvalThrottle,
    CompressionAuditRunThrottle,
    GraphRebuildThrottle as _GraphRebuildThrottle,
    PerformanceCertRunThrottle,
    WeightRecalcThrottle as _WeightRecalcThrottle,
)

from apps.suggestions.recommended_weights import (
    recommended_bool,
    recommended_float,
    recommended_int,
    recommended_str,
)


def _safe_confidence_snapshot() -> dict | None:
    """Phase 4.3 — return the Confidence Meter snapshot or None on failure.

    Wraps ``apps.core.services.confidence_meter.get_confidence_snapshot``
    in a try/except so a confidence-meter regression cannot break the
    dashboard endpoint. The frontend simply hides the chip when the
    payload is None.
    """
    try:
        from apps.core.services.confidence_meter import get_confidence_snapshot
        from dataclasses import asdict

        snap = get_confidence_snapshot()
        return {
            "total": snap.total,
            "label": snap.label,
            "contributors": [asdict(c) for c in snap.contributors],
        }
    except Exception:
        logger.debug("confidence_meter snapshot failed", exc_info=True)
        return None


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
    # silo accepts inf/NaN historically (no isfinite check) — opt out.
    return {
        "mode": mode,
        "same_silo_boost": read_app_setting_float(
            "silo.same_silo_boost",
            DEFAULT_SILO_SETTINGS["same_silo_boost"],
            require_finite=False,
        ),
        "cross_silo_penalty": read_app_setting_float(
            "silo.cross_silo_penalty",
            DEFAULT_SILO_SETTINGS["cross_silo_penalty"],
            require_finite=False,
        ),
    }


def _validate_silo_settings(payload: dict) -> dict[str, float | str]:
    mode = payload.get("mode", DEFAULT_SILO_SETTINGS["mode"])
    if mode not in {"disabled", "prefer_same_silo", "strict_same_silo"}:
        raise ValueError(
            "mode must be one of disabled, prefer_same_silo, strict_same_silo."
        )
    # Silo accepts inf/NaN historically (no isfinite check), so use require_finite=False.
    same_silo_boost = coerce_setting_float(
        payload,
        DEFAULT_SILO_SETTINGS,
        "same_silo_boost",
        require_finite=False,
    )
    cross_silo_penalty = coerce_setting_float(
        payload,
        DEFAULT_SILO_SETTINGS,
        "cross_silo_penalty",
        require_finite=False,
    )
    if same_silo_boost < 0:
        raise ValueError("same_silo_boost must be >= 0.")
    if cross_silo_penalty < 0:
        raise ValueError("cross_silo_penalty must be >= 0.")
    return {
        "mode": mode,
        "same_silo_boost": same_silo_boost,
        "cross_silo_penalty": cross_silo_penalty,
    }


def _read_wp_string(
    key: str, django_default: str, *, rstrip_slash: bool = False
) -> str:
    """Read + strip a WordPress AppSetting, falling back to a Django default.

    All four WP string columns share the same shape — operator's AppSetting
    if set, else Django settings, normalise trailing whitespace, optionally
    strip a trailing slash. Pulling it out keeps ``get_wordpress_settings``
    readable.
    """
    raw = (_get_app_setting_value(key, django_default) or "").strip()
    return raw.rstrip("/") if rstrip_slash else raw


def get_wordpress_settings() -> dict[str, object]:
    """Load persisted WordPress sync settings with environment fallbacks."""
    base_url = _read_wp_string(
        "wordpress.base_url",
        django_settings.WORDPRESS_BASE_URL,
        rstrip_slash=True,
    )
    username = _read_wp_string("wordpress.username", django_settings.WORDPRESS_USERNAME)
    app_password = (
        _get_app_setting_value(
            "wordpress.app_password", django_settings.WORDPRESS_APP_PASSWORD
        )
        or ""
    )
    sync_enabled = coerce_bool(
        _get_app_setting_value("wordpress.sync_enabled"), default=False
    )
    from apps.health.services import get_service_health_status

    return {
        "base_url": base_url,
        "username": username,
        "app_password_configured": bool(app_password.strip()),
        "sync_enabled": sync_enabled,
        "sync_hour": read_app_setting_int(
            "wordpress.sync_hour",
            DEFAULT_WORDPRESS_SETTINGS["sync_hour"],
        ),
        "sync_minute": read_app_setting_int(
            "wordpress.sync_minute",
            DEFAULT_WORDPRESS_SETTINGS["sync_minute"],
        ),
        "health": get_service_health_status("wordpress"),
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
    except Exception:  # noqa: BLE001 — bad operator-stored settings fall back to safe defaults; logger keeps a paper trail.
        logger.warning(
            "Graph candidate settings validation failed; using defaults",
            exc_info=True,
        )
        return dict(DEFAULT_GRAPH_CANDIDATE_SETTINGS)


def get_value_model_settings() -> dict[str, float | int | bool]:
    """Load persisted FR-021 value-model settings with defensive defaults."""
    settings = _read_value_model_settings()
    try:
        return _validate_value_model_settings(
            settings,
            current=dict(DEFAULT_VALUE_MODEL_SETTINGS),
        )
    except Exception:  # noqa: BLE001 — bad operator-stored settings fall back to safe defaults; logger keeps a paper trail.
        logger.warning(
            "Value-model settings validation failed; using defaults",
            exc_info=True,
        )
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
    except Exception:  # noqa: BLE001 — bad operator-stored settings fall back to safe defaults; logger keeps a paper trail.
        logger.warning(
            "Clustering settings validation failed; using defaults",
            exc_info=True,
        )
        return dict(DEFAULT_CLUSTERING_SETTINGS)


def _read_clustering_settings() -> dict[str, float | bool]:
    """Read near-duplicate clustering settings from AppSetting without applying bounds."""
    return {
        "enabled": read_app_setting_bool(
            "clustering.enabled",
            DEFAULT_CLUSTERING_SETTINGS["enabled"],
        ),
        "similarity_threshold": read_app_setting_float(
            "clustering.similarity_threshold",
            DEFAULT_CLUSTERING_SETTINGS["similarity_threshold"],
        ),
        "suppression_penalty": read_app_setting_float(
            "clustering.suppression_penalty",
            DEFAULT_CLUSTERING_SETTINGS["suppression_penalty"],
        ),
    }


_WEIGHTED_AUTHORITY_KEYS = (
    "ranking_weight",
    "position_bias",
    "empty_anchor_factor",
    "bare_url_factor",
    "weak_context_factor",
    "isolated_context_factor",
)


def _read_weighted_authority_settings() -> dict[str, float]:
    """Read weighted-authority settings from AppSetting without applying bounds."""
    return {
        key: read_app_setting_float(
            f"weighted_authority.{key}",
            DEFAULT_WEIGHTED_AUTHORITY_SETTINGS[key],
        )
        for key in _WEIGHTED_AUTHORITY_KEYS
    }


_LINK_FRESHNESS_FLOAT_DEFAULT_KEYS = (
    "ranking_weight",
    "newest_peer_percent",
    "w_recent",
    "w_growth",
    "w_cohort",
    "w_loss",
)
_LINK_FRESHNESS_INT_DEFAULT_KEYS = ("recent_window_days", "min_peer_count")


def _read_link_freshness_settings() -> dict[str, float | int]:
    """Read link-freshness settings from AppSetting without applying bounds."""
    out: dict[str, float | int] = {
        key: read_app_setting_float(
            f"link_freshness.{key}",
            DEFAULT_LINK_FRESHNESS_SETTINGS[key],
        )
        for key in _LINK_FRESHNESS_FLOAT_DEFAULT_KEYS
    }
    for key in _LINK_FRESHNESS_INT_DEFAULT_KEYS:
        out[key] = read_app_setting_int(
            f"link_freshness.{key}",
            DEFAULT_LINK_FRESHNESS_SETTINGS[key],
        )
    return out


def _read_phrase_matching_settings() -> dict[str, float | int | bool]:
    """Read phrase-matching settings from AppSetting without applying bounds."""
    return {
        "ranking_weight": read_app_setting_float(
            "phrase_matching.ranking_weight",
            DEFAULT_PHRASE_MATCHING_SETTINGS["ranking_weight"],
        ),
        "enable_anchor_expansion": read_app_setting_bool(
            "phrase_matching.enable_anchor_expansion",
            DEFAULT_PHRASE_MATCHING_SETTINGS["enable_anchor_expansion"],
        ),
        "enable_partial_matching": read_app_setting_bool(
            "phrase_matching.enable_partial_matching",
            DEFAULT_PHRASE_MATCHING_SETTINGS["enable_partial_matching"],
        ),
        "context_window_tokens": read_app_setting_int(
            "phrase_matching.context_window_tokens",
            DEFAULT_PHRASE_MATCHING_SETTINGS["context_window_tokens"],
        ),
    }


_CLICK_DISTANCE_KEYS = ("ranking_weight", "k_cd", "b_cd", "b_ud")


def _read_click_distance_settings() -> dict[str, float]:
    """Read click-distance settings from AppSetting without applying bounds."""
    return {
        key: read_app_setting_float(
            f"click_distance.{key}",
            DEFAULT_CLICK_DISTANCE_SETTINGS[key],
        )
        for key in _CLICK_DISTANCE_KEYS
    }


def _read_feedback_rerank_settings() -> dict[str, float | bool]:
    """Read feedback-driven explore/exploit settings from AppSetting without applying bounds.

    Sister-bug fix 2026-05-04: prior _read_bool closure only accepted the
    literal "true" string — was inconsistent with every other settings
    reader. Now uses read_app_setting_bool which delegates to the
    project-wide coerce_bool (accepts "true"/"1"/"yes"/"on", case-insensitive).
    """
    return {
        "enabled": read_app_setting_bool(
            "explore_exploit.enabled",
            DEFAULT_FEEDBACK_RERANK_SETTINGS["enabled"],
        ),
        "ranking_weight": read_app_setting_float(
            "explore_exploit.ranking_weight",
            DEFAULT_FEEDBACK_RERANK_SETTINGS["ranking_weight"],
        ),
        "exploration_rate": read_app_setting_float(
            "explore_exploit.exploration_rate",
            DEFAULT_FEEDBACK_RERANK_SETTINGS["exploration_rate"],
        ),
    }


def _read_slate_diversity_settings() -> dict:
    """Read FR-015 slate diversity settings from AppSetting without applying bounds."""
    return {
        "enabled": read_app_setting_bool(
            "slate_diversity.enabled",
            DEFAULT_SLATE_DIVERSITY_SETTINGS["enabled"],
        ),
        "diversity_lambda": read_app_setting_float(
            "slate_diversity.diversity_lambda",
            DEFAULT_SLATE_DIVERSITY_SETTINGS["diversity_lambda"],
        ),
        "score_window": read_app_setting_float(
            "slate_diversity.score_window",
            DEFAULT_SLATE_DIVERSITY_SETTINGS["score_window"],
        ),
        "similarity_cap": read_app_setting_float(
            "slate_diversity.similarity_cap",
            DEFAULT_SLATE_DIVERSITY_SETTINGS["similarity_cap"],
        ),
        "algorithm_version": DEFAULT_SLATE_DIVERSITY_SETTINGS["algorithm_version"],
    }


def get_slate_diversity_settings() -> dict:
    """Return current FR-015 slate diversity settings with defaults applied."""
    try:
        return _read_slate_diversity_settings()
    except Exception:  # noqa: BLE001 — read failure falls back to defaults; logger keeps a paper trail.
        logger.warning(
            "Slate diversity settings read failed; using defaults",
            exc_info=True,
        )
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
        return coerce_bool(val, default=False)

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
    return {
        "ranking_weight": read_app_setting_float(
            "learned_anchor.ranking_weight",
            DEFAULT_LEARNED_ANCHOR_SETTINGS["ranking_weight"],
        ),
        "minimum_anchor_sources": read_app_setting_int(
            "learned_anchor.minimum_anchor_sources",
            DEFAULT_LEARNED_ANCHOR_SETTINGS["minimum_anchor_sources"],
        ),
        "minimum_family_support_share": read_app_setting_float(
            "learned_anchor.minimum_family_support_share",
            DEFAULT_LEARNED_ANCHOR_SETTINGS["minimum_family_support_share"],
        ),
        "enable_noise_filter": read_app_setting_bool(
            "learned_anchor.enable_noise_filter",
            DEFAULT_LEARNED_ANCHOR_SETTINGS["enable_noise_filter"],
        ),
    }


def _read_rare_term_propagation_settings() -> dict[str, float | int | bool]:
    """Read FR-010 rare-term settings from AppSetting without applying bounds."""
    return {
        "enabled": read_app_setting_bool(
            "rare_term_propagation.enabled",
            DEFAULT_RARE_TERM_PROPAGATION_SETTINGS["enabled"],
        ),
        "ranking_weight": read_app_setting_float(
            "rare_term_propagation.ranking_weight",
            DEFAULT_RARE_TERM_PROPAGATION_SETTINGS["ranking_weight"],
        ),
        "max_document_frequency": read_app_setting_int(
            "rare_term_propagation.max_document_frequency",
            DEFAULT_RARE_TERM_PROPAGATION_SETTINGS["max_document_frequency"],
        ),
        "minimum_supporting_related_pages": read_app_setting_int(
            "rare_term_propagation.minimum_supporting_related_pages",
            DEFAULT_RARE_TERM_PROPAGATION_SETTINGS["minimum_supporting_related_pages"],
        ),
    }


_FIELD_AWARE_RELEVANCE_KEY_NAMES = (
    "ranking_weight",
    "title_field_weight",
    "body_field_weight",
    "scope_field_weight",
    "learned_anchor_field_weight",
)


def _read_field_aware_relevance_settings() -> dict[str, float]:
    """Read FR-011 field-aware settings from AppSetting without applying bounds."""
    return {
        key: read_app_setting_float(
            f"field_aware_relevance.{key}",
            DEFAULT_FIELD_AWARE_RELEVANCE_SETTINGS[key],
        )
        for key in _FIELD_AWARE_RELEVANCE_KEY_NAMES
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


def _ga4_gsc_connection_status(
    property_url: str,
    service_account_email: str,
    private_key: str,
) -> tuple[str, str]:
    """Return ``(status, plain-English message)`` for the GA4/GSC connection card."""
    if property_url and service_account_email and private_key:
        return (
            "saved",
            "Search Console credentials are saved. Run Test Connection to confirm access.",
        )
    return (
        "not_configured",
        "Fill in the Search Console property URL and service-account credentials.",
    )


def _read_ga4_gsc_settings() -> dict[str, object]:
    """Read GA4/GSC settings from AppSetting without applying bounds."""
    property_url = (
        (_get_app_setting_value("ga4_gsc.property_url", "") or "").strip().rstrip("/")
    )
    service_account_email = (
        _get_app_setting_value("ga4_gsc.service_account_email", "") or ""
    ).strip()
    private_key = (_get_app_setting_value("ga4_gsc.private_key", "") or "").strip()
    connection_status, connection_message = _ga4_gsc_connection_status(
        property_url,
        service_account_email,
        private_key,
    )
    return {
        "ranking_weight": read_app_setting_float(
            "ga4_gsc.ranking_weight",
            DEFAULT_GA4_GSC_SETTINGS["ranking_weight"],
        ),
        "property_url": property_url,
        "service_account_email": service_account_email,
        "private_key_configured": bool(private_key),
        "sync_enabled": read_app_setting_bool(
            "ga4_gsc.sync_enabled",
            DEFAULT_GA4_GSC_SETTINGS["sync_enabled"],
        ),
        "sync_lookback_days": read_app_setting_int(
            "ga4_gsc.sync_lookback_days",
            DEFAULT_GA4_GSC_SETTINGS["sync_lookback_days"],
        ),
        "connection_status": connection_status,
        "connection_message": connection_message,
    }


def _resolve_wp_app_password(
    payload: dict,
    current: dict[str, object],
) -> tuple[str | None, bool, bool]:
    """Extract the optional WordPress Application Password.

    Returns:
        ``(app_password, app_password_provided, effective_has_password)``.
        Stays None unless the operator explicitly supplied a value — protects
        against partial PUTs clobbering the stored secret.
    """
    app_password_provided = "app_password" in payload
    app_password: str | None = None
    if app_password_provided:
        app_password = str(payload.get("app_password", "")).strip()
    effective_has_password = bool(current["app_password_configured"])
    if app_password_provided:
        effective_has_password = bool(app_password)
    return app_password, app_password_provided, effective_has_password


def _validate_wp_credentials_consistency(
    *,
    base_url: str,
    username: str,
    has_password: bool,
    sync_enabled: bool,
) -> None:
    """Cross-field consistency rules for the WordPress credential set."""
    if username and not has_password:
        raise ValueError(
            "Application Password is required when a WordPress username is configured."
        )
    if has_password and not username:
        raise ValueError(
            "username is required when an Application Password is configured."
        )
    if sync_enabled and not base_url:
        raise ValueError(
            "base_url is required when scheduled WordPress sync is enabled."
        )


def _validate_wordpress_settings(payload: dict) -> dict[str, object]:
    current = get_wordpress_settings()

    base_url = str(payload.get("base_url", current["base_url"])).strip().rstrip("/")
    username = str(payload.get("username", current["username"])).strip()
    if base_url:
        parsed = urlparse(base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("base_url must be a valid http(s) URL.")

    app_password, app_password_provided, effective_has_password = (
        _resolve_wp_app_password(payload, current)
    )

    sync_enabled = coerce_bool(
        payload.get("sync_enabled"), default=bool(current["sync_enabled"])
    )
    validated_sync = {
        "sync_hour": coerce_setting_int(payload, current, "sync_hour"),
        "sync_minute": coerce_setting_int(payload, current, "sync_minute"),
    }
    enforce_bounds(validated_sync, {"sync_hour": (0, 23), "sync_minute": (0, 59)})

    _validate_wp_credentials_consistency(
        base_url=base_url,
        username=username,
        has_password=effective_has_password,
        sync_enabled=sync_enabled,
    )

    return {
        "base_url": base_url,
        "username": username,
        "app_password": app_password,
        "app_password_provided": app_password_provided,
        "app_password_configured": effective_has_password,
        "sync_enabled": sync_enabled,
        **validated_sync,
    }


_WEIGHTED_AUTHORITY_BOUNDS: dict[str, tuple[float, float]] = {
    "ranking_weight": (0.0, 0.25),
    "position_bias": (0.0, 1.0),
    "empty_anchor_factor": (0.1, 1.0),
    "bare_url_factor": (0.1, 1.0),
    "weak_context_factor": (0.1, 1.0),
    "isolated_context_factor": (0.1, 1.0),
}


def _validate_weighted_authority_settings(
    payload: dict,
    *,
    current: dict[str, float] | None = None,
) -> dict[str, float]:
    current = current or _read_weighted_authority_settings()

    validated = {
        key: coerce_setting_float(payload, current, key)
        for key in _WEIGHTED_AUTHORITY_BOUNDS
    }
    enforce_bounds(validated, _WEIGHTED_AUTHORITY_BOUNDS)

    if validated["isolated_context_factor"] > validated["weak_context_factor"]:
        raise ValueError("isolated_context_factor must be <= weak_context_factor.")
    if validated["weak_context_factor"] > 1.0:
        raise ValueError("weak_context_factor must be <= 1.0.")
    if validated["bare_url_factor"] > 1.0:
        raise ValueError("bare_url_factor must be <= 1.0.")

    return validated


_LINK_FRESHNESS_BOUNDS: dict[str, tuple[float, float]] = {
    "ranking_weight": (0.0, 0.15),
    "recent_window_days": (7, 90),
    "newest_peer_percent": (0.10, 0.50),
    "min_peer_count": (1, 20),
    "w_recent": (0.0, 1.0),
    "w_growth": (0.0, 1.0),
    "w_cohort": (0.0, 1.0),
    "w_loss": (0.0, 1.0),
}
_LINK_FRESHNESS_FLOAT_KEYS = (
    "ranking_weight",
    "newest_peer_percent",
    "w_recent",
    "w_growth",
    "w_cohort",
    "w_loss",
)
_LINK_FRESHNESS_INT_KEYS = ("recent_window_days", "min_peer_count")


def _validate_link_freshness_settings(
    payload: dict,
    *,
    current: dict[str, float | int] | None = None,
) -> dict[str, float | int]:
    current = current or _read_link_freshness_settings()

    validated: dict[str, float | int] = {
        key: coerce_setting_float(payload, current, key)
        for key in _LINK_FRESHNESS_FLOAT_KEYS
    }
    for key in _LINK_FRESHNESS_INT_KEYS:
        validated[key] = coerce_setting_int(payload, current, key)

    enforce_bounds(validated, _LINK_FRESHNESS_BOUNDS)

    weight_total = sum(
        float(validated[k]) for k in ("w_recent", "w_growth", "w_cohort", "w_loss")
    )
    if not math.isclose(weight_total, 1.0, rel_tol=0.0, abs_tol=1e-6):
        raise ValueError("w_recent + w_growth + w_cohort + w_loss must equal 1.0.")

    return validated


_PHRASE_MATCHING_BOUNDS: dict[str, tuple[float, float]] = {
    "ranking_weight": (0.0, 0.10),
    "context_window_tokens": (4, 12),
}


def _validate_phrase_matching_settings(
    payload: dict,
    *,
    current: dict[str, float | int | bool] | None = None,
) -> dict[str, float | int | bool]:
    current = current or _read_phrase_matching_settings()
    validated: dict[str, float | int | bool] = {
        "ranking_weight": coerce_setting_float(payload, current, "ranking_weight"),
        "enable_anchor_expansion": coerce_setting_bool(
            payload, current, "enable_anchor_expansion"
        ),
        "enable_partial_matching": coerce_setting_bool(
            payload, current, "enable_partial_matching"
        ),
        "context_window_tokens": coerce_setting_int(
            payload, current, "context_window_tokens"
        ),
    }
    enforce_bounds(validated, _PHRASE_MATCHING_BOUNDS)
    return validated


_LEARNED_ANCHOR_BOUNDS: dict[str, tuple[float, float]] = {
    "ranking_weight": (0.0, 0.10),
    "minimum_anchor_sources": (1, 10),
    "minimum_family_support_share": (0.05, 0.50),
}


def _validate_learned_anchor_settings(
    payload: dict,
    *,
    current: dict[str, float | int | bool] | None = None,
) -> dict[str, float | int | bool]:
    current = current or _read_learned_anchor_settings()
    validated: dict[str, float | int | bool] = {
        "ranking_weight": coerce_setting_float(payload, current, "ranking_weight"),
        "minimum_anchor_sources": coerce_setting_int(
            payload, current, "minimum_anchor_sources"
        ),
        "minimum_family_support_share": coerce_setting_float(
            payload, current, "minimum_family_support_share"
        ),
        "enable_noise_filter": coerce_setting_bool(
            payload, current, "enable_noise_filter"
        ),
    }
    enforce_bounds(validated, _LEARNED_ANCHOR_BOUNDS)
    return validated


_RARE_TERM_PROPAGATION_BOUNDS: dict[str, tuple[float, float]] = {
    "ranking_weight": (0.0, 0.10),
    "max_document_frequency": (1, 10),
    "minimum_supporting_related_pages": (1, 5),
}


def _validate_rare_term_propagation_settings(
    payload: dict,
    *,
    current: dict[str, float | int | bool] | None = None,
) -> dict[str, float | int | bool]:
    current = current or _read_rare_term_propagation_settings()
    validated: dict[str, float | int | bool] = {
        "enabled": coerce_setting_bool(payload, current, "enabled"),
        "ranking_weight": coerce_setting_float(payload, current, "ranking_weight"),
        "max_document_frequency": coerce_setting_int(
            payload, current, "max_document_frequency"
        ),
        "minimum_supporting_related_pages": coerce_setting_int(
            payload, current, "minimum_supporting_related_pages"
        ),
    }
    enforce_bounds(validated, _RARE_TERM_PROPAGATION_BOUNDS)
    return validated


_FIELD_AWARE_RELEVANCE_KEYS = (
    "ranking_weight",
    "title_field_weight",
    "body_field_weight",
    "scope_field_weight",
    "learned_anchor_field_weight",
)
_FIELD_AWARE_RELEVANCE_FIELD_KEYS = (
    "title_field_weight",
    "body_field_weight",
    "scope_field_weight",
    "learned_anchor_field_weight",
)
_FIELD_AWARE_RELEVANCE_BOUNDS: dict[str, tuple[float, float]] = {
    "ranking_weight": (0.0, 0.15),
    "title_field_weight": (0.0, 1.0),
    "body_field_weight": (0.0, 1.0),
    "scope_field_weight": (0.0, 1.0),
    "learned_anchor_field_weight": (0.0, 1.0),
}


def _validate_field_aware_relevance_settings(
    payload: dict,
    *,
    current: dict[str, float] | None = None,
) -> dict[str, float]:
    current = current or _read_field_aware_relevance_settings()

    validated = {
        key: coerce_setting_float(payload, current, key)
        for key in _FIELD_AWARE_RELEVANCE_KEYS
    }
    enforce_bounds(validated, _FIELD_AWARE_RELEVANCE_BOUNDS)

    field_weight_sum = sum(validated[key] for key in _FIELD_AWARE_RELEVANCE_FIELD_KEYS)
    if not math.isclose(field_weight_sum, 1.0, abs_tol=1e-6):
        raise ValueError(
            "title/body/scope/learned-anchor field weights must sum to 1.0."
        )

    return validated


def _coerce_float_strict(value: object, *, key: str) -> float:
    """Strict-raising float coercion used by GA4/GSC + similar settings.

    Reused across multiple settings validators so we don't keep
    re-defining the "raise ValueError on non-numeric or infinite"
    contract inline. Different from ``coerce_float`` which silently
    falls back to a default — this one IS the validation step.
    """
    try:
        coerced = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{key} must be numeric.") from exc
    if not math.isfinite(coerced):
        raise ValueError(f"{key} must be finite.")
    return coerced


def _coerce_int_strict(value: object, *, key: str, minimum: int, maximum: int) -> int:
    """Strict-raising int coercion + range check (raises on bad input)."""
    try:
        coerced = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{key} must be a whole number.") from exc
    if coerced < minimum or coerced > maximum:
        raise ValueError(f"{key} must be between {minimum} and {maximum}.")
    return coerced


def _coerce_bool_strict(value: object, *, key: str) -> bool:
    """Strict-raising bool coercion. Uses the canonical truthy/falsy sets.

    Reuses the shared ``TRUTHY_STRING_VALUES`` / ``FALSY_STRING_VALUES``
    constants so a future tweak to the truthy set propagates everywhere.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        from apps.api.query_params import (
            FALSY_STRING_VALUES,
            TRUTHY_STRING_VALUES,
        )

        if lowered in TRUTHY_STRING_VALUES:
            return True
        if lowered in FALSY_STRING_VALUES:
            return False
    raise ValueError(f"{key} must be true or false.")


def _validate_ga4_gsc_settings(
    payload: dict,
    *,
    current: dict[str, object] | None = None,
) -> dict[str, object]:
    """Refactored 2026-05-04: 80 → 30 lines.

    Inner coercer closures replaced with module-level strict-raising
    helpers (``_coerce_*_strict``) so the validation contract can be
    reused by other settings validators. Cross-field consistency checks
    extracted into ``_validate_ga4_gsc_consistency``.
    """
    current = current or _read_ga4_gsc_settings()

    validated: dict[str, object] = {
        "ranking_weight": _coerce_float_strict(
            payload.get("ranking_weight", current["ranking_weight"]),
            key="ranking_weight",
        ),
        "property_url": str(payload.get("property_url", current["property_url"]))
        .strip()
        .rstrip("/"),
        "service_account_email": str(
            payload.get("service_account_email", current["service_account_email"])
        ).strip(),
        "sync_enabled": _coerce_bool_strict(
            payload.get("sync_enabled", current["sync_enabled"]), key="sync_enabled"
        ),
        "sync_lookback_days": _coerce_int_strict(
            payload.get("sync_lookback_days", current["sync_lookback_days"]),
            key="sync_lookback_days",
            minimum=1,
            maximum=30,
        ),
    }
    private_key_provided = "private_key" in payload
    private_key = (
        str(payload.get("private_key", "")).strip() if private_key_provided else None
    )
    _validate_ga4_gsc_consistency(validated, current, private_key=private_key)
    validated["private_key"] = private_key
    validated["private_key_provided"] = private_key_provided
    return validated


def _validate_ga4_gsc_consistency(
    validated: dict, current: dict, *, private_key: str | None
) -> None:
    """Cross-field consistency checks for GA4/GSC settings. Raises on failure."""
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
            "Search Console sync needs property_url, service_account_email, "
            "and private_key."
        )


_FEEDBACK_RERANK_BOUNDS: dict[str, tuple[float, float]] = {
    "ranking_weight": (0.0, 0.5),
    "exploration_rate": (0.1, 2.0),
}


def _validate_feedback_rerank_settings(
    payload: dict,
    *,
    current: dict[str, float | bool] | None = None,
) -> dict[str, float | bool]:
    """Validate and clamp feedback-driven explore/exploit settings.

    Sister-bug fix 2026-05-04: replaced ad-hoc bool coercer that didn't
    accept ``"y"`` / ``"Y"`` with the project-wide ``coerce_setting_bool``
    so this endpoint's bool semantics match every other settings PUT.
    """
    current = current or _read_feedback_rerank_settings()
    validated: dict[str, float | bool] = {
        "enabled": coerce_setting_bool(payload, current, "enabled"),
        "ranking_weight": coerce_setting_float(payload, current, "ranking_weight"),
        "exploration_rate": coerce_setting_float(payload, current, "exploration_rate"),
    }
    enforce_bounds(validated, _FEEDBACK_RERANK_BOUNDS)
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
        """Aggregate every dashboard panel into one Response.

        Refactored 2026-05-04: was a 175-line monolith. Now delegates
        every panel to a per-section helper (``_dashboard_*``) so each
        piece is independently testable and the handler reads top-down
        like documentation. Behaviour preserved exactly.
        """
        return Response(
            {
                "suggestion_counts": _dashboard_suggestion_counts(),
                "content_count": _dashboard_content_count(),
                "open_broken_links": _dashboard_open_broken_links(),
                "last_sync": _dashboard_last_completed_sync(),
                "pipeline_runs": _dashboard_recent_pipeline_runs(),
                "recent_imports": _dashboard_recent_imports(),
                "system_health": _dashboard_system_health(),
                **_dashboard_freshness_timestamps(),
                "runtime_mode": _dashboard_runtime_mode_display(),
                "show_quick_controls": recommended_bool(
                    "dashboard.show_quick_controls"
                ),
                # Phase 4.3 — Confidence Meter "Ready to Rock" snapshot.
                # Cached 60 s in Redis so the dashboard read is cheap.
                # Falls back to None on any failure so the chip just
                # hides instead of breaking the dashboard.
                "confidence": _safe_confidence_snapshot(),
            }
        )


# ── Dashboard panel helpers ──────────────────────────────────────
# Extracted from DashboardView.get to keep that handler under the
# 50-line lint budget AND make each panel independently testable.


def _dashboard_suggestion_counts() -> dict[str, int]:
    """Phase 2.18 — read from the matview (with live-ORM fallback).

    Returns a dict shaped for the frontend with every status the UI
    knows about, even when the count is 0 — so downstream JS doesn't
    need null-checks.
    """
    from apps.core.services.dashboard_aggregates import (
        get_suggestion_status_counts,
    )

    counts = get_suggestion_status_counts()
    return {
        "pending": counts.get("pending", 0),
        "approved": counts.get("approved", 0),
        "rejected": counts.get("rejected", 0),
        "applied": counts.get("applied", 0),
        "total": sum(counts.values()),
    }


def _dashboard_content_count() -> int:
    from apps.content.models import ContentItem

    return ContentItem.objects.count()


def _dashboard_open_broken_links() -> int:
    from apps.graph.models import BrokenLink

    return BrokenLink.objects.filter(status="open").count()


def _dashboard_last_completed_sync():
    from apps.sync.models import SyncJob

    return (
        SyncJob.objects.filter(status="completed")
        .values("completed_at", "source", "mode", "items_synced")
        .order_by("-completed_at")
        .first()
    )


def _dashboard_recent_pipeline_runs() -> list[dict]:
    """Last 5 pipeline runs with stringified IDs + duration display."""
    from apps.suggestions.models import PipelineRun

    runs = list(
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
    for run in runs:
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
    return runs


def _dashboard_recent_imports() -> list[dict]:
    """Last 5 SyncJob rows with stringified IDs + ISO timestamps."""
    from apps.sync.models import SyncJob

    jobs = list(
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
    for job in jobs:
        job["job_id"] = str(job["job_id"])
        if job["created_at"]:
            job["created_at"] = job["created_at"].isoformat()
        if job["completed_at"]:
            job["completed_at"] = job["completed_at"].isoformat()
    return jobs


def _dashboard_system_health() -> dict:
    """Aggregate per-status counts + overall verdict from health records."""
    from django.db.models import Count

    from apps.health.models import ServiceHealthRecord

    records = ServiceHealthRecord.objects.all()
    status_counts = records.values("status").annotate(count=Count("status"))
    summary = {row["status"]: row["count"] for row in status_counts}
    return {
        "status": _dashboard_overall_health_status(records),
        "summary": summary,
        "total_monitored": records.count(),
    }


def _dashboard_overall_health_status(records) -> str:
    """Pure function: pick the worst severity present across health records."""
    from apps.health.models import ServiceHealthRecord

    if any(r.status == ServiceHealthRecord.STATUS_DOWN for r in records):
        return ServiceHealthRecord.STATUS_DOWN
    if any(
        r.status in (ServiceHealthRecord.STATUS_ERROR, ServiceHealthRecord.STATUS_STALE)
        for r in records
    ):
        return ServiceHealthRecord.STATUS_ERROR
    if any(r.status == ServiceHealthRecord.STATUS_WARNING for r in records):
        return ServiceHealthRecord.STATUS_WARNING
    return ServiceHealthRecord.STATUS_HEALTHY


def _dashboard_freshness_timestamps() -> dict[str, str | None]:
    """Three ISO timestamps for the dashboard's freshness ribbon."""
    from apps.suggestions.models import PipelineRun
    from apps.sync.models import SyncJob

    last_sync = (
        SyncJob.objects.filter(status="completed")
        .values_list("completed_at", flat=True)
        .order_by("-completed_at")
        .first()
    )
    last_pipeline = (
        PipelineRun.objects.filter(run_state="completed")
        .values_list("updated_at", flat=True)
        .order_by("-updated_at")
        .first()
    )
    last_analytics = _dashboard_last_analytics_completed_at()
    return {
        "last_sync_at": last_sync.isoformat() if last_sync else None,
        "last_pipeline_at": last_pipeline.isoformat() if last_pipeline else None,
        "last_analytics_at": last_analytics.isoformat() if last_analytics else None,
    }


def _dashboard_last_analytics_completed_at():
    """Defensive: returns the last GSC sync timestamp or None.

    The GSC analytics model isn't shipped in every install (older
    deployments + minimal configurations); a missing import is normal
    and should not break the dashboard.
    """
    try:
        from apps.analytics.models import GSCSyncRun

        return (
            GSCSyncRun.objects.filter(status="completed")
            .values_list("completed_at", flat=True)
            .order_by("-completed_at")
            .first()
        )
    except Exception:  # noqa: BLE001 — analytics module is optional; missing-import is documented behaviour.
        logger.debug("GSCSyncRun model not available, skipping analytics freshness")
        return None


def _dashboard_runtime_mode_display() -> str:
    """Live effective device (CPU / GPU) — uppercase for the dashboard chip."""
    try:
        from apps.pipeline.services.embeddings import (
            get_effective_runtime_resolution,
        )

        return get_effective_runtime_resolution()["effective_runtime_mode"].upper()
    except Exception:  # noqa: BLE001 — embeddings module unavailable on cold start; CPU is the safe default.
        logger.debug("Embedding runtime unavailable, using default runtime_mode")
        return "CPU"


# ---------------------------------------------------------------------------
# Dashboard operating desk endpoints (Stage 3)
# ---------------------------------------------------------------------------


# ── TodayActionsView priority-rule helpers ──────────────────────
# Each rule is a pure function returning ``list[dict]`` of action items.
# Splitting per rule means each can be unit-tested + a future operator
# tweak (e.g. "raise pending-review threshold to 50") touches one
# place, not an inline-mixed-with-others block.

_PENDING_REVIEW_THRESHOLD = 20
_STALE_SYNC_HOURS = 48
_STALE_PIPELINE_DAYS = 14


def _today_actions_urgent_alerts() -> list[dict]:
    """Top-3 unread urgent / error OperatorAlerts."""
    from apps.notifications.models import OperatorAlert

    alerts = OperatorAlert.objects.filter(
        status="unread", severity__in=["urgent", "error"]
    ).order_by("-first_seen_at")[:3]
    return [
        {
            "title": alert.title,
            "reason": (
                f"Unresolved {alert.severity} alert since "
                f"{alert.first_seen_at:%b %d}"
            ),
            "route": f"/alerts/{alert.alert_id}",
            "severity": alert.severity,
            "isBlocking": alert.severity == "urgent",
        }
        for alert in alerts
    ]


def _today_actions_sync_freshness(now) -> list[dict]:
    """Stale-sync (>48h) or no-sync-yet warning."""
    from apps.sync.models import SyncJob

    last_sync = (
        SyncJob.objects.filter(status="completed").order_by("-completed_at").first()
    )
    if last_sync is None:
        return [
            {
                "title": "No content synced yet",
                "reason": "Run your first content sync to get started.",
                "route": "/jobs",
                "severity": "warning",
                "isBlocking": False,
            }
        ]
    if not last_sync.completed_at:
        return []
    hours_since = (now - last_sync.completed_at).total_seconds() / 3600
    if hours_since <= _STALE_SYNC_HOURS:
        return []
    days = int(hours_since // 24)
    return [
        {
            "title": "Content is getting stale",
            "reason": (
                f"Last sync was {days} days ago. Run a fresh sync to "
                "catch new content."
            ),
            "route": "/jobs",
            "severity": "warning",
            "isBlocking": False,
        }
    ]


def _today_actions_pending_suggestions() -> list[dict]:
    """Pending-review backlog warning when the queue exceeds the threshold."""
    from apps.suggestions.models import Suggestion

    pending_count = Suggestion.objects.filter(status="pending").count()
    if pending_count <= _PENDING_REVIEW_THRESHOLD:
        return []
    return [
        {
            "title": f"{pending_count} suggestions waiting for review",
            "reason": (
                "Review and approve link suggestions to improve your "
                "internal linking."
            ),
            "route": "/review",
            "severity": "info",
            "isBlocking": False,
        }
    ]


def _today_actions_pipeline_freshness(now) -> list[dict]:
    """Stale-pipeline + zero-suggestion-on-last-run warnings (one or both)."""
    from apps.suggestions.models import PipelineRun

    last_run = (
        PipelineRun.objects.filter(run_state="completed")
        .order_by("-updated_at")
        .first()
    )
    if last_run is None:
        return []
    actions: list[dict] = []
    if last_run.updated_at and (now - last_run.updated_at).days > _STALE_PIPELINE_DAYS:
        days_since = (now - last_run.updated_at).days
        actions.append(
            {
                "title": "Pipeline hasn't run in a while",
                "reason": (
                    f"Last pipeline run was {days_since} days ago. Run "
                    "it to generate fresh suggestions."
                ),
                "route": "/jobs",
                "severity": "info",
                "isBlocking": False,
            }
        )
    if last_run.suggestions_created == 0:
        actions.append(
            {
                "title": "Last pipeline produced no suggestions",
                "reason": ("Check your settings — the pipeline may need tuning."),
                "route": "/settings",
                "deepLinkTarget": "ranking-weights",
                "severity": "warning",
                "isBlocking": False,
            }
        )
    return actions


class TodayActionsView(APIView):
    """GET /api/dashboard/today-actions/

    Returns up to 5 priority-ranked action items for the current day.
    Priority waterfall: blocking alert > stale sync > pending review > idle.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        """Return up to 5 priority-ranked action items for the operator.

        Refactored 2026-05-04: was 98 lines walking 5 distinct rule
        blocks inline. Now each rule is its own pure function returning
        ``list[dict]``; the handler concatenates + caps at 5. Each rule
        is independently testable.
        """
        from django.utils import timezone

        now = timezone.now()
        actions: list[dict] = []
        actions.extend(_today_actions_urgent_alerts())
        actions.extend(_today_actions_sync_freshness(now))
        actions.extend(_today_actions_pending_suggestions())
        actions.extend(_today_actions_pipeline_freshness(now))
        return Response(actions[:5])


class WhatChangedView(APIView):
    """GET /api/dashboard/what-changed/

    Returns counts of changes in the last 24 hours plus autotuner outcomes.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        from django.utils import timezone
        from datetime import timedelta

        since = timezone.now() - timedelta(hours=24)
        return Response(
            {
                "period_hours": 24,
                **_today_summary_counts(since),
                "autotuner_outcome": _today_autotuner_outcome(since),
            }
        )


def _today_summary_counts(since) -> dict[str, int]:
    """Counts of suggestions / reviews / sync items / pipeline runs since ``since``."""
    from apps.suggestions.models import PipelineRun, Suggestion
    from apps.sync.models import SyncJob

    synced_items = SyncJob.objects.filter(
        status="completed",
        completed_at__gte=since,
    ).values_list("items_synced", flat=True)
    return {
        "new_suggestions": Suggestion.objects.filter(created_at__gte=since).count(),
        "reviewed": Suggestion.objects.filter(reviewed_at__gte=since).count(),
        "items_synced": sum(synced_items),
        "pipeline_runs": PipelineRun.objects.filter(created_at__gte=since).count(),
    }


def _today_autotuner_outcome(since) -> dict | None:
    """Most-recent challenger promoted/rolled-back since ``since``; None if none."""
    try:
        from apps.suggestions.models import RankingChallenger
    except Exception:
        logger.debug(
            "RankingChallenger model not available, skipping autotuner outcome"
        )
        return None
    recent_challenger = (
        RankingChallenger.objects.filter(updated_at__gte=since)
        .exclude(status="pending")
        .order_by("-updated_at")
        .first()
    )
    if recent_challenger is None:
        return None
    return {
        "status": recent_challenger.status,
        "label": (
            recent_challenger.label
            if hasattr(recent_challenger, "label")
            else str(recent_challenger.pk)
        ),
        "updated_at": recent_challenger.updated_at.isoformat(),
    }


# ── ResumeStateView helpers (extracted from .get) ────────────────


def _resume_view_interrupted_runs() -> list[dict]:
    """Top-3 pipeline runs still in 'running' state (likely interrupted)."""
    from apps.suggestions.models import PipelineRun

    runs = list(
        PipelineRun.objects.filter(run_state="running")
        .values("run_id", "run_state", "created_at", "updated_at")
        .order_by("-created_at")[:3]
    )
    for run in runs:
        run["run_id"] = str(run["run_id"])
        if run["created_at"]:
            run["created_at"] = run["created_at"].isoformat()
        if run["updated_at"]:
            run["updated_at"] = run["updated_at"].isoformat()
    return runs


def _resume_view_resumable_syncs() -> list[dict]:
    """Top-3 sync jobs flagged resumable + not yet completed."""
    from apps.sync.models import SyncJob

    jobs = list(
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
    for job in jobs:
        job["job_id"] = str(job["job_id"])
    return jobs


def _resume_view_missed_tasks() -> list[dict]:
    """Catch-up registry: tasks past their threshold or never-ran.

    Defensive: catch-up registry / django_celery_beat may not be loaded
    on minimal installs; returns empty list silently in that case.
    """
    try:
        from django.utils import timezone
        from django_celery_beat.models import PeriodicTask

        from config.catchup_registry import CATCHUP_REGISTRY
    except Exception:  # noqa: BLE001 — optional dependency on minimal installs.
        logger.debug("Catch-up registry unavailable, skipping missed tasks check")
        return []

    now = timezone.now()
    missed: list[dict] = []
    for task_name, entry in CATCHUP_REGISTRY.items():
        periodic = PeriodicTask.objects.filter(name=task_name).first()
        if periodic is None:
            continue
        if periodic.last_run_at is None:
            missed.append(
                {
                    "task_name": task_name,
                    "weight_class": entry.weight_class,
                    "hours_overdue": None,
                    "reason": "Never ran",
                }
            )
            continue
        hours_since = (now - periodic.last_run_at).total_seconds() / 3600
        if hours_since > entry.threshold_hours:
            missed.append(
                {
                    "task_name": task_name,
                    "weight_class": entry.weight_class,
                    "hours_overdue": round(hours_since - entry.threshold_hours, 1),
                    "reason": (
                        f"Last ran {int(hours_since)}h ago "
                        f"(threshold: {int(entry.threshold_hours)}h)"
                    ),
                }
            )
    return missed


class ResumeStateView(APIView):
    """GET /api/dashboard/resume-state/

    Returns interrupted pipeline runs, last review position, and missed
    tasks from the catch-up registry.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        """Return interrupted runs + resumable syncs + missed-task breadcrumbs.

        Refactored 2026-05-04: was 78 lines. Each section is now its own
        helper so a future operator-UX tweak (e.g. raise the limit
        from 3 → 10) is one edit per section.
        """
        return Response(
            {
                "interrupted_runs": _resume_view_interrupted_runs(),
                "resumable_syncs": _resume_view_resumable_syncs(),
                "missed_tasks": _resume_view_missed_tasks(),
            }
        )


# ── Status-story helpers (extracted from StatusStoryView.get) ───
# Each query is a thin defensive helper that returns 0 / "unknown" if
# the upstream model isn't loadable (cold start, optional-app missing).
# Each fragment-builder is pure so the narrative copy is testable
# without spinning up a request lifecycle.


def _status_story_alert_count(since: object) -> int:
    """Count today's unread urgent / error / warning alerts."""
    from apps.notifications.models import OperatorAlert

    return OperatorAlert.objects.filter(
        first_seen_at__gte=since,
        status="unread",
        severity__in=["urgent", "error", "warning"],
    ).count()


def _status_story_pending_count() -> int:
    from apps.suggestions.models import Suggestion

    return Suggestion.objects.filter(status="pending").count()


def _status_story_health_status() -> str:
    """Best-effort: 'unknown' when the health app can't compute a summary."""
    try:
        from apps.health.services import compute_system_summary

        return compute_system_summary().get("system_status", "unknown")
    except Exception:  # noqa: BLE001 — health app is optional; narrative gracefully omits the fragment when unknown.
        logger.debug("health summary unavailable for status story")
        return "unknown"


def _status_story_broken_links_count() -> int:
    """Best-effort: 0 when the graph app isn't migrated."""
    try:
        from apps.graph.models import BrokenLink

        return BrokenLink.objects.filter(status="open").count()
    except Exception:  # noqa: BLE001 — graph app is optional on cold start.
        logger.debug("BrokenLink not available for status story")
        return 0


def _status_story_alerts_fragment(alerts_today: int) -> str:
    if alerts_today == 0:
        return "no new alerts"
    if alerts_today == 1:
        return "1 alert fired today"
    return f"{alerts_today} alerts fired today"


def _status_story_health_fragment(health_status: str) -> str | None:
    """Returns ``None`` when health is 'unknown' — narrative omits it."""
    if health_status == "healthy":
        return "all systems healthy"
    if health_status == "degraded":
        return "some services degraded"
    if health_status in ("critical", "error"):
        return "a critical service is down"
    return None  # 'unknown' stays silent rather than mislead


def _status_story_pending_fragment(pending_reviews: int) -> str:
    if pending_reviews == 0:
        return "no suggestions waiting"
    if pending_reviews == 1:
        return "1 suggestion waiting for review"
    return f"{pending_reviews} suggestions waiting for review"


def _status_story_broken_fragment(broken_links_open: int) -> str | None:
    """Only mentioned when broken-link count > 0 — silence is healthy."""
    if broken_links_open <= 0:
        return None
    return _pluralise(broken_links_open, "broken link")


def _status_story_fragments(
    *,
    alerts_today: int,
    health_status: str,
    pending_reviews: int,
    broken_links_open: int,
) -> list[str]:
    """Compose the per-bullet narrative; drop None fragments."""
    candidates = [
        _status_story_alerts_fragment(alerts_today),
        _status_story_health_fragment(health_status),
        _status_story_pending_fragment(pending_reviews),
        _status_story_broken_fragment(broken_links_open),
    ]
    return [f for f in candidates if f]


def _status_story_time_prefix(hour: int) -> str:
    if hour < 12:
        return "This morning"
    if hour < 17:
        return "This afternoon"
    return "This evening"


class StatusStoryView(APIView):
    """GET /api/dashboard/story/

    Phase D1 / Gap 53 — a plain-English narrative summary for the
    dashboard's "Status Story" card.

    Composes one or two sentences from data the frontend already
    has, plus counts that would be awkward to aggregate client-side.
    Refreshed every 5 minutes by the caller (dashboard component).

    Example output:
        "This morning: 3 alerts fired, Celery is healthy, 47
         suggestions are waiting for review."
        "Quiet so far — no alerts, no broken links, 12 suggestions
         ready."
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        """Return a 1-line operator narrative + supporting counts.

        Refactored 2026-05-04: was 95 lines. Each data-source query +
        each fragment-builder is now its own pure function so adding a
        new narrative bullet (or unit-testing the existing ones) is a
        single edit.
        """
        from django.utils import timezone

        now = timezone.now()
        since_morning = now.replace(hour=0, minute=0, second=0, microsecond=0)

        alerts_today = _status_story_alert_count(since_morning)
        pending_reviews = _status_story_pending_count()
        health_status = _status_story_health_status()
        broken_links_open = _status_story_broken_links_count()

        fragments = _status_story_fragments(
            alerts_today=alerts_today,
            health_status=health_status,
            pending_reviews=pending_reviews,
            broken_links_open=broken_links_open,
        )
        return Response(
            {
                "headline": f"{_status_story_time_prefix(now.hour)}: {self._join_fragments(fragments)}.",
                "fragments": fragments,
                "alerts_today": alerts_today,
                "pending_reviews": pending_reviews,
                "broken_links_open": broken_links_open,
                "health_status": health_status,
                "generated_at": now.isoformat(),
            }
        )

    @staticmethod
    def _join_fragments(fragments: list[str]) -> str:
        if not fragments:
            return "nothing to report"
        if len(fragments) == 1:
            return fragments[0]
        if len(fragments) == 2:
            return f"{fragments[0]} and {fragments[1]}"
        return ", ".join(fragments[:-1]) + f", and {fragments[-1]}"


class MissionBriefView(APIView):
    """GET /api/dashboard/mission-brief/

    Phase D1 / Gap 61 — a pinned three-sentence summary for the
    dashboard header. Differs from StatusStoryView by timeframe:
    Mission Brief is the morning executive summary (yesterday's
    outcomes + today's priorities), Status Story is a rolling
    present-tense snapshot.

    Three sentences, plain English:
      1. Yesterday: what the system did (counts).
      2. Today: what's queued (counts).
      3. Watch: the single most pressing thing to fix, if any.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        """Return the 3-sentence "Today" summary + supporting counts.

        Refactored 2026-05-04: was 114 lines. Each sentence + the
        top-alert lookup is now a separate helper so the handler reads
        like a brief — and each helper is independently testable.
        """
        from datetime import timedelta

        from django.utils import timezone

        now = timezone.now()
        yesterday_cutoff = now - timedelta(hours=24)

        yesterday = _today_view_yesterday_counts(yesterday_cutoff)
        today_queue = _today_view_today_queue_counts()
        top_alert = _today_view_top_alert()

        return Response(
            {
                "sentences": [
                    _today_view_sentence_yesterday(yesterday),
                    _today_view_sentence_today(today_queue),
                    _today_view_sentence_watch(top_alert),
                ],
                "counts": {
                    "approved_last_24h": yesterday["approved"],
                    "synced_last_24h": yesterday["synced"],
                    "pipeline_runs_last_24h": yesterday["pipeline_runs"],
                    "pending_reviews": today_queue["pending_reviews"],
                    "running_syncs": today_queue["running_syncs"],
                },
                "top_alert": _today_view_top_alert_dict(top_alert),
                "generated_at": now.isoformat(),
            }
        )


# ── Today-actions helpers (extracted from TodayActionsView.get) ──


def _today_view_yesterday_counts(cutoff) -> dict[str, int]:
    """Count approvals / sync completions / pipeline runs since *cutoff*."""
    from apps.suggestions.models import PipelineRun, Suggestion
    from apps.sync.models import SyncJob

    return {
        "approved": Suggestion.objects.filter(
            status="approved", reviewed_at__gte=cutoff
        ).count(),
        "synced": SyncJob.objects.filter(
            status="completed", completed_at__gte=cutoff
        ).count(),
        "pipeline_runs": PipelineRun.objects.filter(created_at__gte=cutoff).count(),
    }


def _today_view_today_queue_counts() -> dict[str, int]:
    """Live queue counts (pending reviews + in-flight syncs)."""
    from apps.suggestions.models import Suggestion
    from apps.sync.models import SyncJob

    return {
        "pending_reviews": Suggestion.objects.filter(status="pending").count(),
        "running_syncs": SyncJob.objects.filter(
            status__in=["running", "pending"]
        ).count(),
    }


def _today_view_top_alert():
    """Most pressing unread alert (urgent or error severity), or None."""
    from apps.notifications.models import OperatorAlert

    return (
        OperatorAlert.objects.filter(status="unread", severity__in=["urgent", "error"])
        .order_by("-first_seen_at")
        .first()
    )


def _today_view_top_alert_dict(top_alert) -> dict | None:
    """Serialise the top-alert object for the JSON payload, or None."""
    if top_alert is None:
        return None
    return {
        "alert_id": str(top_alert.alert_id),
        "severity": top_alert.severity,
        "title": top_alert.title,
    }


def _pluralise(n: int, singular: str, plural: str = "") -> str:
    """Format ``"N word"`` / ``"N words"`` — single source for the
    pluralisation that was inline in 5+ places in the today-view body."""
    word = singular if n == 1 else (plural or f"{singular}s")
    return f"{n} {word}"


def _today_view_sentence_yesterday(counts: dict[str, int]) -> str:
    """Build the plain-English sentence describing the last 24 hours."""
    parts: list[str] = []
    if counts["approved"]:
        parts.append(f"{_pluralise(counts['approved'], 'suggestion')} approved")
    if counts["synced"]:
        parts.append(f"{_pluralise(counts['synced'], 'sync job')} finished")
    if counts["pipeline_runs"]:
        parts.append(_pluralise(counts["pipeline_runs"], "pipeline run"))
    if not parts:
        return "In the last 24 hours nothing was approved or synced."
    return "In the last 24 hours: " + ", ".join(parts) + "."


def _today_view_sentence_today(queue: dict[str, int]) -> str:
    """Build the plain-English sentence describing the right-now queue."""
    parts: list[str] = []
    if queue["pending_reviews"]:
        parts.append(
            f"{_pluralise(queue['pending_reviews'], 'suggestion')} waiting for review"
        )
    if queue["running_syncs"]:
        parts.append(f"{_pluralise(queue['running_syncs'], 'sync')} in flight")
    if not parts:
        return "Right now the queue is clear."
    return "Right now: " + " and ".join(parts) + "."


def _today_view_sentence_watch(top_alert) -> str:
    """Build the plain-English sentence describing the most pressing alert."""
    if top_alert is None:
        return "Nothing is on fire."
    return f'Watch: {top_alert.severity} alert — "{top_alert.title[:80]}".'


# ── JobQueueView helpers (extracted from .get) ───────────────────


def _job_queue_active_runs() -> list[dict]:
    """Active + queued PipelineRun rows formatted for the queue panel."""
    from apps.pipeline.services.eta_estimator import estimate_eta
    from apps.suggestions.models import PipelineRun

    runs = list(
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
    for run in runs:
        run["run_id"] = str(run["run_id"])
        run["type"] = "pipeline"
        if run["created_at"]:
            run["created_at"] = run["created_at"].isoformat()
        if run["updated_at"]:
            run["updated_at"] = run["updated_at"].isoformat()
        eta = estimate_eta("pipeline.run_pipeline")
        run["estimated_remaining_seconds"] = eta.total_seconds() if eta else None
    return runs


def _job_queue_active_syncs() -> list[dict]:
    """Active + queued SyncJob rows formatted for the queue panel."""
    from apps.pipeline.services.eta_estimator import estimate_eta
    from apps.sync.models import SyncJob

    jobs = list(
        SyncJob.objects.filter(status__in=["pending", "running", "paused"])
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
    for job in jobs:
        job["job_id"] = str(job["job_id"])
        job["type"] = "sync"
        if job["created_at"]:
            job["created_at"] = job["created_at"].isoformat()
        if job["started_at"]:
            job["started_at"] = job["started_at"].isoformat()
        eta = estimate_eta("nightly-xenforo-sync", mode=job.get("mode"))
        job["estimated_remaining_seconds"] = eta.total_seconds() if eta else None
    return jobs


class JobQueueView(APIView):
    """GET /api/jobs/queue/ — active and queued tasks with ETA and lock status."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        """Active + queued tasks across pipeline + sync, plus active locks.

        Refactored 2026-05-04: was 67 lines. Each source list is now its
        own helper that returns dicts already in the canonical response
        shape. The ``items`` array preserves the original "pipeline runs
        first, then sync jobs" ordering.
        """
        from apps.pipeline.services.task_lock import get_active_locks

        return Response(
            {
                "items": (_job_queue_active_runs() + _job_queue_active_syncs()),
                "locks": get_active_locks(),
            }
        )


# ── JobQuarantineView helpers (extracted from .get) ──────────────


def _quarantine_records_and_run_ids() -> tuple[list[dict], set[str]]:
    """New-style: open ``QuarantineRecord`` rows.

    Returns ``(records, quarantined_run_ids)`` so the legacy fold-in
    helper can dedup against rows already covered by a record.
    """
    from apps.core.models import QuarantineRecord

    open_records = QuarantineRecord.objects.filter(resolved_at__isnull=True).order_by(
        "-updated_at"
    )[:50]
    records: list[dict] = []
    quarantined_run_ids: set[str] = set()
    for rec in open_records:
        records.append(
            {
                "id": rec.pk,
                "kind": "record",
                "run_id": rec.related_object_id,
                "related_object_type": rec.related_object_type,
                "reason": rec.reason,
                "reason_display": rec.get_reason_display(),
                "reason_detail": rec.reason_detail,
                "affected_items": rec.affected_items,
                "fix_available": rec.fix_available,
                "resume_from_checkpoint": rec.resume_from_checkpoint,
                "checkpoint_id": rec.checkpoint_id,
                "created_at": rec.created_at.isoformat(),
                "updated_at": rec.updated_at.isoformat(),
            }
        )
        if rec.related_object_type == "pipeline_run":
            quarantined_run_ids.add(rec.related_object_id)
    return records, quarantined_run_ids


def _quarantine_legacy_rows(*, skip_run_ids: set[str]) -> list[dict]:
    """Legacy: ``PipelineRun.is_quarantined=True`` rows without a matching record.

    The ``skip_run_ids`` set lets the caller exclude legacy rows that
    are already represented in the new ``QuarantineRecord`` table —
    preserves the dedup contract from the original 76-line handler.
    """
    from apps.suggestions.models import PipelineRun

    legacy_runs = list(
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
    rows: list[dict] = []
    for run in legacy_runs:
        rid = str(run["run_id"])
        if rid in skip_run_ids:
            continue
        rows.append(_legacy_quarantine_row(run, rid))
    return rows


def _legacy_quarantine_row(run: dict, rid: str) -> dict:
    """Build one legacy-quarantine dict in the canonical response shape."""
    return {
        "id": None,
        "kind": "legacy",
        "run_id": rid,
        "related_object_type": "pipeline_run",
        "reason": "repeated_failure",
        "reason_display": "Repeated failures",
        "reason_detail": run.get("error_message") or "",
        "affected_items": [],
        "fix_available": "reset-quarantined-job",
        "resume_from_checkpoint": False,
        "checkpoint_id": "",
        "run_state": run["run_state"],
        "rerun_mode": run["rerun_mode"],
        "phase_log": run["phase_log"],
        "created_at": run["created_at"].isoformat() if run["created_at"] else None,
        "updated_at": run["updated_at"].isoformat() if run["updated_at"] else None,
    }


class JobQuarantineView(APIView):
    """GET /api/jobs/quarantine/ — quarantined items (first-class model, plan item 16).

    Prefers the new `QuarantineRecord` table; for back-compat also folds in any
    `PipelineRun.is_quarantined=True` rows that don't have a matching
    QuarantineRecord yet.  Frontend reads from the same endpoint; no breaking
    change.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        """Combined open-quarantine list — new QuarantineRecord rows + legacy.

        Refactored 2026-05-04: was 76 lines. Each source (new + legacy)
        is now its own helper so the merge logic is testable in
        isolation. The dedup-by-run_id rule is preserved exactly.
        """
        records, quarantined_run_ids = _quarantine_records_and_run_ids()
        legacy = _quarantine_legacy_rows(skip_run_ids=quarantined_run_ids)
        return Response(records + legacy)


class HelperNodeListView(APIView):
    """GET/POST /api/settings/helpers/ — list and register helper nodes."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        from apps.core.models import HelperNode
        from apps.core.views_runtime_registry import serialize_helper_node

        nodes = HelperNode.objects.all()
        data = [serialize_helper_node(n) for n in nodes]
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
                "accepting_work": bool(request.data.get("accepting_work", True)),
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
        import hashlib

        from apps.core.models import HelperNode
        from apps.core.views_runtime_registry import serialize_helper_node

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
            "accepting_work",
            "active_jobs",
            "queued_jobs",
            "cpu_pct",
            "ram_pct",
            "gpu_util_pct",
            "gpu_vram_used_mb",
            "gpu_vram_total_mb",
            "network_rtt_ms",
            "native_kernels_healthy",
        ):
            if field in request.data:
                setattr(node, field, request.data[field])
        for json_field in (
            "capabilities",
            "allowed_queues",
            "allowed_job_types",
            "warmed_model_keys",
        ):
            if json_field in request.data:
                setattr(node, json_field, request.data[json_field])
        token = request.data.get("token")
        if token:
            node.token_hash = hashlib.sha256(str(token).encode()).hexdigest()
        node.save()
        return Response(serialize_helper_node(node))

    def delete(self, request, pk):
        from apps.core.models import HelperNode

        deleted, _ = HelperNode.objects.filter(pk=pk).delete()
        if not deleted:
            return Response({"error": "Not found"}, status=404)
        return Response(status=204)


# ── Heartbeat helpers (extracted from HelperNodeHeartbeatView.post) ──
# Each helper mutates the in-memory HelperNode, leaving persistence to
# the caller. Splitting per field group keeps the main handler small +
# makes each defensive coercion independently testable.

# Save fields list — single source of truth so adding a new field
# updates the helper AND the caller's update_fields=[...] list together.
_HEARTBEAT_UPDATE_FIELDS = (
    "last_heartbeat",
    "last_snapshot_at",
    "status",
    "capabilities",
    "accepting_work",
    "active_jobs",
    "queued_jobs",
    "cpu_pct",
    "ram_pct",
    "gpu_util_pct",
    "gpu_vram_used_mb",
    "gpu_vram_total_mb",
    "network_rtt_ms",
    "native_kernels_healthy",
    "warmed_model_keys",
    "updated_at",
)


def _apply_heartbeat_identity(node, data: dict) -> None:
    """Apply non-numeric identity fields: status enum + capabilities + accepting_work.

    Defensive type checks: status restricted to documented enum,
    accepting_work routed through ``coerce_bool`` so non-bool truthy
    inputs ("yes", 1) parse correctly without silently flipping
    operators trying to disable a feature via curl.
    """
    from apps.core.models import HelperNode

    if "status" in data:
        raw_status = data["status"]
        if (
            isinstance(raw_status, str)
            and raw_status in HelperNode.VALID_HEARTBEAT_STATUSES
        ):
            node.status = raw_status
    if "capabilities" in data and isinstance(data["capabilities"], dict):
        merged = dict(node.capabilities or {})
        merged.update(data["capabilities"])
        node.capabilities = merged
    if "accepting_work" in data:
        raw_accepting = data["accepting_work"]
        if isinstance(raw_accepting, (bool, int, float, str)):
            node.accepting_work = coerce_bool(
                raw_accepting, default=node.accepting_work
            )


def _apply_heartbeat_load_metrics(node, data: dict) -> None:
    """Apply CPU + queue-depth metrics with defensive int / float clamps."""
    if "active_jobs" in data:
        node.active_jobs = coerce_int(
            data["active_jobs"], default=node.active_jobs, min_value=0
        )
    if "queued_jobs" in data:
        node.queued_jobs = coerce_int(
            data["queued_jobs"], default=node.queued_jobs, min_value=0
        )
    if "cpu_pct" in data:
        node.cpu_pct = coerce_float(
            data["cpu_pct"],
            default=node.cpu_pct or 0.0,
            min_value=0.0,
            max_value=100.0,
        )
    if "ram_pct" in data:
        node.ram_pct = coerce_float(
            data["ram_pct"],
            default=node.ram_pct or 0.0,
            min_value=0.0,
            max_value=100.0,
        )


def _apply_heartbeat_gpu_metrics(node, data: dict) -> None:
    """Apply GPU utilisation + VRAM metrics. Empty / null clears the field."""
    if "gpu_util_pct" in data:
        gpu_util = data["gpu_util_pct"]
        node.gpu_util_pct = (
            None
            if gpu_util in ("", None)
            else coerce_float(
                gpu_util,
                default=node.gpu_util_pct or 0.0,
                min_value=0.0,
                max_value=100.0,
            )
        )
    if "gpu_vram_used_mb" in data:
        gpu_vram_used = data["gpu_vram_used_mb"]
        node.gpu_vram_used_mb = (
            None
            if gpu_vram_used in ("", None)
            else coerce_int(
                gpu_vram_used, default=node.gpu_vram_used_mb or 0, min_value=0
            )
        )
    if "gpu_vram_total_mb" in data:
        gpu_vram_total = data["gpu_vram_total_mb"]
        node.gpu_vram_total_mb = (
            None
            if gpu_vram_total in ("", None)
            else coerce_int(
                gpu_vram_total, default=node.gpu_vram_total_mb or 0, min_value=0
            )
        )


def _apply_heartbeat_network_health(node, data: dict) -> None:
    """Apply network RTT + kernel health + warmed-model-keys list."""
    if "network_rtt_ms" in data:
        rtt = data["network_rtt_ms"]
        node.network_rtt_ms = (
            None
            if rtt in ("", None)
            else coerce_int(rtt, default=node.network_rtt_ms or 0, min_value=0)
        )
    if "native_kernels_healthy" in data:
        node.native_kernels_healthy = bool(data["native_kernels_healthy"])
    if "warmed_model_keys" in data and isinstance(data["warmed_model_keys"], list):
        node.warmed_model_keys = data["warmed_model_keys"]


class HelperNodeHeartbeatView(APIView):
    """POST /api/settings/helpers/<id>/heartbeat/

    Stub endpoint for helper nodes to report liveness. Updates
    ``last_heartbeat`` and optionally merges ``capabilities`` and updates
    ``status``. Returns 204 on success.

    The helper-client side that calls this endpoint is forward-looking
    (Stage 8 / multi-node). The endpoint exists so docs/PERFORMANCE.md §2
    is not lying about it and so the next session that wires up the helper
    client has a real route to POST to.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        """Accept one helper-PC heartbeat payload + persist any updated fields.

        Refactored 2026-05-04: was 138 lines. Each field group is now a
        per-domain helper (``_apply_heartbeat_*``) so the handler stays
        small, the per-field defensive logic is reusable, and each helper
        can be unit-tested without spinning up the full request lifecycle.
        Behaviour preserved exactly — every defensive type check + range
        clamp survives unchanged.
        """
        from django.utils import timezone

        from apps.core.models import HelperNode

        try:
            node = HelperNode.objects.get(pk=pk)
        except HelperNode.DoesNotExist:
            return Response({"error": "Not found"}, status=404)

        node.last_heartbeat = timezone.now()
        node.last_snapshot_at = timezone.now()
        _apply_heartbeat_identity(node, request.data)
        _apply_heartbeat_load_metrics(node, request.data)
        _apply_heartbeat_gpu_metrics(node, request.data)
        _apply_heartbeat_network_health(node, request.data)
        node.save(update_fields=_HEARTBEAT_UPDATE_FIELDS)
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

        for key, row in _build_graph_candidate_rows(validated).items():
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


# (validated_key, setting_key, value_type, description) for graph-candidate rows.
_GRAPH_CANDIDATE_ROW_SPEC: tuple[tuple[str, str, str, str], ...] = (
    (
        "enabled",
        "graph_candidate.enabled",
        "bool",
        "Whether FR-021 Pixie walk candidate generation is active.",
    ),
    (
        "walk_steps_per_entity",
        "graph_candidate.walk_steps_per_entity",
        "int",
        "Number of Pixie random walk steps to perform per query entity.",
    ),
    (
        "min_stable_candidates",
        "graph_candidate.min_stable_candidates",
        "int",
        "Minimum number of stable candidates to find before early stopping.",
    ),
    (
        "min_visit_threshold",
        "graph_candidate.min_visit_threshold",
        "int",
        "Minimum walk visits required for a node to be considered stable.",
    ),
    (
        "top_k_candidates",
        "graph_candidate.top_k_candidates",
        "int",
        "Max number of top-visited candidates to return to the pipeline.",
    ),
    (
        "top_n_entities_per_article",
        "graph_candidate.top_n_entities_per_article",
        "int",
        "Max number of top entities to extract per article for graph linking.",
    ),
)


def _build_graph_candidate_rows(validated: dict) -> dict[str, dict]:
    """Pure function — turn a validated graph-candidate dict into AppSetting rows."""
    return {
        setting_key: {
            "value": _format_setting_value(validated[validated_key], value_type),
            "value_type": value_type,
            "description": description,
        }
        for validated_key, setting_key, value_type, description in _GRAPH_CANDIDATE_ROW_SPEC
    }


class ValueModelSettingsView(APIView):
    """
    GET  /api/settings/value-model/ - returns FR-021 value model settings
    PUT  /api/settings/value-model/ - validates and persists those settings
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(get_value_model_settings())

    def put(self, request):
        """Persist a validated value-model settings payload.

        Refactored 2026-05-04: was a 143-line monolith mostly composed
        of a giant ``rows`` dict literal. Extracted that into the pure
        helper ``_build_value_model_rows`` so the handler stays under
        the lint budget AND the row-shape is independently testable.
        """
        from apps.core.models import AppSetting

        current = get_value_model_settings()
        try:
            validated = _validate_value_model_settings(request.data, current)
        except ValueError as exc:
            return Response({"error": str(exc)}, status=400)

        for key, row in _build_value_model_rows(validated).items():
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


def _vm_bool_str(v: object) -> str:
    """Bool → "true"/"false" — single source for value-model rows."""
    return "true" if v else "false"


def _build_value_model_rows(validated: dict) -> dict[str, dict[str, str]]:
    """Pure function — turn a validated value-model dict into AppSetting rows.

    Each entry maps an AppSetting key to ``{value, value_type, description}``.
    The body is split into per-feature-area helpers so the table data
    stays scannable while no single function exceeds the 50-line lint
    budget. Tests pin every serialisation rule + the "every input key
    produces a row" invariant.
    """
    return {
        **_vm_rows_core(validated),
        **_vm_rows_engagement(validated),
        **_vm_rows_hot_decay(validated),
        **_vm_rows_co_occurrence(validated),
    }


def _vm_rows_core(validated: dict) -> dict[str, dict[str, str]]:
    """FR-021 base value-model: enabled flag + 5 component weights + traffic."""
    return {
        "value_model.enabled": {
            "value": _vm_bool_str(validated["enabled"]),
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
    }


def _vm_rows_engagement(validated: dict) -> dict[str, dict[str, str]]:
    """FR-024 engagement / read-through rate signal."""
    return {
        "value_model.engagement_signal_enabled": {
            "value": _vm_bool_str(validated["engagement_signal_enabled"]),
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
    }


def _vm_rows_hot_decay(validated: dict) -> dict[str, dict[str, str]]:
    """FR-023 Reddit-style hot-decay signal."""
    return {
        "value_model.hot_decay_enabled": {
            "value": _vm_bool_str(validated["hot_decay_enabled"]),
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
    }


def _vm_rows_co_occurrence(validated: dict) -> dict[str, dict[str, str]]:
    """FR-025 session co-occurrence signal."""
    return {
        "value_model.co_occurrence_signal_enabled": {
            "value": _vm_bool_str(validated["co_occurrence_signal_enabled"]),
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


DEFAULT_SPAM_GUARD_SETTINGS: dict[str, int] = {
    "max_existing_links_per_host": 2,
    "max_anchor_words": 4,
    "paragraph_window": 3,
}


_SPAM_GUARD_KEYS = (
    "max_existing_links_per_host",
    "max_anchor_words",
    "paragraph_window",
)


def get_spam_guard_settings() -> dict[str, int]:
    """Return current spam-guard limits, falling back to patent-backed defaults."""
    return {
        key: read_app_setting_int(
            f"spam_guards.{key}",
            DEFAULT_SPAM_GUARD_SETTINGS[key],
        )
        for key in _SPAM_GUARD_KEYS
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
        for key, row in _build_spam_guard_rows(validated).items():
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


# Spam-guard row spec. Descriptions cite the specific patent / source so the
# operator-visible AppSetting row carries provenance.
_SPAM_GUARD_ROW_SPEC: tuple[tuple[str, str, str, str], ...] = (
    (
        "max_existing_links_per_host",
        "spam_guards.max_existing_links_per_host",
        "int",
        "Maximum number of existing outgoing body links a host page may "
        "already carry before the pipeline skips it. "
        "Default 3 — Ntoulas et al. anchor-word fraction research (US20060184500A1).",
    ),
    (
        "max_anchor_words",
        "spam_guards.max_anchor_words",
        "int",
        "Maximum number of words allowed in a suggested anchor phrase. "
        "Default 4 — Google recommends 2–5 words; US8380722B2 confirms "
        "anchors are 'usually short and descriptive'.",
    ),
    (
        "paragraph_window",
        "spam_guards.paragraph_window",
        "int",
        "Sentence-position window for paragraph-cluster detection. "
        "Two suggestions within this many sentences of each other on "
        "the same host are treated as the same paragraph — only the "
        "higher-scoring one is kept. Default 3 — US8577893B1.",
    ),
)


def _build_spam_guard_rows(validated: dict) -> dict[str, dict]:
    """Pure function — turn a validated spam-guard dict into AppSetting rows."""
    return {
        setting_key: {
            "value": _format_setting_value(validated[validated_key], value_type),
            "value_type": value_type,
            "description": description,
        }
        for validated_key, setting_key, value_type, description in _SPAM_GUARD_ROW_SPEC
    }


class GraphRebuildView(APIView):
    """POST /api/settings/graph/rebuild/ - manual trigger for bipartite graph refresh."""

    permission_classes = [IsAuthenticated]
    throttle_classes = [_GraphRebuildThrottle]

    def post(self, request):
        from apps.pipeline.tasks import dispatch_graph_rebuild

        job_id = str(uuid.uuid4())
        payload = dispatch_graph_rebuild(job_id=job_id)
        return Response(payload, status=202)


_GRAPH_CANDIDATE_INT_KEYS = (
    "walk_steps_per_entity",
    "min_stable_candidates",
    "min_visit_threshold",
    "top_k_candidates",
    "top_n_entities_per_article",
)


def _read_graph_candidate_settings() -> dict[str, float | int | bool]:
    out: dict[str, float | int | bool] = {
        "enabled": read_app_setting_bool(
            "graph_candidate.enabled",
            DEFAULT_GRAPH_CANDIDATE_SETTINGS["enabled"],
        ),
    }
    for key in _GRAPH_CANDIDATE_INT_KEYS:
        out[key] = read_app_setting_int(
            f"graph_candidate.{key}",
            DEFAULT_GRAPH_CANDIDATE_SETTINGS[key],
        )
    return out


_GRAPH_CANDIDATE_INT_BOUNDS: dict[str, tuple[int, int]] = {
    "walk_steps_per_entity": (10, 10000),
    "min_stable_candidates": (5, 500),
    "min_visit_threshold": (1, 20),
    "top_k_candidates": (10, 1000),
    "top_n_entities_per_article": (1, 100),
}


def _validate_graph_candidate_settings(payload: dict, current: dict) -> dict:
    out: dict = {"enabled": coerce_lenient_bool(payload, current, "enabled")}
    for key, (lo, hi) in _GRAPH_CANDIDATE_INT_BOUNDS.items():
        out[key] = coerce_clamp_int(payload, current, key, lo, hi)
    return out


def _vm_read_float(key: str, default: float) -> float:
    """Read one float-typed value-model AppSetting; fall back to default."""
    return coerce_float(_get_app_setting_value(key), default=default)


def _vm_read_int(key: str, default: int) -> int:
    """Read one int-typed value-model AppSetting; fall back to default."""
    return coerce_int(_get_app_setting_value(key), default=default)


def _vm_read_bool(key: str, default: bool) -> bool:
    """Read one bool-typed value-model AppSetting; fall back to default.

    Reuses the shared coerce_bool helper so a future tweak to the
    truthy-string rules propagates everywhere automatically.
    """
    raw = _get_app_setting_value(key)
    if raw is None:
        return default
    return coerce_bool(raw, default=default)


def _read_value_model_settings() -> dict[str, float | int | bool]:
    """Mirror of _build_value_model_rows: read every value-model setting.

    Refactored 2026-05-04: was 108 lines of inline reads. Now delegates
    each feature area to its own pure-function reader so the master
    function fits in a single screen + each feature area can be tested
    in isolation. Behaviour preserved exactly.
    """
    return {
        **_vm_settings_core(),
        **_vm_settings_engagement(),
        **_vm_settings_hot_decay(),
        **_vm_settings_co_occurrence(),
    }


def _vm_settings_core() -> dict[str, float | int | bool]:
    """FR-021 base value-model settings (enabled + 5 weights + traffic)."""
    d = DEFAULT_VALUE_MODEL_SETTINGS
    return {
        "enabled": _vm_read_bool("value_model.enabled", d["enabled"]),
        "w_relevance": _vm_read_float("value_model.w_relevance", d["w_relevance"]),
        "w_traffic": _vm_read_float("value_model.w_traffic", d["w_traffic"]),
        "w_freshness": _vm_read_float("value_model.w_freshness", d["w_freshness"]),
        "w_authority": _vm_read_float("value_model.w_authority", d["w_authority"]),
        "w_penalty": _vm_read_float("value_model.w_penalty", d["w_penalty"]),
        "traffic_lookback_days": _vm_read_int(
            "value_model.traffic_lookback_days", d["traffic_lookback_days"]
        ),
        "traffic_fallback_value": _vm_read_float(
            "value_model.traffic_fallback_value", d["traffic_fallback_value"]
        ),
    }


def _vm_settings_engagement() -> dict[str, float | int | bool]:
    """FR-024 read-through-rate engagement signal settings."""
    d = DEFAULT_VALUE_MODEL_SETTINGS
    return {
        "engagement_signal_enabled": _vm_read_bool(
            "value_model.engagement_signal_enabled",
            d["engagement_signal_enabled"],
        ),
        "w_engagement": _vm_read_float("value_model.w_engagement", d["w_engagement"]),
        "engagement_lookback_days": _vm_read_int(
            "value_model.engagement_lookback_days", d["engagement_lookback_days"]
        ),
        "engagement_words_per_minute": _vm_read_int(
            "value_model.engagement_words_per_minute",
            d["engagement_words_per_minute"],
        ),
        "engagement_cap_ratio": _vm_read_float(
            "value_model.engagement_cap_ratio", d["engagement_cap_ratio"]
        ),
        "engagement_fallback_value": _vm_read_float(
            "value_model.engagement_fallback_value",
            d["engagement_fallback_value"],
        ),
    }


def _vm_settings_hot_decay() -> dict[str, float | int | bool]:
    """FR-023 Reddit-style hot-decay signal settings."""
    d = DEFAULT_VALUE_MODEL_SETTINGS
    return {
        "hot_decay_enabled": _vm_read_bool(
            "value_model.hot_decay_enabled", d["hot_decay_enabled"]
        ),
        "hot_gravity": _vm_read_float("value_model.hot_gravity", d["hot_gravity"]),
        "hot_clicks_weight": _vm_read_float(
            "value_model.hot_clicks_weight", d["hot_clicks_weight"]
        ),
        "hot_impressions_weight": _vm_read_float(
            "value_model.hot_impressions_weight", d["hot_impressions_weight"]
        ),
        "hot_lookback_days": _vm_read_int(
            "value_model.hot_lookback_days", d["hot_lookback_days"]
        ),
    }


def _vm_settings_co_occurrence() -> dict[str, float | int | bool]:
    """FR-025 session co-occurrence signal settings."""
    d = DEFAULT_VALUE_MODEL_SETTINGS
    return {
        "co_occurrence_signal_enabled": _vm_read_bool(
            "value_model.co_occurrence_signal_enabled",
            d["co_occurrence_signal_enabled"],
        ),
        "w_cooccurrence": _vm_read_float(
            "value_model.w_cooccurrence", d["w_cooccurrence"]
        ),
        "co_occurrence_fallback_value": _vm_read_float(
            "value_model.co_occurrence_fallback_value",
            d["co_occurrence_fallback_value"],
        ),
        "co_occurrence_min_co_sessions": _vm_read_int(
            "value_model.co_occurrence_min_co_sessions",
            d["co_occurrence_min_co_sessions"],
        ),
    }


# Per-key (lo, hi) for the value-model settings.
# Spec is "clamp don't reject" so out-of-range values silently become the
# nearest endpoint via coerce_clamp_*. Adding a new value-model knob =
# add the key here + one line in the helper below.
_VALUE_MODEL_FLOAT_BOUNDS: dict[str, tuple[float, float]] = {
    "w_relevance": (0.0, 1.0),
    "w_traffic": (0.0, 1.0),
    "w_freshness": (0.0, 1.0),
    "w_authority": (0.0, 1.0),
    "w_penalty": (0.0, 1.0),
    "traffic_fallback_value": (0.0, 1.0),
    "w_engagement": (0.0, 1.0),
    "engagement_cap_ratio": (1.0, 5.0),
    "engagement_fallback_value": (0.0, 1.0),
    "hot_gravity": (0.001, 0.5),  # FR-023
    "hot_clicks_weight": (0.0, 5.0),  # FR-023
    "hot_impressions_weight": (0.0, 5.0),  # FR-023
    "w_cooccurrence": (0.0, 1.0),  # FR-025
    "co_occurrence_fallback_value": (0.0, 1.0),  # FR-025
}
_VALUE_MODEL_INT_BOUNDS: dict[str, tuple[int, int]] = {
    "traffic_lookback_days": (1, 365),
    "engagement_lookback_days": (1, 365),
    "engagement_words_per_minute": (50, 600),
    "hot_lookback_days": (7, 365),  # FR-023
    "co_occurrence_min_co_sessions": (1, 100),  # FR-025
}
_VALUE_MODEL_BOOL_KEYS: tuple[str, ...] = (
    "enabled",
    "engagement_signal_enabled",
    "hot_decay_enabled",  # FR-023
    "co_occurrence_signal_enabled",  # FR-025
)


def _validate_value_model_settings(payload: dict, current: dict) -> dict:
    """Validate value-model settings with the lenient "clamp don't reject" contract.

    Bad operator input is silently clamped to the nearest valid value instead
    of raising — matches spec FR-013 / FR-023 / FR-025 expectations.
    """
    validated: dict = {
        key: coerce_lenient_bool(payload, current, key)
        for key in _VALUE_MODEL_BOOL_KEYS
    }
    for key, (lo, hi) in _VALUE_MODEL_FLOAT_BOUNDS.items():
        validated[key] = coerce_clamp_float(payload, current, key, lo, hi)
    for key, (lo_i, hi_i) in _VALUE_MODEL_INT_BOUNDS.items():
        validated[key] = coerce_clamp_int(payload, current, key, lo_i, hi_i)
    return validated


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


class LocalVerificationBootstrapView(APIView):
    """Mint a localhost-only auth token for browser verification.

    Three independent gates must all pass before a token is issued:
    1. LOCAL_VERIFICATION_BOOTSTRAP_ENABLED must be True (opt-in, default False).
    2. The request must carry the X-XFIL-Verification: playwright header.
    3. The TCP peer IP (REMOTE_ADDR) must be the loopback address — this
       cannot be spoofed via HTTP headers the way the Host header can.

    The endpoint ONLY ever creates or repairs the 'playwright-local' throwaway
    account. It never touches any other user's credentials or returns any other
    user's token, regardless of what accounts exist in the database.
    """

    authentication_classes = []
    permission_classes = []
    VERIFICATION_HEADER = "HTTP_X_XFIL_VERIFICATION"
    _PLAYWRIGHT_USERNAME = "playwright-local"
    _PLAYWRIGHT_EMAIL = "playwright-local@example.invalid"

    def post(self, request):
        if not self._request_is_authorised(request):
            return Response({"detail": "Not found."}, status=404)

        from rest_framework.authtoken.models import Token

        user = self._get_or_repair_playwright_user()
        token, _ = Token.objects.get_or_create(user=user)
        return Response({"token": token.key, "username": user.username})

    def _request_is_authorised(self, request) -> bool:
        """Three-gate guard: feature flag, secret header, and loopback peer IP."""
        if not getattr(django_settings, "LOCAL_VERIFICATION_BOOTSTRAP_ENABLED", False):
            return False
        if request.META.get(self.VERIFICATION_HEADER) != "playwright":
            return False
        # Use the TCP peer IP, not the Host header (which is attacker-controlled).
        peer_ip = request.META.get("REMOTE_ADDR", "")
        return peer_ip in {"127.0.0.1", "::1"}

    def _get_or_repair_playwright_user(self):
        """Get-or-create + heal the playwright-local account.

        Repairs stale playwright-local accounts unconditionally (not only on
        first creation) so a previously-downgraded account is always healed.
        Touches the playwright-local account and only the playwright-local
        account — protected by ABSOLUTE rule "Never change user passwords".
        """
        from django.contrib.auth import get_user_model

        user_model = get_user_model()
        user, _ = user_model.objects.get_or_create(
            username=self._PLAYWRIGHT_USERNAME,
            defaults={
                "email": self._PLAYWRIGHT_EMAIL,
                "is_staff": True,
                "is_superuser": True,
            },
        )
        fields_to_update: list[str] = []
        if not user.is_staff:
            user.is_staff = True
            fields_to_update.append("is_staff")
        if not user.is_superuser:
            user.is_superuser = True
            fields_to_update.append("is_superuser")
        if user.email != self._PLAYWRIGHT_EMAIL:
            user.email = self._PLAYWRIGHT_EMAIL
            fields_to_update.append("email")
        if user.has_usable_password():
            # Playwright uses token auth; a usable password is a liability.
            user.set_unusable_password()
            fields_to_update.append("password")
        if fields_to_update:
            user.save(update_fields=fields_to_update)
        return user


def _client_is_local_setup_request(request) -> bool:
    """Return True only for localhost or the local Docker proxy path."""
    peer_ip = request.META.get("REMOTE_ADDR", "")
    forwarded_for = (
        (request.META.get("HTTP_X_FORWARDED_FOR") or "").split(",")[0].strip()
    )
    if peer_ip in {"127.0.0.1", "::1"}:
        return True
    return peer_ip.startswith("172.") and forwarded_for in {"127.0.0.1", "::1"}


class FirstOperatorSetupView(APIView):
    """Create the first local operator account when the user table is empty."""

    authentication_classes = []
    permission_classes = []

    def get(self, request):
        from django.contrib.auth import get_user_model

        available = (
            _client_is_local_setup_request(request)
            and not get_user_model().objects.exists()
        )
        return Response({"available": available, "username": "admin"})

    def post(self, request):
        from django.contrib.auth import get_user_model
        from django.contrib.auth.password_validation import validate_password
        from django.core.exceptions import ValidationError
        from rest_framework.authtoken.models import Token

        if not _client_is_local_setup_request(request):
            return Response({"detail": "Not found."}, status=404)

        user_model = get_user_model()
        if user_model.objects.exists():
            return Response(
                {"detail": "First operator setup is already closed."},
                status=404,
            )

        username = str(request.data.get("username") or "").strip()
        password = str(request.data.get("password") or "")
        email = str(request.data.get("email") or "admin@example.com").strip()
        if username != "admin":
            return Response(
                {"detail": "The first operator username must be admin."},
                status=400,
            )
        if not password:
            return Response({"detail": "Password is required."}, status=400)
        try:
            validate_password(password)
        except ValidationError as exc:
            return Response({"detail": " ".join(exc.messages)}, status=400)

        user = user_model.objects.create_superuser(
            username=username,
            email=email,
            password=password,
        )
        token, _ = Token.objects.get_or_create(user=user)
        return Response({"token": token.key, "username": user.username})


class ActiveUsersView(APIView):
    """GET /api/auth/active-users/ — who has made an authenticated request recently.

    Read by the dashboard's "whos on shift" widget. A user is considered
    active if their last_seen_at is within ``ACTIVE_WINDOW_MIN`` minutes.
    The caller is never omitted from the list — the frontend decides
    whether to hide the widget when the only active user is "me".
    """

    permission_classes = [IsAuthenticated]

    ACTIVE_WINDOW_MIN = 5

    def get(self, request):
        from datetime import timedelta

        from django.utils import timezone

        from .models import UserActivity

        cutoff = timezone.now() - timedelta(minutes=self.ACTIVE_WINDOW_MIN)
        rows = (
            UserActivity.objects.filter(last_seen_at__gte=cutoff)
            .select_related("user")
            .order_by("-last_seen_at")
        )
        payload = [
            {
                "username": r.user.username,
                "last_seen": r.last_seen_at.isoformat(),
                "route": r.last_route,
            }
            for r in rows
        ]
        return Response(payload)


# ── Phase 4.9 — Helper PC roster endpoint ─────────────────────────


class BudgetForecastView(APIView):
    """GET /api/system/budget-forecast/?task=<task_name>&kwarg1=value...

    Phase 4.2 — Budget & Space Forecasts pre-flight estimator.

    Returns an operator-facing forecast: estimated bytes, projected
    free-disk after the job, traffic-light verdict (safe / yellow / red),
    plain-English why, and the calibration history used.

    Query params:
        ?task=<task_name>      — required; must be a registered estimator
                                 (see GET /api/system/budget-forecast/tasks/
                                 for the full list)
        ?safety_margin_pct=N   — optional; overrides the 20% default
        ?<kwarg>=<value>       — every other query param is passed to the
                                 estimator function as a string-typed kwarg
                                 (the estimator coerces with int())
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        from dataclasses import asdict

        from apps.core.services.budget_forecaster import (
            forecast,
            get_registered_tasks,
        )

        task_name = request.query_params.get("task", "")
        if not task_name:
            return Response(
                {
                    "detail": "?task=<task_name> is required",
                    "available_tasks": get_registered_tasks(),
                },
                status=400,
            )

        kwargs: dict = {}
        for k, v in request.query_params.items():
            if k in {"task", "safety_margin_pct"}:
                continue
            kwargs[k] = v

        # Refactor 2026-05-04: shared coerce_int helper. Bad
        # `?safety_margin_pct=foo` falls back to None (= use the
        # forecaster's default 20% headroom) instead of being silently
        # dropped or crashing.
        margin = (
            coerce_int(
                request.query_params.get("safety_margin_pct"),
                default=-1,
                min_value=0,
                max_value=200,
            )
            if request.query_params.get("safety_margin_pct")
            else None
        )
        if margin is not None and margin < 0:
            margin = None

        result = forecast(
            task_name=task_name,
            kwargs=kwargs,
            safety_margin_pct=margin,
        )
        return Response(asdict(result))


class CachePolicySummaryView(APIView):
    """GET /api/system/cache-policy/

    Phase 4.13 — operator-facing cache stats. Returns one summary per
    cache layer with hit/miss/evict counts, hit ratio, estimated size,
    max-size budget, pin-count, and the list of pinned keys.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        from dataclasses import asdict

        from apps.core.services.cache_policy import summarise_all_layers

        return Response(
            {
                "layers": [asdict(s) for s in summarise_all_layers()],
            }
        )


class CompressionAuditView(APIView):
    """GET /api/system/compression-audit/

    Phase 4.9 — read-only view of the latest compression audit report.

    Returns the top-N tables where compression would save meaningful
    disk, plus the timestamp of the last audit run. The audit itself
    is a Celery beat task (``core.compression_audit``) that runs
    weekly; this endpoint is the operator-facing read.

    Response shape::

        {
            "run_at_iso": "2026-05-04T03:00:11+00:00",  // empty if never run
            "sample_size": 1000,
            "candidates": [...],
            "total_estimated_savings_bytes": 524288000,
            "total_estimated_savings_mb": 500,
            "note": "Audited 10 candidate tables; 7 have ≥1 MB projected savings."
        }
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        from dataclasses import asdict

        from apps.core.services.compression_audit import get_last_compression_audit

        report = get_last_compression_audit()
        if report is None:
            return Response(
                {
                    "run_at_iso": "",
                    "sample_size": 0,
                    "candidates": [],
                    "total_estimated_savings_bytes": 0,
                    "total_estimated_savings_mb": 0,
                    "note": (
                        "No compression audit has run yet. The first audit "
                        "fires Sundays at 03:00 UTC; trigger immediately via "
                        "POST /api/system/compression-audit/run/."
                    ),
                }
            )
        payload = asdict(report)
        # Convert tuples → lists for JSON serialisation
        for c in payload["candidates"]:
            c["columns"] = list(c["columns"])
        payload["total_estimated_savings_mb"] = int(
            report.total_estimated_savings_bytes // (1024 * 1024)
        )
        return Response(payload)


class CompressionAuditRunView(APIView):
    """POST /api/system/compression-audit/run/

    Phase 4.9 — operator-triggered immediate audit. Useful when the
    operator just freed disk + wants to confirm the candidate list
    instead of waiting until Sunday's beat tick.

    Returns the freshly-computed report. Synchronous — typically takes
    30-120 seconds depending on corpus size. Restricted to staff users
    + rate-limited at 3/hour per user (``CompressionAuditRunThrottle``)
    so an accidentally-mashed button (or compromised non-admin token)
    can't pin the request-worker pool.
    """

    permission_classes = [IsAdminUser]
    throttle_classes = [CompressionAuditRunThrottle]

    def post(self, request):
        from dataclasses import asdict

        from apps.core.services.compression_audit import run_compression_audit

        report = run_compression_audit()
        payload = asdict(report)
        for c in payload["candidates"]:
            c["columns"] = list(c["columns"])
        payload["total_estimated_savings_mb"] = int(
            report.total_estimated_savings_bytes // (1024 * 1024)
        )
        return Response(payload)


class PerformanceCertView(APIView):
    """GET /api/system/performance-cert/

    Phase 4.11 — read-only "Ready to Ship?" badge. Returns the
    persisted pass/fail verdict computed by the Celery beat (daily) or
    by an operator-triggered run-now (POST run/ below).

    Response shape::

        {
            "run_at_iso": "2026-05-04T04:00:11+00:00",
            "verdict": "pass" | "warn" | "fail" | "unknown",
            "label": "Ready to ship — every benchmark meets baseline.",
            "benchmark_run_id": 42,
            "benchmark_run_started_at_iso": "2026-05-03T04:00:00+00:00",
            "areas": [
                {"area": "cpp", "fast_count": 8, "ok_count": 4,
                 "slow_count": 0, "total": 12, "verdict": "pass",
                 "note": "All 12 cpp benchmarks meet baseline."},
                ...
            ],
            "note": "All systems go..."
        }
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        from dataclasses import asdict

        from apps.core.services.performance_certification import (
            get_last_certification,
        )

        verdict = get_last_certification()
        if verdict is None:
            return Response(
                {
                    "run_at_iso": "",
                    "verdict": "unknown",
                    "label": (
                        "No performance certification has run yet. The first "
                        "cert fires daily at 04:00 UTC; trigger immediately "
                        "via POST /api/system/performance-cert/run/."
                    ),
                    "benchmark_run_id": None,
                    "benchmark_run_started_at_iso": "",
                    "areas": [],
                    "note": "",
                }
            )
        return Response(asdict(verdict))


class PerformanceCertRunView(APIView):
    """POST /api/system/performance-cert/run/

    Phase 4.11 — operator-triggered immediate cert recompute. Cheap
    (~1-2 s) — aggregates the latest BenchmarkRun without re-running
    benchmarks. Restricted to staff users + 6/hour throttle so an
    accidentally-mashed button can't pile up audit-event noise.

    To trigger a FRESH benchmark run (5-15 minutes) use
    ``POST /api/benchmarks/trigger/``; this endpoint only re-aggregates
    the latest existing run.
    """

    permission_classes = [IsAdminUser]
    throttle_classes = [PerformanceCertRunThrottle]

    def post(self, request):
        from dataclasses import asdict

        from apps.core.services.performance_certification import (
            run_performance_certification,
        )

        verdict = run_performance_certification()
        return Response(asdict(verdict))


class CppFallbackStatusView(APIView):
    """GET /api/system/cpp-fallback/

    Phase 4.14 — C++ Fallback Warning summary. Returns the live
    runtime-path status of every C++ extension plus a one-line banner
    message the dashboard can render at the top of the page when ANY
    extension is on the Python fallback.

    Response shape::

        {
            "total_extensions": 17,
            "on_cpp": 16,
            "on_python_fallback": 1,
            "banner": "Performance warning: …",  // empty when all loaded
            "fallbacks": [
                {
                    "module": "ivf_index",
                    "label": "IVF index search",
                    "critical": true,
                    "fallback_reason": "ABI mismatch: …",
                    "since_iso": "2026-05-04T17:32:11+00:00",
                    "duration_seconds": 7321
                }
            ]
        }
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        from dataclasses import asdict

        from apps.core.services.cpp_fallback_warning import (
            format_dashboard_banner,
            get_current_fallback_status,
        )

        snap = get_current_fallback_status()
        payload = asdict(snap)
        payload["banner"] = format_dashboard_banner()
        return Response(payload)


class CachePolicyPinView(APIView):
    """POST /api/system/cache-policy/<layer>/pin/   {"key": "<cache_key>"}
    DELETE /api/system/cache-policy/<layer>/pin/   {"key": "<cache_key>"}

    Phase 4.13 — pin / unpin a cache key so the eviction policy keeps
    or releases it. Pin-set lives in AppSetting (one row per pin).
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, layer: str):
        from apps.core.services.cache_policy import pin_key

        key = (request.data.get("key") or "").strip()
        if not key:
            return Response({"detail": "Body must include 'key'."}, status=400)
        pin_key(layer, key)
        return Response({"layer": layer, "key": key, "pinned": True})

    def delete(self, request, layer: str):
        from apps.core.services.cache_policy import unpin_key

        key = (request.data.get("key") or "").strip()
        if not key:
            return Response({"detail": "Body must include 'key'."}, status=400)
        unpin_key(layer, key)
        return Response({"layer": layer, "key": key, "pinned": False})


class CachePolicyEvictView(APIView):
    """POST /api/system/cache-policy/<layer>/evict/   {"key": "<key>"} (optional)

    Phase 4.13 — operator-triggered cache purge. With ``key`` set the
    single entry is removed; without ``key`` the whole layer is
    purged (pinned keys are skipped). Returns the lists of
    ``removed_keys`` and ``skipped_pinned`` for the UI snackbar.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, layer: str):
        from apps.core.services.cache_policy import evict_on_demand

        key = (request.data.get("key") or "").strip() or None
        result = evict_on_demand(layer, key=key)
        return Response({"layer": layer, **result})


class BudgetForecastTasksView(APIView):
    """GET /api/system/budget-forecast/tasks/

    Lists the task_names the budget forecaster knows about. Used by the
    pre-flight chip's task picker.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        from apps.core.services.budget_forecaster import get_registered_tasks

        return Response({"tasks": get_registered_tasks()})


class HelpersRosterView(APIView):
    """GET /api/helpers/

    Returns the right-now state of every connected helper PC, shaped
    for the frontend roster card + Confidence Meter contributor.
    Cached 60 s in Redis via the ``roster()`` helper. Empty list when
    no helpers are connected (the operator hasn't enrolled any yet) —
    callers should treat empty as "main PC handles everything",
    not as an error.

    Response shape::

        {
            "online_count": 1,
            "accepting_work_count": 1,
            "sampled_at": "2026-05-02T12:34:56+00:00",
            "helpers": [
                {
                    "name": "helper-cpu-1",
                    "role": "worker",
                    "status": "online",
                    "accepting_work": true,
                    "heartbeat_age_seconds": 12,
                    "has_gpu": false,
                    "cpu_pct": 22.4,
                    "ram_pct": 41.0,
                    "active_jobs": 1,
                    "queued_jobs": 0,
                    "allowed_queues": ["cpu_only", "default"],
                    "allowed_job_types": ["enrichment", "audience"],
                    "warmed_model_keys": [],
                    "capabilities": {"cpu_cores": 8, "ram_gb": 16, "gpu_vram_gb": 0}
                }
            ]
        }
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        from dataclasses import asdict

        from apps.core.helpers import roster

        snap = roster()
        return Response(
            {
                "online_count": snap.online_count,
                "accepting_work_count": snap.accepting_work_count,
                "sampled_at": snap.sampled_at,
                "helpers": [asdict(h) for h in snap.helpers],
            }
        )


# ── Re-exports for backward compatibility ────────────────────────
# Every importer that previously did
# ``from apps.core.views import AppearanceSettingsView`` (or any of
# the other names below) keeps working unchanged after the
# 2026-05-10 settings-view extraction. The actual definitions now
# live in ``apps/core/views_settings.py`` — see that file's module
# docstring for the rationale.
from .views_settings import (  # noqa: E402, F401
    AppearanceSettingsView,
    FaviconUploadView,
    FieldAwareRelevanceSettingsView,
    GA4GSCSettingsView,
    GSCConnectionTestView,
    LearnedAnchorSettingsView,
    LinkFreshnessRecalculateView,
    LinkFreshnessSettingsView,
    LogoUploadView,
    PhraseMatchingSettingsView,
    RareTermPropagationSettingsView,
    SiloSettingsView,
    WebhookSettingsView,
    WebhookTestView,
    WeightedAuthorityRecalculateView,
    WeightedAuthoritySettingsView,
    WordPressSettingsView,
    WordPressSyncRunView,
    WordPressTestConnectionView,
    XenForoSettingsView,
    XenForoTestConnectionView,
    _GA4_GSC_ROW_SPEC,
    _SiteAssetUploadView,
    _build_ga4_gsc_rows,
    _build_gsc_service,
    _build_link_freshness_rows,
    _build_wordpress_rows,
    _format_setting_value,
    _gsc_private_key,
    _gsc_probe_credentials,
    _gsc_resolve_credentials,
    _probe_webhook_endpoint,
    _save_appearance_key,
    _wordpress_app_password_row,
    _wordpress_base_rows,
    _wp_probe_credentials,
    _wp_resolve_credentials,
    _xf_probe_credentials,
    _xf_resolve_credentials,
)

# 2026-05-10 turn 2 — runtime/system-metrics extraction. See
# apps/core/views_runtime.py for the actual definitions.
from .views_runtime import (  # noqa: E402, F401
    MaintenanceModeSettingsView,
    MasterPauseToggleView,
    RuntimeActivityResumedView,
    RuntimeConfigView,
    RuntimeSettingsView,
    RuntimeSwitchRunView,
    RuntimeSwitchStatusView,
    RuntimeSwitchView,
    SafeModeBootView,
    SystemMetricsView,
    _hardware_capability_snapshot,
    _persist_master_pause_state,
    _persist_performance_mode_settings,
    _read_effective_runtime_mode,
    _read_master_pause_state,
    _read_runtime_mode_setting,
    _record_master_pause_audit_safe,
    _resolve_performance_expiry_choice,
    _runtime_settings_snapshot,
    _sample_cpu_ram_metrics,
    _sample_gpu_metrics,
)
