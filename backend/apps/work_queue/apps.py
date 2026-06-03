from django.apps import AppConfig


class WorkQueueConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.work_queue"
    verbose_name = "Agent work queue"

