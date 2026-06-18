"""Celery task wrapper for the daily database backup (Group L #91).

Plain-English: runs once a day inside the operator's 11 AM – 11 PM
laptop window, calls ``apps.core.backups.run_backup_pass``, routes
any failure to ``/error-log`` so it shows up on the deduped errors
page instead of vanishing into Celery logs.

Schedule: see ``backend/config/settings/celery_schedules.py`` —
``daily-database-backup`` entry. Default 02:30 UTC is inside the
laptop window after midnight; operators in earlier timezones can
adjust without touching this file.

Manual trigger:
    python scripts/backend_manage.py shell -c "from config.celery import app; app.send_task('core.create_database_snapshot')"
"""

from __future__ import annotations

import logging
import traceback

from celery import shared_task

from apps.core.helpers import HelperConstraint
from django.db import connection

logger = logging.getLogger(__name__)


@shared_task(
    name="core.create_database_snapshot",
    time_limit=2400,
    soft_time_limit=2300,
)
@HelperConstraint(
    cpu_intensive=False,
    gpu_required=False,
    storage_writes_to="postgres_main",
    ram_peak_mb=512,
    expected_seconds_p50=300,
)
def create_database_snapshot() -> dict:
    if not connection.in_atomic_block:
        connection.close()

    from apps.audit.error_ingest import ingest_error
    from apps.audit.models import ErrorLog
    from apps.core.backups import run_backup_pass

    try:
        result = run_backup_pass()
    except Exception as exc:
        logger.exception(
            "create_database_snapshot: unexpected failure during run_backup_pass"
        )
        try:
            ingest_error(
                job_type="db_backup",
                step="run_backup_pass",
                error_message=str(exc) or exc.__class__.__name__,
                raw_exception=traceback.format_exc(),
                why=(
                    "The daily database backup failed before completing. "
                    "Check Postgres connectivity, that pg_dump exists in "
                    "the backend image, and that there is at least 5 GB "
                    "free on the volume that holds backups/."
                ),
                severity=ErrorLog.SEVERITY_HIGH,
            )
        except Exception:  # pragma: no cover — defensive
            logger.exception(
                "create_database_snapshot: failed AND audit-log path is broken"
            )
        return {"status": "error", "detail": str(exc) or exc.__class__.__name__}

    if result.get("created") is None:
        # The service skipped the backup deliberately (low disk, pg_dump
        # missing, server unreachable). The service already logged the
        # specific reason via logger.error / logger.warning. We add a
        # /error-log entry so the noob-friendly errors page surfaces it.
        try:
            ingest_error(
                job_type="db_backup",
                step="create_snapshot",
                error_message=(
                    "Daily backup skipped (no snapshot created). "
                    "Check the previous Celery log lines for the reason — "
                    "typically: low disk on the backups/ volume, missing "
                    "pg_dump binary, or unreachable Postgres."
                ),
                why=(
                    "The backup service refused to write a snapshot. The "
                    "most common cause is < 5 GB free on the disk that "
                    "holds backups/; second most common is the backend "
                    "image missing postgresql-client (rebuild after the "
                    "Group L #91 Dockerfile change to fix)."
                ),
                severity=ErrorLog.SEVERITY_HIGH,
            )
        except Exception:  # pragma: no cover — defensive
            logger.exception(
                "create_database_snapshot: skip-path audit log also failed"
            )
        return {"status": "skipped", **result}

    return {"status": "ok", **result}
