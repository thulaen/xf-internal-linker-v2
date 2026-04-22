"""Django AppConfig for the Scheduled Updates orchestrator."""

from django.apps import AppConfig


class ScheduledUpdatesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.scheduled_updates"
    verbose_name = "Scheduled Updates"

    def ready(self) -> None:
        """Import the ``jobs`` module so every ``@scheduled_job`` decorator
        runs at Django startup and fills ``JOB_REGISTRY``. Without this,
        the runner wakes up with an empty registry and does nothing.
        """
        # Late import — AppConfig.ready fires after models are loaded, which
        # some entrypoints need.
        from . import jobs  # noqa: F401
