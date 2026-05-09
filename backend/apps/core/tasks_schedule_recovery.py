"""Sentient-schedules recovery tick.

Fires every 10 minutes via Celery Beat (see celery_schedules.py
"schedule-tracker-recovery-tick"). Idempotent — running it twice in 10s is
a no-op thanks to the unique constraint on (task_name, scheduled_for) in
the ScheduledTaskRun table.
"""

from __future__ import annotations

import logging

from celery import shared_task

from apps.core.helpers import HelperConstraint

logger = logging.getLogger(__name__)


@shared_task(
    name="core.schedule_tracker_recovery_tick",
    time_limit=180,
    soft_time_limit=120,
)
@HelperConstraint(
    cpu_intensive=False,
    gpu_required=False,
    storage_writes_to="postgres_main",
    ram_peak_mb=256,
)
def schedule_tracker_recovery_tick() -> dict:
    """Run the missed-schedule recovery sweep."""
    from apps.core.services.schedule_tracker import recover_missed_runs

    fired = recover_missed_runs()
    if fired:
        logger.info(
            "schedule_tracker_recovery_tick: dispatched %d missed run(s)", fired
        )
    return {"recovered": fired}
