"""Monthly Top-50 link-suggestion Celery wrapper.

Fires on the 1st of each month at 09:00 UTC via Celery Beat (see
celery_schedules.py "monthly-top-50-suggestions"). The actual work lives in
the management command `run_monthly_top_50` so it stays callable from the
shell and from the "Run Now" button on the AI Agents page.
"""

from __future__ import annotations

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(
    name="pipeline.run_monthly_top_50_celery",
    time_limit=600,
    soft_time_limit=420,
)
def run_monthly_top_50_celery() -> dict:
    """Invoke the management command with strategy='auto' for the current UTC month."""
    from datetime import datetime, timezone

    from django.core.management import call_command

    month = datetime.now(timezone.utc).strftime("%Y-%m")
    call_command("run_monthly_top_50", month=month, strategy="python")
    return {"month": month, "strategy": "python"}
