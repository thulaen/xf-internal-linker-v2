"""Plugins app — plugin registry with enable/disable toggle system."""

import os
import sys

from django.apps import AppConfig


_PLUGIN_SKIP_COMMANDS = {
    "makemigrations",
    "migrate",
    "pytest",
    "showmigrations",
    "sqlmigrate",
    "test",
}


def _should_skip_plugin_loading(argv: list[str], settings_module: str | None) -> bool:
    """Return True when startup should avoid plugin autoload side effects."""
    resolved_settings_module = (settings_module or "").strip().lower()
    if resolved_settings_module.endswith(".test"):
        return True
    return any(arg in _PLUGIN_SKIP_COMMANDS for arg in argv)


class PluginsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.plugins"
    verbose_name = "Plugins"

    def ready(self) -> None:
        # Skip plugin loading during migrations, management commands, and tests
        if _should_skip_plugin_loading(
            argv=list(sys.argv),
            settings_module=os.environ.get("DJANGO_SETTINGS_MODULE"),
        ):
            return

        from .loader import load_enabled_plugins

        try:
            load_enabled_plugins()
        except Exception:
            import logging

            logging.getLogger(__name__).exception("Plugin loading failed at startup")
