from __future__ import annotations

from celery import shared_task
from django.db import connection

from apps.core.helpers import HelperConstraint


@shared_task(name="work_queue.refresh_projection")
@HelperConstraint(
    cpu_intensive=False,
    gpu_required=False,
    storage_writes_to="postgres_main",
    ram_peak_mb=256,
    expected_seconds_p50=5,
)
def refresh_projection() -> dict:
    if not connection.in_atomic_block:
        connection.close()
    from apps.work_queue.api import build_overview

    return build_overview(limit=12)
