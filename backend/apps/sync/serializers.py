from rest_framework import serializers
from .models import SyncJob, WebhookReceipt


class SyncJobSerializer(serializers.ModelSerializer):
    class Meta:
        model = SyncJob
        fields = [
            "job_id",
            "status",
            "source",
            "mode",
            "file_name",
            "file_path",
            "progress",
            "message",
            "items_synced",
            "items_updated",
            "ml_items_queued",
            "ml_items_completed",
            "spacy_items_completed",
            "embedding_items_completed",
            "error_message",
            "checkpoint_stage",
            "checkpoint_last_item_id",
            "checkpoint_items_processed",
            "is_resumable",
            "started_at",
            "completed_at",
            "created_at",
        ]
        read_only_fields = fields


class WebhookReceiptSerializer(serializers.ModelSerializer):
    class Meta:
        model = WebhookReceipt
        fields = [
            "receipt_id",
            "source",
            "event_type",
            "payload",
            "status",
            "error_message",
            "sync_job",
            "created_at",
        ]
        read_only_fields = fields
