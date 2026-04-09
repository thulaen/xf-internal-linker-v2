"""
Plugin loader — discovers and loads enabled plugins at startup.

Called from PluginsConfig.ready() to import plugin modules and
register their hooks.
"""

from __future__ import annotations

import importlib
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .hooks import PluginHooks

logger = logging.getLogger(__name__)

_registry: list[PluginHooks] = []


def get_registered_hooks() -> list[PluginHooks]:
    """Return all currently registered plugin hook instances."""
    return list(_registry)


def load_enabled_plugins() -> None:
    """Import all enabled & installed plugins and register their hooks.

    Called once at Django startup from PluginsConfig.ready().
    Plugins that fail to load are auto-disabled and logged.
    """
    from .models import Plugin

    for plugin in Plugin.objects.filter(is_enabled=True, is_installed=True):
        if not plugin.module_path:
            continue
        try:
            module = importlib.import_module(plugin.module_path)
            if hasattr(module, "register"):
                hooks_instance = module.register()
                if hooks_instance is not None:
                    _registry.append(hooks_instance)
                    logger.info(
                        "Loaded plugin '%s' from %s", plugin.name, plugin.module_path
                    )
            else:
                logger.warning(
                    "Plugin '%s' (%s) has no register() function — skipped.",
                    plugin.name,
                    plugin.module_path,
                )
        except Exception:
            logger.exception(
                "Failed to load plugin '%s' (%s) — disabling.",
                plugin.name,
                plugin.module_path,
            )
            Plugin.objects.filter(pk=plugin.pk).update(is_enabled=False)
