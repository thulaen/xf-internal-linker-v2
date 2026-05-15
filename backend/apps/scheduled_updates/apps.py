"""Django app configuration for scheduled updates."""

import sys

from django.apps import AppConfig

from apps.core.services.management_commands import is_lightweight_management_command


class ScheduledUpdatesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.scheduled_updates"
    verbose_name = "Scheduled Updates"

    def ready(self) -> None:
        """Import scheduled jobs unless this is a lightweight command."""
        if is_lightweight_management_command(sys.argv):
            return

        from . import jobs  # noqa: F401
        from . import tasks  # noqa: F401
