from __future__ import annotations

from pathlib import Path

from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.auto_issues.services.findbugs import (
    build_findbugs_summary,
    assign_to_agent,
    approve_latest_lesson,
    confirm_real_bug,
    create_fix_task,
    duplicate_check,
    evaluate_with_agents,
    generate_findbugs_report,
    import_latest_findbugs_report,
    list_findbugs_findings,
    move_issue_to_learned_lesson,
    prune_findbugs_artifacts,
    regression_check,
    run_findbugs_scan,
    sync_findbugs_context,
)


class FindBugsSummaryView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        return Response(build_findbugs_summary(root=_artifact_root_from_request(request)))


class FindBugsFindingsView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        findings = list_findbugs_findings(
            status=request.query_params.get("status"),
            severity=request.query_params.get("severity"),
            category=request.query_params.get("category"),
            agent=request.query_params.get("agent"),
            model=request.query_params.get("model"),
            search=request.query_params.get("search"),
        )
        return Response({"results": findings})


class FindBugsRunView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        result = run_findbugs_scan()
        return Response(result, status=_status_for(result))


class FindBugsImportLatestView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        result = import_latest_findbugs_report(root=_artifact_root_from_request(request))
        return Response(result, status=_status_for(result))


class FindBugsPruneArtifactsView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        result = prune_findbugs_artifacts(root=_artifact_root_from_request(request))
        return Response(result)


class FindBugsLessonView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        lesson = move_issue_to_learned_lesson(
            issue_id=int(request.data["issue_id"]),
            classification=str(request.data["classification"]),
            lesson=str(request.data["lesson"]),
            agent=str(request.data.get("agent") or request.user.username or "agent"),
        )
        return Response({"status": "ok", "lesson_id": lesson.id})


class FindBugsConfirmView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        return Response(confirm_real_bug(
            issue_id=int(request.data["issue_id"]),
            agent=str(request.user.username or "agent"),
        ))


class FindBugsEvaluateView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        issue_ids = [int(value) for value in request.data.get("issue_ids", [])]
        return Response(evaluate_with_agents(
            issue_ids=issue_ids,
            agent=str(request.data.get("agent") or request.user.username or "agent"),
        ))


class FindBugsDuplicateCheckView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        return Response(duplicate_check(issue_id=int(request.data["issue_id"])))


class FindBugsRegressionCheckView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        return Response(regression_check(issue_id=int(request.data["issue_id"])))


class FindBugsReportView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        return Response(generate_findbugs_report())


class FindBugsSyncContextView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        return Response(sync_findbugs_context(root=_artifact_root_from_request(request)))


class FindBugsCreateFixTaskView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        return Response(create_fix_task(issue_id=int(request.data["issue_id"])))


class FindBugsAssignAgentView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        return Response(assign_to_agent(
            issue_id=int(request.data["issue_id"]),
            agent=str(request.data.get("agent") or "codex"),
        ))


class FindBugsApproveLessonView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        return Response(approve_latest_lesson(
            issue_id=int(request.data["issue_id"]),
            agent=str(request.user.username or "agent"),
        ))


def _artifact_root_from_request(request) -> Path | None:
    value = request.META.get("HTTP_X_FINDBUGS_ARTIFACT_ROOT")
    return Path(value) if value else None


def _status_for(result: dict) -> int:
    return status.HTTP_202_ACCEPTED if result.get("status") == "ok" else status.HTTP_200_OK
