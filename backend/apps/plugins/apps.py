"""Plugins app — plugin registry with enable/disable toggle system."""

import sys

from django.apps import AppConfig


class PluginsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.plugins"
    verbose_name = "Plugins"

    def ready(self) -> None:
        # Skip plugin loading during migrations, management commands, and tests
        if any(cmd in sys.argv for cmd in ("migrate", "makemigrations", "test")):
            return

        from .loader import load_enabled_plugins

        try:
            load_enabled_plugins()
        except Exception:
            import logging

            logging.getLogger(__name__).exception("Plugin loading failed at startup")
