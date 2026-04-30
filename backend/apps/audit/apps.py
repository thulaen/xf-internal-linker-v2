"""Audit app — full audit trail and reviewer scorecards."""

from django.apps import AppConfig


class AuditConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.audit"
    verbose_name = "Audit Trail"

    def ready(self):
        # Startup smoke tests are wired from CoreConfig. Keeping this app
        # side-effect free avoids duplicate post-migrate audits.
        return None
