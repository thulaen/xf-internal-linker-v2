"""URL routes for the diagnostics app."""

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
    path("accuracy/tools/", views.AccuracyToolsView.as_view(), name="accuracy-tools"),
    path(
        "accuracy/summary/",
        views.AccuracySummaryView.as_view(),
        name="accuracy-summary",
    ),
    path(
        "accuracy/findings/",
        views.AccuracyFindingsView.as_view(),
        name="accuracy-findings",
    ),
    path(
        "accuracy/report/",
        views.AccuracyReportView.as_view(),
        name="accuracy-report",
    ),
    path("accuracy/run/", views.AccuracyRunView.as_view(), name="accuracy-run"),
    # FR-247 — Stage-2 cpp/python pathway counter for the /performance card.
    # See docs/specs/fr247-fast-path-observability.md.
    path(
        "stage2-path-status/",
        views.Stage2PathStatusView.as_view(),
        name="stage2-path-status",
    ),
    # Polish.B — daily NDCG@10 readout over the reviewed-Suggestion
    # stream. Paper-backed (Järvelin-Kekäläinen 2002, Buckley-Voorhees
    # 2004, Sanderson 2010) automated retriever-quality eval.
    path(
        "ndcg-eval/",
        views.NdcgEvalView.as_view(),
        name="ndcg-eval",
    ),
    # Phase 1v — suppressed-pair counter for the Diagnostics page (Phase 1
    # negative memory visibility).
    path(
        "suppressed-pairs/",
        views.NegativeMemoryDiagnosticsView.as_view(),
        name="suppressed-pairs",
    ),
    # Tier 2 slice 4 — drilldown list + manual clear action.
    path(
        "suppressed-pairs/list/",
        views.NegativeMemoryListView.as_view(),
        name="suppressed-pairs-list",
    ),
    path(
        "suppressed-pairs/<int:pair_id>/clear/",
        views.NegativeMemoryClearView.as_view(),
        name="suppressed-pairs-clear",
    ),
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
    path(
        "internal/scheduler/dispatch/",
        views.SchedulerDispatchView.as_view(),
        name="scheduler-dispatch",
    ),
    # Phase 4.7 — "Why Is It Slow?" bottleneck analyzer.
    # GET /api/diagnostics/why-slow/ samples live system state and
    # returns a one-word verdict + plain-English reason. Used by the
    # operator's per-job slowness panel.
    path(
        "why-slow/",
        views.WhyIsItSlowView.as_view(),
        name="why-is-it-slow",
    ),
    # Phase 4.5 — "Why Is This Taking So Long?" structured panel.
    # GET /api/diagnostics/why-so-long/?job=<job_key>
    # Returns stage progress + items/sec + ETA + bottleneck verdict
    # + action chips for one running job. Long-running tasks publish
    # their live stage state via
    # apps.diagnostics.services.why_so_long.publish_stage_update().
    path(
        "why-so-long/",
        views.WhySoLongPanelView.as_view(),
        name="why-so-long-panel",
    ),
]
