"""URL routing for the Scheduled Updates API."""

from __future__ import annotations

from django.urls import path

from .views import (
    AlertAcknowledgeView,
    AlertListView,
    ScheduledJobCancelView,
    ScheduledJobDetailView,
    ScheduledJobListView,
    ScheduledJobPauseView,
    ScheduledJobResumeView,
    ScheduledJobRunNowView,
    WindowStatusView,
)

app_name = "scheduled_updates"

urlpatterns = [
    # Jobs
    path("jobs/", ScheduledJobListView.as_view(), name="job-list"),
    path("jobs/<int:pk>/", ScheduledJobDetailView.as_view(), name="job-detail"),
    path(
        "jobs/<int:pk>/pause/",
        ScheduledJobPauseView.as_view(),
        name="job-pause",
    ),
    path(
        "jobs/<int:pk>/resume/",
        ScheduledJobResumeView.as_view(),
        name="job-resume",
    ),
    path(
        "jobs/<int:pk>/cancel/",
        ScheduledJobCancelView.as_view(),
        name="job-cancel",
    ),
    path(
        "jobs/<int:pk>/run-now/",
        ScheduledJobRunNowView.as_view(),
        name="job-run-now",
    ),
    # Alerts
    path("alerts/", AlertListView.as_view(), name="alert-list"),
    path(
        "alerts/<int:pk>/acknowledge/",
        AlertAcknowledgeView.as_view(),
        name="alert-acknowledge",
    ),
    # Window status
    path("window/", WindowStatusView.as_view(), name="window-status"),
]
