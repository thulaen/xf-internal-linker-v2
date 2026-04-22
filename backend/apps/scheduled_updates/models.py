"""Models for the Scheduled Updates orchestrator.

Two models:

- ``ScheduledJob`` — one row per registered refresh job. Holds the
  lifecycle state (pending / running / paused / completed / failed /
  missed), progress snapshot, and a short log tail.
- ``JobAlert`` — deduped missed-job / failed / stalled alerts. The
  ``UNIQUE(job_key, alert_type, calendar_date)`` constraint is what
  prevents alert spam — one row per (job, day, type), period.

Both tables are lightweight. The orchestrator prunes resolved alerts
after 30 days via the ``jobalert_dedup_cleanup`` nightly task.
"""

from __future__ import annotations

from django.db import models

from apps.core.models import TimestampedModel


# ── States ────────────────────────────────────────────────────────────────

JOB_STATE_PENDING = "pending"
JOB_STATE_RUNNING = "running"
JOB_STATE_PAUSED = "paused"
JOB_STATE_COMPLETED = "completed"
JOB_STATE_FAILED = "failed"
JOB_STATE_MISSED = "missed"

JOB_STATE_CHOICES: tuple[tuple[str, str], ...] = (
    (JOB_STATE_PENDING, "Pending"),
    (JOB_STATE_RUNNING, "Running"),
    (JOB_STATE_PAUSED, "Paused"),
    (JOB_STATE_COMPLETED, "Completed"),
    (JOB_STATE_FAILED, "Failed"),
    (JOB_STATE_MISSED, "Missed"),
)

#: States that the runner considers "finished" — safe to start the next
#: queued job without interrupting anything. Paused is deliberately NOT
#: terminal (the job owns the runner slot until resumed or cancelled).
TERMINAL_JOB_STATES: frozenset[str] = frozenset(
    {JOB_STATE_COMPLETED, JOB_STATE_FAILED, JOB_STATE_MISSED}
)


# ── Priorities ────────────────────────────────────────────────────────────

JOB_PRIORITY_CRITICAL = "critical"
JOB_PRIORITY_HIGH = "high"
JOB_PRIORITY_MEDIUM = "medium"
JOB_PRIORITY_LOW = "low"

JOB_PRIORITY_CHOICES: tuple[tuple[str, str], ...] = (
    (JOB_PRIORITY_CRITICAL, "Critical"),
    (JOB_PRIORITY_HIGH, "High"),
    (JOB_PRIORITY_MEDIUM, "Medium"),
    (JOB_PRIORITY_LOW, "Low"),
)

#: Priority sort key — lower number runs first. The runner orders
#: pending jobs by this and then by scheduled_for.
PRIORITY_SORT_KEY: dict[str, int] = {
    JOB_PRIORITY_CRITICAL: 0,
    JOB_PRIORITY_HIGH: 1,
    JOB_PRIORITY_MEDIUM: 2,
    JOB_PRIORITY_LOW: 3,
}


# ── Alert types ───────────────────────────────────────────────────────────

ALERT_TYPE_MISSED = "missed"
ALERT_TYPE_FAILED = "failed"
ALERT_TYPE_STALLED = "stalled"

ALERT_TYPE_CHOICES: tuple[tuple[str, str], ...] = (
    (ALERT_TYPE_MISSED, "Missed"),
    (ALERT_TYPE_FAILED, "Failed"),
    (ALERT_TYPE_STALLED, "Stalled"),
)


# ── Models ────────────────────────────────────────────────────────────────


class ScheduledJob(TimestampedModel):
    """One row per registered refresh job."""

    key = models.CharField(
        max_length=128,
        unique=True,
        help_text=(
            "Stable identifier for this job, e.g. 'pagerank_refresh' or "
            "'lda_topic_refresh'. Code looks the job up by this key."
        ),
    )
    display_name = models.CharField(
        max_length=160,
        help_text="Human-readable label shown in the Scheduled Updates tab.",
    )
    priority = models.CharField(
        max_length=16,
        choices=JOB_PRIORITY_CHOICES,
        default=JOB_PRIORITY_MEDIUM,
        help_text="Runner orders pending jobs by this.",
    )
    state = models.CharField(
        max_length=16,
        choices=JOB_STATE_CHOICES,
        default=JOB_STATE_PENDING,
        db_index=True,
    )
    progress_pct = models.FloatField(
        default=0.0,
        help_text="0-100. Set by job code via report_progress().",
    )
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    #: Estimated duration, seconds. Used by the window guard to refuse
    #: a job that would overflow the 23:00 cutoff.
    duration_estimate_sec = models.IntegerField(default=60)
    last_run_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the job last *started*, regardless of outcome.",
    )
    last_success_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the job last *completed successfully*. Null until first success.",
    )
    scheduled_for = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
        help_text=(
            "When the job's next run is planned. The runner uses this plus "
            "the priority to decide what to start next. Null = on-demand only."
        ),
    )
    cadence_seconds = models.IntegerField(
        default=86400,
        help_text=(
            "Expected gap between successful runs. The catch-up detector "
            "flags the job as missed when now - last_success_at exceeds this."
        ),
    )
    #: When True, the runner should stop at the next report_progress()
    #: checkpoint and transition the job to paused. Set via the
    #: pause API; cleared by resume.
    pause_token = models.BooleanField(default=False)
    log_tail = models.TextField(
        blank=True,
        default="",
        help_text="Last ~4 KB of output. Truncated in save().",
    )
    current_message = models.CharField(
        max_length=240,
        blank=True,
        default="",
        help_text="Short status string the UI shows next to the progress bar.",
    )

    #: Max log_tail length. Anything beyond this is truncated with a
    #: leading "...[truncated]\n" marker so the tail stays readable.
    LOG_TAIL_MAX_CHARS: int = 4000

    class Meta:
        verbose_name = "Scheduled job"
        verbose_name_plural = "Scheduled jobs"
        indexes = [
            models.Index(fields=["state", "priority"]),
            models.Index(fields=["scheduled_for"]),
            models.Index(fields=["last_success_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.key} [{self.state}]"

    def save(self, *args, **kwargs) -> None:
        if self.log_tail and len(self.log_tail) > self.LOG_TAIL_MAX_CHARS:
            overflow = len(self.log_tail) - self.LOG_TAIL_MAX_CHARS
            # Keep the TAIL (most recent output), drop the head.
            self.log_tail = (
                "...[truncated " + str(overflow) + " chars]\n"
                + self.log_tail[-(self.LOG_TAIL_MAX_CHARS - 80):]
            )
        super().save(*args, **kwargs)


class JobAlert(TimestampedModel):
    """Deduped alert for a ScheduledJob.

    The ``UNIQUE(job_key, alert_type, calendar_date)`` constraint is the
    whole point of this model — raise_alert() uses ``update_or_create``
    so a job that keeps missing its window emits exactly one alert row
    per calendar day, not thousands.
    """

    #: Store the job key (not an FK) so alerts survive a ScheduledJob
    #: rename or accidental deletion. The UI looks up the related job
    #: by key on render.
    job_key = models.CharField(max_length=128, db_index=True)
    alert_type = models.CharField(
        max_length=16,
        choices=ALERT_TYPE_CHOICES,
        db_index=True,
    )
    calendar_date = models.DateField(
        db_index=True,
        help_text="The local-time date the alert refers to (missed window, failure day, etc.).",
    )
    first_raised_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(auto_now=True)
    acknowledged_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Set when an operator clicks the ✕ in the UI. Hides from active list.",
    )
    resolved_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=(
            "Set automatically when the job's next successful run completes. "
            "Resolved alerts drop out of the active list and are pruned after "
            "30 days by jobalert_dedup_cleanup."
        ),
    )
    message = models.CharField(max_length=400, blank=True, default="")

    class Meta:
        verbose_name = "Job alert"
        verbose_name_plural = "Job alerts"
        constraints = [
            models.UniqueConstraint(
                fields=["job_key", "alert_type", "calendar_date"],
                name="unique_job_alert_per_day",
            ),
        ]
        indexes = [
            models.Index(fields=["acknowledged_at", "resolved_at"]),
            models.Index(fields=["job_key", "alert_type"]),
        ]

    def __str__(self) -> str:
        status = (
            "resolved"
            if self.resolved_at
            else "acknowledged"
            if self.acknowledged_at
            else "active"
        )
        return (
            f"{self.job_key} / {self.alert_type} / "
            f"{self.calendar_date.isoformat()} [{status}]"
        )

    @property
    def is_active(self) -> bool:
        """True when this alert should show in the dashboard badge count."""
        return self.acknowledged_at is None and self.resolved_at is None
