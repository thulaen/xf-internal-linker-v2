"""URL config for the auto_issues HTTP API."""

from django.urls import path
from rest_framework.routers import DefaultRouter

from .sidecar_views import list_bulletins, list_snapshots
from .views import AutoIssueViewSet

router = DefaultRouter()
router.register(r"auto-issues", AutoIssueViewSet, basename="auto-issues")

# Slice 1.6 — read-only proxies for the Errors page sidecars tabs.
# Moves to apps.governance / apps.operations URLs in slice 9 (paper-trail #571).
urlpatterns = [
    *router.urls,
    path("sidecars/snapshots/", list_snapshots, name="sidecars-snapshots"),
    path("sidecars/bulletins/", list_bulletins, name="sidecars-bulletins"),
]
