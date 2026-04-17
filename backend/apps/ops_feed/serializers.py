"""Serializers for the Operations Feed."""

from rest_framework import serializers

from .models import OperationEvent


class OperationEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = OperationEvent
        fields = [
            "id",
            "timestamp",
            "event_type",
            "source",
            "plain_english",
            "severity",
            "related_entity_type",
            "related_entity_id",
            "runtime_context",
            "occurrence_count",
            "error_log_id",
        ]
        read_only_fields = fields
