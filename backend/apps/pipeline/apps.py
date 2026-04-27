"""Pipeline app — Celery tasks for import, embed, rank, sync."""

from django.apps import AppConfig


class PipelineConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.pipeline"
    verbose_name = "Pipeline"

    def ready(self):
        import os
        import sys

        if os.environ.get("FAISS_INDEX_SKIP_BUILD"):
            return

        # ISS-003: Skip FAISS index build for management commands to avoid DB hits before apps are ready
        if sys.argv and "manage.py" in sys.argv[0]:
            # Allow runserver and test, but block makemigrations, migrate, etc.
            if len(sys.argv) == 1 or sys.argv[1] not in ["runserver", "test"]:
                return

        import logging

        logger = logging.getLogger(__name__)
        try:
            from .services.faiss_index import build_faiss_index

            build_faiss_index()
        except Exception:
            logger.exception(
                "FAISS index build failed at startup — falling back to NumPy path"
            )
