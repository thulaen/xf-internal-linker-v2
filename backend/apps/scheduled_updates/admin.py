"""Django admin registrations for the Scheduled Updates orchestrator.

Kept minimal: list pages that are useful for an operator manually
inspecting or editing a job mid-incident. Deep UI (progress bar, pause
buttons) lives in the Angular Scheduled Updates tab, not here.
"""

from django.contrib import admin

from .models import JobAlert, ScheduledJob


@admin.register(ScheduledJob)
class ScheduledJobAdmin(admin.ModelAdmin):
    list_display = (
        "key",
        "display_name",
        "state",
        "priority",
        "progress_pct",
        "last_success_at",
        "scheduled_for",
    )
    list_filter = ("state", "priority")
    search_fields = ("key", "display_name")
    readonly_fields = ("created_at", "updated_at", "started_at", "finished_at")
    ordering = ("priority", "key")


@admin.register(JobAlert)
class JobAlertAdmin(admin.ModelAdmin):
    list_display = (
        "job_key",
        "alert_type",
        "calendar_date",
        "first_raised_at",
        "acknowledged_at",
        "resolved_at",
    )
    list_filter = ("alert_type",)
    search_fields = ("job_key", "message")
    readonly_fields = ("first_raised_at", "last_seen_at")
    ordering = ("-calendar_date", "job_key")
