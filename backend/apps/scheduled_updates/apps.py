"""Django AppConfig for the Scheduled Updates orchestrator."""

from django.apps import AppConfig


class ScheduledUpdatesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.scheduled_updates"
    verbose_name = "Scheduled Updates"
