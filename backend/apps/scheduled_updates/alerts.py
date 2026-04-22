"""Missed-job / failed / stalled alerts with deduplication + auto-resolve.

The ``JobAlert`` table's ``UNIQUE(job_key, alert_type, calendar_date)``
constraint means the dedup is enforced by the database, not by code.
This module just wraps ``update_or_create`` so callers don't have to
remember the idiom.

Three entry points a caller wants:

- ``raise_alert(...)`` — upsert an active alert (no dup, refreshes
  ``last_seen_at`` + ``message``).
- ``resolve_open_alerts_for_job(...)`` — called from the runner's
  COMPLETED branch; sweeps any active alerts for the job and sets
  ``resolved_at``, so a successful run silently clears what was
  previously surfacing on the dashboard.
- ``acknowledge(...)`` — called from the API when an operator clicks
  the ✕; sets ``acknowledged_at`` without resolving. An acknowledged
  alert that later hits the resolve path is ALSO resolved, so the
  history tab can distinguish "I saw it and waved it off" from
  "the job self-healed" from "both."

Plus ``detect_missed_jobs()`` which the runner calls at the top of
every beat tick: transitions stale ScheduledJobs into MISSED and
raises one alert per (job, day, missed).
"""

from __future__ import annotations

import datetime as dt
import logging
from typing import Iterable

from django.db import transaction
from django.utils import timezone

from .broadcasts import (
    broadcast_alert_acknowledged,
    broadcast_alert_raised,
    broadcast_alerts_resolved,
)
from .models import (
    ALERT_TYPE_FAILED,
    ALERT_TYPE_MISSED,
    ALERT_TYPE_STALLED,
    JOB_STATE_COMPLETED,
    JOB_STATE_FAILED,
    JOB_STATE_MISSED,
    JOB_STATE_PAUSED,
    JOB_STATE_PENDING,
    JOB_STATE_RUNNING,
    JobAlert,
    ScheduledJob,
)

logger = logging.getLogger(__name__)


#: Resolved alerts older than this are deleted by
#: ``prune_resolved_alerts``.
RESOLVED_ALERT_RETENTION_DAYS: int = 30

#: Running jobs whose ``started_at`` is older than this are considered
#: stalled. Raised as a STALLED alert but state is NOT flipped — the
#: job might still be legitimately running a slow step; the alert just
#: invites the operator to check.
STALLED_JOB_THRESHOLD_SECONDS: int = 4 * 60 * 60  # 4 h


# ─────────────────────────────────────────────────────────────────────
# Raise / resolve / acknowledge
# ─────────────────────────────────────────────────────────────────────


def raise_alert(
    *,
    job_key: str,
    alert_type: str,
    calendar_date: dt.date,
    message: str = "",
) -> tuple[JobAlert, bool]:
    """Upsert an alert row. Returns ``(alert, created)``.

    The ``UNIQUE(job_key, alert_type, calendar_date)`` constraint
    guarantees at most one row per bucket — a second call on the same
    day updates ``last_seen_at`` + ``message`` and returns the existing
    row with ``created=False``.

    Never reactivates an already-resolved alert: if the runner had
    already cleared this bucket (auto-resolve on success), we do
    overwrite ``resolved_at`` back to None to reopen it — the job
    transitioned back into trouble, operator should see it again.
    """
    alert, created = JobAlert.objects.update_or_create(
        job_key=job_key,
        alert_type=alert_type,
        calendar_date=calendar_date,
        defaults={
            "message": (message or "")[:400],
            # Reopen on retrigger: clear resolved_at so the dashboard
            # badge counts this alert again.
            "resolved_at": None,
        },
    )
    # ``reopened`` tells the WS client whether this is a new row or a
    # reopened one — the badge may want to bump attention-getting
    # visuals differently.
    reopened = (not created) and alert.resolved_at is None
    if created:
        logger.info(
            "scheduled_updates.alert RAISE job=%s type=%s date=%s",
            job_key, alert_type, calendar_date,
        )
    else:
        logger.debug(
            "scheduled_updates.alert RETRIGGER job=%s type=%s date=%s",
            job_key, alert_type, calendar_date,
        )
    broadcast_alert_raised(alert, reopened=reopened and not created)
    return alert, created


def resolve_open_alerts_for_job(job_key: str, *, now: dt.datetime | None = None) -> int:
    """Auto-resolve every active alert for *job_key*. Returns the count updated.

    "Active" = ``resolved_at IS NULL``. Acknowledged alerts also get
    ``resolved_at`` set — acknowledged-only had removed them from the
    active list but not from the history tab; resolving properly
    closes the loop.
    """
    ts = now or timezone.now()
    updated = JobAlert.objects.filter(
        job_key=job_key,
        resolved_at__isnull=True,
    ).update(resolved_at=ts)
    if updated:
        logger.info(
            "scheduled_updates.alert RESOLVE job=%s count=%s",
            job_key, updated,
        )
        broadcast_alerts_resolved(job_key, updated)
    return updated


def acknowledge(alert_id: int, *, now: dt.datetime | None = None) -> JobAlert | None:
    """Set ``acknowledged_at`` on the alert. Returns the row or None."""
    try:
        alert = JobAlert.objects.get(pk=alert_id)
    except JobAlert.DoesNotExist:
        return None
    if alert.acknowledged_at is None:
        alert.acknowledged_at = now or timezone.now()
        alert.save(update_fields=["acknowledged_at", "updated_at"])
        broadcast_alert_acknowledged(alert)
    return alert


# ─────────────────────────────────────────────────────────────────────
# Catch-up detection — runs from inside the runner's beat tick
# ─────────────────────────────────────────────────────────────────────


def _calendar_date(ts: dt.datetime) -> dt.date:
    """Return the local calendar date for a timezone-aware datetime."""
    return timezone.localtime(ts).date()


def detect_missed_jobs(*, now: dt.datetime | None = None) -> list[ScheduledJob]:
    """Transition stale ScheduledJobs to MISSED and raise deduped alerts.

    A job is "stale" when:
      - ``state`` is one of pending / completed / failed / missed
        (i.e. NOT currently running or paused — those are in flight)
      - ``cadence_seconds`` is positive (a cadence of 0 means "never
        automatically run", those are triggered on-demand and should
        not flag missed alerts)
      - ``last_success_at`` is either ``None`` or older than
        ``cadence_seconds * 1.5`` — the 1.5× slack lets the runner miss
        one window without crying wolf.

    Returns the list of ScheduledJobs that were transitioned this
    tick. Safe to call frequently — the alert dedup keeps it quiet.
    """
    current = now or timezone.now()
    cutoff_floor = current - dt.timedelta(seconds=1)  # sentinel, replaced below
    transitioned: list[ScheduledJob] = []

    candidates = ScheduledJob.objects.filter(
        cadence_seconds__gt=0,
        state__in=(
            JOB_STATE_PENDING,
            JOB_STATE_COMPLETED,
            JOB_STATE_FAILED,
            JOB_STATE_MISSED,
        ),
    )
    for job in candidates:
        # Per-job cutoff based on its own cadence.
        slack_seconds = int(job.cadence_seconds * 1.5)
        cutoff_floor = current - dt.timedelta(seconds=slack_seconds)
        last_ok = job.last_success_at
        is_stale = (last_ok is None and job.created_at < cutoff_floor) or (
            last_ok is not None and last_ok < cutoff_floor
        )
        if not is_stale:
            continue

        with transaction.atomic():
            # Only flip non-MISSED rows — keep the transition count
            # honest for tests/metrics.
            if job.state != JOB_STATE_MISSED:
                ScheduledJob.objects.filter(pk=job.pk).update(
                    state=JOB_STATE_MISSED,
                    current_message=(
                        f"Missed — last success "
                        f"{last_ok.isoformat() if last_ok else 'never'}"
                    )[:240],
                )
                job.refresh_from_db()
                transitioned.append(job)
            raise_alert(
                job_key=job.key,
                alert_type=ALERT_TYPE_MISSED,
                calendar_date=_calendar_date(current),
                message=(
                    f"{job.display_name or job.key} has not succeeded since "
                    f"{last_ok.isoformat() if last_ok else 'it was first registered'}."
                ),
            )
    return transitioned


def detect_stalled_jobs(*, now: dt.datetime | None = None) -> list[ScheduledJob]:
    """Raise STALLED alerts for jobs that have been RUNNING for too long.

    Does NOT flip the state — a stalled job might still be doing
    useful work (a big LDA training, say). The alert nudges the
    operator to check; they can pause or cancel via the API.
    """
    current = now or timezone.now()
    cutoff = current - dt.timedelta(seconds=STALLED_JOB_THRESHOLD_SECONDS)
    stalled: list[ScheduledJob] = []

    for job in ScheduledJob.objects.filter(
        state=JOB_STATE_RUNNING,
        started_at__lt=cutoff,
    ):
        raise_alert(
            job_key=job.key,
            alert_type=ALERT_TYPE_STALLED,
            calendar_date=_calendar_date(current),
            message=(
                f"{job.display_name or job.key} has been running for more than "
                f"{STALLED_JOB_THRESHOLD_SECONDS // 3600} h "
                f"(started {job.started_at.isoformat() if job.started_at else '?'})."
            ),
        )
        stalled.append(job)
    return stalled


# ─────────────────────────────────────────────────────────────────────
# Nightly prune — kicked off by the beat schedule in B.6
# ─────────────────────────────────────────────────────────────────────


def prune_resolved_alerts(*, now: dt.datetime | None = None) -> int:
    """Delete resolved JobAlert rows older than RESOLVED_ALERT_RETENTION_DAYS."""
    current = now or timezone.now()
    cutoff = current - dt.timedelta(days=RESOLVED_ALERT_RETENTION_DAYS)
    deleted, _details = JobAlert.objects.filter(
        resolved_at__lt=cutoff,
    ).delete()
    if deleted:
        logger.info(
            "scheduled_updates.alert PRUNE deleted=%s cutoff=%s",
            deleted, cutoff.isoformat(),
        )
    return deleted


# ─────────────────────────────────────────────────────────────────────
# Helpers callable from views + tests
# ─────────────────────────────────────────────────────────────────────


def active_alerts_qs():
    """QuerySet of alerts visible on the dashboard (not acked, not resolved)."""
    return JobAlert.objects.filter(
        acknowledged_at__isnull=True,
        resolved_at__isnull=True,
    )


def active_alerts_count() -> int:
    return active_alerts_qs().count()
