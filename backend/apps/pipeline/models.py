"""
Pipeline models — full field definitions added in Phase 1.
Stage 10: JobLease model for ownership tracking.
"""

from django.db import models

from apps.core.models import TimestampedModel  # noqa: F401


class JobLease(TimestampedModel):
    """Ownership lease for active tasks.

    Prevents dual control — only one worker can own a task at a time.
    Expired heartbeats → status='resumable', safe for reassignment.

    See docs/PERFORMANCE.md §10 for the multi-node architecture.
    """

    STATUS_CHOICES = [
        ("active", "Active"),
        ("completed", "Completed"),
        ("expired", "Expired"),
        ("resumable", "Resumable"),
    ]

    task_id = models.CharField(
        max_length=255,
        db_index=True,
        help_text="Celery task ID or unique job identifier.",
    )
    task_type = models.CharField(
        max_length=50,
        help_text="Type of task: sync, pipeline, embeddings, broken_link_scan, etc.",
    )
    owner = models.CharField(
        max_length=200,
        help_text="Worker name or helper node name that owns this task.",
    )
    acquired_at = models.DateTimeField(
        help_text="When this lease was acquired.",
    )
    last_heartbeat = models.DateTimeField(
        help_text="Last time the owner confirmed it is still working on this task.",
    )
    expires_at = models.DateTimeField(
        db_index=True,
        help_text="If no heartbeat arrives by this time, the lease is considered expired.",
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="active",
        db_index=True,
    )

    class Meta:
        verbose_name = "Job Lease"
        verbose_name_plural = "Job Leases"
        ordering = ["-acquired_at"]

    def __str__(self) -> str:
        return f"Lease {self.task_id[:12]} → {self.owner} ({self.status})"
