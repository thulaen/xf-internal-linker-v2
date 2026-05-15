"""Plugins app — plugin registry with enable/disable toggle system."""

import os
import sys

from django.apps import AppConfig


_PLUGIN_SKIP_COMMANDS = {
    "daphne",
    "makemigrations",
    "migrate",
    "pytest",
    "showmigrations",
    "sqlmigrate",
    "test",
    "uvicorn",
}


def _should_skip_plugin_loading(argv: list[str], settings_module: str | None) -> bool:
    """Return True when startup should avoid plugin autoload side effects."""
    resolved_settings_module = (settings_module or "").strip().lower()
    if resolved_settings_module.endswith(".test"):
        return True
    return any(_is_skip_command(arg) for arg in argv)


def _is_skip_command(arg: str) -> bool:
    command = arg.rsplit("/", maxsplit=1)[-1].rsplit("\\", maxsplit=1)[-1]
    command = command.removesuffix(".exe").removesuffix(".py")
    return command in _PLUGIN_SKIP_COMMANDS


class PluginsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.plugins"
    verbose_name = "Plugins"

    def ready(self) -> None:
        # Skip plugin loading during migrations, management commands, and tests
        from apps.core.services.management_commands import is_lightweight_management_command

        if is_lightweight_management_command(sys.argv):
            return

        if _should_skip_plugin_loading(
            argv=list(sys.argv),
            settings_module=os.environ.get("DJANGO_SETTINGS_MODULE"),
        ):
            return

        from .loader import load_enabled_plugins

        try:
            load_enabled_plugins()
        except Exception:  # noqa: BLE001  # Best-effort fallback in service/helper code; downstream code logs / returns a safe default — must not raise to the pipeline orchestrator.
            import logging

            logging.getLogger(__name__).exception("Plugin loading failed at startup")
