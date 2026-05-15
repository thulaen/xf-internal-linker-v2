"""Django AppConfig for the sync app."""

from django.apps import AppConfig

from apps.core.services.management_commands import is_lightweight_management_command


class SyncConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.sync"
    verbose_name = "Synchronization"

    def ready(self) -> None:
        import sys

        if is_lightweight_management_command(sys.argv):
            return

        # Register realtime broadcast signals. Idempotent via dispatch_uid.
        from . import signals  # noqa: F401
