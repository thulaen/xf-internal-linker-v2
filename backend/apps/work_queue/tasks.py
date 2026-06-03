from __future__ import annotations

from celery import shared_task
from django.db import connection


@shared_task(name="work_queue.refresh_projection")
def refresh_projection() -> dict:
    if not connection.in_atomic_block:
        connection.close()
    from apps.work_queue.api import build_overview

    return build_overview(limit=12)

