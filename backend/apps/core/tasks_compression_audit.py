"""Phase 4.9 — Celery beat task that runs the weekly compression audit.

The audit walks ~10 candidate tables, samples 1000 rows each, measures
zlib compression ratio, and persists a top-10 "would benefit from
compression" report. Read-only — no rows are actually compressed.

Storage discipline: the audit service persists ONE AppSetting row +
ONE timestamp row (see ``apps.core.services.compression_audit``).
NO new tables.
"""

from __future__ import annotations

import logging

from celery import shared_task

from apps.core.helpers import HelperConstraint

logger = logging.getLogger(__name__)


@shared_task(
    name="core.compression_audit",
    time_limit=600,
    soft_time_limit=540,
    ignore_result=True,
)
@HelperConstraint(
    cpu_intensive=True,             # zlib.compress on ~10k rows
    gpu_required=False,
    storage_writes_to="postgres_main",
    ram_peak_mb=256,
    expected_seconds_p50=120,
)
def compression_audit_run() -> dict[str, int]:
    """Walk every candidate table; persist a top-10 savings report.

    Plain-English: every Sunday at 03:00 UTC, scan ~10 known-large
    tables (JSON diagnostics blobs, BinaryField vectors, the
    SupersededEmbedding archive). For each, sample 1000 rows, run
    them through zlib, and report the projected disk savings if the
    operator chose to compress that column going forward.

    Operator views the report via ``GET /api/system/compression-audit/``.

    Returns ``{candidates: N, total_savings_mb: M}`` so the operator
    can see the run completed.
    """
    from apps.core.services.compression_audit import run_compression_audit

    report = run_compression_audit()
    total_mb = report.total_estimated_savings_bytes // (1024 * 1024)
    if report.candidates:
        logger.info(
            "compression_audit: top candidate %s would save ~%d MB; "
            "total across top-%d = ~%d MB",
            report.candidates[0].table_label,
            report.candidates[0].estimated_savings_bytes // (1024 * 1024),
            len(report.candidates),
            total_mb,
        )
    return {
        "candidates": len(report.candidates),
        "total_savings_mb": int(total_mb),
    }
