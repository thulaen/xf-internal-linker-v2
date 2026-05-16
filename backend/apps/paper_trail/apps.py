"""Paper trail Django app config."""

from __future__ import annotations

from django.apps import AppConfig


class PaperTrailConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.paper_trail"
    verbose_name = "Paper Trail"

    def ready(self) -> None:
        # Signal handlers live in signals.py and self-register on import.
        # Guarded so test settings and migrations don't trigger the signal
        # graph before the AutoIssue table exists.
        import sys

        from apps.core.services.management_commands import (
            is_lightweight_management_command,
        )

        if is_lightweight_management_command(sys.argv):
            return
        try:
            from . import signals  # noqa: F401
        except Exception:  # noqa: BLE001 — defensive; signals are optional wiring
            import logging

            logging.getLogger(__name__).debug(
                "paper_trail signals not loaded",
                exc_info=True,
            )
