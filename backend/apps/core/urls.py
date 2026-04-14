"""Core URL routes — system status + dashboard operating desk."""

from django.urls import path
from .views import (
    HealthCheckView,
    TodayActionsView,
    WhatChangedView,
    ResumeStateView,
    RuntimeSettingsView,
    RuntimeSwitchView,
    SystemMetricsView,
    RuntimeConfigView,
    SafeModeBootView,
    JobQueueView,
    JobQuarantineView,
    HelperNodeListView,
    HelperNodeDetailView,
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
    path("settings/runtime/", RuntimeSettingsView.as_view(), name="settings-runtime"),
    path(
        "settings/runtime/switch/",
        RuntimeSwitchView.as_view(),
        name="settings-runtime-switch",
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
    path(
        "settings/helpers/<int:pk>/",
        HelperNodeDetailView.as_view(),
        name="helpers-detail",
    ),
]
