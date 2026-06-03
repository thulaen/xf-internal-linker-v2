"""URL config for the auto_issues HTTP API."""

from django.urls import path
from rest_framework.routers import DefaultRouter

from . import findbugs_views
from .sidecar_views import list_bulletins, list_snapshots
from .views import AutoIssueViewSet

router = DefaultRouter()
router.register(r"auto-issues", AutoIssueViewSet, basename="auto-issues")

# Slice 1.6 — read-only proxies for the Errors page sidecars tabs.
# Moves to apps.governance / apps.operations URLs in slice 9 (paper-trail #571).
urlpatterns = [
    *router.urls,
    path(
        "find-bugs/summary/",
        findbugs_views.FindBugsSummaryView.as_view(),
        name="findbugs-summary",
    ),
    path(
        "find-bugs/findings/",
        findbugs_views.FindBugsFindingsView.as_view(),
        name="findbugs-findings",
    ),
    path(
        "find-bugs/run/", findbugs_views.FindBugsRunView.as_view(), name="findbugs-run"
    ),
    path(
        "find-bugs/import-latest/",
        findbugs_views.FindBugsImportLatestView.as_view(),
        name="findbugs-import-latest",
    ),
    path(
        "find-bugs/prune-artifacts/",
        findbugs_views.FindBugsPruneArtifactsView.as_view(),
        name="findbugs-prune-artifacts",
    ),
    path(
        "find-bugs/lesson/",
        findbugs_views.FindBugsLessonView.as_view(),
        name="findbugs-lesson",
    ),
    path(
        "find-bugs/confirm/",
        findbugs_views.FindBugsConfirmView.as_view(),
        name="findbugs-confirm",
    ),
    path(
        "find-bugs/evaluate/",
        findbugs_views.FindBugsEvaluateView.as_view(),
        name="findbugs-evaluate",
    ),
    path(
        "find-bugs/duplicate-check/",
        findbugs_views.FindBugsDuplicateCheckView.as_view(),
        name="findbugs-duplicate-check",
    ),
    path(
        "find-bugs/regression-check/",
        findbugs_views.FindBugsRegressionCheckView.as_view(),
        name="findbugs-regression-check",
    ),
    path(
        "find-bugs/generate-report/",
        findbugs_views.FindBugsReportView.as_view(),
        name="findbugs-generate-report",
    ),
    path(
        "find-bugs/sync-context/",
        findbugs_views.FindBugsSyncContextView.as_view(),
        name="findbugs-sync-context",
    ),
    path(
        "find-bugs/create-fix-task/",
        findbugs_views.FindBugsCreateFixTaskView.as_view(),
        name="findbugs-create-fix-task",
    ),
    path(
        "find-bugs/assign-agent/",
        findbugs_views.FindBugsAssignAgentView.as_view(),
        name="findbugs-assign-agent",
    ),
    path(
        "find-bugs/approve-lesson/",
        findbugs_views.FindBugsApproveLessonView.as_view(),
        name="findbugs-approve-lesson",
    ),
    path("sidecars/snapshots/", list_snapshots, name="sidecars-snapshots"),
    path("sidecars/bulletins/", list_bulletins, name="sidecars-bulletins"),
]
