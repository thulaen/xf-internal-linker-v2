from django.apps import AppConfig


class CrawlerConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.crawler"
    verbose_name = "Web Crawler"

    def ready(self) -> None:
        # Register realtime broadcast signals. Idempotent via dispatch_uid.
        from . import signals  # noqa: F401
