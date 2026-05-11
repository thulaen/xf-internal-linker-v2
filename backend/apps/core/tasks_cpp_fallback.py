"""Phase 4.14 — Celery beat task that watches for C++ extension fallbacks.

Runs every 5 minutes (cheap; just imports a few extensions and checks
their state). Emits ops feed events on transition + once-per-hour
"still down" reminders while a fallback is active.

Storage discipline: the fallback-warning service stores one
``AppSetting`` row per extension (see
``apps.core.services.cpp_fallback_warning``). NO new tables.
"""

from __future__ import annotations

import logging

from celery import shared_task

from apps.core.helpers import HelperConstraint

logger = logging.getLogger(__name__)


@shared_task(
    name="core.cpp_fallback_check",
    time_limit=60,
    soft_time_limit=45,
    ignore_result=True,
)
@HelperConstraint(
    cpu_intensive=False,  # imports + state checks; no heavy compute
    gpu_required=False,
    storage_writes_to="postgres_main",
    ram_peak_mb=64,
    expected_seconds_p50=2,
)
def cpp_fallback_check() -> dict[str, int]:
    """Detect cpp↔python transitions; emit Operations Feed events.

    Plain-English: every 5 minutes, walk every C++ extension and see
    if any have dropped to the Python fallback path (or recovered).
    Each transition fires one ``cpp_extension.fallback_started`` or
    ``cpp_extension.fallback_recovered`` event so the operator sees
    a clear timeline of perf events instead of just feeling things
    get slow.

    Returns ``{events_emitted: N}`` so the operator can see it ran.
    """
    from django.db import connection

    from apps.core.services.cpp_fallback_warning import check_and_emit_fallback_events

    # Mandatory Prevention Sweep (#86): close stale connections before task logic.
    connection.close()

    events = check_and_emit_fallback_events()
    if events:
        logger.info(
            "cpp_fallback_check: emitted %d transition/persist events",
            len(events),
        )
    return {"events_emitted": len(events)}
