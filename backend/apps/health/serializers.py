from rest_framework import serializers
from .models import ServiceHealthRecord

class ServiceHealthRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = ServiceHealthRecord
        fields = [
            'service_key',
            'service_name',
            'service_description',
            'status',
            'status_label',
            'last_check_at',
            'last_success_at',
            'last_error_at',
            'last_error_message',
            'issue_description',
            'suggested_fix',
            'metadata',
        ]
        read_only_fields = fields
