"""Audit URL routes — audit trail, reviewer scorecards."""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    AuditEntryViewSet,
    ClientErrorLogView,
    FeatureRequestViewSet,
    ReviewerScorecardViewSet,
    SiloLeakageView,
    WebVitalView,
)

router = DefaultRouter()
router.register(r"audit-entries", AuditEntryViewSet, basename="audit-entry")
router.register(
    r"reviewer-scorecards", ReviewerScorecardViewSet, basename="reviewer-scorecard"
)
# Phase GB / Gap 151 — in-app feature-request inbox.
router.register(r"feature-requests", FeatureRequestViewSet, basename="feature-request")

urlpatterns = [
    path("", include(router.urls)),
    path("graph/silo-leakage/", SiloLeakageView.as_view(), name="graph-silo-leakage"),
    # Phase U1 / Gap 26 — frontend GlobalErrorHandler POSTs here.
    path(
        "telemetry/client-errors/",
        ClientErrorLogView.as_view(),
        name="client-error-log",
    ),
    # Phase E2 / Gap 51 — WebVitalsService POSTs here (via sendBeacon).
    path(
        "telemetry/web-vitals/",
        WebVitalView.as_view(),
        name="web-vitals",
    ),
]
