"""Phase 4.11 — Celery beat task that recomputes the cert verdict daily.

The cert is a thin aggregation over the latest BenchmarkRun (no
benchmark execution here — that's ``apps.benchmarks.services.runner``).
Cheap (~1-2 s); safe to run daily so the dashboard chip is always
fresh even if no operator hit the run-now endpoint recently.

Storage discipline: 2 AppSetting rows total via update_or_create (see
``apps.core.services.performance_certification``). NO new tables.
"""

from __future__ import annotations

import logging

from celery import shared_task

from apps.core.helpers import HelperConstraint
from django.db import connection

logger = logging.getLogger(__name__)


@shared_task(
    name="core.performance_cert_recompute",
    time_limit=60,
    soft_time_limit=45,
    ignore_result=True,
)
@HelperConstraint(
    cpu_intensive=False,  # pure aggregation over an existing run
    gpu_required=False,
    storage_writes_to="postgres_main",
    ram_peak_mb=64,
    expected_seconds_p50=2,
)
def performance_cert_recompute() -> dict[str, str]:
    if not connection.in_atomic_block:
        connection.close()

    """Refresh the cert verdict from the latest completed BenchmarkRun.

    Returns ``{verdict: "pass"|"warn"|"fail"|"unknown"}`` so the
    operator can see what the cert is when looking at the task result.
    """
    from apps.core.services.performance_certification import (
        run_performance_certification,
    )

    verdict = run_performance_certification()
    if verdict.verdict in ("fail", "warn"):
        logger.warning(
            "performance_cert: %s verdict — %s",
            verdict.verdict,
            verdict.label,
        )
    return {"verdict": verdict.verdict}
