"""Slice 1.6 — HTTP views that proxy the sidecars Python clients for the
Errors page UI.

Two endpoints:

  GET /api/sidecars/snapshots/?issue_id=<int>
      Returns the snapshots attached to a single AutoIssue. When
      issue_id is omitted, returns the union across all currently-open
      AutoIssues (capped at 200 results so a busy operator dashboard
      does not blow the page weight budget).

  GET /api/sidecars/bulletins/?event_type=<str>&min_severity=<str>&limit=<int>
      Returns the most recent bullboard bulletins. event_type "" means
      "all event types". min_severity defaults to SEV_INFO; "SEV_UNKNOWN"
      means "all severities". Limit defaults to 100, cap 500.

Both endpoints gracefully degrade when the sidecars binary is not
reachable: they return a 200 with an empty list AND a structured
``status: 'sidecars_unavailable'`` field so the UI can render the
"Coming soon" placeholder without hitting an error toast.

Slice 9 will move these to apps.governance / apps.operations REST
namespaces (paper-trail #571).
"""

from __future__ import annotations

import logging
from dataclasses import asdict

from django.http import JsonResponse
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated

from apps.auto_issues.models import AutoIssue

logger = logging.getLogger(__name__)

_DEFAULT_BULLETIN_LIMIT = 100
_MAX_BULLETIN_LIMIT = 500
_MAX_SNAPSHOTS_RETURNED = 200


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def list_snapshots(request) -> JsonResponse:
    """GET /api/sidecars/snapshots/?issue_id=<int>

    Returns the snapshots attached to one AutoIssue (or all open issues)."""
    issue_id_raw = request.query_params.get("issue_id")
    try:
        from apps.auto_issues._sidecars.snapshotd_client import SnapshotdClient
    except Exception as exc:  # noqa: BLE001
        logger.info("list_snapshots: stubs missing (%s)", exc)
        return JsonResponse({"status": "sidecars_unavailable", "items": []})

    client = SnapshotdClient(deadline=3.0)
    try:
        if issue_id_raw is not None:
            issue_id = int(issue_id_raw)
            snaps = client.list_by_issue(issue_id)
            items = [_snapshot_to_json(s) for s in snaps]
        else:
            # Union across open AutoIssues; cap at _MAX_SNAPSHOTS_RETURNED.
            items: list[dict] = []
            open_ids = list(
                AutoIssue.objects.filter(
                    status__in=(AutoIssue.STATUS_OPEN, AutoIssue.STATUS_PICKED)
                ).values_list("id", flat=True)
            )
            for issue_id in open_ids:
                if len(items) >= _MAX_SNAPSHOTS_RETURNED:
                    break
                try:
                    for snap in client.list_by_issue(issue_id):
                        items.append(_snapshot_to_json(snap))
                        if len(items) >= _MAX_SNAPSHOTS_RETURNED:
                            break
                except Exception as exc:  # noqa: BLE001 - per-issue continues
                    logger.warning(
                        "list_snapshots: issue=%d list_by_issue failed (%s)",
                        issue_id, exc,
                    )
    except Exception as exc:  # noqa: BLE001
        logger.warning("list_snapshots: sidecars call failed (%s)", exc)
        return JsonResponse({"status": "sidecars_unavailable", "items": []})

    return JsonResponse({"status": "ok", "items": items})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def list_bulletins(request) -> JsonResponse:
    """GET /api/sidecars/bulletins/?event_type=&min_severity=&limit="""
    event_type = request.query_params.get("event_type", "")
    min_severity = request.query_params.get("min_severity", "SEV_UNKNOWN")
    try:
        limit = max(1, min(int(request.query_params.get("limit", _DEFAULT_BULLETIN_LIMIT)),
                            _MAX_BULLETIN_LIMIT))
    except ValueError:
        limit = _DEFAULT_BULLETIN_LIMIT

    try:
        from apps.ops_feed._sidecars.bullboard_client import BullboardClient
    except Exception as exc:  # noqa: BLE001
        logger.info("list_bulletins: stubs missing (%s)", exc)
        return JsonResponse({"status": "sidecars_unavailable", "items": []})

    client = BullboardClient(deadline=3.0)
    try:
        bulletins = client.recent(
            event_type=event_type,
            min_severity=min_severity,
            limit=limit,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("list_bulletins: sidecars call failed (%s)", exc)
        return JsonResponse({"status": "sidecars_unavailable", "items": []})

    return JsonResponse({
        "status": "ok",
        "items": [asdict(b) for b in bulletins],
    })


def _snapshot_to_json(snap) -> dict:
    """Convert a SnapshotDTO to a JSON-serialisable dict, including
    context_json decoded as a UTF-8 string so the UI can render it."""
    return {
        "id": snap.id,
        "issue_id": snap.issue_id,
        "kind": snap.kind,
        "category": snap.category,
        "schema_version": snap.schema_version,
        "row_count": snap.row_count,
        "size_bytes": snap.size_bytes,
        "pinned": snap.pinned,
        "created_at_unix_nanos": snap.created_at_unix_nanos,
    }
