"""
Notifications models — OperatorAlert and AlertDeliveryAttempt.

OperatorAlert is the canonical persisted alert row.
AlertDeliveryAttempt logs per-channel delivery for debugging.
"""

import uuid

from django.db import models

from apps.audit.models import ErrorLog
from apps.core.models import TimestampedModel


class OperatorAlert(TimestampedModel):
    """
    Persisted operator-facing alert.

    Every important background event (job completion, failure, model state,
    GSC spike) becomes an OperatorAlert row. Alerts survive page refreshes
    and can fan out to in-app bell, toast, desktop popup, and sound.

    Repeated events are deduped via dedupe_key — same key inside the cooldown
    window increments occurrence_count instead of creating a new row.
    """

    # ── Severity ─────────────────────────────────────────────────────
    SEVERITY_INFO = "info"
    SEVERITY_SUCCESS = "success"
    SEVERITY_WARNING = "warning"
    SEVERITY_ERROR = "error"
    SEVERITY_URGENT = "urgent"

    SEVERITY_CHOICES = [
        (SEVERITY_INFO, "Info"),
        (SEVERITY_SUCCESS, "Success"),
        (SEVERITY_WARNING, "Warning"),
        (SEVERITY_ERROR, "Error"),
        (SEVERITY_URGENT, "Urgent"),
    ]

    # ── Status ────────────────────────────────────────────────────────
    STATUS_UNREAD = "unread"
    STATUS_READ = "read"
    STATUS_ACKNOWLEDGED = "acknowledged"
    STATUS_RESOLVED = "resolved"

    STATUS_CHOICES = [
        (STATUS_UNREAD, "Unread"),
        (STATUS_READ, "Read"),
        (STATUS_ACKNOWLEDGED, "Acknowledged"),
        (STATUS_RESOLVED, "Resolved"),
    ]

    # ── Source areas ──────────────────────────────────────────────────
    AREA_JOBS = "jobs"
    AREA_PIPELINE = "pipeline"
    AREA_MODELS = "models"
    AREA_ANALYTICS = "analytics"
    AREA_SYSTEM = "system"

    SOURCE_AREA_CHOICES = [
        (AREA_JOBS, "Jobs"),
        (AREA_PIPELINE, "Pipeline"),
        (AREA_MODELS, "Models"),
        (AREA_ANALYTICS, "Analytics"),
        (AREA_SYSTEM, "System"),
    ]

    # ── Fields ────────────────────────────────────────────────────────
    alert_id = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        db_index=True,
        help_text="Public-safe UUID for this alert.",
    )
    event_type = models.CharField(
        max_length=80,
        db_index=True,
        help_text=(
            "Stable event type string, e.g. job.failed, model.ready, "
            "analytics.gsc_spike."
        ),
    )
    source_area = models.CharField(
        max_length=30,
        choices=SOURCE_AREA_CHOICES,
        default=AREA_SYSTEM,
        db_index=True,
        help_text="High-level area that produced this alert.",
    )
    severity = models.CharField(
        max_length=20,
        choices=SEVERITY_CHOICES,
        default=SEVERITY_INFO,
        db_index=True,
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_UNREAD,
        db_index=True,
    )
    title = models.CharField(
        max_length=200,
        help_text="Short plain-English alert title shown in the bell center.",
    )
    message = models.TextField(
        help_text="Plain-English body text with more detail.",
    )
    dedupe_key = models.CharField(
        max_length=200,
        db_index=True,
        help_text=(
            "Deduplication key. Same key inside cooldown window increments "
            "occurrence_count instead of creating a new row."
        ),
    )
    fingerprint = models.CharField(
        max_length=200,
        blank=True,
        help_text="Optional secondary fingerprint for fine-grained deduping.",
    )
    occurrence_count = models.PositiveIntegerField(
        default=1,
        help_text="How many times this same event has fired in the current window.",
    )
    related_object_type = models.CharField(
        max_length=80,
        blank=True,
        help_text="Model type of the related object, e.g. 'PipelineRun'.",
    )
    related_object_id = models.CharField(
        max_length=100,
        blank=True,
        help_text="PK of the related object.",
    )
    related_route = models.CharField(
        max_length=200,
        blank=True,
        help_text="Frontend route the operator should open, e.g. /jobs or /analytics.",
    )
    payload = models.JSONField(
        default=dict,
        help_text="Extra event-specific data.",
    )
    error_log = models.ForeignKey(
        ErrorLog,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="operator_alerts",
        help_text="Linked ErrorLog row when this alert was raised by a job failure.",
    )
    first_seen_at = models.DateTimeField(
        help_text="When this event was first observed.",
    )
    last_seen_at = models.DateTimeField(
        help_text="When this event was most recently observed (updated on dedupe).",
    )
    read_at = models.DateTimeField(null=True, blank=True)
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Operator Alert"
        verbose_name_plural = "Operator Alerts"
        ordering = ["-first_seen_at"]
        indexes = [
            models.Index(fields=["status", "-first_seen_at"]),
            models.Index(fields=["severity", "status"]),
            models.Index(fields=["dedupe_key", "-last_seen_at"]),
        ]

    def __str__(self) -> str:
        return f"[{self.severity.upper()}] {self.title} ({self.status})"


class AlertDeliveryAttempt(models.Model):
    """
    Per-channel delivery log for an OperatorAlert.

    Tracks whether the in-app, toast, desktop, or sound channel fired,
    was skipped, was blocked (e.g. permission denied), or failed.
    Useful for debugging silent alerts and desktop-permission issues.
    """

    CHANNEL_IN_APP = "in_app"
    CHANNEL_TOAST = "toast"
    CHANNEL_DESKTOP = "desktop"
    CHANNEL_SOUND = "sound"

    CHANNEL_CHOICES = [
        (CHANNEL_IN_APP, "In-app bell"),
        (CHANNEL_TOAST, "Toast / snackbar"),
        (CHANNEL_DESKTOP, "Desktop popup"),
        (CHANNEL_SOUND, "Sound cue"),
    ]

    RESULT_SENT = "sent"
    RESULT_SKIPPED = "skipped"
    RESULT_BLOCKED = "blocked"
    RESULT_FAILED = "failed"

    RESULT_CHOICES = [
        (RESULT_SENT, "Sent"),
        (RESULT_SKIPPED, "Skipped"),
        (RESULT_BLOCKED, "Blocked"),
        (RESULT_FAILED, "Failed"),
    ]

    alert = models.ForeignKey(
        OperatorAlert,
        on_delete=models.CASCADE,
        related_name="delivery_attempts",
    )
    channel = models.CharField(max_length=20, choices=CHANNEL_CHOICES, db_index=True)
    result = models.CharField(max_length=20, choices=RESULT_CHOICES, db_index=True)
    reason = models.TextField(blank=True, help_text="Why the delivery was skipped, blocked, or failed.")
    attempted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Alert Delivery Attempt"
        verbose_name_plural = "Alert Delivery Attempts"
        ordering = ["-attempted_at"]

    def __str__(self) -> str:
        return f"{self.alert} → {self.channel}: {self.result}"
