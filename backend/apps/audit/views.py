"""
Audit views — audit trail, reviewer scorecards, and silo leakage.
"""

from __future__ import annotations

from collections import defaultdict

from django.db.models import Count
from django.db.models.functions import TruncDate
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import AuditEntry, ReviewerScorecard
from .serializers import AuditEntrySerializer, ReviewerScorecardSerializer


class AuditEntryViewSet(viewsets.ReadOnlyModelViewSet):
    """
    GET /api/audit-entries/          — paginated audit trail
    GET /api/audit-entries/{id}/     — full entry with detail JSON
    GET /api/audit-entries/summary/  — action counts grouped by day
    """

    queryset = AuditEntry.objects.all()
    serializer_class = AuditEntrySerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ["action", "target_type"]

    @action(detail=False, methods=["get"])
    def summary(self, request):
        """Action counts grouped by day (last 30 days by default)."""
        rows = (
            AuditEntry.objects
            .annotate(date=TruncDate("created_at"))
            .values("date", "action")
            .annotate(count=Count("id"))
            .order_by("-date")[:210]  # 30 days * 7 action types max
        )
        return Response(list(rows))


class ReviewerScorecardViewSet(viewsets.ReadOnlyModelViewSet):
    """
    GET /api/reviewer-scorecards/       — paginated scorecard list
    GET /api/reviewer-scorecards/{id}/  — single scorecard
    """

    queryset = ReviewerScorecard.objects.all()
    serializer_class = ReviewerScorecardSerializer
    permission_classes = [IsAuthenticated]


class SiloLeakageView(APIView):
    """
    GET /api/graph/silo-leakage/ — cross-silo link statistics.

    Returns total suggestions, cross-silo count, percentage, and per-pair breakdown.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        from apps.suggestions.models import Suggestion

        qs = Suggestion.objects.filter(
            status__in=("approved", "applied", "verified"),
            host__scope__silo_group__isnull=False,
            destination__scope__silo_group__isnull=False,
        ).select_related(
            "host__scope__silo_group",
            "destination__scope__silo_group",
        )

        total = qs.count()
        cross_silo: list[dict] = []
        pair_counts: dict[tuple[str, str], int] = defaultdict(int)
        cross_count = 0

        for s in qs.only(
            "host__scope__silo_group__name",
            "destination__scope__silo_group__name",
        ).iterator():
            src = getattr(getattr(getattr(s.host, "scope", None), "silo_group", None), "name", None)
            dst = getattr(getattr(getattr(s.destination, "scope", None), "silo_group", None), "name", None)
            if src and dst and src != dst:
                cross_count += 1
                pair_counts[(src, dst)] += 1

        for (src, dst), count in sorted(pair_counts.items(), key=lambda x: -x[1]):
            cross_silo.append({"source_silo": src, "target_silo": dst, "count": count})

        return Response({
            "total_suggestions": total,
            "cross_silo_count": cross_count,
            "cross_silo_pct": round(cross_count / total * 100, 2) if total > 0 else 0.0,
            "by_silo_pair": cross_silo[:50],
        })
