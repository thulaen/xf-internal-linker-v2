"""Analytics URL routes."""

from django.urls import path

from .views import (
    AnalyticsTelemetryFunnelView,
    AnalyticsGA4SettingsView,
    AnalyticsGA4ReadConnectionView,
    AnalyticsGA4SyncView,
    AnalyticsGA4TestConnectionView,
    AnalyticsMatomoSettingsView,
    AnalyticsMatomoSyncView,
    AnalyticsMatomoTestConnectionView,
    AnalyticsTelemetryIntegrationView,
    AnalyticsTelemetryOverviewView,
    AnalyticsTelemetryTopSuggestionsView,
    AnalyticsTelemetryTrendView,
)

urlpatterns = [
    path("telemetry/overview/", AnalyticsTelemetryOverviewView.as_view(), name="analytics-telemetry-overview"),
    path("telemetry/funnel/", AnalyticsTelemetryFunnelView.as_view(), name="analytics-telemetry-funnel"),
    path("telemetry/trend/", AnalyticsTelemetryTrendView.as_view(), name="analytics-telemetry-trend"),
    path("telemetry/top-suggestions/", AnalyticsTelemetryTopSuggestionsView.as_view(), name="analytics-telemetry-top-suggestions"),
    path("telemetry/integration/", AnalyticsTelemetryIntegrationView.as_view(), name="analytics-telemetry-integration"),
    path("telemetry/ga4-sync/", AnalyticsGA4SyncView.as_view(), name="analytics-ga4-sync"),
    path("telemetry/matomo-sync/", AnalyticsMatomoSyncView.as_view(), name="analytics-matomo-sync"),
    path("settings/ga4/", AnalyticsGA4SettingsView.as_view(), name="analytics-ga4-settings"),
    path("settings/ga4/test-connection/", AnalyticsGA4TestConnectionView.as_view(), name="analytics-ga4-test-connection"),
    path("settings/ga4/test-read-connection/", AnalyticsGA4ReadConnectionView.as_view(), name="analytics-ga4-read-connection"),
    path("settings/matomo/", AnalyticsMatomoSettingsView.as_view(), name="analytics-matomo-settings"),
    path("settings/matomo/test-connection/", AnalyticsMatomoTestConnectionView.as_view(), name="analytics-matomo-test-connection"),
]
