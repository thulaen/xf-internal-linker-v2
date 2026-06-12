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

    Issue #318: When uvicorn spawns ASGI workers, PluginsConfig.ready() is
    called while an async event loop is already running in the process.
    Calling the synchronous Django ORM (Plugin.objects.filter) from that
    context raises SynchronousOnlyOperation.  Guard: if we are already inside
    an async context we skip plugin loading silently — uvicorn re-runs the
    startup sequence for each sync request in a thread pool, so plugins are
    not needed at the async startup phase.
    """
    from apps.core.services.async_context import in_async_context

    if in_async_context():
        logger.debug(
            "load_enabled_plugins: skipped — running in async context (ASGI worker startup)"
        )
        return

    from .models import Plugin
    import warnings

    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            category=RuntimeWarning,
            message=".*Accessing the database during app initialization is discouraged.*",
        )
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
