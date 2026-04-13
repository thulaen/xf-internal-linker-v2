"""Core URL routes — system status + dashboard operating desk."""

from django.urls import path
from .views import (
    HealthCheckView,
    TodayActionsView,
    WhatChangedView,
    ResumeStateView,
    RuntimeSettingsView,
    RuntimeSwitchView,
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
