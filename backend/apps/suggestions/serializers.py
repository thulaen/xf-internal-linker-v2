"""
Suggestions app DRF serializers.

Serializers for PipelineRun, Suggestion, and PipelineDiagnostic.
The SuggestionReviewSerializer supports partial updates for approve/reject actions.
"""

from rest_framework import serializers

from .models import PipelineDiagnostic, PipelineRun, Suggestion


class PipelineRunSerializer(serializers.ModelSerializer):
    """Serializes pipeline run metadata for the jobs dashboard."""

    duration_display = serializers.SerializerMethodField()

    class Meta:
        model = PipelineRun
        fields = [
            "run_id", "rerun_mode", "run_state",
            "suggestions_created", "destinations_processed", "destinations_skipped",
            "duration_seconds", "duration_display",
            "error_message", "celery_task_id",
            "host_scope", "destination_scope",
            "created_at", "updated_at",
        ]
        read_only_fields = [
            "run_id", "run_state", "suggestions_created",
            "destinations_processed", "destinations_skipped",
            "duration_seconds", "celery_task_id", "error_message",
            "created_at", "updated_at",
        ]

    def get_duration_display(self, obj: PipelineRun) -> str | None:
        if obj.duration_seconds is None:
            return None
        if obj.duration_seconds < 60:
            return f"{obj.duration_seconds:.1f}s"
        m, s = divmod(int(obj.duration_seconds), 60)
        return f"{m}m {s}s"


class SuggestionListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for paginated suggestion list views."""

    destination_url = serializers.CharField(source="destination.url", read_only=True, default="")
    host_title = serializers.CharField(source="host.title", read_only=True, default="")
    destination_silo_group = serializers.IntegerField(source="destination.scope.silo_group_id", read_only=True, allow_null=True)
    destination_silo_group_name = serializers.CharField(source="destination.scope.silo_group.name", read_only=True, default="")
    host_silo_group = serializers.IntegerField(source="host.scope.silo_group_id", read_only=True, allow_null=True)
    host_silo_group_name = serializers.CharField(source="host.scope.silo_group.name", read_only=True, default="")
    same_silo = serializers.SerializerMethodField()

    class Meta:
        model = Suggestion
        fields = [
            "suggestion_id", "status", "score_final",
            "destination", "destination_title", "destination_url",
            "destination_silo_group", "destination_silo_group_name",
            "host", "host_title", "host_sentence_text",
            "host_silo_group", "host_silo_group_name", "same_silo",
            "anchor_phrase", "anchor_confidence", "anchor_edited",
            "repeated_anchor",
            "rejection_reason", "reviewed_at", "is_applied",
            "created_at",
        ]
        read_only_fields = fields

    def get_same_silo(self, obj: Suggestion) -> bool:
        destination_scope = getattr(obj.destination, "scope", None)
        host_scope = getattr(obj.host, "scope", None)
        if destination_scope is None or host_scope is None:
            return False
        if destination_scope.silo_group_id is None or host_scope.silo_group_id is None:
            return False
        return destination_scope.silo_group_id == host_scope.silo_group_id


class SuggestionDetailSerializer(serializers.ModelSerializer):
    """Full serializer for the suggestion review detail view."""

    destination_silo_group = serializers.IntegerField(source="destination.scope.silo_group_id", read_only=True, allow_null=True)
    destination_silo_group_name = serializers.CharField(source="destination.scope.silo_group.name", read_only=True, default="")
    host_silo_group = serializers.IntegerField(source="host.scope.silo_group_id", read_only=True, allow_null=True)
    host_silo_group_name = serializers.CharField(source="host.scope.silo_group.name", read_only=True, default="")
    same_silo = serializers.SerializerMethodField()

    class Meta:
        model = Suggestion
        fields = [
            "suggestion_id", "pipeline_run",
            "status", "score_final",
            "score_semantic", "score_keyword", "score_node_affinity",
            "score_quality", "score_pagerank", "score_velocity",
            "destination", "destination_title",
            "destination_silo_group", "destination_silo_group_name",
            "host", "host_sentence", "host_sentence_text",
            "host_silo_group", "host_silo_group_name", "same_silo",
            "anchor_phrase", "anchor_start", "anchor_end",
            "anchor_confidence", "anchor_edited", "repeated_anchor",
            "rejection_reason", "reviewer_notes", "reviewed_at",
            "is_applied", "applied_at", "verified_at", "stale_reason",
            "superseded_by", "superseded_at",
            "created_at", "updated_at",
        ]

    def get_same_silo(self, obj: Suggestion) -> bool:
        destination_scope = getattr(obj.destination, "scope", None)
        host_scope = getattr(obj.host, "scope", None)
        if destination_scope is None or host_scope is None:
            return False
        if destination_scope.silo_group_id is None or host_scope.silo_group_id is None:
            return False
        return destination_scope.silo_group_id == host_scope.silo_group_id
        read_only_fields = [
            "suggestion_id", "pipeline_run",
            "score_final", "score_semantic", "score_keyword",
            "score_node_affinity", "score_quality", "score_pagerank", "score_velocity",
            "destination", "destination_title",
            "host", "host_sentence", "host_sentence_text",
            "anchor_phrase", "anchor_start", "anchor_end", "anchor_confidence",
            "repeated_anchor",
            "applied_at", "verified_at", "stale_reason",
            "superseded_by", "superseded_at",
            "created_at", "updated_at",
        ]


class SuggestionReviewSerializer(serializers.ModelSerializer):
    """
    Partial-update serializer for reviewer actions.

    Accepts only the fields the reviewer can change:
    status, anchor_edited, rejection_reason, reviewer_notes, is_applied.
    All other fields are read-only.
    """

    class Meta:
        model = Suggestion
        fields = [
            "suggestion_id", "status", "anchor_edited",
            "rejection_reason", "reviewer_notes", "is_applied",
        ]
        read_only_fields = ["suggestion_id"]


class PipelineDiagnosticSerializer(serializers.ModelSerializer):
    """Serializes pipeline skip diagnostics for the why-no-suggestion explorer."""

    destination_title = serializers.CharField(source="destination.title", read_only=True)

    class Meta:
        model = PipelineDiagnostic
        fields = [
            "id", "pipeline_run", "destination", "destination_title",
            "skip_reason", "detail", "created_at",
        ]
        read_only_fields = fields
