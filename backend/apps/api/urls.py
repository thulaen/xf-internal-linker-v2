"""
Root API URL configuration for XF Internal Linker V2.

All REST API endpoints are routed through /api/.
DRF routers wire viewsets from each app into clean URL patterns.
"""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.content.views import ContentItemViewSet, ScopeItemViewSet, SiloGroupViewSet
from apps.core.views import (
    AppearanceSettingsView,
    DashboardView,
    FaviconUploadView,
    LogoUploadView,
    SiloSettingsView,
    WordPressSettingsView,
    WordPressSyncRunView,
)
from apps.graph.views import BrokenLinkViewSet
from apps.suggestions.views import (
    PipelineDiagnosticViewSet,
    PipelineRunViewSet,
    SuggestionViewSet,
)
from apps.sync.views import ImportUploadView, SyncJobViewSet

router = DefaultRouter()

# Content (read-only)
router.register(r"scopes", ScopeItemViewSet, basename="scope")
router.register(r"silo-groups", SiloGroupViewSet, basename="silo-group")
router.register(r"content", ContentItemViewSet, basename="content")

# Suggestions + pipeline
router.register(r"suggestions", SuggestionViewSet, basename="suggestion")
router.register(r"pipeline-runs", PipelineRunViewSet, basename="pipeline-run")
router.register(r"diagnostics", PipelineDiagnosticViewSet, basename="diagnostic")
router.register(r"sync-jobs", SyncJobViewSet, basename="sync-job")
router.register(r"broken-links", BrokenLinkViewSet, basename="broken-link")

urlpatterns = [
    path("", include("apps.core.urls")),
    path("", include(router.urls)),
    path("import/upload/", ImportUploadView.as_view(), name="import-upload"),
    path("settings/appearance/", AppearanceSettingsView.as_view(), name="appearance-settings"),
    path("settings/silos/", SiloSettingsView.as_view(), name="silo-settings"),
    path("settings/wordpress/", WordPressSettingsView.as_view(), name="wordpress-settings"),
    path("settings/logo/", LogoUploadView.as_view(), name="settings-logo"),
    path("settings/favicon/", FaviconUploadView.as_view(), name="settings-favicon"),
    path("sync/wordpress/run/", WordPressSyncRunView.as_view(), name="wordpress-sync-run"),
    path("dashboard/", DashboardView.as_view(), name="dashboard"),
    path("auth/", include("rest_framework.urls", namespace="rest_framework")),
]
