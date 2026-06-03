"""Convention-named SimpleTestCase coverage for apps/plugins/loader.py.

Issue #318: when uvicorn starts an ASGI worker, ``PluginsConfig.ready()`` runs
inside a live asyncio event loop.  Calling the synchronous Django ORM there
raises ``SynchronousOnlyOperation``.  ``load_enabled_plugins`` now checks
``in_async_context()`` first and returns without querying the database when an
event loop is running.  These tests prove both branches with the ORM mocked so
no real database access happens.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase


class LoadEnabledPluginsAsyncGuardTests(SimpleTestCase):
    def test_skips_db_query_when_in_async_context(self) -> None:
        """In an async context the loader must return without touching Plugin."""
        from apps.plugins.loader import load_enabled_plugins

        plugin_cls = MagicMock()
        with patch(
            "apps.core.services.async_context.in_async_context", return_value=True
        ), patch("apps.plugins.models.Plugin", plugin_cls):
            with self.assertLogs("apps.plugins.loader", level="DEBUG") as captured:
                load_enabled_plugins()
        plugin_cls.objects.filter.assert_not_called()
        # Exact-match the skip message so the mutation gate's string mutant
        # (which wraps the literal as "XX...XX") is killed — a substring check
        # would still pass on the wrapped text and let the mutant survive.
        self.assertEqual(
            captured.records[0].getMessage(),
            "load_enabled_plugins: skipped — running in async context "
            "(ASGI worker startup)",
        )

    def test_queries_plugins_when_not_in_async_context(self) -> None:
        """Outside an async context the loader still queries enabled plugins."""
        from apps.plugins.loader import load_enabled_plugins

        plugin_cls = MagicMock()
        plugin_cls.objects.filter.return_value = []
        with patch(
            "apps.core.services.async_context.in_async_context", return_value=False
        ), patch("apps.plugins.models.Plugin", plugin_cls):
            load_enabled_plugins()
        plugin_cls.objects.filter.assert_called_once_with(
            is_enabled=True, is_installed=True
        )
