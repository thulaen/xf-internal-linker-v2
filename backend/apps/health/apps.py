"""
Health app configuration.

The ready() method imports dev_tools_checks so its @HealthCheckRegistry.register()
decorators run at Django startup. This is the standard Django pattern for
wiring up registry entries without touching the services module.
"""

from django.apps import AppConfig


class HealthConfig(AppConfig):
    name = "apps.health"

    def ready(self) -> None:
        # Importing this module causes its @HealthCheckRegistry.register()
        # decorators to execute, adding all dev-tools checkers to the registry.
        from . import dev_tools_checks  # noqa: F401
