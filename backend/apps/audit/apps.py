"""Audit app — full audit trail and reviewer scorecards."""

from django.apps import AppConfig

from apps.core.services.management_commands import is_lightweight_management_command


class AuditConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.audit"
    verbose_name = "Audit Trail"

    def ready(self):
        import sys

        if is_lightweight_management_command(sys.argv):
            return None

        # Startup smoke tests are wired from CoreConfig. Keeping this app
        # side-effect free avoids duplicate post-migrate audits.
        try:
            from . import tasks  # noqa: F401
        except Exception:  # noqa: BLE001
            import logging

            logging.getLogger(__name__).debug("audit.ready: tasks import failed", exc_info=True)
        return None
