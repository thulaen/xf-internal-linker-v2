"""
Celery application configuration for XF Internal Linker V2.

All background ML jobs (import, embed, pipeline, ranking) run as Celery tasks.
Heavy processing NEVER happens inline in request handlers.
"""

import os

from celery import Celery

# Django settings module for Celery workers
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")

app = Celery("xf_linker")

# Read config from Django settings, using CELERY_ prefix
app.config_from_object("django.conf:settings", namespace="CELERY")

# Auto-discover tasks in all installed apps
app.autodiscover_tasks()

# Named queues for routing different job types
app.conf.task_queues = {
    "default": {"exchange": "default", "routing_key": "default"},
    "pipeline": {"exchange": "pipeline", "routing_key": "pipeline"},
    "embeddings": {"exchange": "embeddings", "routing_key": "embeddings"},
}

app.conf.task_default_queue = "default"


@app.task(bind=True, ignore_result=True)
def debug_task(self):
    """Debug task to verify Celery is working."""
    print(f"Request: {self.request!r}")
