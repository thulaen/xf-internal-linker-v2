"""DRF views for the Operations Feed."""

from __future__ import annotations

from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import OperationEvent
from .serializers import OperationEventSerializer


class OperationEventViewSet(viewsets.ReadOnlyModelViewSet):
    """GET /api/operations/events/ — paginated feed; realtime push does the rest.

    The primary render path is the `operations.feed` realtime topic;
    this endpoint exists so a page reload can hydrate the last ~500
    events, and so non-realtime tooling (Playwright snapshots, Ops
    Feed CSV export) has a canonical source.
    """

    queryset = OperationEvent.objects.all().order_by("-timestamp")
    serializer_class = OperationEventSerializer
    permission_classes = [IsAuthenticated]

    def list(self, request, *args, **kwargs):  # type: ignore[override]
        qs = self.filter_queryset(self.get_queryset())

        # Filter by severity / source via plain query params — keeps the
        # endpoint dependency-free (no django-filter required).
        sev = request.query_params.get("severity")
        if sev:
            qs = qs.filter(severity=sev)
        source = request.query_params.get("source")
        if source:
            qs = qs.filter(source=source)
        search = request.query_params.get("q", "").strip()
        if search:
            qs = qs.filter(plain_english__icontains=search)

        limit = min(int(request.query_params.get("limit", "500") or 500), 2000)
        qs = qs[:limit]
        ser = self.get_serializer(qs, many=True)
        return Response(ser.data)
