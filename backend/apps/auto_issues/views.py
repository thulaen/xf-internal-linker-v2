"""HTTP API for the auto_issues registry.

Endpoints:
  GET  /api/auto-issues/                   — list (filterable)
  GET  /api/auto-issues/<id>/              — single row
  POST /api/auto-issues/resync/            — fire all 3 pickers synchronously
  POST /api/auto-issues/flush-cache/       — drop stale audit_errorlog rows + force re-pull

Read access: any authenticated user. Write access (resync, flush): admin only.
"""

from __future__ import annotations

import logging

from django.utils import timezone
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import AutoIssue
from .serializers import AutoIssueSerializer

logger = logging.getLogger(__name__)


class AutoIssueViewSet(viewsets.ReadOnlyModelViewSet):
    """ReadOnly + two custom POST actions: resync and flush-cache."""

    queryset = AutoIssue.objects.all()
    serializer_class = AutoIssueSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = AutoIssue.objects.all()
        status_param = self.request.query_params.get("status")
        if status_param == "open":
            qs = qs.filter(
                status__in=(AutoIssue.STATUS_OPEN, AutoIssue.STATUS_PICKED)
            )
        elif status_param == "resolved":
            qs = qs.filter(status=AutoIssue.STATUS_RESOLVED)
        elif status_param:
            qs = qs.filter(status=status_param)
        source_param = self.request.query_params.get("source")
        if source_param:
            qs = qs.filter(source=source_param)
        return qs.order_by("-priority_score", "-last_seen")

    @action(
        detail=False,
        methods=["post"],
        permission_classes=[permissions.IsAdminUser],
    )
    def resync(self, request):
        """Fire all 3 pickers synchronously + the GT mirror sync.

        Use this from the frontend "Resync" button. Returns the combined
        outcome counts so the UI can show "X new, Y merged, Z resolved".
        """
        from apps.audit.tasks import sync_glitchtip_issues
        from apps.auto_issues.services.glitchtip_picker import (
            pick_glitchtip_issues,
        )
        from apps.auto_issues.services.internal_picker import (
            pick_internal_issues,
        )
        from apps.auto_issues.services.pyroscope_picker import (
            pick_pyroscope_regressions,
        )

        gt_sync = sync_glitchtip_issues()
        gt_pick = pick_glitchtip_issues()
        internal_pick = pick_internal_issues()
        pyro_pick = pick_pyroscope_regressions()
        return Response({
            "status": "ok",
            "glitchtip_sync": gt_sync,
            "glitchtip_picker": gt_pick,
            "internal_picker": internal_pick,
            "pyroscope_picker": pyro_pick,
            "open_count": AutoIssue.objects.filter(
                status__in=(AutoIssue.STATUS_OPEN, AutoIssue.STATUS_PICKED)
            ).count(),
        })

    @action(
        detail=False,
        methods=["post"],
        url_path="flush-cache",
        permission_classes=[permissions.IsAdminUser],
    )
    def flush_cache(self, request):
        """Drop stale `audit_errorlog` rows older than 24h then force re-pull.

        Use this from the frontend "Flush" button. Frees Postgres rows
        that the next sync will re-create from GlitchTip if they're still
        active. Idempotent — re-running adds no work.
        """
        from datetime import timedelta

        from apps.audit.models import ErrorLog
        from apps.audit.tasks import sync_glitchtip_issues

        cutoff = timezone.now() - timedelta(hours=24)
        flushed = ErrorLog.objects.filter(
            source=ErrorLog.SOURCE_GLITCHTIP, created_at__lt=cutoff
        ).delete()[0]
        gt_sync = sync_glitchtip_issues()
        return Response({
            "status": "ok",
            "flushed_rows": flushed,
            "glitchtip_sync": gt_sync,
        }, status=status.HTTP_200_OK)
