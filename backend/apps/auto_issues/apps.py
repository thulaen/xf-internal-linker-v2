from django.apps import AppConfig

from apps.core.services.management_commands import is_lightweight_management_command


class AutoIssuesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.auto_issues"

    def ready(self):
        import sys

        if is_lightweight_management_command(sys.argv):
            return

        try:
            from . import tasks  # noqa: F401
        except Exception:  # noqa: BLE001
            import logging

            logging.getLogger(__name__).debug("auto_issues.ready: tasks import failed", exc_info=True)
