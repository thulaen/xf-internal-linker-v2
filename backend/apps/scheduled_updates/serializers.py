"""DRF serialisers for the Scheduled Updates API (PR-B.5)."""

from __future__ import annotations

from rest_framework import serializers

from .models import JobAlert, ScheduledJob


class ScheduledJobSerializer(serializers.ModelSerializer):
    """Summary payload for list + detail endpoints.

    Read-only — state transitions happen through the explicit
    pause/resume/cancel/run-now actions, never a generic PATCH.
    """

    class Meta:
        model = ScheduledJob
        fields = (
            "id",
            "key",
            "display_name",
            "priority",
            "state",
            "progress_pct",
            "current_message",
            "started_at",
            "finished_at",
            "last_run_at",
            "last_success_at",
            "scheduled_for",
            "cadence_seconds",
            "duration_estimate_sec",
            "pause_token",
            "log_tail",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class JobAlertSerializer(serializers.ModelSerializer):
    is_active = serializers.BooleanField(read_only=True)

    class Meta:
        model = JobAlert
        fields = (
            "id",
            "job_key",
            "alert_type",
            "calendar_date",
            "message",
            "first_raised_at",
            "last_seen_at",
            "acknowledged_at",
            "resolved_at",
            "is_active",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields
