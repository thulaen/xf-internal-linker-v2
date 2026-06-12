"""HTTP views for the retired Go sidecars (snapshots + bulletins).

The Go sidecars host (snapshotd + bullboard) was retired on 2026-06-11
(ADR 0007 — Python + Rust only). Nothing ever created snapshots or
published bulletins from the Python side, so both stores were always
empty. These endpoints stay because the frontend service
(frontend/src/app/error-log/sidecars-data.service.ts) calls them and
already renders the "unavailable" empty state; they now return that
degraded response directly instead of attempting a gRPC call first.

  GET /api/sidecars/snapshots/?issue_id=<int>
  GET /api/sidecars/bulletins/?event_type=<str>&min_severity=<str>&limit=<int>

If a Python-native snapshot or bulletin store is ever built, these are
the endpoints to wire it into.
"""

from __future__ import annotations

from django.http import JsonResponse
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated

_RETIRED_RESPONSE = {"status": "sidecars_unavailable", "items": []}


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def list_snapshots(request) -> JsonResponse:
    """GET /api/sidecars/snapshots/ — always the degraded empty response."""
    return JsonResponse(dict(_RETIRED_RESPONSE))


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def list_bulletins(request) -> JsonResponse:
    """GET /api/sidecars/bulletins/ — always the degraded empty response."""
    return JsonResponse(dict(_RETIRED_RESPONSE))
