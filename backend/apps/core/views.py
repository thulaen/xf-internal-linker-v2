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

# 2026-05-10 turn 3 — dashboard / today-actions / what-changed /
# resume-state / status-story / mission-brief extraction. See
# apps/core/views_dashboard.py for the actual definitions.
from .views_dashboard import (  # noqa: E402, F401
    DashboardView,
    MissionBriefView,
    ResumeStateView,
    StatusStoryView,
    TodayActionsView,
    WhatChangedView,
    _PENDING_REVIEW_THRESHOLD,
    _STALE_PIPELINE_DAYS,
    _STALE_SYNC_HOURS,
    _dashboard_content_count,
    _dashboard_freshness_timestamps,
    _dashboard_last_analytics_completed_at,
    _dashboard_last_completed_sync,
    _dashboard_open_broken_links,
    _dashboard_overall_health_status,
    _dashboard_recent_imports,
    _dashboard_recent_pipeline_runs,
    _dashboard_runtime_mode_display,
    _dashboard_suggestion_counts,
    _dashboard_system_health,
    _pluralise,
    _resume_view_interrupted_runs,
    _resume_view_missed_tasks,
    _resume_view_resumable_syncs,
    _status_story_alert_count,
    _status_story_alerts_fragment,
    _status_story_broken_fragment,
    _status_story_broken_links_count,
    _status_story_fragments,
    _status_story_health_fragment,
    _status_story_health_status,
    _status_story_pending_count,
    _status_story_pending_fragment,
    _status_story_time_prefix,
    _today_actions_pending_suggestions,
    _today_actions_pipeline_freshness,
    _today_actions_sync_freshness,
    _today_actions_urgent_alerts,
    _today_autotuner_outcome,
    _today_summary_counts,
    _today_view_sentence_today,
    _today_view_sentence_watch,
    _today_view_sentence_yesterday,
    _today_view_today_queue_counts,
    _today_view_top_alert,
    _today_view_top_alert_dict,
    _today_view_yesterday_counts,
)

# 2026-05-10 turn 4 (final slice) — jobs / helpers /
# per-feature-optimisation / user-auth / system-analytics extraction.
# This is the last slice; ``views.py`` finally drops below the
# 1500-line cap and leaves the grandfather list. See
# ``apps/core/views_capacity.py`` for the actual definitions.
from .views_capacity import (  # noqa: E402, F401
    ActiveUsersView,
    BudgetForecastTasksView,
    BudgetForecastView,
    CachePolicyEvictView,
    CachePolicyPinView,
    CachePolicySummaryView,
    ChallengerEvaluateView,
    ClickDistanceRecalculateView,
    ClickDistanceSettingsView,
    ClusteringRecalculateView,
    ClusteringSettingsView,
    CompressionAuditRunView,
    CompressionAuditView,
    CppFallbackStatusView,
    DEFAULT_SPAM_GUARD_SETTINGS,
    FeedbackRerankSettingsView,
    FirstOperatorSetupView,
    GraphCandidateSettingsView,
    GraphRebuildView,
    HelperNodeDetailView,
    HelperNodeHeartbeatView,
    HelperNodeListView,
    HelpersRosterView,
    JobQuarantineView,
    JobQueueView,
    LocalVerificationBootstrapView,
    PerformanceCertRunView,
    PerformanceCertView,
    SlateDiversitySettingsView,
    SpamGuardSettingsView,
    UserLogoutView,
    UserMeView,
    ValueModelSettingsView,
    WeightTuneTriggerView,
    _GRAPH_CANDIDATE_INT_BOUNDS,
    _GRAPH_CANDIDATE_ROW_SPEC,
    _HEARTBEAT_UPDATE_FIELDS,
    _SPAM_GUARD_KEYS,
    _SPAM_GUARD_ROW_SPEC,
    _VALUE_MODEL_BOOL_KEYS,
    _VALUE_MODEL_FLOAT_BOUNDS,
    _VALUE_MODEL_INT_BOUNDS,
    _apply_heartbeat_gpu_metrics,
    _apply_heartbeat_identity,
    _apply_heartbeat_load_metrics,
    _apply_heartbeat_network_health,
    _build_graph_candidate_rows,
    _build_spam_guard_rows,
    _build_value_model_rows,
    _client_is_local_setup_request,
    _job_queue_active_runs,
    _job_queue_active_syncs,
    _legacy_quarantine_row,
    _quarantine_legacy_rows,
    _quarantine_records_and_run_ids,
    _validate_graph_candidate_settings,
    _validate_slate_diversity_settings,
    _validate_spam_guard_settings,
    _validate_value_model_settings,
    _vm_bool_str,
    _vm_rows_co_occurrence,
    _vm_rows_core,
    _vm_rows_engagement,
    _vm_rows_hot_decay,
    get_spam_guard_settings,
)
