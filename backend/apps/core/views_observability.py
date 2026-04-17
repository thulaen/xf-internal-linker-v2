"""
Phase OB / Gaps 130 + 131 + 132 — Observability REST views.

  - Gap 130 ``GET /api/rum/summary/``
        Aggregates ``audit.WebVital`` rows into p50/p75/p95 per metric
        + per route for the last 24h. Powers the Real User Monitoring
        dashboard card.
  - Gap 131 ``GET /api/feature-flags/``
        Returns the effective flag set for the requesting user.
  - Gap 132 ``POST /api/feature-flags/exposures/``
        Records "user saw variant X" so the analytics layer can
        correlate flag exposure with downstream outcomes.

Rate-limited per :doc:`PYTHON-RULES` §9.7 — all three endpoints share
the project-wide throttle classes.
"""

from __future__ import annotations

import statistics
from collections import defaultdict
from datetime import timedelta
from typing import Any

from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle, UserRateThrottle
from rest_framework.views import APIView

from .feature_flags import FeatureFlag, FeatureFlagExposure, serialise_for_user


class RumSummaryView(APIView):
    """GET /api/rum/summary/

    Real User Monitoring roll-up for the last 24h. Returns:

    ::

        {
          "window_hours": 24,
          "metrics": {
            "LCP":  { "p50": 1800, "p75": 2300, "p95": 3900, "n": 142 },
            "INP":  { "p50":  120, "p75":  190, "p95":  420, "n": 138 },
            ...
          },
          "routes": {
            "/dashboard": {
              "LCP": { "p75": 1900 },
              ...
            }
          }
        }
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        # Local import to keep app boot cheap + avoid circular imports.
        from apps.audit.models import WebVital

        cutoff = timezone.now() - timedelta(hours=24)
        qs = WebVital.objects.filter(created_at__gte=cutoff).values_list(
            "name", "path", "value"
        )

        metrics: dict[str, list[float]] = defaultdict(list)
        by_route: dict[str, dict[str, list[float]]] = defaultdict(
            lambda: defaultdict(list)
        )
        for name, path, value in qs.iterator():
            metrics[name].append(value)
            by_route[path or "/"][name].append(value)

        def _stats(values: list[float]) -> dict[str, float | int]:
            if not values:
                return {"p50": 0, "p75": 0, "p95": 0, "n": 0}
            sorted_vals = sorted(values)
            n = len(sorted_vals)
            return {
                "p50": _percentile(sorted_vals, 50),
                "p75": _percentile(sorted_vals, 75),
                "p95": _percentile(sorted_vals, 95),
                "n": n,
            }

        return Response(
            {
                "window_hours": 24,
                "metrics": {name: _stats(values) for name, values in metrics.items()},
                "routes": {
                    path: {name: _stats(values) for name, values in by_metric.items()}
                    for path, by_metric in by_route.items()
                },
            }
        )


class FeatureFlagsListView(APIView):
    """GET /api/feature-flags/

    Returns the effective flag set for the requesting user. Anonymous
    requests get only 100%-rollout flags.
    """

    permission_classes = [AllowAny]
    throttle_classes = [AnonRateThrottle, UserRateThrottle]

    def head(self, request):
        # Used by the frontend's HEAD probe (and the passkey feature
        # gate pattern in Gap 95). Responds 204 so clients can detect
        # "endpoint exists" without fetching the list.
        return Response(status=status.HTTP_204_NO_CONTENT)

    def get(self, request):
        user_id = request.user.pk if getattr(request.user, "is_authenticated", False) else None
        return Response(serialise_for_user(user_id))


class FeatureFlagExposureView(APIView):
    """POST /api/feature-flags/exposures/

    Records a "user saw flag X in variant Y" event. Payload::

        { "key": "cta-copy", "variant": "new-cta" }
    """

    permission_classes = [AllowAny]
    throttle_classes = [AnonRateThrottle, UserRateThrottle]

    def post(self, request):
        key = (request.data.get("key") or "").strip()
        variant = (request.data.get("variant") or "").strip()
        if not key:
            return Response(
                {"detail": "key is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        # Guard against bogus keys silently filling the table — must
        # match an existing flag.
        if not FeatureFlag.objects.filter(key=key).exists():
            return Response(
                {"detail": "unknown flag"},
                status=status.HTTP_404_NOT_FOUND,
            )
        user = request.user if getattr(request.user, "is_authenticated", False) else None
        FeatureFlagExposure.objects.create(key=key, variant=variant[:60], user=user)
        return Response({"status": "recorded"}, status=status.HTTP_201_CREATED)


# ── helpers ────────────────────────────────────────────────────────────


def _percentile(sorted_vals: list[float], pct: float) -> float:
    """Linear-interpolation percentile. Input must already be sorted."""
    if not sorted_vals:
        return 0.0
    k = (len(sorted_vals) - 1) * (pct / 100.0)
    f = int(k)
    c = min(f + 1, len(sorted_vals) - 1)
    if f == c:
        return float(sorted_vals[f])
    return float(sorted_vals[f] + (sorted_vals[c] - sorted_vals[f]) * (k - f))


__all__ = [
    "RumSummaryView",
    "FeatureFlagsListView",
    "FeatureFlagExposureView",
]
