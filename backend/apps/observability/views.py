from __future__ import annotations

from django.conf import settings
from django.http import HttpResponse
from rest_framework import status, views
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.observability.api import CONTENT_TYPE_LATEST, METRICS_TOKEN_HEADER, generate_latest, get_registry
from apps.observability.services.stack_status import build_stack_status


class MetricsView(views.APIView):
    authentication_classes = []
    permission_classes = []

    def get(self, request):
        expected = getattr(settings, "METRICS_TOKEN", "")
        supplied = request.META.get(METRICS_TOKEN_HEADER, "")
        if expected and supplied != expected:
            return Response({"detail": "Metrics token is missing or wrong."}, status=403)
        body = generate_latest(get_registry())
        return HttpResponse(body, content_type=CONTENT_TYPE_LATEST)


class ObservabilityStackView(views.APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response({"services": build_stack_status()})
