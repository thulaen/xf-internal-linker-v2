"""
Suggestions admin — PipelineRun, Suggestion, PipelineDiagnostic, ScopePreset.
"""

from django.contrib import admin
from django.utils.html import format_html
from unfold.admin import ModelAdmin, TabularInline

from .models import PipelineDiagnostic, PipelineRun, ScopePreset, Suggestion


class DiagnosticInline(TabularInline):
    """Inline diagnostics inside a PipelineRun."""

    model = PipelineDiagnostic
    fields = ["destination", "skip_reason", "created_at"]
    readonly_fields = ["destination", "skip_reason", "created_at"]
    extra = 0
    can_delete = False
    max_num = 0
    ordering = ["skip_reason"]


@admin.register(ScopePreset)
class ScopePresetAdmin(ModelAdmin):
    """Admin for saved scope configurations."""

    list_display = ["name", "scope_mode", "updated_at"]
    search_fields = ["name"]
    readonly_fields = ["created_at", "updated_at"]


@admin.register(PipelineRun)
class PipelineRunAdmin(ModelAdmin):
    """Admin for pipeline run history and progress monitoring."""

    list_display = [
        "run_id_short", "run_state", "suggestions_created",
        "destinations_processed", "destinations_skipped",
        "duration_display", "created_at",
    ]
    list_filter = ["run_state", "rerun_mode"]
    readonly_fields = [
        "run_id", "run_state", "suggestions_created", "destinations_processed",
        "destinations_skipped", "duration_seconds", "celery_task_id", "created_at", "updated_at",
    ]
    ordering = ["-created_at"]
    inlines = [DiagnosticInline]

    fieldsets = (
        ("Run Identity", {
            "fields": ("run_id", "run_state", "rerun_mode", "celery_task_id"),
        }),
        ("Results", {
            "fields": ("suggestions_created", "destinations_processed",
                       "destinations_skipped", "duration_seconds"),
        }),
        ("Scope Configuration", {
            "fields": ("host_scope", "destination_scope"),
            "classes": ("collapse",),
        }),
        ("Config Snapshot", {
            "fields": ("config_snapshot",),
            "classes": ("collapse",),
        }),
        ("Error", {
            "fields": ("error_message",),
            "classes": ("collapse",),
        }),
        ("Timestamps", {
            "fields": ("created_at", "updated_at"),
            "classes": ("collapse",),
        }),
    )

    @admin.display(description="Run ID")
    def run_id_short(self, obj: PipelineRun) -> str:
        return str(obj.run_id)[:8]

    @admin.display(description="Duration")
    def duration_display(self, obj: PipelineRun) -> str:
        if obj.duration_seconds is None:
            return "—"
        if obj.duration_seconds < 60:
            return f"{obj.duration_seconds:.1f}s"
        minutes = int(obj.duration_seconds // 60)
        seconds = int(obj.duration_seconds % 60)
        return f"{minutes}m {seconds}s"


@admin.register(Suggestion)
class SuggestionAdmin(ModelAdmin):
    """
    Admin for link suggestions.
    The most important view — shows the full review state of every suggestion.
    """

    list_display = [
        "suggestion_id_short", "status_badge", "destination_title_short",
        "anchor_phrase", "score_final", "anchor_confidence", "created_at",
    ]
    list_filter = ["status", "anchor_confidence", "repeated_anchor", "rejection_reason"]
    search_fields = ["destination_title", "host_sentence_text", "anchor_phrase"]
    readonly_fields = [
        "suggestion_id", "pipeline_run", "destination", "host", "host_sentence",
        "score_semantic", "score_keyword", "score_node_affinity", "score_quality",
        "score_march_2026_pagerank", "score_velocity", "score_link_freshness", "score_phrase_relevance",
        "score_learned_anchor_corroboration", "score_final",
        "phrase_match_diagnostics", "learned_anchor_diagnostics",
        "repeated_anchor", "superseded_by", "superseded_at",
        "created_at", "updated_at",
    ]
    ordering = ["-created_at"]
    list_per_page = 50

    fieldsets = (
        ("Suggestion", {
            "fields": ("suggestion_id", "status", "pipeline_run"),
        }),
        ("Destination (linked TO)", {
            "fields": ("destination", "destination_title"),
        }),
        ("Host (link placed IN)", {
            "fields": ("host", "host_sentence", "host_sentence_text"),
        }),
        ("Anchor Text", {
            "fields": ("anchor_phrase", "anchor_start", "anchor_end",
                       "anchor_confidence", "anchor_edited", "repeated_anchor"),
        }),
        ("Score Breakdown", {
            "fields": ("score_semantic", "score_keyword", "score_node_affinity",
                       "score_quality", "score_march_2026_pagerank", "score_velocity", "score_link_freshness",
                       "score_phrase_relevance", "score_learned_anchor_corroboration", "score_final"),
            "classes": ("collapse",),
        }),
        ("Phrase Matching", {
            "fields": ("phrase_match_diagnostics",),
            "classes": ("collapse",),
        }),
        ("Learned Anchor", {
            "fields": ("learned_anchor_diagnostics",),
            "classes": ("collapse",),
        }),
        ("Review", {
            "fields": ("rejection_reason", "reviewer_notes", "reviewed_at"),
        }),
        ("Applied / Verified", {
            "fields": ("is_applied", "applied_at", "verified_at", "stale_reason"),
        }),
        ("Supersede Chain", {
            "fields": ("superseded_by", "superseded_at"),
            "classes": ("collapse",),
        }),
        ("Timestamps", {
            "fields": ("created_at", "updated_at"),
            "classes": ("collapse",),
        }),
    )

    @admin.display(description="ID")
    def suggestion_id_short(self, obj: Suggestion) -> str:
        return str(obj.suggestion_id)[:8]

    @admin.display(description="Status")
    def status_badge(self, obj: Suggestion) -> str:
        colors = {
            "pending": "#f4b400",
            "approved": "#0f9d58",
            "rejected": "#d50000",
            "applied": "#1a73e8",
            "verified": "#0b8043",
            "stale": "#9e9e9e",
            "superseded": "#c4c7c5",
        }
        color = colors.get(obj.status, "#9e9e9e")
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;border-radius:4px;'
            'font-size:11px;font-weight:600">{}</span>',
            color, obj.get_status_display(),
        )

    @admin.display(description="Destination")
    def destination_title_short(self, obj: Suggestion) -> str:
        return obj.destination_title[:60] if obj.destination_title else "—"


@admin.register(PipelineDiagnostic)
class PipelineDiagnosticAdmin(ModelAdmin):
    """Admin for pipeline skip diagnostics (why-no-suggestion explorer)."""

    list_display = ["pipeline_run", "destination", "skip_reason", "created_at"]
    list_filter = ["skip_reason"]
    search_fields = ["destination__title", "pipeline_run__run_id"]
    readonly_fields = ["pipeline_run", "destination", "skip_reason", "detail", "created_at"]
    ordering = ["-created_at"]
