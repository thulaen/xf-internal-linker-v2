"""
Phase 4.9 — Pipeline internal health and resource state tasks.
"""

import logging
from celery import shared_task
from django.db import connection
from apps.core.helpers import HelperConstraint

logger = logging.getLogger(__name__)


@shared_task(
    name="pipeline.refresh_disk_pressure_state",
    time_limit=30,
    soft_time_limit=20,
)
@HelperConstraint(storage_writes_to="redis", ram_peak_mb=128, expected_seconds_p50=5)
def refresh_disk_pressure_state() -> dict:
    """Beat-driven refresh of the cached disk-pressure state."""
    if not connection.in_atomic_block:
        connection.close()

    from apps.pipeline.services.disk_pressure import (
        refresh_disk_pressure_state as _refresh,
    )

    state = _refresh()
    return {"state": state}


@shared_task(
    name="pipeline.cpp_fallback_share_check",
    time_limit=60,
    soft_time_limit=45,
)
@HelperConstraint(ram_peak_mb=128, expected_seconds_p50=10)
def cpp_fallback_share_check() -> dict:
    """Daily check that the Stage-2 Python-fallback share is below the alert
    threshold (FR-247).
    """
    if not connection.in_atomic_block:
        connection.close()

    from apps.pipeline.services.pipeline_stages import (
        get_stage2_path_runtime_status,
    )

    status = get_stage2_path_runtime_status()
    python_share = float(status.get("python_share", 0.0) or 0.0)
    threshold = float(status.get("alert_threshold", 0.05) or 0.05)
    if python_share <= threshold:
        return {"share": python_share, "threshold": threshold, "alert": False}
    try:
        from apps.auto_issues.models import AutoIssue
        from apps.auto_issues.services.dedup import upsert_dedup, IssueObservation

        canonical = "cpp_fallback_share_above_threshold"
        upsert_dedup(**IssueObservation(
            canonical=canonical,
            source="internal",
            external_id=canonical,
            fingerprint=canonical,
            title=(
                f"C++ Stage-2 fallback share {python_share:.1%} > threshold "
                f"{threshold:.1%}"
            ),
            description=(
                f"FR-247 SLO breach: the Python fallback path served "
                f"{python_share:.1%} of Stage-2 sentence scoring runs, above "
                f"the configured alert threshold of {threshold:.1%}.\n\n"
                "Re-run `scripts/build-native-extensions.ps1` or `cd backend/extensions "
                "&& pip install -e .` and restart the backend image."
            ),
            affected_files=[
                "backend/apps/pipeline/services/pipeline_stages.py",
                "backend/extensions/simsearch.cpp",
            ],
            severity=AutoIssue.SEVERITY_HIGH,
            priority_score=72.0,
            occurrence_count=1,
        ).__dict__)
    except Exception:
        logger.exception("cpp_fallback_share_check: AutoIssue insert failed")
    return {"share": python_share, "threshold": threshold, "alert": True}
