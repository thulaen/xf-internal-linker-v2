from django.apps import AppConfig


class DiagnosticsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.diagnostics"

    def ready(self) -> None:
        # Import signals so they register with Django's dispatcher. The
        # receivers are idempotent (dispatch_uid keys) so double-import under
        # autoreload is safe.
        from . import signals  # noqa: F401
