"""Audit URL routes — audit trail, reviewer scorecards."""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import AuditEntryViewSet, ReviewerScorecardViewSet, SiloLeakageView

router = DefaultRouter()
router.register(r"audit-entries", AuditEntryViewSet, basename="audit-entry")
router.register(
    r"reviewer-scorecards", ReviewerScorecardViewSet, basename="reviewer-scorecard"
)

urlpatterns = [
    path("", include(router.urls)),
    path("graph/silo-leakage/", SiloLeakageView.as_view(), name="graph-silo-leakage"),
]
