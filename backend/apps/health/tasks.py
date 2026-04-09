"""
Health tasks — periodic health checks.
"""

import logging
from celery import shared_task
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
def run_all_health_checks():
    """
    Run all registered health checks from the registry.

    This is intended to run every 30 minutes via Celery Beat.
    It updates the ServiceHealthRecord for each service and emits/resolves
    OperatorAlerts accordingly.

    Returns a structured dict so monitoring tools can detect failures
    without having to parse log strings.
    """
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
                f"Health check failed for {service_key}: {str(e)}", exc_info=True
            )
            check_results[service_key] = "FAILED_EXECUTION"
            had_failure = True

    summary = ", ".join(f"{k}: {v}" for k, v in check_results.items())
    logger.info(f"Registry-scale health checks completed: {summary}")

    return {"ok": not had_failure, "checks": check_results}


@shared_task(
    name="health.run_single_health_check",
    time_limit=60,
    soft_time_limit=45,
    autoretry_for=(Exception,),
    max_retries=2,
    retry_backoff=True,
)
def run_single_health_check(service_key: str):
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
