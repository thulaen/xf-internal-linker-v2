from django.apps import AppConfig


class SyncConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.sync"
    verbose_name = "Synchronization"

    def ready(self) -> None:
        # Register realtime broadcast signals. Idempotent via dispatch_uid.
        from . import signals  # noqa: F401
