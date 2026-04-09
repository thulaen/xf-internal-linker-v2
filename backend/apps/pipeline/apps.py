"""Pipeline app — Celery tasks for import, embed, rank, sync."""

from django.apps import AppConfig


class PipelineConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.pipeline"
    verbose_name = "Pipeline"

    def ready(self):
        import os

        if os.environ.get("FAISS_INDEX_SKIP_BUILD"):
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
