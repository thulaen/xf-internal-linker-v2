"""
Health tasks — periodic health checks.
"""

import logging
from celery import shared_task
from django.utils import timezone
from .services import CHECKERS, perform_health_check

logger = logging.getLogger(__name__)

@shared_task(name="health.run_all_health_checks")
def run_all_health_checks():
    """
    Run all registered health checks.
    
    This is intended to run every 5 minutes via Celery Beat.
    It updates the ServiceHealthRecord for each service and emits/resolves
    OperatorAlerts accordingly.
    """
    logger.info("Starting system-wide health checks.")
    results = []
    for service_key in CHECKERS.keys():
        try:
            record = perform_health_check(service_key)
            results.append(f"{service_key}: {record.status}")
        except Exception as e:
            logger.error(f"Health check failed for {service_key}: {str(e)}", exc_info=True)
            results.append(f"{service_key}: FAILED_EXECUTION")
    
    logger.info(f"Health checks completed: {', '.join(results)}")
    return results

@shared_task(name="health.run_single_health_check")
def run_single_health_check(service_key: str):
    """Run a single health check (e.g. from the UI)."""
    try:
        record = perform_health_check(service_key)
        return {
            "status": record.status,
            "status_label": record.status_label,
            "last_check_at": record.last_check_at.isoformat()
        }
    except Exception as e:
        logger.error(f"Single health check failed for {service_key}: {str(e)}", exc_info=True)
        return {"status": "error", "message": str(e)}
