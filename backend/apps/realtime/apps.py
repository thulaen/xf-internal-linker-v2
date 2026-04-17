"""Realtime app config — generic topic-based WebSocket push."""

from django.apps import AppConfig


class RealtimeConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.realtime"
    verbose_name = "Realtime"

    def ready(self) -> None:
        # No signals registered here — every data-owning app registers its
        # own post_save / post_delete handlers that call
        # apps.realtime.services.broadcast(...). This keeps concerns local:
        # the realtime app owns transport, not data.
        return None
