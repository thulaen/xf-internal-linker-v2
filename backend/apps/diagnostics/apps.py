"""Django AppConfig for the diagnostics app."""

from django.apps import AppConfig

from apps.core.services.management_commands import is_lightweight_management_command


class DiagnosticsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.diagnostics"

    def ready(self) -> None:
        import sys

        if is_lightweight_management_command(sys.argv):
            return

        # Import signals so they register with Django's dispatcher. The
        # receivers are idempotent (dispatch_uid keys) so double-import under
        # autoreload is safe.
        from . import signals  # noqa: F401
