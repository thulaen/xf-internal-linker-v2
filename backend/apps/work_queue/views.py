from __future__ import annotations

from django.core.exceptions import ObjectDoesNotExist, ValidationError
from rest_framework import status, views
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.work_queue import api


class WorkQueueOverviewView(views.APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(api.build_overview())


class WorkQueueFeedView(views.APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(api.build_feed())


class WorkQueueCauseGroupsView(views.APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response({"cause_groups": api.build_cause_groups()})


class WorkQueueTaskClaimView(views.APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, item_key: str):
        agent = request.data.get("agent") or request.user.get_username() or "unknown"
        return _safe_response(lambda: api.claim_item(item_key=item_key, agent=agent))


class WorkQueueTaskReleaseView(views.APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, item_key: str):
        agent = request.data.get("agent") or request.user.get_username() or "unknown"
        return _safe_response(lambda: api.release_item(item_key=item_key, agent=agent))


class WorkQueueTaskRehearseView(views.APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, item_key: str):
        return _safe_response(lambda: api.rehearse_item(item_key))


class WorkQueueSelfHealingView(views.APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(api.latest_self_healing_status())


class WorkQueueSelfHealingApproveView(views.APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, decision_id: int):
        return _safe_response(lambda: api.approve_decision(decision_id))


def _safe_response(fn):
    try:
        return Response(fn())
    except (ValidationError, ObjectDoesNotExist) as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

