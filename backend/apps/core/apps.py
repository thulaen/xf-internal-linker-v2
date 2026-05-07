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
    except Exception:  # noqa: BLE001  # pragma: no cover — defensive: app registry may not be ready yet at startup; safest action is just to skip the panic-recovery flag for this boot.
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


def _run_startup_smoke_tests(sender, **kwargs):
    # Skip during test runs: each test-DB boot would otherwise emit
    # ErrorLog rows for every artefact-table policy gap and chain into
    # OperatorAlert via post_save, polluting test isolation. Tests that
    # exercise the smoke logic call `run_startup_smoke_tests()` directly.
    import sys

    if any(arg == "test" for arg in sys.argv[1:3]):
        return
    using = kwargs.get("using", "default")
    try:
        from django.db import connections

        db_name = connections[using].settings_dict.get("NAME") or ""
        if isinstance(db_name, str) and db_name.startswith("test_"):
            return
    except Exception:
        logger.debug("Smoke-test test-DB detection failed", exc_info=True)

    try:
        from apps.core.services.self_test_smoke import run_startup_smoke_tests

        run_startup_smoke_tests()
    except Exception:
        logger.exception("Could not run startup smoke tests")


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.core"
    verbose_name = "Core"

    def ready(self):
        # Run after migrations to avoid touching the table before it exists.
        post_migrate.connect(_consume_safe_mode_boot_flag, sender=self)
        post_migrate.connect(_run_startup_smoke_tests, sender=self)

        # Phase R1.3 — realtime broadcast signals for AppSetting changes.
        # Idempotent via dispatch_uid on each receiver.
        from . import signals  # noqa: F401
