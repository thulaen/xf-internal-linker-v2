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
    """Stable short hash covering the tuple the plan specified."""
    raw = f"{event_type}|{source}|{related_entity_type}|{related_entity_id}".encode()
    return hashlib.sha1(raw).hexdigest()[:20]


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
        cutoff = timezone.now() - timedelta(seconds=_DEDUP_WINDOW_SECONDS)

        with transaction.atomic():
            existing = (
                OperationEvent.objects.select_for_update(skip_locked=True)
                .filter(dedup_key=dedup_key, timestamp__gte=cutoff)
                .order_by("-timestamp")
                .first()
            )
            if existing is not None:
                existing.occurrence_count = (existing.occurrence_count or 1) + 1
                # Update payload to latest — the most recent wording wins
                # so the UI reflects current state instead of the first
                # event's stale copy.
                existing.plain_english = plain_english
                existing.severity = severity
                existing.runtime_context = dict(runtime_context or {})
                existing.error_log_id = error_log_id
                existing.save(
                    update_fields=[
                        "occurrence_count",
                        "plain_english",
                        "severity",
                        "runtime_context",
                        "error_log_id",
                    ]
                )
                row = existing
            else:
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
