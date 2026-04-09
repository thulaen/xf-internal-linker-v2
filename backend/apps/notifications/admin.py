"""Admin for the notifications app."""

from django.contrib import admin
from unfold.admin import ModelAdmin

from .models import AlertDeliveryAttempt, OperatorAlert


class AlertDeliveryAttemptInline(admin.TabularInline):
    model = AlertDeliveryAttempt
    extra = 0
    readonly_fields = ["channel", "result", "reason", "attempted_at"]
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(OperatorAlert)
class OperatorAlertAdmin(ModelAdmin):
    list_display = [
        "title",
        "severity",
        "status",
        "source_area",
        "event_type",
        "occurrence_count",
        "first_seen_at",
    ]
    list_filter = ["severity", "status", "source_area", "event_type"]
    search_fields = ["title", "message", "dedupe_key", "event_type"]
    readonly_fields = [
        "alert_id",
        "event_type",
        "source_area",
        "severity",
        "title",
        "message",
        "dedupe_key",
        "fingerprint",
        "occurrence_count",
        "related_object_type",
        "related_object_id",
        "related_route",
        "payload",
        "error_log",
        "first_seen_at",
        "last_seen_at",
        "read_at",
        "acknowledged_at",
        "resolved_at",
        "created_at",
        "updated_at",
    ]
    ordering = ["-first_seen_at"]
    inlines = [AlertDeliveryAttemptInline]

    def has_add_permission(self, request):
        return False


@admin.register(AlertDeliveryAttempt)
class AlertDeliveryAttemptAdmin(ModelAdmin):
    list_display = ["alert", "channel", "result", "attempted_at"]
    list_filter = ["channel", "result"]
    readonly_fields = ["alert", "channel", "result", "reason", "attempted_at"]
    ordering = ["-attempted_at"]

    def has_add_permission(self, request):
        return False
