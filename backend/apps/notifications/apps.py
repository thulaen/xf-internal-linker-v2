"""Notifications app — operator alert center and delivery tracking."""

from django.apps import AppConfig

from apps.core.services.management_commands import is_lightweight_management_command


class NotificationsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.notifications"
    verbose_name = "Notifications"

    def ready(self) -> None:
        import sys

        if is_lightweight_management_command(sys.argv):
            return

        from .signals import connect_signals

        connect_signals()
