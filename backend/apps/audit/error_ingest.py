"""
Single entry point for writing ErrorLog rows.

Phase GT Step 3B. Every path that records an internal error — Celery
tasks, pipeline failures, slave-node forwards — goes through
`ingest_error()` so the dedup rules stay consistent:

1. Row identity = `(fingerprint, node_id)`. Same fingerprint from two
   different slaves = two rows (attribution preserved). Same fingerprint
   on the same node twice = one row, occurrence_count += 1.
2. Fingerprint = sha1(job_type | step | normalize(error_message)). The
   normaliser strips digits, UUIDs, file paths, and hex blobs so
   `"task 123 failed at /tmp/abc"` and `"task 456 failed at /tmp/def"`
   land on the same fingerprint.
3. Regression re-open: if an acknowledged row's fingerprint reoccurs,
   `acknowledged` flips back to False and the sparkline spikes — the
   operator sees the regression instead of a silent new duplicate row.
4. `how_to_fix` is populated from `fix_suggestions.suggest()` so every
   row has a plain-English fix hint.
5. `runtime_context` captures GPU / CUDA / embedding / spaCy state at
   crash time for post-mortem correlation.

`ingest_error()` never raises — producing an ErrorLog must not be able
to kill the task that was only trying to record its own failure.
"""

from __future__ import annotations

import hashlib
import logging
import re
import socket
from typing import NamedTuple, Optional

from django.db import IntegrityError, InternalError, transaction

from .fix_suggestions import suggest
from .models import ErrorLog
from .runtime_context import local_node_identity, snapshot as runtime_snapshot

logger = logging.getLogger(__name__)


# Strips digits (>=2), hex blobs (>=8 hex chars), UNIX-ish paths, and 0x
# pointer addresses, so that a message that only differs in ephemeral
# values still dedupes to the same fingerprint.
_NORMALIZE = re.compile(r"(\d{2,}|[0-9a-f]{8,}|/[/\w.\-]+|0x[0-9a-f]+)", re.IGNORECASE)


class _ErrorPayload(NamedTuple):
    """The user-supplied half of an ErrorLog row.

    Bundles the six kw-only args of :func:`ingest_error` so the internal
    helpers can pass them around as a single value instead of a 6-arg
    tail (the linter caps function arg count at 7; combined with the
    fingerprint+node tuple, an unbundled signature would tip over).
    """

    job_type: str
    step: str
    error_message: str
    raw_exception: str
    why: str
    severity: str


def _compute_fingerprint(job_type: str, step: str, msg: str) -> str:
    # SHA1 is fine here — we use it as a cheap dedup fingerprint, not a
    # cryptographic hash. `usedforsecurity=False` signals that to both
    # the Python runtime (FIPS-compliant builds) and to bandit.
    normalized = _NORMALIZE.sub("*", msg or "")
    return hashlib.sha1(
        f"{job_type}|{step}|{normalized}".encode(),
        usedforsecurity=False,
    ).hexdigest()


def _gather_context(
    job_type: str, step: str, error_message: str
) -> tuple[str, str, str, dict]:
    """Compute the dedup key and runtime context for a new error row.

    Returns ``(fingerprint, node_id, node_role, runtime_snapshot)``.
    """
    fp = _compute_fingerprint(job_type, step, error_message)
    node_id, node_role = local_node_identity()
    ctx = runtime_snapshot()
    return fp, node_id, node_role, ctx


def _bump_existing(
    existing: ErrorLog, raw_exception: str, severity: str, ctx: dict
) -> ErrorLog:
    """Mutate-in-place: bump count, regression-reopen, refresh raw/sev/ctx.

    Always flips ``acknowledged`` back to False so an operator who had
    dismissed the row sees the regression spike instead of a silent
    repeat.
    """
    existing.occurrence_count += 1
    existing.acknowledged = False
    if raw_exception:
        existing.raw_exception = raw_exception
    existing.severity = severity
    existing.runtime_context = ctx
    existing.save(
        update_fields=[
            "occurrence_count",
            "acknowledged",
            "raw_exception",
            "severity",
            "runtime_context",
        ]
    )
    return existing


def _create_new(
    fp: str,
    node_id: str,
    node_role: str,
    ctx: dict,
    payload: _ErrorPayload,
) -> ErrorLog:
    """Insert a new ErrorLog row with size-bounded fields and how_to_fix lookup."""
    return ErrorLog.objects.create(
        source=ErrorLog.SOURCE_INTERNAL,
        job_type=payload.job_type[:50],
        step=payload.step[:100],
        error_message=(payload.error_message or "")[:4000],
        raw_exception=payload.raw_exception or "",
        why=payload.why or "",
        how_to_fix=suggest(payload.error_message, fp, payload.step),
        fingerprint=fp,
        severity=payload.severity,
        node_id=node_id,
        node_role=node_role,
        node_hostname=socket.gethostname()[:255],
        runtime_context=ctx,
    )


def _dedup_or_create(
    *,
    fp: str,
    node_id: str,
    node_role: str,
    ctx: dict,
    payload: _ErrorPayload,
) -> Optional[ErrorLog]:
    """Inside ``transaction.atomic``: bump the matching row by
    ``(fingerprint, node_id)`` if one exists, otherwise insert a new one.

    On ``IntegrityError`` (a parallel worker raced us to the insert),
    fall back to :func:`_recover_race`.
    """
    try:
        with transaction.atomic():
            existing = (
                ErrorLog.objects.select_for_update()
                .filter(
                    fingerprint=fp,
                    node_id=node_id,
                    source=ErrorLog.SOURCE_INTERNAL,
                )
                .first()
            )
            if existing is not None:
                return _bump_existing(
                    existing, payload.raw_exception, payload.severity, ctx
                )
            return _create_new(fp, node_id, node_role, ctx, payload)
    except (IntegrityError, InternalError):
        # IntegrityError: a parallel worker raced us to the insert.
        # InternalError: we are in a failed transaction block — fall back
        # to a best-effort non-atomic read.
        return _recover_race(fp, node_id)


def _recover_race(fp: str, node_id: str) -> Optional[ErrorLog]:
    """A parallel worker beat us to the insert — fetch their row and bump it.

    Best-effort: if the recovery query itself fails, log and return None
    rather than raise (the public ``ingest_error`` contract is
    never-raises).
    """
    try:
        row = ErrorLog.objects.filter(fingerprint=fp, node_id=node_id).first()
        if row is not None:
            row.occurrence_count += 1
            row.acknowledged = False
            row.save(update_fields=["occurrence_count", "acknowledged"])
            return row
    except Exception:  # noqa: BLE001
        logger.exception("ingest_error race-recovery failed")
    return None


def ingest_error(
    *,
    job_type: str,
    step: str,
    error_message: str,
    raw_exception: str = "",
    why: str = "",
    severity: str = ErrorLog.SEVERITY_MEDIUM,
) -> Optional[ErrorLog]:
    """
    Insert-or-bump an ErrorLog row for the given failure.

    Returns the saved row, or None if writing failed (never raises).

    Slave-node forwarding: a slave worker running the same Django codebase
    against the shared Postgres hits this exact function — its
    `NODE_ID` / `NODE_ROLE` env vars get stamped into the new row, so
    attribution is automatic. No HTTP forwarder needed.
    """
    payload = _ErrorPayload(
        job_type=job_type,
        step=step,
        error_message=error_message,
        raw_exception=raw_exception,
        why=why,
        severity=severity,
    )
    try:
        from apps.core.services.async_context import in_async_context

        if in_async_context():
            logger.debug(
                "ingest_error skipped in async context for job_type=%s step=%s",
                job_type,
                step,
            )
            return None
        fp, node_id, node_role, ctx = _gather_context(job_type, step, error_message)
        row = _dedup_or_create(
            fp=fp, node_id=node_id, node_role=node_role, ctx=ctx, payload=payload
        )
    except Exception:  # noqa: BLE001
        logger.exception("ingest_error failed for job_type=%s step=%s", job_type, step)
        row = None
    _emit_ops_feed(row)
    return row


def _emit_ops_feed(row: Optional[ErrorLog]) -> None:
    """Phase OF — surface this ErrorLog as an ambient feed row."""
    if row is None:
        return
    try:
        from apps.ops_feed.services import emit as ops_emit

        ops_emit(
            event_type="error.ingested",
            source=row.job_type or "internal",
            plain_english=(
                f"Error: {row.error_message[:140]}"
                + (f" — Fix: {row.how_to_fix[:120]}" if row.how_to_fix else "")
            ),
            severity="error" if row.severity in ("critical", "high") else "warning",
            related_entity_type="error_log",
            related_entity_id=str(row.pk),
            error_log_id=row.pk,
            runtime_context=row.runtime_context or {},
        )
    except Exception:  # noqa: BLE001
        # Never let ops-feed emission break error ingestion.
        logger.debug("[error_ingest] ops-feed emission failed", exc_info=True)


__all__ = ["ingest_error"]
