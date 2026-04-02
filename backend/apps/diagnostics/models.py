from django.db import models
from apps.core.models import TimestampedModel


class ServiceStatusSnapshot(TimestampedModel):
    """
    Historical snapshot of a service's health.
    """
    SERVICE_CHOICES = [
        ('django', 'Django API'),
        ('postgresql', 'PostgreSQL'),
        ('redis', 'Redis'),
        ('celery_worker', 'Celery Worker'),
        ('celery_beat', 'Celery Beat'),
        ('channels', 'Channels / WebSockets'),
        ('http_worker', 'C# HttpWorker'),
        ('xenforo_sync', 'XenForo Sync'),
        ('wordpress_sync', 'WordPress Sync'),
        ('ga4', 'GA4'),
        ('gsc', 'GSC'),
        ('analytics_app', 'Analytics App'),
        ('r_analytics', 'R Analytics Service'),
        ('r_weight_tuning', 'R Auto-Weight Tuning'),
        ('local_model', 'Local Embedding/Model Runtime'),
        ('matomo', 'Matomo'),
        ('runtime_lanes', 'Runtime Lanes'),
        ('scheduler_lane', 'C# Scheduler Lane'),
        ('native_scoring', 'Native C++ Scoring'),
        ('slate_diversity_runtime', 'Slate Diversity Runtime'),
        ('embedding_specialist', 'Python Embedding Specialist'),
    ]

    STATE_CHOICES = [
        ('healthy', 'Healthy'),
        ('degraded', 'Degraded'),
        ('failed', 'Failed'),
        ('disabled', 'Disabled'),
        ('not_configured', 'Not Configured'),
        ('not_installed', 'Not Installed'),
        ('planned_only', 'Planned Only'),
        ('spec_missing', 'Spec Missing'),
        ('spec_exists_not_implemented', 'Spec Exists but Not Implemented'),
        ('partial_or_conflicting', 'Partial or Conflicting'),
    ]

    service_name = models.CharField(max_length=50, choices=SERVICE_CHOICES, db_index=True)
    state = models.CharField(max_length=30, choices=STATE_CHOICES, default='planned_only')
    explanation = models.TextField(blank=True, help_text="Plain-English explanation of the state.")
    last_check = models.DateTimeField(auto_now=True)
    last_success = models.DateTimeField(null=True, blank=True)
    last_failure = models.DateTimeField(null=True, blank=True)
    next_action_step = models.TextField(blank=True, help_text="User-friendly next step.")
    metadata = models.JSONField(default=dict, blank=True, help_text="Extra data like version, latency, etc.")

    class Meta:
        ordering = ['-last_check']
        verbose_name = "Service Status Snapshot"
        verbose_name_plural = "Service Status Snapshots"

    def __str__(self):
        return f"{self.service_name} - {self.state} at {self.last_check}"


class SystemConflict(TimestampedModel):
    """
    Records detected repo drift, duplication, or spec/code mismatches.
    """
    CONFLICT_TYPE_CHOICES = [
        ('duplication', 'Duplication / Stub Paths'),
        ('mismatch', 'Spec / Code Mismatch'),
        ('placeholder', 'Placeholder UI / API'),
        ('drift', 'Repo Drift'),
    ]

    conflict_type = models.CharField(max_length=30, choices=CONFLICT_TYPE_CHOICES)
    title = models.CharField(max_length=200)
    description = models.TextField()
    severity = models.CharField(max_length=20, default='medium', choices=[
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('critical', 'Critical'),
    ])
    location = models.CharField(max_length=500, help_text="File path or URL where conflict occurs.")
    why = models.TextField(blank=True, help_text="Plain-English explanation of the conflict.")
    next_step = models.TextField(blank=True, help_text="What to do to resolve this.")
    resolved = models.BooleanField(default=False)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "System Conflict"
        verbose_name_plural = "System Conflicts"

    def __str__(self):
        return f"{self.conflict_type}: {self.title}"
