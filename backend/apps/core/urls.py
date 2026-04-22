"""Core URL routes — system status + dashboard operating desk."""

from django.urls import path
from .views_runbooks import RunbookExecuteView
from .views_streaming import (
    StreamedSuggestionsHtmlView,
    StreamedSuggestionsSseView,
)
from .views_observability import (
    FeatureFlagExposureView,
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
    # Safe-mode boot flag (arm now, consumed at next Django startup)
    path(
        "system/safe-mode-boot/",
        SafeModeBootView.as_view(),
        name="system-safe-mode-boot",
    ),
    # Jobs execution center (Stage 5)
    path("jobs/queue/", JobQueueView.as_view(), name="jobs-queue"),
    path("jobs/quarantine/", JobQuarantineView.as_view(), name="jobs-quarantine"),
    # Helper nodes (Stage 8)
    path("settings/helpers/", HelperNodeListView.as_view(), name="helpers-list"),
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
        "feature-flags/exposures/",
        FeatureFlagExposureView.as_view(),
        name="feature-flags-exposure",
    ),
]
