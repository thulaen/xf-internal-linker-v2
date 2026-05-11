"""Phase 2.18 — Celery task that refreshes dashboard materialised views.

Runs every 5 minutes via Celery Beat. Uses
``REFRESH MATERIALIZED VIEW CONCURRENTLY`` so dashboard reads never block.
The 5-minute window is short enough that operator decisions stay accurate
and long enough that the matview refresh cost is negligible compared to
the per-request savings on the dashboard view.

Citation: PostgreSQL docs §38.3.

Add the schedule to ``backend/config/settings/celery_schedules.py``::

    "core.refresh_dashboard_matviews": {
        "task": "core.refresh_dashboard_matviews",
        "schedule": 300.0,  # 5 minutes
    },
"""

from __future__ import annotations

import logging

from celery import shared_task

from apps.core.helpers import HelperConstraint
from django.db import connection

logger = logging.getLogger(__name__)


@shared_task(name="core.refresh_dashboard_matviews", time_limit=120, soft_time_limit=90)
@HelperConstraint(
    cpu_intensive=False,
    gpu_required=False,
    storage_writes_to="postgres_main",
    ram_peak_mb=256,
)
def refresh_dashboard_matviews() -> dict[str, bool]:
    # Mandatory Prevention Sweep (#86): close stale connections before task logic.
    connection.close()

    """Refresh every dashboard materialised view.

    Returns a status dict so the operator (or alerting layer) can see which
    matviews succeeded. Each refresh is independent — one failure doesn't
    block the others.
    """
    from apps.core.services.dashboard_aggregates import (
        refresh_suggestion_counts_matview,
    )

    results = {
        "dashboard_suggestion_counts_mv": refresh_suggestion_counts_matview(
            concurrently=True
        ),
    }

    failed = [name for name, ok in results.items() if not ok]
    if failed:
        logger.warning(
            "[refresh_dashboard_matviews] failed to refresh: %s", ", ".join(failed)
        )
    else:
        logger.info("[refresh_dashboard_matviews] all matviews refreshed")
    return results
