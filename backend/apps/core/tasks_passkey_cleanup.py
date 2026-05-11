"""Celery task to prune expired ``PasskeyChallenge`` rows.

Plain-English: WebAuthn issues a one-time challenge for each
register/login ceremony. The challenge has a 5-minute TTL; once it
expires it can never be redeemed, so the row is dead weight.

The login/register *finish* handlers prune expired rows opportunistically,
but if a user starts a ceremony and never finishes (closes the tab,
hits cancel, hits a network error), the row sits around forever. This
task sweeps stragglers every 6 hours.

Schedule: ``backend/config/settings/celery_schedules.py`` —
``passkey-cleanup-expired-challenges`` entry. Idempotent: if there's
nothing to delete, it returns 0 and exits.

Manual trigger:
    docker compose exec backend \\
        celery -A config.celery call core.passkey_cleanup_expired_challenges
"""

from __future__ import annotations

import logging

from celery import shared_task

from apps.core.helpers import HelperConstraint
from django.db import connection

logger = logging.getLogger(__name__)


@shared_task(
    name="core.passkey_cleanup_expired_challenges",
    time_limit=120,
    soft_time_limit=60,
)
@HelperConstraint(
    cpu_intensive=False,
    gpu_required=False,
    storage_writes_to="postgres_main",
    ram_peak_mb=64,
    expected_seconds_p50=2,
)
def passkey_cleanup_expired_challenges() -> dict:
    # Mandatory Prevention Sweep (#86): close stale connections before task logic.
    connection.close()

    """Delete every ``PasskeyChallenge`` whose ``expires_at`` is in the past."""
    from django.utils import timezone

    from apps.core.models import PasskeyChallenge

    deleted, _detail = PasskeyChallenge.objects.filter(
        expires_at__lt=timezone.now()
    ).delete()
    if deleted:
        logger.info("passkey_cleanup_expired_challenges: pruned %s rows", deleted)
    return {"deleted_challenges": int(deleted)}
