"""
Suggestions app DRF serializers.

Serializers for PipelineRun, Suggestion, and PipelineDiagnostic.
The SuggestionReviewSerializer supports partial updates for approve/reject actions.
"""

from rest_framework import serializers

from apps.pipeline.services.link_freshness import get_destination_link_freshness_diagnostics

from .models import PipelineDiagnostic, PipelineRun, Suggestion, WeightAdjustmentHistory, WeightPreset
from .telemetry_markup import build_suggestion_telemetry_payload


class WeightPresetSerializer(serializers.ModelSerializer):
    class Meta:
        model = WeightPreset
        fields = ["id", "name", "is_system", "weights", "created_at", "updated_at"]
        read_only_fields = ["id", "is_system", "created_at", "updated_at"]


class WeightAdjustmentHistorySerializer(serializers.ModelSerializer):
    preset_name = serializers.CharField(source="preset.name", read_only=True, allow_null=True)

    class Meta:
        model = WeightAdjustmentHistory
        fields = [
            "id", "source", "preset", "preset_name",
            "previous_weights", "new_weights", "delta",
            "reason", "r_run_id", "created_at",
        ]
        read_only_fields = fields


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
            "host_scope", "destination_scope", "config_snapshot",
            "created_at", "updated_at",
        ]
        read_only_fields = [
            "run_id", "run_state", "suggestions_created",
            "destinations_processed", "destinations_skipped",
            "duration_seconds", "celery_task_id", "error_message", "config_snapshot",
            "created_at", "updated_at",
        ]

    def get_duration_display(self, obj: PipelineRun) -> str | None:
        if obj.duration_seconds is None:
            return None
        if obj.duration_seconds < 60:
            return f"{obj.duration_seconds:.1f}s"
        minutes, seconds = divmod(int(obj.duration_seconds), 60)
        return f"{minutes}m {seconds}s"


class _SuggestionSerializerMixin:
    """Shared computed fields for suggestion serializers."""

    def get_same_silo(self, obj) -> bool:
        destination_scope = getattr(obj.destination, "scope", None)
        host_scope = getattr(obj.host, "scope", None)
        if destination_scope is None or host_scope is None:
            return False
        if destination_scope.silo_group_id is None or host_scope.silo_group_id is None:
            return False
        same_silo = destination_scope.silo_group_id == host_scope.silo_group_id
        setattr(obj, "_same_silo_cached", same_silo)
        return same_silo

    def get_destination_source_label(self, obj) -> str:
        return _content_source_label(getattr(obj.destination, "content_type", ""))

    def get_host_source_label(self, obj) -> str:
        return _content_source_label(getattr(obj.host, "content_type", ""))


class SuggestionListSerializer(_SuggestionSerializerMixin, serializers.ModelSerializer):
    """Lightweight serializer for paginated suggestion list views."""

    destination_url = serializers.CharField(source="destination.url", read_only=True, default="")
    host_title = serializers.CharField(source="host.title", read_only=True, default="")
    destination_content_type = serializers.CharField(source="destination.content_type", read_only=True, default="")
    destination_source_label = serializers.SerializerMethodField()
    host_content_type = serializers.CharField(source="host.content_type", read_only=True, default="")
    host_source_label = serializers.SerializerMethodField()
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
            "destination_content_type", "destination_source_label",
            "destination_silo_group", "destination_silo_group_name",
            "host", "host_title", "host_sentence_text",
            "host_content_type", "host_source_label",
            "host_silo_group", "host_silo_group_name", "same_silo",
            "anchor_phrase", "anchor_confidence", "anchor_edited",
            "repeated_anchor",
            "rejection_reason", "reviewed_at", "is_applied",
            "created_at",
        ]
        read_only_fields = fields


class SuggestionDetailSerializer(_SuggestionSerializerMixin, serializers.ModelSerializer):
    """Full serializer for the suggestion review detail view."""

    destination_url = serializers.CharField(source="destination.url", read_only=True, default="")
    destination_content_type = serializers.CharField(source="destination.content_type", read_only=True, default="")
    destination_source_label = serializers.SerializerMethodField()
    host_title = serializers.CharField(source="host.title", read_only=True, default="")
    host_content_type = serializers.CharField(source="host.content_type", read_only=True, default="")
    host_source_label = serializers.SerializerMethodField()
    destination_silo_group = serializers.IntegerField(source="destination.scope.silo_group_id", read_only=True, allow_null=True)
    destination_silo_group_name = serializers.CharField(source="destination.scope.silo_group.name", read_only=True, default="")
    host_silo_group = serializers.IntegerField(source="host.scope.silo_group_id", read_only=True, allow_null=True)
    host_silo_group_name = serializers.CharField(source="host.scope.silo_group.name", read_only=True, default="")
    same_silo = serializers.SerializerMethodField()
    link_freshness_diagnostics = serializers.SerializerMethodField()
    telemetry_instrumentation = serializers.SerializerMethodField()

    class Meta:
        model = Suggestion
        fields = [
            "suggestion_id", "pipeline_run",
            "status", "score_final",
            "score_semantic", "score_keyword", "score_node_affinity",
            "score_quality", "score_march_2026_pagerank", "score_velocity", "score_link_freshness", "score_ga4_gsc",
            "score_phrase_relevance", "score_learned_anchor_corroboration", "score_rare_term_propagation",
            "score_field_aware_relevance", "score_click_distance", "score_explore_exploit",
            "score_cluster_suppression", "score_slate_diversity",
            "destination", "destination_title", "destination_url",
            "destination_content_type", "destination_source_label",
            "destination_silo_group", "destination_silo_group_name",
            "host", "host_title", "host_sentence", "host_sentence_text",
            "host_content_type", "host_source_label",
            "host_silo_group", "host_silo_group_name", "same_silo",
            "anchor_phrase", "anchor_start", "anchor_end",
            "anchor_confidence", "anchor_edited", "repeated_anchor",
            "rejection_reason", "reviewer_notes", "reviewed_at",
            "is_applied", "applied_at", "verified_at", "stale_reason",
            "superseded_by", "superseded_at",
            "phrase_match_diagnostics", "learned_anchor_diagnostics", "rare_term_diagnostics",
            "field_aware_diagnostics", "click_distance_diagnostics",
            "explore_exploit_diagnostics", "cluster_diagnostics",
            "slate_diversity_diagnostics",
            "link_freshness_diagnostics",
            "telemetry_instrumentation",
            "created_at", "updated_at",
        ]
        read_only_fields = [
            "suggestion_id", "pipeline_run",
            "score_final", "score_semantic", "score_keyword",
            "score_node_affinity", "score_quality", "score_march_2026_pagerank", "score_velocity", "score_link_freshness", "score_ga4_gsc",
            "score_phrase_relevance", "score_learned_anchor_corroboration", "score_rare_term_propagation",
            "score_field_aware_relevance", "score_click_distance", "score_explore_exploit",
            "score_cluster_suppression", "score_slate_diversity",
            "destination", "destination_title", "destination_url",
            "destination_content_type", "destination_source_label",
            "destination_silo_group", "destination_silo_group_name",
            "host", "host_title", "host_sentence", "host_sentence_text",
            "host_content_type", "host_source_label",
            "host_silo_group", "host_silo_group_name", "same_silo",
            "anchor_phrase", "anchor_start", "anchor_end", "anchor_confidence",
            "repeated_anchor",
            "applied_at", "verified_at", "stale_reason",
            "superseded_by", "superseded_at",
            "phrase_match_diagnostics", "learned_anchor_diagnostics", "rare_term_diagnostics",
            "field_aware_diagnostics", "click_distance_diagnostics",
            "explore_exploit_diagnostics", "cluster_diagnostics",
            "slate_diversity_diagnostics",
            "link_freshness_diagnostics",
            "telemetry_instrumentation",
            "created_at", "updated_at",
        ]

    def get_link_freshness_diagnostics(self, obj: Suggestion) -> dict[str, object]:
        return get_destination_link_freshness_diagnostics(obj.destination_id).as_dict()

    def get_telemetry_instrumentation(self, obj: Suggestion) -> dict[str, object]:
        return build_suggestion_telemetry_payload(obj)

class SuggestionReviewSerializer(serializers.ModelSerializer):
    """
    Partial-update serializer for reviewer actions.

    Accepts only the fields the reviewer can change:
    status, anchor_edited, rejection_reason, reviewer_notes, is_applied.
    All other fields are read-only.
    """

    VALID_TRANSITIONS = {
        "pending": {"approved", "rejected"},
        "approved": {"applied", "rejected"},
        "rejected": {"approved"},
        "applied": set(),
        "verified": set(),
        "stale": set(),
        "superseded": set(),
    }

    class Meta:
        model = Suggestion
        fields = [
            "suggestion_id", "status", "anchor_edited",
            "rejection_reason", "reviewer_notes", "is_applied",
        ]
        read_only_fields = ["suggestion_id"]

    def validate(self, attrs):
        if self.instance and "status" in attrs:
            current = self.instance.status
            requested = attrs["status"]
            allowed = self.VALID_TRANSITIONS.get(current, set())
            if requested not in allowed:
                from rest_framework.exceptions import ValidationError

                raise ValidationError(
                    {"status": f"Cannot transition from '{current}' to '{requested}'."}
                )
        return attrs


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


def _content_source_label(content_type: str) -> str:
    if content_type.startswith("wp_"):
        return "WordPress"
    return "XenForo"
