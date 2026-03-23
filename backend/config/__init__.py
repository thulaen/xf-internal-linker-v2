# This file makes config/ a Python package.
# Celery app is imported here so Django's @shared_task decorator works.
from .celery import app as celery_app  # noqa: F401

__all__ = ("celery_app",)
