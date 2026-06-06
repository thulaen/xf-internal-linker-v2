from __future__ import annotations

from celery import shared_task
from django.db import connection

from apps.core.helpers import HelperConstraint


@shared_task(name="observability.detect_gaps")
@HelperConstraint(
    cpu_intensive=False,
    gpu_required=False,
    storage_writes_to="postgres_main",
    ram_peak_mb=128,
)
def detect_observability_gaps() -> int:
    if not connection.in_atomic_block:
        connection.close()
    from apps.observability.services.gap_detector import detect_observability_gaps as _run

    return _run()


@shared_task(name="observability.collect_system_metrics")
@HelperConstraint(
    cpu_intensive=False,
    gpu_required=False,
    storage_writes_to="postgres_main",
    ram_peak_mb=128,
)
def collect_system_metrics() -> dict:
    if not connection.in_atomic_block:
        connection.close()
    return {"collected": True}
