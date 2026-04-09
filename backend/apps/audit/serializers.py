"""Serializers for the audit trail and reviewer scorecards."""

from rest_framework import serializers

from .models import AuditEntry, ErrorLog, ReviewerScorecard


class AuditEntrySerializer(serializers.ModelSerializer):
    class Meta:
        model = AuditEntry
        fields = [
            "id",
            "action",
            "target_type",
            "target_id",
            "detail",
            "ip_address",
            "created_at",
        ]
        read_only_fields = fields


class ReviewerScorecardSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReviewerScorecard
        fields = [
            "id",
            "period_start",
            "period_end",
            "total_reviewed",
            "approved_count",
            "rejected_count",
            "approval_rate",
            "verified_rate",
            "stale_rate",
            "avg_review_time_seconds",
            "top_rejection_reasons",
            "created_at",
        ]
        read_only_fields = fields


class ErrorLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = ErrorLog
        fields = [
            "id",
            "job_type",
            "step",
            "error_message",
            "raw_exception",
            "why",
            "acknowledged",
            "created_at",
        ]
        read_only_fields = [
            "id",
            "job_type",
            "step",
            "error_message",
            "raw_exception",
            "why",
            "created_at",
        ]
