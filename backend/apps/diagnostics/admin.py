from django.contrib import admin
from .models import ServiceStatusSnapshot, SystemConflict


@admin.register(ServiceStatusSnapshot)
class ServiceStatusSnapshotAdmin(admin.ModelAdmin):
    list_display = (
        "service_name",
        "state",
        "last_check",
        "last_success",
        "last_failure",
    )
    list_filter = ("service_name", "state")
    search_fields = ("service_name", "explanation")
    readonly_fields = ("last_check",)


@admin.register(SystemConflict)
class SystemConflictAdmin(admin.ModelAdmin):
    list_display = ("title", "conflict_type", "severity", "resolved", "created_at")
    list_filter = ("conflict_type", "severity", "resolved")
    search_fields = ("title", "description", "location")
    list_editable = ("resolved",)
