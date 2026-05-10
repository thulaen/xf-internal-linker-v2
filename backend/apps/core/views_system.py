"""
System monitoring, audits, and performance certification views extracted from ``views_capacity.py``.
Part of the domain-driven decomposition to stay under the 1500-line cap.
"""

from __future__ import annotations

import logging
from dataclasses import asdict

from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.api.query_params import coerce_int
from apps.api.throttles import (
    CompressionAuditRunThrottle,
    PerformanceCertRunThrottle,
)

logger = logging.getLogger(__name__)


class BudgetForecastView(APIView):
    """GET /api/system/budget-forecast/ — pre-flight estimator."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        from apps.core.services.budget_forecaster import (
            forecast,
            get_registered_tasks,
        )

        task_name = request.query_params.get("task", "")
        if not task_name:
            return Response(
                {
                    "detail": "?task=<task_name> is required",
                    "available_tasks": get_registered_tasks(),
                },
                status=400,
            )

        kwargs: dict = {}
        for k, v in request.query_params.items():
            if k in {"task", "safety_margin_pct"}:
                continue
            kwargs[k] = v

        margin = (
            coerce_int(
                request.query_params.get("safety_margin_pct"),
                default=-1,
                min_value=0,
                max_value=200,
            )
            if request.query_params.get("safety_margin_pct")
            else None
        )
        if margin is not None and margin < 0:
            margin = None

        result = forecast(
            task_name=task_name,
            kwargs=kwargs,
            safety_margin_pct=margin,
        )
        return Response(asdict(result))


class BudgetForecastTasksView(APIView):
    """GET /api/system/budget-forecast/tasks/"""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        from apps.core.services.budget_forecaster import get_registered_tasks
        return Response({"tasks": get_registered_tasks()})


class CachePolicySummaryView(APIView):
    """GET /api/system/cache-policy/"""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        from apps.core.services.cache_policy import summarise_all_layers
        return Response({"layers": [asdict(s) for s in summarise_all_layers()]})


class CachePolicyPinView(APIView):
    """POST/DELETE /api/system/cache-policy/<layer>/pin/"""

    permission_classes = [IsAuthenticated]

    def post(self, request, layer: str):
        from apps.core.services.cache_policy import pin_key
        key = (request.data.get("key") or "").strip()
        if not key:
            return Response({"detail": "Body must include 'key'."}, status=400)
        pin_key(layer, key)
        return Response({"layer": layer, "key": key, "pinned": True})

    def delete(self, request, layer: str):
        from apps.core.services.cache_policy import unpin_key
        key = (request.data.get("key") or "").strip()
        if not key:
            return Response({"detail": "Body must include 'key'."}, status=400)
        unpin_key(layer, key)
        return Response({"layer": layer, "key": key, "pinned": False})


class CachePolicyEvictView(APIView):
    """POST /api/system/cache-policy/<layer>/evict/"""

    permission_classes = [IsAuthenticated]

    def post(self, request, layer: str):
        from apps.core.services.cache_policy import evict_on_demand
        key = (request.data.get("key") or "").strip() or None
        result = evict_on_demand(layer, key=key)
        return Response({"layer": layer, **result})


class CompressionAuditView(APIView):
    """GET /api/system/compression-audit/"""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        from apps.core.services.compression_audit import get_last_compression_audit

        report = get_last_compression_audit()
        if report is None:
            return Response(
                {
                    "run_at_iso": "",
                    "sample_size": 0,
                    "candidates": [],
                    "total_estimated_savings_bytes": 0,
                    "total_estimated_savings_mb": 0,
                    "note": "No compression audit has run yet.",
                }
            )
        payload = asdict(report)
        for c in payload["candidates"]:
            c["columns"] = list(c["columns"])
        payload["total_estimated_savings_mb"] = int(
            report.total_estimated_savings_bytes // (1024 * 1024)
        )
        return Response(payload)


class CompressionAuditRunView(APIView):
    """POST /api/system/compression-audit/run/"""

    permission_classes = [IsAdminUser]
    throttle_classes = [CompressionAuditRunThrottle]

    def post(self, request):
        from apps.core.services.compression_audit import run_compression_audit
        report = run_compression_audit()
        payload = asdict(report)
        for c in payload["candidates"]:
            c["columns"] = list(c["columns"])
        payload["total_estimated_savings_mb"] = int(
            report.total_estimated_savings_bytes // (1024 * 1024)
        )
        return Response(payload)


class PerformanceCertView(APIView):
    """GET /api/system/performance-cert/"""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        from apps.core.services.performance_certification import (
            get_last_certification,
        )

        verdict = get_last_certification()
        if verdict is None:
            return Response(
                {
                    "run_at_iso": "",
                    "verdict": "unknown",
                    "label": "No performance certification has run yet.",
                    "benchmark_run_id": None,
                    "benchmark_run_started_at_iso": "",
                    "areas": [],
                    "note": "",
                }
            )
        return Response(asdict(verdict))


class PerformanceCertRunView(APIView):
    """POST /api/system/performance-cert/run/"""

    permission_classes = [IsAdminUser]
    throttle_classes = [PerformanceCertRunThrottle]

    def post(self, request):
        from apps.core.services.performance_certification import (
            run_performance_certification,
        )
        verdict = run_performance_certification()
        return Response(asdict(verdict))


class CppFallbackStatusView(APIView):
    """GET /api/system/cpp-fallback/"""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        from apps.core.services.cpp_fallback_warning import (
            format_dashboard_banner,
            get_current_fallback_status,
        )

        snap = get_current_fallback_status()
        payload = asdict(snap)
        payload["banner"] = format_dashboard_banner()
        return Response(payload)
