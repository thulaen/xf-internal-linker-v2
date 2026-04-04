from django.db import models
import uuid

class SyncJob(models.Model):
    """
    Tracks the state and progress of a content sync/import operation.
    """
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('running', 'Running'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]

    SOURCE_CHOICES = [
        ('api', 'XenForo API'),
        ('jsonl', 'JSONL File'),
        ('wp', 'WordPress API'),
    ]

    job_id = models.UUIDField(default=uuid.uuid4, primary_key=True, editable=False)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
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
    
    error_message = models.TextField(blank=True)
    
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.source} ({self.mode}) - {self.status} - {self.created_at}"
