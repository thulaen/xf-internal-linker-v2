"""Pipeline app — Celery tasks for import, embed, rank, sync.

Group B (FAISS hygiene) — closes ISS-003.

Plain-English rationale:
- Old behaviour: this AppConfig.ready() built the FAISS index at every
  Django startup, including ``manage.py showmigrations`` and
  ``makemigrations --check``. That hit the database before all apps
  were initialised and triggered Django's ``APPS_NOT_READY`` warning.
- New behaviour: we no longer build the index at startup. The 15-minute
  Celery beat task ``refresh_faiss_index`` (apps/pipeline/tasks.py)
  builds it within minutes of worker boot, and the just-in-time
  fallback in ``pipeline_stages._stage1_candidates()`` builds on the
  first query if a request arrives before beat fires. Either way the
  index is ready by the time anyone needs it.
- We DO still call ``_assert_single_worker()`` at startup so a
  misconfigured multi-process Celery worker is caught loudly (logs +
  ``/error-log`` row) instead of silently serving stale results from
  per-process indexes.
- Any startup failure routes to the audit-log via ``ingest_error()``,
  so FAISS misconfigurations surface on the deduped errors page
  alongside everything else. We never re-raise from ``ready()`` —
  Django startup must not be blocked by an audit-log failure.
"""

from django.apps import AppConfig


class PipelineConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.pipeline"
    verbose_name = "Pipeline"

    def ready(self):
        import os
        import sys

        # Legacy escape hatch — leave intact in case any harness still
        # relies on a fully-silent startup.
        if os.environ.get("FAISS_INDEX_SKIP_BUILD"):
            return

        # Skip the audit-logging side-effects under `manage.py test`.
        # The single-worker check still runs (and emits its log line)
        # but no ErrorLog row gets written into the per-test DB, which
        # would otherwise cascade into a stray OperatorAlert that
        # pollutes notifications-app test isolation.
        if any(arg == "test" for arg in sys.argv[1:3]):
            return

        # Group B.2 — single-worker assertion. Does NOT build the index
        # any more; just inspects the env and warns + audit-logs on
        # misconfiguration. Wrapped in a generic try/except so any
        # failure routes to /error-log instead of crashing startup.
        try:
            from .services.faiss_index import _assert_single_worker

            _assert_single_worker()
        except Exception as exc:  # noqa: BLE001  # Pipeline ready() must never crash startup — funnel every failure to the audit log via _record_startup_failure.
            self._record_startup_failure(
                step="single_worker_assertion",
                exc=exc,
            )

    def _record_startup_failure(self, *, step: str, exc: BaseException) -> None:
        """Group B.3 — deduped audit-log entry for FAISS startup failures.

        Defensive: wraps the whole audit path in another try/except so a
        broken audit subsystem can't bring down the pipeline app's
        ``ready()``. Falls back to the standard logger as a last resort.
        """
        try:
            import traceback

            from apps.audit.error_ingest import ingest_error
            from apps.audit.models import ErrorLog

            ingest_error(
                job_type="faiss_init",
                step=step,
                error_message=str(exc) or exc.__class__.__name__,
                raw_exception=traceback.format_exc(),
                severity=ErrorLog.SEVERITY_CRITICAL,
            )
        except Exception:  # noqa: BLE001  # Last-resort fallback when the audit-ingestion path itself is broken — surface to stderr so the boot failure isn't silent.
            # Audit subsystem itself is broken — log to stderr at least.
            import logging

            logging.getLogger(__name__).exception(
                "FAISS startup failed AND audit-log ingestion path is broken; "
                "step=%s",
                step,
            )
