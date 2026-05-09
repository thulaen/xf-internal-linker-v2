"""URL config for the auto_issues HTTP API."""

from rest_framework.routers import DefaultRouter

from .views import AutoIssueViewSet

router = DefaultRouter()
router.register(r"auto-issues", AutoIssueViewSet, basename="auto-issues")

urlpatterns = router.urls
