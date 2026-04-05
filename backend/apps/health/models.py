"""
Health models — ServiceHealthRecord stores the latest check results.
"""

from django.db import models
from apps.core.models import TimestampedModel


class ServiceHealthRecord(TimestampedModel):
    """
    Stores the most recent health check result per service.

    Keyed by service_key (e.g. 'ga4', 'gsc', 'xenforo', 'celery').
    Each check updates the existing row rather than appending a history log.
    """

    # ── Status Choice Constants ──────────────────────────────────────
    STATUS_HEALTHY = "healthy"
    STATUS_WARNING = "warning"
    STATUS_ERROR = "error"
    STATUS_DOWN = "down"
    STATUS_STALE = "stale"
    STATUS_NOT_CONFIGURED = "not_configured"
    STATUS_NOT_ENABLED = "not_enabled"

    STATUS_CHOICES = [
        (STATUS_HEALTHY, "Healthy"),
        (STATUS_WARNING, "Warning"),
        (STATUS_ERROR, "Error"),
        (STATUS_DOWN, "Down"),
        (STATUS_STALE, "Stale"),
        (STATUS_NOT_CONFIGURED, "Not Configured"),
        (STATUS_NOT_ENABLED, "Not Enabled"),
    ]

    service_key = models.CharField(
        max_length=80,
        unique=True,
        db_index=True,
        help_text="Unique stable key for the monitored service.",
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_HEALTHY,
        db_index=True,
    )
    status_label = models.CharField(
        max_length=200,
        help_text="Short plain-English summary of current status.",
    )
    last_check_at = models.DateTimeField(
        help_text="When the last attempt was made to check this service.",
    )
    last_success_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the service was last confirmed as healthy.",
    )
    last_error_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the last failure occurred.",
    )
    last_error_message = models.TextField(
        blank=True,
        help_text="Technical error details from the last failed attempt.",
    )
    metadata = models.JSONField(
        default=dict,
        help_text="Service-specific metrics (e.g. lag hours, row counts, ping latency).",
    )

    class Meta:
        verbose_name = "Service Health Record"
        verbose_name_plural = "Service Health Records"
        ordering = ["service_key"]

    def __str__(self) -> str:
        return f"{self.service_key}: {self.status}"
