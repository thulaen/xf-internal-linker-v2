"""DRF serializers for AutoIssue rows."""

from __future__ import annotations

from rest_framework import serializers

from .models import AutoIssue


class AutoIssueSerializer(serializers.ModelSerializer):
    """Read-only shape for the /api/auto-issues/ endpoint.

    Exposes `lessons_learned` so the frontend (and agents reading via
    HTTP) see what prior fixes taught us about each area.
    """

    class Meta:
        model = AutoIssue
        fields = (
            "id",
            "source",
            "external_id",
            "fingerprint",
            "canonical_fingerprint",
            "title",
            "description",
            "affected_files",
            "severity",
            "status",
            "priority_score",
            "occurrence_count",
            "first_seen",
            "last_seen",
            "resolved_at",
            "resolved_by",
            "fix_commit_sha",
            "lessons_learned",
            "source_observations",
        )
        read_only_fields = fields
