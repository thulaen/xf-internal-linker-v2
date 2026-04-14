"""URL patterns for the notifications app."""

from django.urls import path

from .views import (
    AlertDetailView,
    AlertAcknowledgeAllView,
    AlertAcknowledgeView,
    AlertListView,
    AlertReadView,
    AlertResolveView,
    AlertSummaryView,
    NotificationPreferencesView,
    TestNotificationView,
)

urlpatterns = [
    path("notifications/alerts/", AlertListView.as_view(), name="alert-list"),
    path(
        "notifications/alerts/<uuid:alert_id>/",
        AlertDetailView.as_view(),
        name="alert-detail",
    ),
    path(
        "notifications/alerts/summary/",
        AlertSummaryView.as_view(),
        name="alert-summary",
    ),
    path(
        "notifications/alerts/acknowledge-all/",
        AlertAcknowledgeAllView.as_view(),
        name="alert-acknowledge-all",
    ),
    path(
        "notifications/alerts/<uuid:alert_id>/read/",
        AlertReadView.as_view(),
        name="alert-read",
    ),
    path(
        "notifications/alerts/<uuid:alert_id>/acknowledge/",
        AlertAcknowledgeView.as_view(),
        name="alert-acknowledge",
    ),
    path(
        "notifications/alerts/<uuid:alert_id>/resolve/",
        AlertResolveView.as_view(),
        name="alert-resolve",
    ),
    path(
        "settings/notifications/",
        NotificationPreferencesView.as_view(),
        name="notification-preferences",
    ),
    path(
        "notifications/test/", TestNotificationView.as_view(), name="notification-test"
    ),
]
