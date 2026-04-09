"""Serializers for the notifications app."""

from rest_framework import serializers

from .models import AlertDeliveryAttempt, OperatorAlert


class AlertDeliveryAttemptSerializer(serializers.ModelSerializer):
    class Meta:
        model = AlertDeliveryAttempt
        fields = ["id", "channel", "result", "reason", "attempted_at"]


class OperatorAlertSerializer(serializers.ModelSerializer):
    delivery_attempts = AlertDeliveryAttemptSerializer(many=True, read_only=True)
    error_log_id = serializers.PrimaryKeyRelatedField(
        source="error_log", read_only=True
    )

    class Meta:
        model = OperatorAlert
        fields = [
            "id",
            "alert_id",
            "event_type",
            "source_area",
            "severity",
            "status",
            "title",
            "message",
            "dedupe_key",
            "occurrence_count",
            "related_object_type",
            "related_object_id",
            "related_route",
            "payload",
            "error_log_id",
            "first_seen_at",
            "last_seen_at",
            "read_at",
            "acknowledged_at",
            "resolved_at",
            "created_at",
            "updated_at",
            "delivery_attempts",
        ]
        read_only_fields = fields
