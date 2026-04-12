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


class RequiredSchemaRouteTests(SimpleTestCase):
    def test_schema_route_is_registered(self):
        self.assertEqual(reverse("schema"), "/api/schema/")

    def test_swagger_route_is_registered(self):
        self.assertEqual(reverse("swagger-ui"), "/api/schema/swagger-ui/")
