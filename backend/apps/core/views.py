"""
Core views — health check + back-compat re-exports.

GET    /api/health/             → {"status": "ok", "version": "2.0.0"}

This file used to be the historical home of every view in the core app
and grew well past the 1500-line cap. The cleanup happened in five
slices on 2026-05-10:

    Slice 1 (commit c315c40d) → ``views_settings.py``
    Slice 2 (commit b5c1ae97) → ``views_runtime.py``
    Slice 3 (commit 7eafdbec) → ``views_dashboard.py``
    Slice 4 (commit 3ace0ce8) → ``views_capacity.py``
    Slice 5 (this file)       → shared helpers in
                                ``services/settings_helpers.py``

Each of the four ``views_*`` modules and the ``settings_helpers``
service module is re-exported from the bottom of this file so existing
``from apps.core.views import …`` callers (the URL configs, the
pipeline tasks, the settings tests, the suggestions module, etc.) keep
working unchanged.

The only first-class symbols defined here are ``HealthCheckView``,
``_safe_confidence_snapshot`` (used by the dashboard via lazy import),
and the appearance / asset-upload module-level constants
(``DEFAULT_APPEARANCE``, ``_LOGO_ALLOWED``, ``_FAVICON_ALLOWED``,
``_ASSET_MAX_BYTES``) that ``views_settings`` consumes.
"""

import logging

from django.http import JsonResponse
from django.views import View

logger = logging.getLogger(__name__)


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


class HealthCheckView(View):
    """
    Simple health check endpoint.
    Used by Docker Compose and load balancers to verify the backend is alive.
    """

    def get(self, request):
        """Return a simple JSON response confirming the backend is running."""
        return JsonResponse({"status": "ok", "version": "2.0.0"})


# 2026-05-10 turn 5 (final slice) — shared-helpers extraction. See
# ``apps/core/services/settings_helpers.py`` for the actual definitions.
# Every importer that previously did ``from apps.core.views import
# get_silo_settings`` (or any other shared helper) keeps working
# unchanged via this re-export block.
from .services.settings_helpers import (  # noqa: E402, F401
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
    _coerce_bool_strict,
    _coerce_float_strict,
    _coerce_int_strict,
    _ga4_gsc_connection_status,
    _get_app_setting_value,
    _read_clustering_settings,
    _read_click_distance_settings,
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
    _sync_wordpress_periodic_task,
    _validate_clustering_settings,
    _validate_click_distance_settings,
    _validate_feedback_rerank_settings,
    _validate_field_aware_relevance_settings,
    _validate_ga4_gsc_consistency,
    _validate_ga4_gsc_settings,
    _validate_learned_anchor_settings,
    _validate_link_freshness_settings,
    _validate_phrase_matching_settings,
    _validate_rare_term_propagation_settings,
    _validate_silo_settings,
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
    get_clustering_settings,
    get_click_distance_settings,
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
    get_value_model_settings,
    get_weighted_authority_settings,
    get_wordpress_runtime_config,
    get_wordpress_settings,
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

# 2026-05-10 turn 4 — jobs / helpers / per-feature-optimisation /
# user-auth / system-analytics extraction. See
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
