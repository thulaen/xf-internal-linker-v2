"""
Audit models — full audit trail, reviewer scorecards, and error log.

Every significant action in the app is logged to AuditEntry.
This provides a complete history of who approved what, and when.
"""

from django.db import models


class AuditEntry(models.Model):
    """
    Immutable log of every significant action taken in the application.

    Covers suggestion reviews, setting changes, plugin toggles, and more.
    Records are never deleted — they form a permanent audit trail.
    """

    ACTION_CHOICES = [
        ("approve", "Approved suggestion"),
        ("reject", "Rejected suggestion"),
        ("apply", "Marked as applied"),
        ("verify", "Verified live link"),
        ("edit_anchor", "Edited anchor text"),
        ("mark_stale", "Marked as stale"),
        ("supersede", "Superseded"),
        ("note", "Note added"),
        ("setting_change", "Setting changed"),
        ("plugin_toggle", "Plugin enabled/disabled"),
        ("pipeline_start", "Pipeline run started"),
        ("pipeline_complete", "Pipeline run completed"),
        ("sync_start", "Sync started"),
        ("sync_complete", "Sync completed"),
    ]

    action = models.CharField(
        max_length=30,
        choices=ACTION_CHOICES,
        db_index=True,
        help_text="What type of action was taken.",
    )
    target_type = models.CharField(
        max_length=50,
        help_text="The model/entity type affected, e.g. 'suggestion', 'setting', 'plugin'.",
    )
    target_id = models.CharField(
        max_length=100,
        help_text="The primary key of the affected record.",
    )
    detail = models.JSONField(
        default=dict,
        help_text="Extra context: previous value, new value, reason, etc.",
    )
    ip_address = models.GenericIPAddressField(
        null=True,
        blank=True,
        help_text="IP address of the user who took this action.",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
        help_text="When this action was recorded.",
    )

    class Meta:
        verbose_name = "Audit Entry"
        verbose_name_plural = "Audit Trail"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["target_type", "target_id"]),
            models.Index(fields=["action", "-created_at"]),
        ]

    def __str__(self) -> str:
        return (
            f"[{self.action}] {self.target_type}:{self.target_id} at {self.created_at}"
        )


class ReviewerScorecard(models.Model):
    """
    Aggregated reviewer performance metrics for a time period.

    Calculated periodically (e.g. weekly) to show how the reviewer
    is performing: approval rate, how many applied links stayed live, etc.
    """

    period_start = models.DateField(
        help_text="Start date of the reporting period.",
    )
    period_end = models.DateField(
        help_text="End date of the reporting period.",
    )
    total_reviewed = models.IntegerField(
        default=0,
        help_text="Total suggestions reviewed in this period.",
    )
    approved_count = models.IntegerField(
        default=0,
        help_text="Number of suggestions approved.",
    )
    rejected_count = models.IntegerField(
        default=0,
        help_text="Number of suggestions rejected.",
    )
    approval_rate = models.FloatField(
        default=0.0,
        help_text="Percentage of reviewed suggestions that were approved.",
    )
    verified_rate = models.FloatField(
        default=0.0,
        help_text="Percentage of approved suggestions later verified as live.",
    )
    stale_rate = models.FloatField(
        default=0.0,
        help_text="Percentage of approved suggestions that went stale.",
    )
    avg_review_time_seconds = models.FloatField(
        null=True,
        blank=True,
        help_text="Average seconds per suggestion review decision.",
    )
    top_rejection_reasons = models.JSONField(
        default=list,
        help_text="Top rejection reason codes and their counts for this period.",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When this scorecard was generated.",
    )

    class Meta:
        verbose_name = "Reviewer Scorecard"
        verbose_name_plural = "Reviewer Scorecards"
        ordering = ["-period_end"]

    def __str__(self) -> str:
        return f"Scorecard {self.period_start} → {self.period_end} ({self.total_reviewed} reviewed)"


class ErrorLog(models.Model):
    """
    Centralized error log for background job failures.

    Errors from Celery tasks (import, embed, pipeline, sync) are written here
    so the user can see what went wrong without needing to read Docker logs.
    """

    job_type = models.CharField(
        max_length=50,
        db_index=True,
        help_text="Type of job that failed, e.g. 'import', 'embed', 'pipeline', 'sync'.",
    )
    step = models.CharField(
        max_length=100,
        help_text="The specific step or function where the error occurred.",
    )
    error_message = models.TextField(
        help_text="Human-readable error message.",
    )
    raw_exception = models.TextField(
        blank=True,
        help_text="Full Python traceback (for debugging).",
    )
    why = models.TextField(
        blank=True,
        help_text="Plain-English explanation of what likely caused this error.",
    )
    acknowledged = models.BooleanField(
        default=False,
        db_index=True,
        help_text="True once the user has reviewed and dismissed this error.",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
        help_text="When this error was recorded.",
    )

    class Meta:
        verbose_name = "Error Log Entry"
        verbose_name_plural = "Error Log"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["acknowledged", "-created_at"]),
        ]

    def __str__(self) -> str:
        return f"[{self.job_type}:{self.step}] {self.error_message[:80]}"
