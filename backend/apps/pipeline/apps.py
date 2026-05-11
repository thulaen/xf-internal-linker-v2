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

        # Sentient-schedules — register the monthly top-50 job so the tracker
        # detects missed runs (e.g. laptop off on the 1st at 09:00) and fires
        # the catch-up automatically on next boot. Best-effort: a registration
        # failure must not crash startup.
        try:
            self._register_monthly_top_50_schedule()
        except Exception:  # noqa: BLE001  # noqa: forbidden-pattern silent-except  # justification: best-effort schedule-registration at Django app ready; logger.exception below records the failure and the boot continues so the rest of the app stays available — the schedule tracker re-attempts on the next Celery beat tick.
            import logging

            logging.getLogger(__name__).exception(
                "pipeline.ready: failed to register monthly_top_50 schedule (continuing)"
            )

        # Explicit import so the @shared_task decorator registers
        # all pipeline tasks with Celery on boot. Celery autodiscover
        # only finds tasks.py; split modules must be imported manually.
        try:
            from . import tasks  # noqa: F401
            from . import tasks_broken_links  # noqa: F401
            from . import tasks_embedding_audit  # noqa: F401
            from . import tasks_embedding_bakeoff  # noqa: F401
            from . import tasks_import  # noqa: F401
            from . import tasks_monthly  # noqa: F401
            from . import tasks_tuning  # noqa: F401
            from . import tasks_embeddings  # noqa: F401
            from . import tasks_link_health  # noqa: F401
        except Exception:  # noqa: BLE001
            import logging

            logging.getLogger(__name__).exception(
                "pipeline.ready: failed to import tasks modules (continuing)"
            )

    def _register_monthly_top_50_schedule(self) -> None:
        """Hook the monthly Top-50 job into apps.core.services.schedule_tracker."""
        from datetime import datetime

        from apps.core.services.schedule_tracker import register_schedule

        def _fire(slot: datetime) -> None:
            # Recovered runs invoke the management command in-process via
            # call_command — keeps the work on the worker that noticed the
            # missed slot rather than spawning Claude Code from a backend
            # container that can't reach the user's PATH.
            from django.core.management import call_command

            month_str = slot.strftime("%Y-%m")
            call_command("run_monthly_top_50", month=month_str, strategy="python")

        register_schedule(
            task_name="pipeline.run_monthly_top_50",
            cron_expr="0 9 1 * *",  # 1st of every month, 09:00 UTC
            fire_callable=_fire,
            max_lookback_hours=24
            * 35,  # up to ~5 weeks back so a 1st-of-month never falls outside the window
            description="Top 50 internal-link suggestions for the month, picked deterministically and written to docs/reports/.",
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
