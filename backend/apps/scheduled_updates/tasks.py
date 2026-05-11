"""Celery tasks owned by the Scheduled Updates orchestrator.

Only thin wrappers live here — the real logic is in ``runner``,
``alerts``, etc. Keeping them separate lets Celery beat reference them
by dotted path (``scheduled_updates.prune_resolved_alerts``) without
sucking in runner imports at module-load time.
"""

from __future__ import annotations

import logging

from celery import shared_task
from django.db import connection

from apps.core.helpers import HelperConstraint

from .alerts import detect_stalled_jobs, prune_resolved_alerts

# Import the runner module so its @shared_task (run_next_scheduled_job)
# registers with the Celery app at autodiscovery time. Celery's
# autodiscover_tasks() only walks <app>.tasks, so runner.py would
# otherwise never load until the first HTTP request hit the API.
from . import runner  # noqa: F401

logger = logging.getLogger(__name__)


@shared_task(name="scheduled_updates.prune_resolved_alerts")
@HelperConstraint(
    cpu_intensive=False,
    gpu_required=False,
    storage_writes_to="postgres_main",
    ram_peak_mb=256,
)
def prune_resolved_alerts_task() -> dict:
    # Mandatory Prevention Sweep (#86): close stale connections before task logic.
    connection.close()

    """Nightly-ish task: delete resolved JobAlert rows past the 30-day cutoff."""
    deleted = prune_resolved_alerts()
    return {"deleted": deleted}


@shared_task(name="scheduled_updates.detect_stalled_jobs")
@HelperConstraint(
    cpu_intensive=False,
    gpu_required=False,
    storage_writes_to="postgres_main",
    ram_peak_mb=256,
)
def detect_stalled_jobs_task() -> dict:
    # Mandatory Prevention Sweep (#86): close stale connections before task logic.
    connection.close()

    """Raise STALLED alerts for long-running ScheduledJobs (≥ 4 h).

    Scheduled independently so it keeps running even during hours when
    the main runner is idle — a stuck job that started yesterday inside
    the window but never finished should still flag today.
    """
    stalled = detect_stalled_jobs()
    return {"stalled_count": len(stalled), "keys": [j.key for j in stalled]}
