"""ETA estimation for pipeline and sync tasks.

Queries the last N completed runs and returns the median duration as the
ETA for a new run.  Returns ``None`` when fewer than 3 historical runs
exist (not enough data for a reliable estimate).

For in-progress tasks: ``eta = median_duration - elapsed``.  If negative,
returns a small positive timedelta with the label "finishing soon".

See docs/PERFORMANCE.md §4 for task weight classes and queue definitions.
"""

from __future__ import annotations

import logging
import statistics
from datetime import timedelta

logger = logging.getLogger(__name__)

_MIN_HISTORICAL_RUNS = 3
_HISTORY_WINDOW = 10


def estimate_eta(
    task_name: str,
    *,
    mode: str | None = None,
    elapsed_seconds: float | None = None,
) -> timedelta | None:
    """Estimate remaining time for a task.

    Args:
        task_name: The Beat schedule name or task type to look up.
        mode: Optional run mode filter (e.g. 'full', 'titles').
        elapsed_seconds: If the task is already running, pass how long
            it has been running.  The return value is then
            ``median_duration - elapsed``.

    Returns:
        Estimated remaining time, or None if insufficient history.
    """
    durations = _get_historical_durations(task_name, mode=mode)

    if len(durations) < _MIN_HISTORICAL_RUNS:
        return None

    median_seconds = statistics.median(durations)

    if elapsed_seconds is not None:
        remaining = median_seconds - elapsed_seconds
        if remaining <= 0:
            # Task has already exceeded the median — return a small
            # positive value so the UI can show "finishing soon".
            return timedelta(seconds=30)
        return timedelta(seconds=remaining)

    return timedelta(seconds=median_seconds)


def _get_historical_durations(
    task_name: str,
    *,
    mode: str | None = None,
) -> list[float]:
    """Query completed runs and return their durations in seconds.

    Checks both PipelineRun and SyncJob depending on the task name.
    """
    durations: list[float] = []

    # Try PipelineRun first (covers pipeline.run_pipeline and related).
    if "sync" not in task_name and "import" not in task_name:
        try:
            from apps.suggestions.models import PipelineRun

            qs = PipelineRun.objects.filter(run_state="completed").exclude(
                duration_seconds__isnull=True
            )
            if mode:
                qs = qs.filter(config_snapshot__contains={"mode": mode})
            qs = qs.order_by("-updated_at")[:_HISTORY_WINDOW]
            durations = [
                r.duration_seconds
                for r in qs
                if r.duration_seconds and r.duration_seconds > 0
            ]
        except Exception:
            logger.debug("eta_estimator: PipelineRun query failed", exc_info=True)

    # Try SyncJob (covers sync/import tasks).
    if not durations:
        try:
            from apps.sync.models import SyncJob

            qs = (
                SyncJob.objects.filter(status="completed")
                .exclude(started_at__isnull=True)
                .exclude(completed_at__isnull=True)
            )
            if mode:
                qs = qs.filter(mode=mode)
            qs = qs.order_by("-completed_at")[:_HISTORY_WINDOW]
            for job in qs:
                if job.started_at and job.completed_at:
                    delta = (job.completed_at - job.started_at).total_seconds()
                    if delta > 0:
                        durations.append(delta)
        except Exception:
            logger.debug("eta_estimator: SyncJob query failed", exc_info=True)

    return durations
