"""
Health tasks — periodic health checks.
"""

import logging
from celery import shared_task
from django.db import connection

from apps.core.helpers import HelperConstraint

from .services import HealthCheckRegistry, perform_health_check

logger = logging.getLogger(__name__)


@shared_task(
    name="health.run_all_health_checks",
    time_limit=120,
    soft_time_limit=90,
    autoretry_for=(Exception,),
    max_retries=2,
    retry_backoff=True,
)
@HelperConstraint(
    cpu_intensive=False,
    gpu_required=False,
    storage_writes_to="postgres_main",
    ram_peak_mb=256,
)
def run_all_health_checks():
    """
    Run all registered health checks from the registry.

    This is intended to run every 30 minutes via Celery Beat.
    It updates the ServiceHealthRecord for each service and emits/resolves
    OperatorAlerts accordingly.

    Returns a structured dict so monitoring tools can detect failures
    without having to parse log strings.

    Issues #1338 and #423: close the DB connection before starting so a
    Celery retry (triggered by autoretry_for) begins with a fresh connection
    rather than one left in a failed/aborted transaction state.  After each
    individual check failure, close again so the next check is not poisoned.
    """
    if not connection.in_atomic_block:
        connection.close()

    logger.info("Starting system-wide health checks via Registry.")
    checkers = HealthCheckRegistry.get_checkers()
    check_results: dict[str, str] = {}
    had_failure = False

    for service_key in checkers.keys():
        try:
            record = perform_health_check(service_key)
            check_results[service_key] = record.status
        except Exception as e:
            logger.error(
                "Health check failed for %s: %s", service_key, e, exc_info=True
            )
            check_results[service_key] = "FAILED_EXECUTION"
            had_failure = True
            # Reset the DB connection so a failed check (e.g. check_database_health
            # opening a cursor that errors) does not leave the connection in an
            # aborted transaction state and poison the next check with
            # psycopg.errors.InFailedSqlTransaction (issues #1338, #423).
            if not connection.in_atomic_block:
                try:
                    connection.close()
                except Exception:  # noqa: BLE001
                    pass

    summary = ", ".join(f"{k}: {v}" for k, v in check_results.items())
    logger.info("Registry-scale health checks completed: %s", summary)

    return {"ok": not had_failure, "checks": check_results}


@shared_task(
    name="health.run_single_health_check",
    time_limit=60,
    soft_time_limit=45,
    autoretry_for=(Exception,),
    max_retries=2,
    retry_backoff=True,
)
@HelperConstraint(
    cpu_intensive=False,
    gpu_required=False,
    storage_writes_to="postgres_main",
    ram_peak_mb=256,
)
def run_single_health_check(service_key: str):
    # Mandatory Prevention Sweep (#86): close stale connections before task logic.
    if not connection.in_atomic_block:
        connection.close()

    """Run a single health check (e.g. from the UI)."""
    try:
        record = perform_health_check(service_key)
        return {
            "status": record.status,
            "status_label": record.status_label,
            "last_check_at": record.last_check_at.isoformat(),
        }
    except Exception as e:
        logger.error(
            f"Single health check failed for {service_key}: {str(e)}", exc_info=True
        )
        return {"status": "error", "message": str(e)}
