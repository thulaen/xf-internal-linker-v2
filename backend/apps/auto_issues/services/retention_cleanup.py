"""90-day retention cleanup across the observability stores.

Pyroscope OSS 1.9 doesn't expose a `retention_period` config key in any
of `limits`, `compactor`, or `tracker` (verified empirically — the
server crashloops with `field retention_period not found` if added).
The pragmatic alternative: a daily filesystem cleanup that walks the
profile-block tree and deletes blocks older than the retention window.

This module ALSO handles the per-source store cleanups GlitchTip's
own retention doesn't cover:
  - `audit_errorlog` (the GlitchTip-mirror table) — Django ORM delete.
  - `auto_issues_autoissue` resolved rows older than 180 days — keep
    the recent 6 months for `lessons_learned` lookup; older ones
    accumulate noise.

GlitchTip's own event store is left alone — its boot log confirms a
90-day retention is already in place via internal partition rotation.
"""

from __future__ import annotations

import logging
import time
from datetime import timedelta
from pathlib import Path

from django.utils import timezone

logger = logging.getLogger(__name__)


# ── Pyroscope filesystem cleanup ─────────────────────────────────────────


# Mount path inside the Celery worker containers — see docker-compose.yml.
# Pyroscope itself writes to /data inside ITS container; the same named
# volume is mounted at /pyroscope-data inside celery-worker-default + -pipeline.
_PYROSCOPE_DATA_PATH = "/pyroscope-data"
_PYROSCOPE_RETENTION_DAYS = 90


def _cleanup_pyroscope_blocks() -> dict:
    """Delete profile blocks older than 90 days from the Pyroscope volume.

    Pyroscope OSS 1.9 doesn't expose a `retention_period` config knob, so
    we walk the data tree directly via pathlib. Files are deleted by mtime
    — Pyroscope's block layout writes a block once and never modifies it,
    so mtime is a reliable proxy for "block age".
    """
    root = Path(_PYROSCOPE_DATA_PATH)
    if not root.exists():
        logger.warning(
            "[retention.pyroscope] volume not mounted at %s — "
            "is celery-worker-default running with the pyroscope_data volume?",
            root,
        )
        return {"status": "skipped", "reason": f"{root} not mounted"}

    cutoff_ts = time.time() - (_PYROSCOPE_RETENTION_DAYS * 86400)
    deleted = 0
    failed = 0
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        try:
            if path.stat().st_mtime < cutoff_ts:
                path.unlink()
                deleted += 1
        except OSError as exc:
            logger.debug(
                "[retention.pyroscope] could not delete %s: %s", path, exc
            )
            failed += 1
    logger.info(
        "[retention.pyroscope] deleted=%d failed=%d (older than %d days)",
        deleted, failed, _PYROSCOPE_RETENTION_DAYS,
    )
    return {
        "status": "ok",
        "deleted_count": deleted,
        "failed_count": failed,
        "retention_days": _PYROSCOPE_RETENTION_DAYS,
    }


# ── audit_errorlog cleanup ───────────────────────────────────────────────


_ERRORLOG_RETENTION_DAYS = 90


def _cleanup_audit_errorlog() -> dict:
    """Delete `audit_errorlog` rows older than 90 days."""
    from apps.audit.models import ErrorLog

    cutoff = timezone.now() - timedelta(days=_ERRORLOG_RETENTION_DAYS)
    deleted, _ = ErrorLog.objects.filter(created_at__lt=cutoff).delete()
    logger.info(
        "[retention.audit_errorlog] deleted=%d (older than %d days)",
        deleted, _ERRORLOG_RETENTION_DAYS,
    )
    return {
        "status": "ok",
        "deleted_count": deleted,
        "retention_days": _ERRORLOG_RETENTION_DAYS,
    }


# ── auto_issues resolved-row cleanup ─────────────────────────────────────


_AUTO_ISSUES_RESOLVED_RETENTION_DAYS = 180


def _cleanup_auto_issues_resolved() -> dict:
    """Delete RESOLVED auto_issues older than 180 days.

    Keep the most recent 6 months for `lessons_learned` lookup via
    `manage.py search_resolved_issues`. Older ones accumulate noise
    and the lessons in them are usually long-since absorbed.
    """
    from apps.auto_issues.models import AutoIssue

    cutoff = timezone.now() - timedelta(days=_AUTO_ISSUES_RESOLVED_RETENTION_DAYS)
    qs = AutoIssue.objects.filter(
        status=AutoIssue.STATUS_RESOLVED, resolved_at__lt=cutoff
    )
    deleted, _ = qs.delete()
    logger.info(
        "[retention.auto_issues] deleted=%d resolved rows older than %d days",
        deleted, _AUTO_ISSUES_RESOLVED_RETENTION_DAYS,
    )
    return {
        "status": "ok",
        "deleted_count": deleted,
        "retention_days": _AUTO_ISSUES_RESOLVED_RETENTION_DAYS,
    }


# ── Public entry-point ───────────────────────────────────────────────────


def run_retention_cleanup() -> dict:
    """Run all three cleanups independently; a single failure does not block the others."""
    results: dict = {}
    for key, fn in [
        ("pyroscope", _cleanup_pyroscope_blocks),
        ("audit_errorlog", _cleanup_audit_errorlog),
        ("auto_issues", _cleanup_auto_issues_resolved),
    ]:
        try:
            results[key] = fn()
        except Exception as exc:
            logger.error("[retention.%s] cleanup failed: %s", key, exc)
            results[key] = {"status": "error", "error": str(exc)}
    overall_ok = all(v.get("status") != "error" for v in results.values())
    results["status"] = "ok" if overall_ok else "partial"
    return results
