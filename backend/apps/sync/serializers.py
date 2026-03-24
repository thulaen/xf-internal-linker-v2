from rest_framework import serializers
from .models import SyncJob

class SyncJobSerializer(serializers.ModelSerializer):
    class Meta:
        model = SyncJob
        fields = [
            'job_id', 'status', 'source', 'mode', 'file_name',
            'progress', 'message', 'items_synced', 'items_updated',
            'error_message', 'started_at', 'completed_at', 'created_at'
        ]
        read_only_fields = fields
