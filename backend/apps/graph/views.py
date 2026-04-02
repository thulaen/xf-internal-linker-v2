"""Graph views — existing-link and broken-link API endpoints."""

from __future__ import annotations

import csv
import uuid
from datetime import datetime

from django.http import StreamingHttpResponse
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import status, viewsets
from rest_framework.permissions import AllowAny
from rest_framework.decorators import action
from rest_framework.response import Response

from .serializers import BrokenLinkSerializer


class BrokenLinkViewSet(viewsets.ModelViewSet):
    """
    Link-health endpoints.

    GET   /api/broken-links/
    PATCH /api/broken-links/{broken_link_id}/
    POST  /api/broken-links/scan/
    GET   /api/broken-links/export-csv/
    """

    permission_classes = [AllowAny]
    serializer_class = BrokenLinkSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["status", "http_status"]
    http_method_names = ["get", "patch", "post", "head", "options"]
    lookup_field = "broken_link_id"

    def get_queryset(self):
        from apps.graph.models import BrokenLink

        return BrokenLink.objects.select_related("source_content").order_by("status", "-last_checked_at")

    def partial_update(self, request, *args, **kwargs) -> Response:
        disallowed_keys = set(request.data.keys()) - {"status", "notes"}
        if disallowed_keys:
            return Response(
                {"detail": "Only status and notes can be updated."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return super().partial_update(request, *args, **kwargs)

    @action(detail=False, methods=["post"])
    def scan(self, request) -> Response:
        from apps.graph.services.http_worker_client import HttpWorkerError
        from apps.pipeline.tasks import dispatch_broken_link_scan

        try:
            payload = dispatch_broken_link_scan(job_id=str(uuid.uuid4()))
            return Response(payload, status=status.HTTP_202_ACCEPTED)
        except HttpWorkerError as exc:
            return Response(
                {
                    "detail": (
                        "The broken-link scan could not start because the C# worker lane is unavailable. "
                        "The system did not silently fall back to Celery."
                    ),
                    "error": str(exc),
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

    @action(detail=False, methods=["get"], url_path="export-csv")
    def export_csv(self, request) -> StreamingHttpResponse:
        queryset = self.filter_queryset(self.get_queryset())

        class Echo:
            def write(self, value: str) -> str:
                return value

        writer = csv.writer(Echo())

        def _rows():
            yield writer.writerow(
                [
                    "broken_link_id",
                    "source_content_id",
                    "source_content_title",
                    "source_content_url",
                    "url",
                    "http_status",
                    "redirect_url",
                    "status",
                    "notes",
                    "first_detected_at",
                    "last_checked_at",
                ]
            )
            for record in queryset.iterator(chunk_size=250):
                yield writer.writerow(
                    [
                        str(record.broken_link_id),
                        record.source_content_id,
                        record.source_content.title,
                        record.source_content.url,
                        record.url,
                        record.http_status,
                        record.redirect_url,
                        record.status,
                        record.notes,
                        _isoformat(record.first_detected_at),
                        _isoformat(record.last_checked_at),
                    ]
                )

        response = StreamingHttpResponse(_rows(), content_type="text/csv")
        response["Content-Disposition"] = (
            f'attachment; filename="broken-links-{datetime.utcnow().strftime("%Y%m%d-%H%M%S")}.csv"'
        )
        return response


def _isoformat(value: datetime | None) -> str:
    return value.isoformat() if value else ""
