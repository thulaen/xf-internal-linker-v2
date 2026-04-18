"""Suggestions app Celery tasks.

Per BUSINESS-LOGIC-CHECKLIST §6.3 every persistent telemetry table must have
an automated pruning task. This module holds those tasks for the suggestions
app (currently: RejectedPair).
"""

from __future__ import annotations

import logging
from datetime import timedelta

from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task(name="suggestions.prune_rejected_pairs")
def prune_rejected_pairs() -> dict[str, int]:
    """Delete RejectedPair rows older than REJECTED_PAIR_PRUNE_AFTER_DAYS.

    These rows are well past the suppression window (SUPPRESSION_DAYS = 90,
    PRUNE_AFTER_DAYS = 365) and no longer influence candidate generation, so
    keeping them only grows the table. Scheduled weekly (Sunday 22:25 UTC).

    Returns a dict with ``deleted`` and ``remaining`` counts for the operator.
    """
    from .models import REJECTED_PAIR_PRUNE_AFTER_DAYS, RejectedPair

    threshold = timezone.now() - timedelta(days=REJECTED_PAIR_PRUNE_AFTER_DAYS)
    deleted_count, _ = RejectedPair.objects.filter(
        last_rejected_at__lt=threshold,
    ).delete()
    remaining = RejectedPair.objects.count()
    logger.info(
        "prune_rejected_pairs: deleted %d rows, %d remaining",
        deleted_count,
        remaining,
    )
    return {"deleted": deleted_count, "remaining": remaining}
