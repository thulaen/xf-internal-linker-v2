"""Startup catch-up dispatcher.

Called once via ``@worker_ready.connect`` in ``celery.py``.  Queries each
catch-up-eligible Beat task's ``last_run_at`` and dispatches overdue ones in
priority order with a 30-second stagger between Heavy tasks.

See docs/PERFORMANCE.md §5 for the schedule contract.
"""

from __future__ import annotations

import logging

from django.utils import timezone

from config.catchup_registry import (
    CATCHUP_REGISTRY,
    CatchupEntry,
    _HEAVY_STAGGER_SECONDS,
)

logger = logging.getLogger(__name__)


def _get_overdue_tasks() -> list[tuple[str, CatchupEntry]]:
    """Return (task_name, entry) pairs that are overdue, sorted by priority."""
    from django_celery_beat.models import PeriodicTask

    now = timezone.now()
    overdue: list[tuple[str, CatchupEntry, float]] = []

    for task_name, entry in CATCHUP_REGISTRY.items():
        try:
            periodic = PeriodicTask.objects.filter(name=task_name).first()
        except Exception:
            logger.debug(
                "catch-up: PeriodicTask table not ready, skipping %s", task_name
            )
            continue

        if periodic is None:
            # Task not yet seeded in the DB — skip.
            continue

        last_run = periodic.last_run_at
        if last_run is None:
            # A task that has NEVER run was not "missed while the laptop was
            # off" (this dispatcher's stated purpose) — it is simply new. Firing
            # every never-run task at boot stampedes the queue, and on a fresh or
            # freshly-seeded database that is EVERY task at once. On an
            # unconfigured staging cluster those jobs (which need external
            # settings that are absent) pile up and have taken the single worker
            # down. Let Beat run it at its normal cron time instead; catch-up
            # only rescues tasks that ran before and then fell behind.
            continue
        hours_since = (now - last_run).total_seconds() / 3600

        if hours_since > entry.threshold_hours:
            overdue.append((task_name, entry, hours_since))

    # Sort by priority (lower number = higher priority).
    overdue.sort(key=lambda t: t[1].priority)
    return [(name, entry) for name, entry, _ in overdue]


def _dispatch_task(task_name: str, queue: str, countdown: int = 0) -> bool:
    """Send the Beat task to its Celery queue.  Returns True on success.

    ``countdown`` delays the task's EXECUTION (not its dispatch) by that many
    seconds, so Heavy tasks spread out without the dispatcher blocking the worker
    boot. The message is enqueued immediately; the broker releases it later.
    """
    from django_celery_beat.models import PeriodicTask

    periodic = PeriodicTask.objects.filter(name=task_name).first()
    if periodic is None:
        logger.warning(
            "catch-up: cannot dispatch %s — not in PeriodicTask table", task_name
        )
        return False

    celery_task_name = periodic.task
    kwargs = {}
    if periodic.kwargs:
        import json

        try:
            kwargs = json.loads(periodic.kwargs)
        except (json.JSONDecodeError, TypeError):
            pass

    from config.celery import app

    app.send_task(celery_task_name, kwargs=kwargs, queue=queue, countdown=countdown)
    logger.info(
        "catch-up: dispatched %s → queue=%s (countdown=%ds)",
        task_name, queue, countdown,
    )
    return True


def run_startup_catchup() -> dict[str, str]:
    """Check all registered tasks and dispatch overdue ones.

    Returns a dict mapping task_name → 'dispatched' | 'skipped' | 'error'.
    """
    results: dict[str, str] = {}
    overdue = _get_overdue_tasks()

    if not overdue:
        logger.info("catch-up: no overdue tasks found")
        return results

    logger.info("catch-up: %d overdue task(s) to dispatch", len(overdue))
    # Stagger Heavy tasks to avoid memory spikes — but do it with a per-task
    # EXECUTION countdown, never by sleeping here. This handler runs in the
    # worker's MAIN process during ``worker_ready``; a blocking sleep would stall
    # the boot and starve the broker heartbeat, which can drop the connection and
    # take the worker down. Dispatching with a countdown is non-blocking: the
    # Nth Heavy task simply runs N*stagger seconds later.
    heavy_dispatched = 0

    for task_name, entry in overdue:
        countdown = 0
        if entry.weight_class == "heavy":
            countdown = heavy_dispatched * _HEAVY_STAGGER_SECONDS

        try:
            success = _dispatch_task(task_name, entry.queue, countdown=countdown)
            results[task_name] = "dispatched" if success else "skipped"
            if success and entry.weight_class == "heavy":
                heavy_dispatched += 1
        except Exception:
            logger.exception("catch-up: failed to dispatch %s", task_name)
            results[task_name] = "error"

    # Emit a summary alert.
    dispatched = [k for k, v in results.items() if v == "dispatched"]
    if dispatched:
        try:
            from apps.notifications.services import emit_operator_alert
            from apps.notifications.models import OperatorAlert

            emit_operator_alert(
                event_type="system.catchup_complete",
                severity="info",
                title="Catch-up dispatch complete",
                message=f"Dispatched {len(dispatched)} overdue task(s): {', '.join(dispatched)}",
                source_area=OperatorAlert.AREA_SYSTEM,
                dedupe_key="system.catchup_complete",
            )
        except Exception:
            logger.warning("catch-up: failed to emit summary alert", exc_info=True)

    return results
