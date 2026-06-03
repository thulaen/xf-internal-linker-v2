"""Test suite for the plugins app."""

from unittest.mock import patch

from django.test import SimpleTestCase
from django.urls import reverse

from apps.plugins.apps import _should_skip_plugin_loading


class PluginStartupGuardTests(SimpleTestCase):
    def test_skip_plugin_loading_for_test_settings(self):
        self.assertTrue(
            _should_skip_plugin_loading(
                argv=["manage.py", "runserver"],
                settings_module="config.settings.test",
            )
        )

    def test_skip_plugin_loading_for_showmigrations_command(self):
        self.assertTrue(
            _should_skip_plugin_loading(
                argv=["manage.py", "showmigrations"],
                settings_module="config.settings.development",
            )
        )

    def test_do_not_skip_plugin_loading_for_normal_runtime_start(self):
        self.assertFalse(
            _should_skip_plugin_loading(
                argv=["manage.py", "runserver"],
                settings_module="config.settings.development",
            )
        )

    def test_skip_plugin_loading_for_uvicorn_async_server(self):
        self.assertTrue(
            _should_skip_plugin_loading(
                argv=["python", "-m", "uvicorn", "config.asgi:application"],
                settings_module="config.settings.production",
            )
        )

    def test_skip_plugin_loading_for_celery_worker(self):
        """Issue #20206: the Celery worker entrypoint must skip plugin autoload.

        The worker boots as ``celery -A config.celery worker ...``.  Without the
        skip guard, PluginsConfig.ready() runs a Plugin.objects.filter() query
        during AppConfig.ready(), which Django flags with the RuntimeWarning
        "Accessing the database during app initialization" ~370x/24h.
        """
        self.assertTrue(
            _should_skip_plugin_loading(
                argv=[
                    "/usr/local/bin/celery",
                    "-A",
                    "config.celery",
                    "worker",
                    "--loglevel=warning",
                    "-Q",
                    "pipeline,embeddings",
                ],
                settings_module="config.settings.production",
            )
        )


class AsyncContextPluginGuardTests(SimpleTestCase):
    """Issue #318: load_enabled_plugins must not raise SynchronousOnlyOperation."""

    def test_load_enabled_plugins_skips_db_query_in_async_context(self):
        """When an event loop is running, load_enabled_plugins must skip silently."""
        from apps.plugins.loader import load_enabled_plugins

        # Patch in_async_context to simulate an ASGI async context.
        with patch(
            "apps.core.services.async_context.in_async_context", return_value=True
        ):
            # Patch the Django ORM query to detect if it's called.
            with patch("apps.plugins.models.Plugin") as mock_plugin_cls:
                mock_plugin_cls.objects.filter.return_value = []
                # Must not raise; must return without querying the DB.
                load_enabled_plugins()
                mock_plugin_cls.objects.filter.assert_not_called()


class RequiredSchemaRouteTests(SimpleTestCase):
    def test_schema_route_is_registered(self):
        self.assertEqual(reverse("schema"), "/api/schema/")

    def test_swagger_route_is_registered(self):
        self.assertEqual(reverse("swagger-ui"), "/api/schema/swagger-ui/")
