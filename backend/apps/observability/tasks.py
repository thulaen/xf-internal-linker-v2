from __future__ import annotations

from celery import shared_task
from django.db import connection


@shared_task(name="observability.detect_gaps")
def detect_observability_gaps() -> int:
    if not connection.in_atomic_block:
        connection.close()
    from apps.observability.services.gap_detector import detect_observability_gaps as _run

    return _run()


@shared_task(name="observability.collect_system_metrics")
def collect_system_metrics() -> dict:
    if not connection.in_atomic_block:
        connection.close()
    return {"collected": True}

