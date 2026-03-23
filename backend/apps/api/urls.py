"""
Root API URL configuration for XF Internal Linker V2.

All REST API endpoints are routed through /api/
DRF routers wire viewsets from each app into clean URL patterns.
"""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.content.views import ContentItemViewSet, ScopeItemViewSet
from apps.suggestions.views import (
    PipelineDiagnosticViewSet,
    PipelineRunViewSet,
    SuggestionViewSet,
)

router = DefaultRouter()

# Content (read-only)
router.register(r"scopes", ScopeItemViewSet, basename="scope")
router.register(r"content", ContentItemViewSet, basename="content")

# Suggestions + pipeline
router.register(r"suggestions", SuggestionViewSet, basename="suggestion")
router.register(r"pipeline-runs", PipelineRunViewSet, basename="pipeline-run")
router.register(r"diagnostics", PipelineDiagnosticViewSet, basename="diagnostic")

urlpatterns = [
    # Health check (from core app)
    path("", include("apps.core.urls")),

    # All DRF routed endpoints
    path("", include(router.urls)),

    # DRF browsable API login/logout
    path("auth/", include("rest_framework.urls", namespace="rest_framework")),
]
