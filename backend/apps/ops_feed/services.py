"""
Phase OF — Operations Feed emitter.

Single `emit()` entry point all subsystems call. Handles:
  * 60-second dedup (merges repeats into one row with `occurrence_count`)
  * real-time broadcast over the `operations.feed` topic (Phase R0)
  * best-effort failure — a broken realtime broker must never crash the
    subsystem that called us.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import timedelta
from typing import Mapping

from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)

_DEDUP_WINDOW_SECONDS = 60
_REALTIME_TOPIC = "operations.feed"


def _make_dedup_key(
    event_type: str,
    source: str,
    related_entity_type: str,
    related_entity_id: str,
) -> str:
    """Stable short hash covering the tuple the plan specified.

    SHA1 is used as a cheap dedup key, not a cryptographic hash —
    `usedforsecurity=False` tells both the runtime and bandit that.
    """
    raw = f"{event_type}|{source}|{related_entity_type}|{related_entity_id}".encode()
    return hashlib.sha1(raw, usedforsecurity=False).hexdigest()[:20]


def _update_event(
    event,
    plain_english: str,
    severity: str,
    runtime_context: Mapping[str, object] | None,
    error_log_id: int | None,
) -> None:
    event.occurrence_count = (event.occurrence_count or 1) + 1
    event.plain_english = plain_english
    event.severity = severity
    event.runtime_context = dict(runtime_context or {})
    event.error_log_id = error_log_id
    event.save(
        update_fields=[
            "occurrence_count",
            "plain_english",
            "severity",
            "runtime_context",
            "error_log_id",
        ]
    )


def emit(
    event_type: str,
    plain_english: str,
    *,
    source: str = "",
    severity: str = "info",
    related_entity_type: str = "",
    related_entity_id: str = "",
    runtime_context: Mapping[str, object] | None = None,
    error_log_id: int | None = None,
) -> None:
    """Record one ambient event and push it to connected clients.

    Safe to call from inside a transaction; the dedup update uses
    ``select_for_update`` on the matching row so concurrent writers
    collapse onto one counter bump instead of racing.
    """
    try:
        from .models import OperationEvent

        dedup_key = _make_dedup_key(
            event_type, source, related_entity_type, related_entity_id
        )

        # Schema-enforced dedup since 2026-05-10 (AutoIssue #10):
        # `dedup_key` carries a partial UniqueConstraint on non-blank
        # values. The previous 60-second window logic is now redundant
        # at the DB level — there is at most one row per dedup_key.
        # The application still bumps occurrence_count + refreshes
        # plain_english/severity on each emission so the UI shows the
        # most recent wording. Race-safe via select_for_update.
        from django.db import IntegrityError
        from django.db.models import F

        # Phase OF — Optimized Upsert Pattern (AutoIssue #118).
        # We use update() first as it's the 99% case for repeats and is 
        # naturally race-safe (atomic increment).
        updated = OperationEvent.objects.filter(dedup_key=dedup_key).update(
            occurrence_count=F("occurrence_count") + 1,
            plain_english=plain_english,
            severity=severity
            if severity in {c[0] for c in OperationEvent.SEVERITY_CHOICES}
            else "info",
            runtime_context=dict(runtime_context or {}),
            error_log_id=error_log_id,
            timestamp=timezone.now(),
        )

        if updated:
            # Re-fetch the row we just updated to broadcast it.
            # Using .first() is safer than .get() if legacy data has duplicates.
            row = OperationEvent.objects.filter(dedup_key=dedup_key).first()
        else:
            # Row doesn't exist. Try to create it. 
            # We handle the race where another thread creates it between our 
            # update and create calls.
            try:
                with transaction.atomic():
                    row = OperationEvent.objects.create(
                        event_type=event_type[:60],
                        source=source[:60],
                        plain_english=plain_english,
                        severity=severity
                        if severity in {c[0] for c in OperationEvent.SEVERITY_CHOICES}
                        else "info",
                        related_entity_type=related_entity_type[:60],
                        related_entity_id=str(related_entity_id)[:100],
                        runtime_context=dict(runtime_context or {}),
                        dedup_key=dedup_key,
                        error_log_id=error_log_id,
                    )
            except IntegrityError:
                # Someone else created it. Update the existing one.
                OperationEvent.objects.filter(dedup_key=dedup_key).update(
                    occurrence_count=F("occurrence_count") + 1,
                    plain_english=plain_english,
                    severity=severity
                    if severity in {c[0] for c in OperationEvent.SEVERITY_CHOICES}
                    else "info",
                    runtime_context=dict(runtime_context or {}),
                    error_log_id=error_log_id,
                    timestamp=timezone.now(),
                )
                row = OperationEvent.objects.filter(dedup_key=dedup_key).first()

        if row:
            _broadcast(row)
    except Exception:  # noqa: BLE001
        # Emission is observability glue — never let it bring down the
        # caller. A dropped event is better than a dropped import task.
        logger.debug("[ops_feed.emit] failed", exc_info=True)


def _broadcast(row) -> None:  # type: ignore[no-untyped-def]
    try:
        from apps.realtime.services import broadcast

        broadcast(
            _REALTIME_TOPIC,
            "event.appended",
            {
                "id": row.pk,
                "timestamp": row.timestamp.isoformat() if row.timestamp else None,
                "event_type": row.event_type,
                "source": row.source,
                "severity": row.severity,
                "plain_english": row.plain_english,
                "related_entity_type": row.related_entity_type,
                "related_entity_id": row.related_entity_id,
                "runtime_context": row.runtime_context or {},
                "occurrence_count": row.occurrence_count,
                "error_log_id": row.error_log_id,
            },
        )
    except Exception:  # noqa: BLE001
        logger.debug("[ops_feed._broadcast] failed", exc_info=True)


__all__ = ["emit"]
