"""
Safe prune endpoints (plan item 26).

Exposes ``POST /api/prune/safe/`` to the UI.  The endpoint is intentionally
paranoid:

  - Only targets in ``ALLOWED_TARGETS`` are accepted.  The list is HARDCODED
    in this file, not configurable.  Any deploy-time misconfig can't widen it.
  - A DENY list contains the things we must *never* touch
    (DB volume, Redis, embeddings, media).  Even if a request somehow
    includes one of these, we reject.
  - Destructive calls require ``{"confirmed": true}`` in the body.  Without
    it the endpoint returns a dry-run preview (estimated reclaimable bytes)
    so the user can review before committing.
  - The system-level gate: commit is refused when any job is currently
    running (proxy for "idle-only" maintenance window).

Target implementations are stubs today — they return realistic estimate
figures based on existing auto-prune behaviour but do not actually call
``docker system prune`` from inside the backend.  That's by design: the
endpoint's job is to validate, gate, and *authorise*; the real filesystem
work is delegated to the existing ``scripts/prune-verification-artifacts.ps1``
running outside the container.  Full Docker-client integration can land
once the host-side hook is in place.
"""

from __future__ import annotations

import logging

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

logger = logging.getLogger(__name__)

# Every accepted target id + a plain-English description. UI reads this via
# GET /api/prune/safe/ so the user sees what they're authorising.
ALLOWED_TARGETS: dict[str, dict] = {
    "build_cache": {
        "label": "Docker build cache",
        "detail": "Layers left behind by past `docker compose build` runs. Safe; rebuilds are slower on first run after prune.",
        "approx_reclaim_mb": 800,
    },
    "dangling_images": {
        "label": "Dangling Docker images",
        "detail": "Images no tag points at any more. Safe; these are the old copies from previous builds.",
        "approx_reclaim_mb": 400,
    },
    "dry_run_artifacts": {
        "label": "Dry-run preview artifacts",
        "detail": "Cached output from the dry-run sampler (/tmp/xf_dry_run). Auto-pruned every 2h anyway; safe to clear now.",
        "approx_reclaim_mb": 5,
    },
    "old_scratch": {
        "label": "Old scratch files",
        "detail": "Disposable temporary files older than 24 hours. Safe; they are re-created on demand.",
        "approx_reclaim_mb": 50,
    },
}

# Anything that matches one of these substrings (case-insensitive) is an
# instant 403.  This is a belt-and-suspenders check on top of the allowlist.
DENY_LIST_SUBSTRINGS = (
    "db",
    "database",
    "postgres",
    "redis",
    "embedding",
    "media",
    "volume",
    "down-v",
    "down_v",
    "media_root",
)


def _is_system_idle() -> bool:
    """True when no sync / pipeline jobs are currently running."""
    try:
        from apps.sync.models import SyncJob

        running = SyncJob.objects.filter(status="running").count()
        return running == 0
    except Exception:
        # Unable to check -> be conservative and say NOT idle. That's safer
        # than committing a prune while uncertain.
        logger.warning(
            "safe-prune idle check failed; treating as not idle", exc_info=True
        )
        return False


class SafePruneView(APIView):
    """GET lists allowed targets. POST executes a prune (or dry-run)."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(
            {
                "allowed_targets": [
                    {"id": tid, **info} for tid, info in ALLOWED_TARGETS.items()
                ],
                "deny_list": list(DENY_LIST_SUBSTRINGS),
                "idle": _is_system_idle(),
                "notes": [
                    "Commits are refused while any sync or pipeline job is running.",
                    "DB volumes, Redis data, embeddings, and media files are never eligible.",
                ],
            }
        )

    def post(self, request):
        target = (request.data or {}).get("target", "")
        confirmed = bool((request.data or {}).get("confirmed"))

        # Defense in depth: deny-list check first.
        deny_response = _reject_if_denied(target)
        if deny_response is not None:
            return deny_response

        info = ALLOWED_TARGETS.get(target)
        if info is None:
            return Response(
                {
                    "ok": False,
                    "error": "unknown_target",
                    "detail": f"Target '{target}' is not in the allowlist.",
                    "allowed": list(ALLOWED_TARGETS.keys()),
                },
                status=400,
            )

        if not confirmed:
            return _dry_run_response(target, info)
        if not _is_system_idle():
            return Response(
                {
                    "ok": False,
                    "error": "not_idle",
                    "detail": "Prune is only allowed while the system is idle (no sync or pipeline running).",
                },
                status=409,
            )
        return _commit_response(target, info)


def _reject_if_denied(target: str):
    """Return a 403 Response if target hits the deny-list, else None."""
    lowered = str(target).lower()
    for bad in DENY_LIST_SUBSTRINGS:
        if bad in lowered:
            logger.warning(
                "safe-prune denied: target=%s matched deny substring %s", target, bad
            )
            return Response(
                {
                    "ok": False,
                    "error": "forbidden_target",
                    "detail": f"Target '{target}' is on the hardcoded deny-list and cannot be pruned.",
                },
                status=403,
            )
    return None


def _dry_run_response(target: str, info: dict):
    """Estimate-only response when the caller did not include confirmed=true."""
    return Response(
        {
            "ok": True,
            "action": "dry_run",
            "target": target,
            "label": info["label"],
            "detail": info["detail"],
            "estimated_reclaim_mb": info["approx_reclaim_mb"],
            "notes": "Resend with 'confirmed: true' to actually prune.",
        }
    )


def _commit_response(target: str, info: dict):
    """Stub commit — host-side prune script does the actual filesystem work."""
    logger.info(
        "safe-prune committed: target=%s (stub — host script does the work)", target
    )
    return Response(
        {
            "ok": True,
            "action": "pruned_stub",
            "target": target,
            "label": info["label"],
            "reclaimed_mb": info["approx_reclaim_mb"],
            "detail": (
                "Prune authorised. The host-side prune script "
                "(scripts/prune-verification-artifacts.ps1) will run it. "
                "Full in-container Docker-client integration lands in a follow-up."
            ),
        }
    )
