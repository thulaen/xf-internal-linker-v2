from django.db import models
import uuid


class SyncJob(models.Model):
    """
    Tracks the state and progress of a content sync/import operation.
    """

    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("running", "Running"),
        ("paused", "Paused"),  # plan item 27 — graceful user-initiated pause
        ("completed", "Completed"),
        ("failed", "Failed"),
        ("cancelled", "Cancelled"),
    ]

    SOURCE_CHOICES = [
        ("api", "XenForo API"),
        ("jsonl", "JSONL File"),
        ("wp", "WordPress API"),
    ]

    job_id = models.UUIDField(default=uuid.uuid4, primary_key=True, editable=False)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES)
    mode = models.CharField(max_length=20)  # active-import mode (full, titles, quick)

    file_name = models.CharField(max_length=255, blank=True, null=True)
    progress = models.FloatField(default=0.0)
    message = models.CharField(max_length=500, blank=True)

    items_synced = models.IntegerField(default=0)
    items_updated = models.IntegerField(default=0)

    # ML Enrichment (Intelligence) phase
    ml_items_queued = models.IntegerField(default=0)
    ml_items_completed = models.IntegerField(default=0)

    # Granular ML progress
    spacy_items_completed = models.IntegerField(default=0)
    embedding_items_completed = models.IntegerField(default=0)

    error_message = models.TextField(blank=True)

    # Pipeline checkpoint for crash-resilient resume (FR-097).
    # When the pipeline processes content items, it saves the last successfully
    # processed content_item ID here. If the job crashes or the server shuts
    # down, the next run can resume from this checkpoint instead of reprocessing
    # everything from scratch. This avoids duplicate work and saves time.
    checkpoint_stage = models.CharField(
        max_length=50,
        blank=True,
        default="",
        help_text="Pipeline stage when checkpoint was saved (e.g. 'ingest', 'spacy', 'embed', 'pipeline').",
    )
    checkpoint_last_item_id = models.IntegerField(
        null=True,
        blank=True,
        help_text="ID of the last content item successfully processed before interruption.",
    )
    checkpoint_items_processed = models.IntegerField(
        default=0,
        help_text="Total items processed before interruption. Used to calculate remaining work on resume.",
    )
    is_resumable = models.BooleanField(
        default=False,
        help_text="True if this job was interrupted and can be resumed from its checkpoint.",
    )

    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.source} ({self.mode}) - {self.status} - {self.created_at}"


class WebhookReceipt(models.Model):
    """
    Audit log for every incoming webhook attempt from XF or WP.
    """

    receipt_id = models.UUIDField(default=uuid.uuid4, primary_key=True, editable=False)
    source = models.CharField(max_length=20, choices=SyncJob.SOURCE_CHOICES)
    event_type = models.CharField(max_length=100)
    payload = models.JSONField(help_text="Raw payload received from the webhook.")

    status = models.CharField(
        max_length=20, default="received"
    )  # received, processed, ignored, error
    error_message = models.TextField(blank=True)

    # Link to the resulting SyncJob if one was triggered
    sync_job = models.ForeignKey(
        SyncJob,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="webhooks",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Webhook {self.source} {self.event_type} - {self.status} at {self.created_at}"
