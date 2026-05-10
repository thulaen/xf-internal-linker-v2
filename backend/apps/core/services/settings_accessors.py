"""Public settings accessors (getters).

Split from settings_helpers.py on 2026-05-10.
This module provides the get_*_settings functions for external consumption.
"""

from __future__ import annotations

import logging
import json
from django.conf import settings as django_settings
logger = logging.getLogger(__name__)

from apps.api.query_params import coerce_bool
from apps.core.services.settings_base import (
    _get_app_setting_value,
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
    DEFAULT_SILO_SETTINGS,
    DEFAULT_SLATE_DIVERSITY_SETTINGS,
    DEFAULT_VALUE_MODEL_SETTINGS,
    DEFAULT_WEIGHTED_AUTHORITY_SETTINGS,
    DEFAULT_WORDPRESS_SETTINGS,
    DEFAULT_SPAM_GUARD_SETTINGS,
)
from apps.core.services.settings_validators import (
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
    _validate_click_distance_settings,
    _validate_clustering_settings,
    _validate_feedback_rerank_settings,
    _validate_field_aware_relevance_settings,
    _validate_learned_anchor_settings,
    _validate_link_freshness_settings,
    _validate_phrase_matching_settings,
    _validate_rare_term_propagation_settings,
    _validate_weighted_authority_settings,
)

logger = logging.getLogger(__name__)

# ── Silo ──────────────────────────────────────────────────────────

def get_silo_settings() -> dict[str, float | str]:
    mode = _get_app_setting_value("silo.mode", DEFAULT_SILO_SETTINGS["mode"]) or DEFAULT_SILO_SETTINGS["mode"]
    if mode not in {"disabled", "prefer_same_silo", "strict_same_silo"}: mode = DEFAULT_SILO_SETTINGS["mode"]
    return {
        "mode": mode,
        "same_silo_boost": read_app_setting_float("silo.same_silo_boost", DEFAULT_SILO_SETTINGS["same_silo_boost"], require_finite=False),
        "cross_silo_penalty": read_app_setting_float("silo.cross_silo_penalty", DEFAULT_SILO_SETTINGS["cross_silo_penalty"], require_finite=False),
    }

# ── WordPress ─────────────────────────────────────────────────────

def get_wordpress_settings() -> dict[str, object]:
    def _read_wp(k, df, rstrip=False):
        raw = (_get_app_setting_value(k, df) or "").strip()
        return raw.rstrip("/") if rstrip else raw

    base_url = _read_wp("wordpress.base_url", django_settings.WORDPRESS_BASE_URL, rstrip=True)
    username = _read_wp("wordpress.username", django_settings.WORDPRESS_USERNAME)
    app_password = _get_app_setting_value("wordpress.app_password", django_settings.WORDPRESS_APP_PASSWORD) or ""
    sync_enabled = coerce_bool(_get_app_setting_value("wordpress.sync_enabled"), default=False)
    
    from apps.health.services import get_service_health_status
    return {
        "base_url": base_url, "username": username, "app_password_configured": bool(app_password.strip()),
        "sync_enabled": sync_enabled,
        "sync_hour": read_app_setting_int("wordpress.sync_hour", DEFAULT_WORDPRESS_SETTINGS["sync_hour"]),
        "sync_minute": read_app_setting_int("wordpress.sync_minute", DEFAULT_WORDPRESS_SETTINGS["sync_minute"]),
        "health": get_service_health_status("wordpress"),
    }

def get_wordpress_runtime_config() -> dict[str, str]:
    def _read_wp(k, df): return (_get_app_setting_value(k, df) or "").strip()
    return {
        "base_url": _read_wp("wordpress.base_url", django_settings.WORDPRESS_BASE_URL).rstrip("/"),
        "username": _read_wp("wordpress.username", django_settings.WORDPRESS_USERNAME),
        "app_password": _read_wp("wordpress.app_password", django_settings.WORDPRESS_APP_PASSWORD),
    }

def _sync_wordpress_periodic_task(config: dict[str, object]) -> None:
    from django_celery_beat.models import CrontabSchedule, PeriodicTask
    schedule, _ = CrontabSchedule.objects.get_or_create(
        minute=str(config["sync_minute"]), hour=str(config["sync_hour"]),
        day_of_week="*", day_of_month="*", month_of_year="*", timezone="UTC"
    )
    PeriodicTask.objects.update_or_create(
        name="wordpress-content-sync",
        defaults={
            "task": "pipeline.import_content", "crontab": schedule,
            "kwargs": json.dumps({"source": "wp", "mode": "full"}), "queue": "pipeline",
            "enabled": bool(config["sync_enabled"]) and bool(config["base_url"]),
            "description": "Scheduled WordPress content sync for cross-link indexing.",
        },
    )

# ── Feature Accessors (Pattern: Read -> Validate -> Default) ───────

def get_weighted_authority_settings() -> dict[str, float]:
    try: return _validate_weighted_authority_settings(_read_weighted_authority_settings(), current=dict(DEFAULT_WEIGHTED_AUTHORITY_SETTINGS))
    except ValueError: return dict(DEFAULT_WEIGHTED_AUTHORITY_SETTINGS)

def get_link_freshness_settings() -> dict[str, float | int]:
    try: return _validate_link_freshness_settings(_read_link_freshness_settings(), current=dict(DEFAULT_LINK_FRESHNESS_SETTINGS))
    except ValueError: return dict(DEFAULT_LINK_FRESHNESS_SETTINGS)

def get_phrase_matching_settings() -> dict[str, float | int | bool]:
    try: return _validate_phrase_matching_settings(_read_phrase_matching_settings(), current=dict(DEFAULT_PHRASE_MATCHING_SETTINGS))
    except ValueError: return dict(DEFAULT_PHRASE_MATCHING_SETTINGS)

def get_learned_anchor_settings() -> dict[str, float | int | bool]:
    try: return _validate_learned_anchor_settings(_read_learned_anchor_settings(), current=dict(DEFAULT_LEARNED_ANCHOR_SETTINGS))
    except ValueError: return dict(DEFAULT_LEARNED_ANCHOR_SETTINGS)

def get_rare_term_propagation_settings() -> dict[str, float | int | bool]:
    try: return _validate_rare_term_propagation_settings(_read_rare_term_propagation_settings(), current=dict(DEFAULT_RARE_TERM_PROPAGATION_SETTINGS))
    except ValueError: return dict(DEFAULT_RARE_TERM_PROPAGATION_SETTINGS)

def get_field_aware_relevance_settings() -> dict[str, float]:
    try: return _validate_field_aware_relevance_settings(_read_field_aware_relevance_settings(), current=dict(DEFAULT_FIELD_AWARE_RELEVANCE_SETTINGS))
    except ValueError: return dict(DEFAULT_FIELD_AWARE_RELEVANCE_SETTINGS)

def get_click_distance_settings() -> dict[str, float]:
    try: return _validate_click_distance_settings(_read_click_distance_settings(), current=dict(DEFAULT_CLICK_DISTANCE_SETTINGS))
    except ValueError: return dict(DEFAULT_CLICK_DISTANCE_SETTINGS)

def get_feedback_rerank_settings() -> dict[str, float | bool]:
    try: return _validate_feedback_rerank_settings(_read_feedback_rerank_settings(), current=dict(DEFAULT_FEEDBACK_RERANK_SETTINGS))
    except ValueError: return dict(DEFAULT_FEEDBACK_RERANK_SETTINGS)

def get_clustering_settings() -> dict[str, float | bool]:
    try: return _validate_clustering_settings(_read_clustering_settings(), current=dict(DEFAULT_CLUSTERING_SETTINGS))
    except Exception:
        logger.exception("Failed to read clustering settings")
        return dict(DEFAULT_CLUSTERING_SETTINGS)

def get_slate_diversity_settings() -> dict:
    try: return _read_slate_diversity_settings()
    except Exception:
        logger.exception("Failed to read slate diversity settings")
        return dict(DEFAULT_SLATE_DIVERSITY_SETTINGS)

def get_ga4_gsc_settings() -> dict[str, object]:
    settings = _read_ga4_gsc_settings()
    if not isinstance(settings.get("ranking_weight"), (float, int)): settings["ranking_weight"] = DEFAULT_GA4_GSC_SETTINGS["ranking_weight"]
    from apps.health.services import get_service_health_status
    settings["ga4_health"] = get_service_health_status("ga4")
    settings["gsc_health"] = get_service_health_status("gsc")
    return settings

def get_graph_candidate_settings() -> dict[str, float | int | bool]:
    # Import logic was lazy-import in settings_helpers; preserving that or moving it here.
    # Actually, views_ml_settings imports from this module, so we must be careful.
    from apps.core.services.settings_validators import _validate_graph_candidate_settings
    try: return _validate_graph_candidate_settings(_read_graph_candidate_settings(), current=dict(DEFAULT_GRAPH_CANDIDATE_SETTINGS))
    except Exception:
        logger.exception("Failed to read graph candidate settings")
        return dict(DEFAULT_GRAPH_CANDIDATE_SETTINGS)

def get_value_model_settings() -> dict[str, float | int | bool]:
    from apps.core.services.settings_validators import _validate_value_model_settings
    try: return _validate_value_model_settings(_read_value_model_settings(), current=dict(DEFAULT_VALUE_MODEL_SETTINGS))
    except Exception:
        logger.exception("Failed to read value model settings")
        return dict(DEFAULT_VALUE_MODEL_SETTINGS)

def get_spam_guard_settings() -> dict[str, int]:
    return {k: read_app_setting_int(f"spam_guards.{k}", DEFAULT_SPAM_GUARD_SETTINGS[k]) for k in DEFAULT_SPAM_GUARD_SETTINGS}
