from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r"services", views.ServiceStatusViewSet, basename="service-status")
router.register(r"conflicts", views.ConflictViewSet, basename="conflict")
router.register(r"errors", views.SystemErrorViewSet, basename="system-error")

urlpatterns = [
    path("", include(router.urls)),
    path(
        "overview/",
        views.DiagnosticsOverviewView.as_view(),
        name="diagnostics-overview",
    ),
    path("features/", views.FeatureReadinessView.as_view(), name="feature-readiness"),
    path("resources/", views.ResourceUsageView.as_view(), name="resource-usage"),
    path("weights/", views.WeightDiagnosticsView.as_view(), name="weight-diagnostics"),
    # Phase GT Step 5 — operator intelligence endpoints
    path(
        "runtime-context/",
        views.RuntimeContextView.as_view(),
        name="runtime-context",
    ),
    path("nodes/", views.NodesView.as_view(), name="nodes-summary"),
    path(
        "pipeline-gate/",
        views.PipelineGateView.as_view(),
        name="pipeline-gate",
    ),
    # Phase SEQ — signal queue visibility
    path(
        "signal-queue/",
        views.SignalQueueView.as_view(),
        name="signal-queue",
    ),
    # Phase MC — Mission Critical tile aggregator for the dashboard tab.
    path(
        "mission-critical/",
        views.MissionCriticalView.as_view(),
        name="mission-critical",
    ),
    # FR-225 — Meta Tournament
    path(
        "meta-tournament/", views.MetaTournamentView.as_view(), name="meta-tournament"
    ),
    path(
        "meta-tournament/run/",
        views.MetaTournamentRunView.as_view(),
        name="meta-tournament-run",
    ),
    path(
        "meta-tournament/pin/",
        views.MetaTournamentPinView.as_view(),
        name="meta-tournament-pin",
    ),
    path(
        "internal/scheduler/dispatch/",
        views.SchedulerDispatchView.as_view(),
        name="scheduler-dispatch",
    ),
]
