from django.apps import AppConfig


class AutoIssuesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.auto_issues"

    def ready(self):
        try:
            from . import tasks  # noqa: F401
        except Exception:  # noqa: BLE001
            import logging

            logging.getLogger(__name__).debug("auto_issues.ready: tasks import failed", exc_info=True)
