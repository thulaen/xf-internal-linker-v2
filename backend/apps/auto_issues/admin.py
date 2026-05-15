"""Django admin for the AutoIssue table.

Exposes search across `lessons_learned` so humans can grep prior fixes
the same way agents do via `manage.py search_resolved_issues`.
"""

from django.contrib import admin

from .models import AutoIssue, AutoIssueCategory, QualityEvidence, QualityRawSnippet


@admin.register(AutoIssueCategory)
class AutoIssueCategoryAdmin(admin.ModelAdmin):
    list_display = ("key", "label", "parent", "is_active", "sort_order")
    list_filter = ("is_active", "parent")
    search_fields = ("key", "label", "description")
    ordering = ("sort_order", "label")


@admin.register(AutoIssue)
class AutoIssueAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "source",
        "category",
        "severity",
        "status",
        "priority_score",
        "title",
        "occurrence_count",
        "last_seen",
    )
    list_filter = ("status", "source", "category", "severity")
    search_fields = (
        "title",
        "description",
        "external_id",
        "fingerprint",
        "lessons_learned",
    )
    readonly_fields = ("first_seen", "last_seen", "fingerprint")
    ordering = ("-priority_score", "-last_seen")


@admin.register(QualityEvidence)
class QualityEvidenceAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "check_type",
        "status",
        "tool_name",
        "file_path",
        "occurrence_count",
        "last_seen",
    )
    list_filter = ("check_type", "status", "tool_name")
    search_fields = ("tool_name", "command", "file_path", "summary")
    readonly_fields = ("dedupe_key", "first_seen", "last_seen")
    ordering = ("-last_seen",)


@admin.register(QualityRawSnippet)
class QualityRawSnippetAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "raw_report_hash",
        "reference_count",
        "uncompressed_bytes",
        "compressed_bytes",
        "last_captured_week_start",
    )
    readonly_fields = ("raw_report_hash", "first_seen", "last_seen")
    ordering = ("-last_captured_week_start", "-last_seen")
