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

        if not _should_build_faiss_index_on_startup(sys.argv):
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


def _should_build_faiss_index_on_startup(argv: list[str]) -> bool:
    if not argv:
        return False

    executable = argv[0].lower()
    command = argv[1].lower() if len(argv) > 1 else ""
    if "manage.py" in executable:
        return command == "runserver"

    runtime_tokens = ("celery", "daphne", "gunicorn", "uvicorn")
    return any(token in executable or token == command for token in runtime_tokens)
