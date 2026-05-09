"""Django admin for the AutoIssue table.

Exposes search across `lessons_learned` so humans can grep prior fixes
the same way agents do via `manage.py search_resolved_issues`.
"""

from django.contrib import admin

from .models import AutoIssue


@admin.register(AutoIssue)
class AutoIssueAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "source",
        "severity",
        "status",
        "priority_score",
        "title",
        "occurrence_count",
        "last_seen",
    )
    list_filter = ("status", "source", "severity")
    search_fields = (
        "title",
        "description",
        "external_id",
        "fingerprint",
        "lessons_learned",
    )
    readonly_fields = ("first_seen", "last_seen", "fingerprint")
    ordering = ("-priority_score", "-last_seen")
