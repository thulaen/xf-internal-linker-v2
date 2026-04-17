"""Suggestions app — link suggestions, pipeline runs, anchor policy."""

from django.apps import AppConfig


class SuggestionsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.suggestions"
    verbose_name = "Suggestions"

    def ready(self) -> None:  # noqa: D401
        """Register Phase SR real-time invalidation receivers."""
        try:
            from .readiness_signals import register as _register_readiness

            _register_readiness()
        except Exception:  # noqa: BLE001
            # Never block app startup on observability glue.
            import logging

            logging.getLogger(__name__).debug(
                "[suggestions] readiness signals not wired", exc_info=True
            )
