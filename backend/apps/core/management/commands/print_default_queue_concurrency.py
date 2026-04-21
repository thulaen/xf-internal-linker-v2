from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Print the configured concurrency for the default Celery queue."

    minimum = 1
    maximum = 6

    def handle(self, *args, **options):
        value = self._read_configured_concurrency()
        value = min(self.maximum, max(self.minimum, value))
        self.stdout.write(str(value))

    def _read_configured_concurrency(self) -> int:
        default = int(getattr(settings, "CELERY_WORKER_CONCURRENCY", 2) or 2)
        try:
            from apps.core.models import AppSetting

            raw_value = (
                AppSetting.objects.filter(key="system.default_queue_concurrency")
                .values_list("value", flat=True)
                .first()
            )
            if raw_value is None:
                raw_value = (
                    AppSetting.objects.filter(key="system.celery_concurrency")
                    .values_list("value", flat=True)
                    .first()
                )
            return int(raw_value) if raw_value is not None else default
        except Exception:
            return default
