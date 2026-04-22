"""Serial job runner for the Scheduled Updates orchestrator.

A single Celery task (``run_next_scheduled_job``) is the only thing
that ever starts a ScheduledJob. Celery beat fires this task every
5 minutes inside the 13:00-23:00 window. On each tick the runner:

1. Asks ``window.is_within_window()`` — outside the window, exit silently.
2. Picks the highest-priority pending job whose duration_estimate_sec
   would NOT overflow 23:00.
3. Acquires the Redis lock ``scheduled_updates:runner``. If another tick
   already holds it, exits (this is the serialisation guarantee).
4. Looks up the job's Python entrypoint in ``registry.JOB_REGISTRY``.
5. Runs the entrypoint with a ``checkpoint`` callable that persists
   progress, checks ``pause_token``, and raises PauseRequested when the
   operator has asked to pause.
6. Handles three terminal outcomes:
   - normal return → state=completed, last_success_at=now
   - PauseRequested → state=paused (keeps job row intact for resume)
   - any other exception → state=failed, tracetail stored in log_tail
7. Releases the lock either way.

Per the plan: a job that's already running past 23:00 is not interrupted.
The window guard only refuses NEW starts.
"""

from __future__ import annotations

import logging
import traceback
from typing import Optional

import redis
from celery import shared_task
from django.conf import settings
from django.utils import timezone

from .alerts import (
    detect_missed_jobs,
    raise_alert,
    resolve_open_alerts_for_job,
)
from .broadcasts import (
    broadcast_progress,
    broadcast_state_change,
)
from .lock import (
    acquire_runner_lock,
    current_holder,
    release_runner_lock,
)
from .models import (
    ALERT_TYPE_FAILED,
    JOB_STATE_COMPLETED,
    JOB_STATE_FAILED,
    JOB_STATE_PAUSED,
    JOB_STATE_PENDING,
    JOB_STATE_RUNNING,
    PRIORITY_SORT_KEY,
    ScheduledJob,
)
from .registry import JOB_REGISTRY, JobDefinition, PauseRequested
from .window import (
    OVERFLOW_GRACE_SECONDS,
    is_within_window,
    seconds_remaining_in_window,
    would_overflow,
)

logger = logging.getLogger(__name__)


#: Minimum lock TTL — even a 1-second job holds the lock for at least
#: this long so a faster-than-expected finish doesn't leave the lock
#: dangling for dozens of seconds with the release Lua pending.
MIN_LOCK_TTL_SECONDS: int = 60

#: Safety buffer added on top of ``duration_estimate_sec`` when setting
#: the lock TTL. Covers jobs that run modestly over estimate without
#: freeing the lock prematurely.
LOCK_TTL_OVERHEAD_SECONDS: int = 300


# ─────────────────────────────────────────────────────────────────────
# Public helpers (exported for views + tests)
# ─────────────────────────────────────────────────────────────────────


def pick_next_job(*, now=None) -> Optional[ScheduledJob]:
    """Return the highest-priority pending ScheduledJob that fits the window.

    Orders pending jobs by (priority rank, scheduled_for). Skips jobs
    whose duration estimate would overflow the 23:00 cutoff.

    Returns ``None`` when there's nothing runnable right now.
    """
    # Select only pending rows — paused / running / completed / failed
    # / missed are either already in flight or historical.
    pending = ScheduledJob.objects.filter(state=JOB_STATE_PENDING)

    # Priority sort in Python because priority_sort_key is not a DB
    # column. This is a small query (dozens of rows at most) so the
    # cost is negligible.
    candidates = list(pending)
    candidates.sort(
        key=lambda j: (
            PRIORITY_SORT_KEY.get(j.priority, 99),
            j.scheduled_for or timezone.now(),
            j.pk,
        )
    )

    for job in candidates:
        if would_overflow(job.duration_estimate_sec, now=now):
            continue
        return job
    return None


def _redis_client():
    """Return a redis.Redis connected to settings.REDIS_URL.

    Kept behind a function so tests can patch it with a fakeredis client.
    """
    url = getattr(settings, "REDIS_URL", None) or "redis://localhost:6379/0"
    return redis.Redis.from_url(url)


def _make_checkpoint(job: ScheduledJob):
    """Build the ``checkpoint(progress_pct=..., message="")`` callable.

    The callable persists progress to the DB, checks pause_token, and
    raises PauseRequested when the operator has flipped the flag.
    PR-B.4 will extend this to also broadcast over Django Channels.
    """

    def checkpoint(*, progress_pct: float, message: str = "") -> None:
        # Re-fetch pause_token from the DB — the request that flipped
        # it may have happened after the runner started.
        fresh = ScheduledJob.objects.filter(pk=job.pk).values(
            "pause_token",
        ).first()
        if fresh is None:
            # Job row was deleted out from under us. Treat as failure
            # — continuing would be lying to the caller about state.
            raise PauseRequested("job row vanished mid-run")
        if fresh["pause_token"]:
            raise PauseRequested("operator requested pause")

        # Clamp to [0, 100] so a rogue entrypoint can't report 110%.
        pct = max(0.0, min(100.0, float(progress_pct)))
        trimmed_message = (message or "")[:240]

        ScheduledJob.objects.filter(pk=job.pk).update(
            progress_pct=pct,
            current_message=trimmed_message,
        )
        # Keep the in-memory object in sync so entrypoint code reading
        # ``job.progress_pct`` sees the same value we just wrote.
        job.progress_pct = pct
        job.current_message = trimmed_message

        # Best-effort WS fan-out. Helper silently no-ops without Redis.
        broadcast_progress(job.key, pct, trimmed_message)

    return checkpoint


# ─────────────────────────────────────────────────────────────────────
# Execution helpers (not a Celery task — called synchronously from one)
# ─────────────────────────────────────────────────────────────────────


def _execute_job(job: ScheduledJob, definition: JobDefinition) -> str:
    """Run *job* through its entrypoint, returning a terminal state string.

    Transitions the job to RUNNING on entry, then one of {COMPLETED,
    PAUSED, FAILED} on exit. Returns the final state so the runner can
    log it.

    Never raises — catches everything so the Redis lock is always
    released in the caller's ``finally``.
    """
    now = timezone.now()
    ScheduledJob.objects.filter(pk=job.pk).update(
        state=JOB_STATE_RUNNING,
        started_at=now,
        finished_at=None,
        last_run_at=now,
        progress_pct=0.0,
        current_message="Starting…",
    )
    job.refresh_from_db()
    broadcast_state_change(job)

    checkpoint = _make_checkpoint(job)

    try:
        definition.entrypoint(job, checkpoint)
    except PauseRequested as paused:
        logger.info(
            "scheduled_updates: job %s paused — %s",
            job.key,
            paused,
        )
        ScheduledJob.objects.filter(pk=job.pk).update(
            state=JOB_STATE_PAUSED,
            finished_at=None,
            current_message=f"Paused: {str(paused)[:200]}",
        )
        job.refresh_from_db()
        broadcast_state_change(job)
        return JOB_STATE_PAUSED
    except Exception as exc:
        tb = traceback.format_exc()
        logger.exception("scheduled_updates: job %s failed", job.key)
        failure_ts = timezone.now()
        prior = ScheduledJob.objects.filter(pk=job.pk).values(
            "log_tail"
        ).first() or {"log_tail": ""}
        new_tail = (
            (prior["log_tail"] or "")
            + f"\n[FAIL {failure_ts.isoformat()}] {exc.__class__.__name__}: {exc}\n"
            + tb
        )
        ScheduledJob.objects.filter(pk=job.pk).update(
            state=JOB_STATE_FAILED,
            finished_at=failure_ts,
            current_message=f"Failed: {exc.__class__.__name__}: {str(exc)[:160]}",
            log_tail=new_tail[-ScheduledJob.LOG_TAIL_MAX_CHARS :],
        )
        # Surface the failure once per (job, day) via the deduped alert
        # channel; the frontend badge picks it up on its next poll.
        raise_alert(
            job_key=job.key,
            alert_type=ALERT_TYPE_FAILED,
            calendar_date=timezone.localtime(failure_ts).date(),
            message=f"{job.display_name or job.key}: {exc.__class__.__name__}: {str(exc)[:240]}",
        )
        job.refresh_from_db()
        broadcast_state_change(job)
        return JOB_STATE_FAILED

    # Success.
    finish = timezone.now()
    ScheduledJob.objects.filter(pk=job.pk).update(
        state=JOB_STATE_COMPLETED,
        finished_at=finish,
        last_success_at=finish,
        progress_pct=100.0,
        current_message="Completed.",
        pause_token=False,  # clear any stale pause flag
    )
    # Auto-resolve any active alerts the job had accumulated — a clean
    # run after a rough patch silently clears the badge.
    resolve_open_alerts_for_job(job.key, now=finish)
    job.refresh_from_db()
    broadcast_state_change(job)
    return JOB_STATE_COMPLETED


# ─────────────────────────────────────────────────────────────────────
# The single Celery beat entry point
# ─────────────────────────────────────────────────────────────────────


@shared_task(name="scheduled_updates.run_next_scheduled_job")
def run_next_scheduled_job() -> dict:
    """Beat-fired runner — starts at most one ScheduledJob per invocation.

    The returned dict is Celery-result-friendly (JSON-serialisable) so
    operators can follow the runner's decisions via task results.
    """
    # Catch-up sweep — deliberately runs BEFORE the window guard so a
    # job that missed yesterday's window still surfaces as an alert the
    # moment the laptop wakes up, even at 10 am local.
    try:
        missed = detect_missed_jobs()
        if missed:
            logger.info(
                "scheduled_updates: detect_missed_jobs flagged %s job(s)",
                len(missed),
            )
    except Exception:
        logger.exception("scheduled_updates: detect_missed_jobs crashed — continuing")

    if not is_within_window():
        return {"status": "skipped", "reason": "outside_window"}

    job = pick_next_job()
    if job is None:
        return {"status": "idle"}

    definition = JOB_REGISTRY.get(job.key)
    if definition is None:
        # Job row exists but no Python handler is registered. Mark it
        # failed with a clear message so the alert system (PR-B.3) can
        # surface it, otherwise the runner would try again every 5 min.
        msg = (
            f"no entrypoint registered for job key '{job.key}'. "
            f"Check that the app module with its @scheduled_job "
            f"decorator is imported by Django startup."
        )
        logger.error("scheduled_updates: %s", msg)
        ScheduledJob.objects.filter(pk=job.pk).update(
            state=JOB_STATE_FAILED,
            finished_at=timezone.now(),
            current_message=msg[:240],
        )
        return {"status": "skipped", "reason": "unregistered_key", "key": job.key}

    # Lock TTL: cover the estimate + buffer, clamped to both a minimum
    # (so tiny jobs still hold the lock long enough to be visible) and
    # the seconds remaining in the window (so we never hold a lock past
    # 23:00 that would block tomorrow's first tick).
    ttl = max(
        MIN_LOCK_TTL_SECONDS,
        job.duration_estimate_sec
        + LOCK_TTL_OVERHEAD_SECONDS
        + OVERFLOW_GRACE_SECONDS,
    )
    remaining = seconds_remaining_in_window()
    if remaining:
        ttl = min(ttl, remaining + OVERFLOW_GRACE_SECONDS)

    rc = _redis_client()
    token = acquire_runner_lock(rc, ttl_seconds=ttl)
    if token is None:
        holder = current_holder(rc) or "(unknown)"
        return {"status": "busy", "holder": holder}

    try:
        final_state = _execute_job(job, definition)
        return {
            "status": "ran",
            "key": job.key,
            "final_state": final_state,
        }
    finally:
        release_runner_lock(rc, token)
