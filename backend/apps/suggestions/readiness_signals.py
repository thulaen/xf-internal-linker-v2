"""
Phase SR — real-time invalidation of the Suggestion Readiness gate.

Hooks Django signals on the data sources that feed
`readiness.assemble_prerequisites()` and rebroadcasts
`suggestions.readiness` so connected Review / Mission Critical clients
refetch and re-render.

Why signals, not a polling task: operators expect the "Preparing
Suggestions" panel to disappear within a second of the blocker clearing.
Polling at that cadence would pin Redis. `post_save` lets the backend
push the instant the data changes.

We deliberately do NOT push the payload itself — clients refetch so
every viewer sees the same server-rendered dedup result. The broadcast
is just the "nudge".
"""

from __future__ import annotations

import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

logger = logging.getLogger(__name__)

_TOPIC = "suggestions.readiness"
_EVENT = "prereq.changed"


def _notify(source: str) -> None:
    """Fire the realtime broadcast. Safe to call from any sync path.

    Swallows every exception — broadcasting is observability glue, not a
    correctness gate. If Redis is down the next polling refresh (if any)
    or the client's own refresh button will catch the change.
    """
    try:
        from apps.realtime.services import broadcast

        broadcast(_TOPIC, _EVENT, {"source": source})
    except Exception:  # noqa: BLE001
        logger.debug("[readiness] broadcast failed", exc_info=True)


def register() -> None:
    """Wire post_save receivers for every prerequisite source.

    Called from `apps.suggestions.apps.SuggestionsConfig.ready()` — the
    canonical Django app-ready hook. Idempotent: re-registration is a
    no-op because Django stores receivers keyed by dispatch_uid.
    """
    # Late imports — models may not be loaded when this module is imported.
    from apps.core.models import AppSetting

    @receiver(
        post_save,
        sender=AppSetting,
        dispatch_uid="readiness.appsetting_changed",
    )
    def _appsetting_changed(sender, instance, **kwargs):
        # Only nudge on keys that feed the readiness aggregator.
        interesting = {
            "system.last_math_refreshed_at",
            "system.last_attribution_run_at",
            "system.master_pause",
            "enforce_readiness_gate",
        }
        if getattr(instance, "key", "") in interesting:
            _notify(f"appsetting:{instance.key}")

    # Best-effort — some models may not exist on every deployment; wrap
    # so a missing app doesn't block app startup.
    try:
        from apps.audit.models import ErrorLog

        @receiver(
            post_save,
            sender=ErrorLog,
            dispatch_uid="readiness.errorlog_changed",
        )
        def _errorlog_changed(sender, instance, **kwargs):
            # Only nudge on critical severity rows — others don't gate.
            if getattr(instance, "severity", "") == "critical":
                _notify("errorlog:critical")
    except Exception:  # noqa: BLE001
        logger.debug("[readiness] ErrorLog wire skipped", exc_info=True)

    try:
        from apps.suggestions.models import PipelineRun

        @receiver(
            post_save,
            sender=PipelineRun,
            dispatch_uid="readiness.pipelinerun_changed",
        )
        def _pipelinerun_changed(sender, instance, **kwargs):
            state = getattr(instance, "run_state", "")
            if state in ("running", "completed", "failed"):
                _notify(f"pipelinerun:{state}")
    except Exception:  # noqa: BLE001
        logger.debug("[readiness] PipelineRun wire skipped", exc_info=True)


__all__ = ["register"]
