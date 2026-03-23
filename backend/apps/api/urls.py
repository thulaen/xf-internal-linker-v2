"""
Root API URL configuration for XF Internal Linker V2.

All REST API endpoints are routed through /api/
DRF routers and viewsets are added per-app in Phase 1.
"""

from django.urls import path, include

urlpatterns = [
    # Health check — always available
    path("", include("apps.core.urls")),

    # App-specific API routes (DRF routers added in Phase 1)
    # path("content/", include("apps.content.urls")),
    # path("suggestions/", include("apps.suggestions.urls")),
    # path("pipeline/", include("apps.pipeline.urls")),
    # path("analytics/", include("apps.analytics.urls")),
    # path("webhooks/", include("apps.webhooks.urls")),
    # path("audit/", include("apps.audit.urls")),
    # path("graph/", include("apps.graph.urls")),
    # path("plugins/", include("apps.plugins.urls")),
]
