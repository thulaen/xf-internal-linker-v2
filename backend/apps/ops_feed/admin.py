"""Django admin for the Operations Feed (read-only triage)."""

from django.contrib import admin
from unfold.admin import ModelAdmin

from .models import OperationEvent


@admin.register(OperationEvent)
class OperationEventAdmin(ModelAdmin):
    list_display = [
        "timestamp",
        "severity",
        "event_type",
        "source",
        "occurrence_count",
        "short_message",
    ]
    list_filter = ["severity", "source", "event_type"]
    search_fields = ["plain_english", "related_entity_id"]
    readonly_fields = [
        "timestamp",
        "event_type",
        "source",
        "plain_english",
        "severity",
        "related_entity_type",
        "related_entity_id",
        "runtime_context",
        "dedup_key",
        "occurrence_count",
        "error_log_id",
    ]

    @admin.display(description="Message")
    def short_message(self, obj):
        return (
            obj.plain_english[:80] + "…"
            if len(obj.plain_english) > 80
            else obj.plain_english
        )
