"""Celery tasks owned by the Scheduled Updates orchestrator.

Only thin wrappers live here — the real logic is in ``runner``,
``alerts``, etc. Keeping them separate lets Celery beat reference them
by dotted path (``scheduled_updates.prune_resolved_alerts``) without
sucking in runner imports at module-load time.
"""

from __future__ import annotations

import logging

from celery import shared_task

from .alerts import detect_stalled_jobs, prune_resolved_alerts

logger = logging.getLogger(__name__)


@shared_task(name="scheduled_updates.prune_resolved_alerts")
def prune_resolved_alerts_task() -> dict:
    """Nightly-ish task: delete resolved JobAlert rows past the 30-day cutoff."""
    deleted = prune_resolved_alerts()
    return {"deleted": deleted}


@shared_task(name="scheduled_updates.detect_stalled_jobs")
def detect_stalled_jobs_task() -> dict:
    """Raise STALLED alerts for long-running ScheduledJobs (≥ 4 h).

    Scheduled independently so it keeps running even during hours when
    the main runner is idle — a stuck job that started yesterday inside
    the window but never finished should still flag today.
    """
    stalled = detect_stalled_jobs()
    return {"stalled_count": len(stalled), "keys": [j.key for j in stalled]}
