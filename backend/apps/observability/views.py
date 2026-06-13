from __future__ import annotations

import logging

from django.conf import settings
from django.http import HttpResponse
from rest_framework import views
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.observability.api import CONTENT_TYPE_LATEST, METRICS_TOKEN_HEADER, generate_latest, get_registry
from apps.observability.services.stack_status import build_stack_status

logger = logging.getLogger(__name__)


class MetricsView(views.APIView):
    authentication_classes = []
    permission_classes = []

    def get(self, request):
        expected = getattr(settings, "METRICS_TOKEN", "")
        supplied = request.META.get(METRICS_TOKEN_HEADER, "")
        if expected and supplied != expected:
            return Response({"detail": "Metrics token is missing or wrong."}, status=403)
        # Refresh the data-backed live gauges (system / db latency / queue depth)
        # in THIS web process right before exposition, so the values vmagent
        # scrapes are current. Best-effort: a refresh failure must not break the
        # scrape endpoint.
        try:
            from apps.observability.tasks import refresh_live_gauges

            refresh_live_gauges()
        except Exception:  # noqa: BLE001 - never let a metric refresh break /metrics.
            logger.debug("metrics refresh failed (ignored)", exc_info=True)
        body = generate_latest(get_registry())
        return HttpResponse(body, content_type=CONTENT_TYPE_LATEST)


class ObservabilityStackView(views.APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response({"services": build_stack_status()})


class PrometheusSummaryView(views.APIView):
    """Return a small set of live metric values sourced from VictoriaMetrics.

    Used by the Angular Prometheus tab to show real numbers (request rate,
    p95 latency, error rate, ranking p95, DB connections, queue depth)
    without needing the frontend to talk to VictoriaMetrics directly.

    If VictoriaMetrics is down every metric reports state="unavailable" so
    the UI can show an honest "metrics store is unreachable" message.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        from apps.observability.services.prometheus_summary import get_prometheus_summary
        return Response(get_prometheus_summary())
