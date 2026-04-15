"""
Dry-run sync preview endpoint (plan item 24).

Wraps ``apps.pipeline.services.dry_run_sampler.run_preview`` in a DRF view so
the Jobs page can ask "what would a sync do?" without committing.

The actual sampling logic lives in the sampler module — this view is just
argument parsing + error fencing.
"""

from __future__ import annotations

import logging

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

logger = logging.getLogger(__name__)


class SyncPreviewView(APIView):
    """POST /api/sync/preview/ — dry-run sampler (plan item 24).

    Request body:
        {"source": "api" | "wp", "mode": "full" | "delta", "sample_size": 10}

    Response mirrors ``run_preview``; see that function for the shape.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        from apps.pipeline.services.dry_run_sampler import run_preview

        data = request.data or {}
        source = str(data.get("source", "api")).lower()
        mode = str(data.get("mode", "full")).lower()
        sample_size = int(data.get("sample_size") or 10)

        if source not in ("api", "wp"):
            return Response(
                {"ok": False, "error": "source must be 'api' or 'wp'"},
                status=400,
            )

        try:
            result = run_preview(source=source, mode=mode, sample_size=sample_size)
            return Response(result)
        except Exception:
            logger.exception("dry-run preview failed")
            return Response(
                {"ok": False, "error": "internal"},
                status=500,
            )
