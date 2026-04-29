"""Audit app — full audit trail and reviewer scorecards."""

from django.apps import AppConfig


class AuditConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.audit"
    verbose_name = "Audit Trail"

    def ready(self):
        from django.db.models.signals import post_migrate
        from .integrity import verify_artefact_integrity

        def run_integrity_checks(sender, **kwargs):
            # Only run for this app to avoid duplicate triggers during migrate
            if sender.name == self.name:
                verify_artefact_integrity()

        post_migrate.connect(run_integrity_checks, sender=self)
