"""Core URL routes — system status + dashboard operating desk."""

from django.urls import path
from .views_docs import view_spec_markdown
from .views_runbooks import RunbookExecuteView
from .views_streaming import (
    StreamedSuggestionsHtmlView,
    StreamedSuggestionsSseView,
)
from .views_observability import (
    FeatureFlagAdminDetailView,
    FeatureFlagExposureView,
    FeatureFlagsAdminView,
    FeatureFlagsListView,
    RumSummaryView,
)
from .views_antispam import (
    AnchorDiversitySettingsView,
    KeywordStuffingSettingsView,
    LinkFarmSettingsView,
)
from .views_runtime_registry import (
    RuntimeModelActionView,
    RuntimeModelPlacementDeleteView,
    RuntimeModelsView,
    RuntimeSummaryView,
)
from .views import (
    HealthCheckView,
    MissionBriefView,
    StatusStoryView,
    TodayActionsView,
    WhatChangedView,
    ResumeStateView,
    RuntimeSettingsView,
    RuntimeSwitchView,
    RuntimeSwitchRunView,
    RuntimeSwitchStatusView,
    RuntimeActivityResumedView,
    MasterPauseToggleView,
    MaintenanceModeSettingsView,
    SystemMetricsView,
    RuntimeConfigView,
    SafeModeBootView,
    JobQueueView,
    JobQuarantineView,
    HelperNodeListView,
    HelperNodeDetailView,
    HelperNodeHeartbeatView,
    HelpersRosterView,
    BudgetForecastView,
    BudgetForecastTasksView,
    CachePolicySummaryView,
    CachePolicyPinView,
    CachePolicyEvictView,
    CppFallbackStatusView,
)

urlpatterns = [
    path("system/health/", HealthCheckView.as_view(), name="health-check"),
    # Dashboard operating desk (Stage 3)
    path(
        "dashboard/today-actions/",
        TodayActionsView.as_view(),
        name="dashboard-today-actions",
    ),
    path(
        "dashboard/what-changed/",
        WhatChangedView.as_view(),
        name="dashboard-what-changed",
    ),
    path(
        "dashboard/resume-state/",
        ResumeStateView.as_view(),
        name="dashboard-resume-state",
    ),
    # Phase D1 / Gap 53 — Status Story card narrative.
    path(
        "dashboard/story/",
        StatusStoryView.as_view(),
        name="dashboard-status-story",
    ),
    # Phase D1 / Gap 61 — Mission Brief pinned summary.
    path(
        "dashboard/mission-brief/",
        MissionBriefView.as_view(),
        name="dashboard-mission-brief",
    ),
    path("settings/runtime/", RuntimeSettingsView.as_view(), name="settings-runtime"),
    path(
        "settings/runtime/models/",
        RuntimeModelsView.as_view(),
        name="settings-runtime-models",
    ),
    path(
        "settings/runtime/models/<int:pk>/action/",
        RuntimeModelActionView.as_view(),
        name="settings-runtime-model-action",
    ),
    path(
        "settings/runtime/models/placements/<int:pk>/",
        RuntimeModelPlacementDeleteView.as_view(),
        name="settings-runtime-model-placement-delete",
    ),
    path(
        "settings/runtime/summary/",
        RuntimeSummaryView.as_view(),
        name="settings-runtime-summary",
    ),
    path(
        "settings/runtime/switch/",
        RuntimeSwitchView.as_view(),
        name="settings-runtime-switch",
    ),
    path(
        "settings/runtime/activity-resumed/",
        RuntimeActivityResumedView.as_view(),
        name="settings-runtime-activity-resumed",
    ),
    path(
        "settings/runtime/switch-runtime/",
        RuntimeSwitchRunView.as_view(),
        name="settings-runtime-switch-runtime",
    ),
    path(
        "settings/runtime/switch-status/",
        RuntimeSwitchStatusView.as_view(),
        name="settings-runtime-switch-status",
    ),
    # Plan item 28 — "Pause Everything" master switch.
    path(
        "settings/master-pause/",
        MasterPauseToggleView.as_view(),
        name="settings-master-pause",
    ),
    # Phase MX3 — maintenance-mode banner (+ future write-gate).
    path(
        "settings/maintenance-mode/",
        MaintenanceModeSettingsView.as_view(),
        name="settings-maintenance-mode",
    ),
    path(
        "settings/runtime-config/",
        RuntimeConfigView.as_view(),
        name="settings-runtime-config",
    ),
    # Live system metrics for the noob-friendly dashboard meters
    path("system/metrics/", SystemMetricsView.as_view(), name="system-metrics"),
    # Group A.5 — read-only spec viewer for the FR-099–FR-105 settings
    # cards. Slug is path-traversal-guarded inside ``views_docs``; the
    # response is JSON {slug, title, html, raw}. Frontend uses this to
    # render the spec inside a Material dialog.
    path(
        "docs/specs/<slug:slug>/",
        view_spec_markdown,
        name="docs-spec-markdown",
    ),
    # Safe-mode boot flag (arm now, consumed at next Django startup)
    path(
        "system/safe-mode-boot/",
        SafeModeBootView.as_view(),
        name="system-safe-mode-boot",
    ),
    # Jobs execution center (Stage 5)
    path("jobs/queue/", JobQueueView.as_view(), name="jobs-queue"),
    path("jobs/quarantine/", JobQuarantineView.as_view(), name="jobs-quarantine"),
    # Helper nodes (Stage 8 + Phase 4.9)
    path("settings/helpers/", HelperNodeListView.as_view(), name="helpers-list"),
    # Phase 4.9 — operator-facing roster endpoint. Returns the
    # right-now state of every connected helper PC + free-disk +
    # heartbeat-age + has_gpu flag. Cached 60 s in Redis.
    path(
        "helpers/",
        HelpersRosterView.as_view(),
        name="helpers-roster",
    ),
    # Phase 4.2 — Budget & Space Forecasts pre-flight estimator.
    # GET /api/system/budget-forecast/?task=<name>&<kwarg>=<value>
    # Returns estimated bytes + projected free disk + verdict chip.
    path(
        "system/budget-forecast/",
        BudgetForecastView.as_view(),
        name="budget-forecast",
    ),
    path(
        "system/budget-forecast/tasks/",
        BudgetForecastTasksView.as_view(),
        name="budget-forecast-tasks",
    ),
    # Phase 4.13 — Cache Eviction Policy. GET stats, POST/DELETE pin,
    # POST evict (per-key or whole-layer with pin-skipping).
    path(
        "system/cache-policy/",
        CachePolicySummaryView.as_view(),
        name="cache-policy-summary",
    ),
    path(
        "system/cache-policy/<str:layer>/pin/",
        CachePolicyPinView.as_view(),
        name="cache-policy-pin",
    ),
    path(
        "system/cache-policy/<str:layer>/evict/",
        CachePolicyEvictView.as_view(),
        name="cache-policy-evict",
    ),
    # Phase 4.14 — C++ Fallback Warning. Returns the live runtime-path
    # status of every C++ extension plus a one-line dashboard banner.
    # The cpp_fallback_check Celery beat (every 5 min) emits ops feed
    # events on transitions; this endpoint is the read-only mirror.
    path(
        "system/cpp-fallback/",
        CppFallbackStatusView.as_view(),
        name="cpp-fallback-status",
    ),
    # Heartbeat must come before the detail route so it isn't swallowed
    # if a future router-style refactor lands here (cf. ISS-012).
    path(
        "settings/helpers/<int:pk>/heartbeat/",
        HelperNodeHeartbeatView.as_view(),
        name="helpers-heartbeat",
    ),
    path(
        "settings/helpers/<int:pk>/",
        HelperNodeDetailView.as_view(),
        name="helpers-detail",
    ),
    path(
        "settings/anchor-diversity/",
        AnchorDiversitySettingsView.as_view(),
        name="settings-anchor-diversity",
    ),
    path(
        "settings/keyword-stuffing/",
        KeywordStuffingSettingsView.as_view(),
        name="settings-keyword-stuffing",
    ),
    path(
        "settings/link-farm/",
        LinkFarmSettingsView.as_view(),
        name="settings-link-farm",
    ),
    path(
        "settings/fr099-fr105/",
        __import__(
            "apps.core.views_fr099_fr105", fromlist=["FR099FR105SettingsView"]
        ).FR099FR105SettingsView.as_view(),
        name="settings-fr099-fr105",
    ),
    # Group C Stage-1 retriever flags (LexicalRetriever + QueryExpansion).
    # Default off; flip on via the Settings UI to enable RRF fusion.
    path(
        "settings/stage1-retrievers/",
        __import__(
            "apps.core.views_stage1_retrievers",
            fromlist=["Stage1RetrieverSettingsView"],
        ).Stage1RetrieverSettingsView.as_view(),
        name="settings-stage1-retrievers",
    ),
    # Phase 6 optional-pick master switches (10 picks: VADER, PySBD,
    # YAKE!, Trafilatura, FastText, LDA, KenLM, Node2Vec, BPR, FM).
    # All default ON via migration 0043. Operator flips off any pick
    # whose cost outweighs the benefit on their corpus.
    path(
        "settings/phase6-picks/",
        __import__(
            "apps.core.views_phase6_picks",
            fromlist=["Phase6PicksSettingsView"],
        ).Phase6PicksSettingsView.as_view(),
        name="settings-phase6-picks",
    ),
    # Runbook execution endpoints (plan item 17)
    path(
        "runbooks/<str:runbook_id>/execute/",
        RunbookExecuteView.as_view(),
        name="runbook-execute",
    ),
    # Phase F1 / Gap 82 — streamed report responses.
    path(
        "reports/stream/suggestions/",
        StreamedSuggestionsHtmlView.as_view(),
        name="reports-stream-suggestions-html",
    ),
    path(
        "reports/stream/suggestions.sse",
        StreamedSuggestionsSseView.as_view(),
        name="reports-stream-suggestions-sse",
    ),
    # Phase OB / Gaps 130-132 — RUM + feature-flag endpoints.
    path(
        "rum/summary/",
        RumSummaryView.as_view(),
        name="rum-summary",
    ),
    path(
        "feature-flags/",
        FeatureFlagsListView.as_view(),
        name="feature-flags-list",
    ),
    path(
        "feature-flags/admin/",
        FeatureFlagsAdminView.as_view(),
        name="feature-flags-admin",
    ),
    path(
        "feature-flags/admin/<slug:key>/",
        FeatureFlagAdminDetailView.as_view(),
        name="feature-flags-admin-detail",
    ),
    path(
        "feature-flags/exposures/",
        FeatureFlagExposureView.as_view(),
        name="feature-flags-exposure",
    ),
]
