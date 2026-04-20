"""
Runbook execution endpoints (plan item 17).

Each runbook step in the frontend library (`shared/runbooks/runbook-library.ts`)
now has a matching safe, idempotent, confirmation-gated backend endpoint.

Safety rules (never violated):
  - No endpoint rebuilds code, recompiles native extensions, or modifies
    ranking logic.
  - No endpoint runs `docker compose down -v` or touches database volumes.
  - Every mutation requires ``{"confirmed": true}`` in the POST body.
  - Every endpoint is idempotent — re-running returns ``already_done`` rather
    than double-acting.

For runbooks whose true enforcement belongs to later plan items (checkpoint
prune at item 19, safe prune at item 26), the endpoint returns a structured
"not-yet-implemented" result so the dialog can surface a plain-English
message to the user.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Callable

from django.core.exceptions import ValidationError
from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Runbook handlers — one per id from shared/runbooks/runbook-library.ts
# --------------------------------------------------------------------------- #


def _recheck_health_services() -> dict:
    """Trigger a fresh health sweep. Pure read + refresh; always safe."""
    try:
        from apps.health.services import run_all_health_checks

        summary = run_all_health_checks()
        return {"ok": True, "action": "rechecked", "summary": summary}
    except Exception as exc:
        logger.warning("recheck-health-services failed: %s", exc)
        return {"ok": False, "action": "error", "detail": str(exc)}


def _clear_stale_alerts() -> dict:
    """Acknowledge read alerts >7 days old, resolve acknowledged >14 days old.

    Idempotent: second run has nothing to act on.
    """
    from apps.notifications.models import OperatorAlert

    now = timezone.now()
    ack_cutoff = now - timedelta(days=7)
    resolve_cutoff = now - timedelta(days=14)

    acknowledged = OperatorAlert.objects.filter(
        status=OperatorAlert.STATUS_READ,
        last_seen_at__lte=ack_cutoff,
    ).update(
        status=OperatorAlert.STATUS_ACKNOWLEDGED,
        acknowledged_at=now,
    )

    resolved = OperatorAlert.objects.filter(
        status=OperatorAlert.STATUS_ACKNOWLEDGED,
        last_seen_at__lte=resolve_cutoff,
    ).update(
        status=OperatorAlert.STATUS_RESOLVED,
        resolved_at=now,
    )

    return {
        "ok": True,
        "action": "cleaned",
        "acknowledged": acknowledged,
        "resolved": resolved,
    }


def _reset_quarantined_job(request) -> dict:
    """Clear the quarantine flag for a specific job and resolve the record.

    Expects ``run_id`` in the POST body so we target a specific item.
    Idempotent: if the item is not quarantined, returns ``already_done``.
    """
    from apps.core.models import QuarantineRecord
    from apps.suggestions.models import PipelineRun

    run_id = (request.data or {}).get("run_id") or ""
    if not run_id:
        return {"ok": False, "action": "error", "detail": "run_id is required"}

    now = timezone.now()
    changed = False

    # Resolve any open QuarantineRecord that points at this run.
    rec_updated = QuarantineRecord.objects.filter(
        related_object_type="pipeline_run",
        related_object_id=run_id,
        resolved_at__isnull=True,
    ).update(
        resolved_at=now,
        resolved_by="runbook:reset-quarantined-job",
        resolved_note="Cleared via runbook. Attempt counter reset; next retry will be fresh.",
    )
    if rec_updated:
        changed = True

    # Clear the legacy boolean. PipelineRun.run_id is a UUID; non-UUID ids
    # (e.g. a test seed or a QuarantineRecord for a different object type)
    # just skip this step silently — the record resolution above still ran.
    try:
        run = PipelineRun.objects.get(run_id=run_id)
        if run.is_quarantined:
            run.is_quarantined = False
            run.save(update_fields=["is_quarantined"])
            changed = True
    except (PipelineRun.DoesNotExist, ValueError, ValidationError):
        pass

    if not changed:
        return {"ok": True, "action": "already_done", "run_id": run_id}

    return {"ok": True, "action": "reset", "run_id": run_id}


def _restart_stuck_pipeline() -> dict:
    """Identify stuck runs (running >30 min with no progress) and mark them as failed.

    Idempotent: a run that's already failed returns ``already_done``.  This
    endpoint does NOT auto-requeue — that stays a user decision.
    """
    from apps.suggestions.models import PipelineRun

    cutoff = timezone.now() - timedelta(minutes=30)
    stuck_qs = PipelineRun.objects.filter(
        run_state="running",
        updated_at__lte=cutoff,
    )
    count = stuck_qs.count()
    if count == 0:
        return {"ok": True, "action": "already_done", "stuck_count": 0}

    updated = stuck_qs.update(run_state="failed")
    return {"ok": True, "action": "unstuck", "stuck_count": updated}


def _prune_docker_artifacts_preview() -> dict:
    """Dry-run only: safe prune enforcement ships in plan item 26.

    Return a clear "preview-only" marker so the dialog can show an honest
    message instead of faking an action.
    """
    return {
        "ok": True,
        "action": "preview_only",
        "detail": "Full safe-prune UI + backend lands in plan item 26. Running this is a no-op today.",
    }


def _retrigger_embedding_for_failed() -> dict:
    """Scaffold: queue re-embedding of items missing embeddings.

    Full implementation depends on plan item 20 (supersede/retention) to avoid
    dropping verified rows.  Return a structured pending marker today.
    """
    from apps.content.models import ContentItem
    from apps.pipeline.services.embeddings import get_current_embedding_filter

    # Count items that look like they need an embedding but don't have one.
    # This is a READ-only count; the actual queueing is deferred to item 20 work.
    total = ContentItem.objects.count()
    missing = total - ContentItem.objects.filter(
        embedding__isnull=False,
        **get_current_embedding_filter(),
    ).count()
    return {
        "ok": True,
        "action": "preview_only",
        "detail": f"{missing} content item(s) are missing embeddings. Re-queueing ships with plan item 20.",
        "missing_count": missing,
    }


# Mapping runbook id -> callable. A value is either zero-arg or takes (request,).
_RUNBOOK_HANDLERS: dict[str, Callable] = {
    "recheck-health-services": _recheck_health_services,
    "clear-stale-alerts": _clear_stale_alerts,
    "reset-quarantined-job": _reset_quarantined_job,
    "restart-stuck-pipeline": _restart_stuck_pipeline,
    "prune-docker-artifacts": _prune_docker_artifacts_preview,
    "retrigger-embedding": _retrigger_embedding_for_failed,
}

# Destructive runbooks always require confirmation; safe ones (dry-run only)
# will accept an unconfirmed POST as a preview.
_DESTRUCTIVE_IDS = {
    "reset-quarantined-job",
    "restart-stuck-pipeline",
    "clear-stale-alerts",
    "retrigger-embedding",
}


class RunbookExecuteView(APIView):
    """POST /api/runbooks/<runbook_id>/execute/ — safe runbook dispatcher.

    Request body:
        {
          "confirmed": true,       # required for destructive runbooks
          "run_id": "...",          # runbook-specific args
          ...
        }

    Response:
        {
          "ok": true,
          "runbook_id": "...",
          "action": "reset" | "unstuck" | "cleaned" | "already_done" | "preview_only" | "error",
          ...  # runbook-specific details
        }
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, runbook_id: str):
        handler = _RUNBOOK_HANDLERS.get(runbook_id)
        if handler is None:
            return Response(
                {
                    "ok": False,
                    "runbook_id": runbook_id,
                    "action": "error",
                    "detail": "Unknown runbook id.",
                },
                status=400,
            )

        confirmed = bool((request.data or {}).get("confirmed"))
        if runbook_id in _DESTRUCTIVE_IDS and not confirmed:
            return Response(
                {
                    "ok": False,
                    "runbook_id": runbook_id,
                    "action": "confirmation_required",
                    "detail": 'This runbook has destructive steps. Re-send with "confirmed": true.',
                },
                status=400,
            )

        # Dispatch. Some handlers need the request for body args; others don't.
        try:
            result = (
                handler(request) if handler.__code__.co_argcount == 1 else handler()
            )
        except Exception as exc:
            logger.exception("Runbook %s failed", runbook_id)
            return Response(
                {
                    "ok": False,
                    "runbook_id": runbook_id,
                    "action": "error",
                    "detail": str(exc),
                },
                status=500,
            )

        return Response({"runbook_id": runbook_id, **result})
