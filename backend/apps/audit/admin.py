"""
Audit admin — AuditEntry, ReviewerScorecard, ErrorLog.
"""

from django.contrib import admin
from unfold.admin import ModelAdmin

from .models import AuditEntry, ErrorLog, ReviewerScorecard


@admin.register(AuditEntry)
class AuditEntryAdmin(ModelAdmin):
    """Admin for the full audit trail. Records are read-only."""

    list_display = ["action", "target_type", "target_id", "ip_address", "created_at"]
    list_filter = ["action", "target_type"]
    search_fields = ["target_id", "action"]
    readonly_fields = [
        "action",
        "target_type",
        "target_id",
        "detail",
        "ip_address",
        "created_at",
    ]
    ordering = ["-created_at"]

    def has_add_permission(self, request) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False


@admin.register(ReviewerScorecard)
class ReviewerScorecardAdmin(ModelAdmin):
    """Admin for reviewer performance summaries."""

    list_display = [
        "period_start",
        "period_end",
        "total_reviewed",
        "approved_count",
        "rejected_count",
        "approval_rate",
        "verified_rate",
    ]
    readonly_fields = [
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
    ordering = ["-period_end"]

    def has_add_permission(self, request) -> bool:
        return False


@admin.register(ErrorLog)
class ErrorLogAdmin(ModelAdmin):
    """Admin for background job error logs."""

    list_display = ["job_type", "step", "error_preview", "acknowledged", "created_at"]
    list_filter = ["job_type", "acknowledged"]
    search_fields = ["job_type", "step", "error_message"]
    readonly_fields = [
        "job_type",
        "step",
        "error_message",
        "raw_exception",
        "why",
        "created_at",
    ]
    list_editable = ["acknowledged"]
    ordering = ["-created_at"]

    @admin.display(description="Error")
    def error_preview(self, obj: ErrorLog) -> str:
        return (
            obj.error_message[:80] + "…"
            if len(obj.error_message) > 80
            else obj.error_message
        )
