"""Django AppConfig for the source layer."""

import logging

from django.apps import AppConfig

from apps.core.services.management_commands import is_lightweight_management_command

logger = logging.getLogger(__name__)


class SourcesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.sources"
    verbose_name = "Source Layer"

    def ready(self) -> None:
        """Seed FR-250 rate-limiter buckets at Django startup.

        Every outbound API call to GSC, GA4, Matomo, XenForo, or WordPress
        passes through ``apps.sources.api_rate_limiter.rate_limited(name)``.
        That context manager looks the bucket up by name, so the buckets
        must exist before any sync task fires. Registering here means a
        cold worker boot (or a Django web restart) reseeds with full
        capacity — the safe-after-restart behaviour we want.
        """
        import sys

        if is_lightweight_management_command(sys.argv):
            return

        try:
            from .api_rate_limiter import register_defaults

            register_defaults()
        except Exception as exc:  # noqa: BLE001
            # Never block Django startup over a rate-limiter seed failure.
            # The wrapper itself raises on first use if a bucket is missing,
            # which is loud enough to debug. Logging here gives the operator
            # something to grep for in container logs.
            logger.warning(
                "FR-250 rate-limiter defaults could not be seeded at app " "ready: %s",
                exc,
            )
