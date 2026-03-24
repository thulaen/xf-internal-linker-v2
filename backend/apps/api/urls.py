"""
Root API URL configuration for XF Internal Linker V2.

All REST API endpoints are routed through /api/
DRF routers wire viewsets from each app into clean URL patterns.
"""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.content.views import ContentItemViewSet, ScopeItemViewSet, SiloGroupViewSet
from apps.suggestions.views import (
    PipelineDiagnosticViewSet,
    PipelineRunViewSet,
    SuggestionViewSet,
)
from apps.sync.views import ImportUploadView, SyncJobViewSet
from apps.core.views import (
    AppearanceSettingsView,
    DashboardView,
    FaviconUploadView,
    LogoUploadView,
    SiloSettingsView,
)
from apps.graph.views import BrokenLinkViewSet

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
    # Health check (from core app)
    path("", include("apps.core.urls")),

    # All DRF routed endpoints
    path("", include(router.urls)),

    # Content import — accepts JSONL file upload, starts background job
    path("import/upload/", ImportUploadView.as_view(), name="import-upload"),

    # Appearance settings — GET returns config, PUT merges updates
    path("settings/appearance/", AppearanceSettingsView.as_view(), name="appearance-settings"),
    path("settings/silos/", SiloSettingsView.as_view(), name="silo-settings"),

    # Site identity assets — POST uploads file, DELETE clears URL
    path("settings/logo/", LogoUploadView.as_view(), name="settings-logo"),
    path("settings/favicon/", FaviconUploadView.as_view(), name="settings-favicon"),

    # Dashboard — aggregated stats
    path("dashboard/", DashboardView.as_view(), name="dashboard"),

    # DRF browsable API login/logout
    path("auth/", include("rest_framework.urls", namespace="rest_framework")),
]
