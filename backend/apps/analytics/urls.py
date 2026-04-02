"""Analytics URL routes."""

from django.urls import path

from .views import (
    AnalyticsGA4SettingsView,
    AnalyticsGA4TestConnectionView,
    AnalyticsMatomoSettingsView,
    AnalyticsMatomoTestConnectionView,
    AnalyticsTelemetryOverviewView,
)

urlpatterns = [
    path("telemetry/overview/", AnalyticsTelemetryOverviewView.as_view(), name="analytics-telemetry-overview"),
    path("settings/ga4/", AnalyticsGA4SettingsView.as_view(), name="analytics-ga4-settings"),
    path("settings/ga4/test-connection/", AnalyticsGA4TestConnectionView.as_view(), name="analytics-ga4-test-connection"),
    path("settings/matomo/", AnalyticsMatomoSettingsView.as_view(), name="analytics-matomo-settings"),
    path("settings/matomo/test-connection/", AnalyticsMatomoTestConnectionView.as_view(), name="analytics-matomo-test-connection"),
]
