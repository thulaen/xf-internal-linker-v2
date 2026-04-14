"""Core app — shared models, base classes, and utilities used across all apps."""

import logging

from django.apps import AppConfig
from django.db.models.signals import post_migrate

logger = logging.getLogger(__name__)


def _consume_safe_mode_boot_flag(sender, **kwargs):
    """If a prior session armed the safe-mode-boot flag, force Performance Mode
    to 'safe' now and clear the flag. Runs once per process after migrations.

    This is the "panic recovery" path: a noob user who got stuck on High
    Performance can arm the flag, restart the backend, and come back to Safe
    mode without touching the database directly.
    """
    try:
        from apps.core.models import AppSetting
    except Exception:  # pragma: no cover — app not ready yet
        return

    try:
        flag = (
            AppSetting.objects.filter(key="system.boot_safe_once")
            .values_list("value", flat=True)
            .first()
        )
        if flag and str(flag).lower() == "true":
            AppSetting.objects.update_or_create(
                key="system.performance_mode",
                defaults={
                    "value": "safe",
                    "value_type": "str",
                    "category": "performance",
                },
            )
            AppSetting.objects.filter(key="system.boot_safe_once").delete()
            logger.warning(
                "Safe-mode-boot flag consumed: performance mode forced to 'safe'."
            )
    except Exception:
        logger.exception("Could not consume safe-mode-boot flag")


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.core"
    verbose_name = "Core"

    def ready(self):
        # Run after migrations to avoid touching the table before it exists.
        post_migrate.connect(_consume_safe_mode_boot_flag, sender=self)
