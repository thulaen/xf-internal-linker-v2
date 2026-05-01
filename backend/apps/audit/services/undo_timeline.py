"""Phase 4.1 — Undo History Timeline service.

Reads the existing ``AuditEvent`` table (Codex Slice 5, 2026-04-30) and
exposes:

    1. ``list_restorable_events()`` — paginated/filtered list of state
       changes the operator can roll back. Includes the human-readable
       diff (old vs new) parsed from the event metadata.
    2. ``restore_event(event_id, ...)`` — applies the inverse of one
       audit event. Currently supports settings (AppSetting key/value)
       and weight-preset payloads; extends incrementally per spec.

Storage discipline: NO new tables. Restore actions emit a NEW
``AuditEvent`` row with ``action="restore_<original>"`` so the rollback
itself is in the timeline (operator can rollback a rollback). AuditEvent
TTL is already wired into ``nightly_data_retention``.

Citations: pattern derived from Fowler 2005 "Event Sourcing" + the
existing AuditEvent model. Idempotent restore semantics borrowed from
PostgreSQL UPSERT.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from django.db.models import Q
from django.utils import timezone

from apps.audit.models import AuditEvent

logger = logging.getLogger(__name__)


# Subject types the restore action knows how to roll back. Each entry
# maps to a small handler in ``_RESTORE_HANDLERS``. Anything not in
# this set returns "not_restorable" with a helpful message.
SUPPORTED_SUBJECT_TYPES = {
    "appsetting",
    "weightpreset",
}

# Default lookback window for the timeline list endpoint (days).
DEFAULT_LOOKBACK_DAYS = 30


@dataclass(frozen=True, slots=True)
class TimelineEntry:
    """One restorable audit event surfaced to the operator."""

    id: int
    action: str
    subject_type: str
    subject_id: str
    actor: str
    message: str
    created_at: str  # ISO 8601
    old_value: Any = None
    new_value: Any = None
    is_restorable: bool = False
    not_restorable_reason: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class RestoreResult:
    """Outcome of a restore action."""

    ok: bool
    message: str
    new_event_id: int | None = None


def list_restorable_events(
    *,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    subject_type_filter: str | None = None,
    actor_filter: str | None = None,
    limit: int = 100,
) -> list[TimelineEntry]:
    """Return the most recent restorable events, newest first.

    Filters:
        * ``lookback_days`` — only events from the last N days (default 30).
        * ``subject_type_filter`` — restrict to a single subject_type
          (e.g. "appsetting" for settings-only view).
        * ``actor_filter`` — restrict to events caused by one operator.
        * ``limit`` — max rows returned (default 100; UI paginates).
    """
    since = timezone.now() - timedelta(days=max(lookback_days, 1))
    qs = AuditEvent.objects.filter(created_at__gte=since)
    if subject_type_filter:
        qs = qs.filter(subject_type=subject_type_filter.lower())
    if actor_filter:
        qs = qs.filter(actor__iexact=actor_filter)
    qs = qs.order_by("-created_at")[: max(1, min(limit, 500))]

    entries: list[TimelineEntry] = []
    for ev in qs:
        entries.append(_to_timeline_entry(ev))
    return entries


def restore_event(
    event_id: int,
    *,
    actor: str = "",
    request=None,
) -> RestoreResult:
    """Apply the inverse of one AuditEvent. Idempotent + safe.

    Plain-English: looks up the event by id, reads its old/new values
    from the metadata, and writes the OLD value back into the system.
    Records a NEW AuditEvent for the rollback so the timeline stays
    honest. If the event isn't restorable (unsupported subject_type,
    missing old value, etc.), returns ``ok=False`` with a clear
    message — never raises.
    """
    try:
        ev = AuditEvent.objects.filter(pk=event_id).first()
    except Exception:
        logger.warning("undo_timeline: lookup failed for event %s", event_id, exc_info=True)
        return RestoreResult(ok=False, message="Could not look up that event in the audit table.")
    if ev is None:
        return RestoreResult(ok=False, message=f"No audit event with id {event_id}.")

    subject_type = ev.subject_type.lower()
    if subject_type not in SUPPORTED_SUBJECT_TYPES:
        return RestoreResult(
            ok=False,
            message=(
                f"Restoring '{subject_type}' isn't supported yet — only "
                f"{sorted(SUPPORTED_SUBJECT_TYPES)} can be rolled back."
            ),
        )

    handler = _RESTORE_HANDLERS.get(subject_type)
    if handler is None:
        return RestoreResult(
            ok=False,
            message=f"No restore handler is wired for subject_type='{subject_type}'.",
        )

    try:
        return handler(ev, actor=actor, request=request)
    except Exception as exc:
        logger.warning(
            "undo_timeline: restore handler for %s failed: %s",
            subject_type,
            exc,
            exc_info=True,
        )
        # Phase 4 / TECH-DEBT-MANDATE — surface to /error-log dedup.
        try:
            from apps.audit.error_ingest import ingest_error
            from apps.audit.models import ErrorLog

            ingest_error(
                job_type="undo_timeline",
                step=f"restore_{subject_type}",
                error_message=str(exc),
                raw_exception=repr(exc),
                why=f"Operator-triggered restore of audit event {event_id} failed.",
                severity=ErrorLog.SEVERITY_LOW,
            )
        except Exception:  # noqa: forbidden-pattern silent-except — best-effort error-log write must not mask the underlying handler failure surfaced via RestoreResult.
            pass
        return RestoreResult(
            ok=False,
            message=f"Restore failed: {exc}. The original event is unchanged; nothing was written.",
        )


# ── Per-subject-type restore handlers ─────────────────────────────


def _restore_appsetting(
    ev: AuditEvent, *, actor: str = "", request=None
) -> RestoreResult:
    """Roll back a single AppSetting key to its prior value."""
    metadata = ev.metadata or {}
    key = metadata.get("key") or ev.subject_id
    if not key:
        return RestoreResult(
            ok=False,
            message="Original event metadata has no 'key' field — can't identify which setting to restore.",
        )
    if "old_value" not in metadata:
        return RestoreResult(
            ok=False,
            message=(
                "Original event has no 'old_value' field — restore needs the prior value. "
                "This setting may have been changed by older code that didn't capture the previous state."
            ),
        )
    old_value = metadata.get("old_value")

    from apps.core.models import AppSetting

    AppSetting.objects.update_or_create(
        key=str(key),
        defaults={"value": "" if old_value is None else str(old_value)},
    )

    # Emit a new audit event for the rollback so the timeline shows
    # what the operator did. The new metadata mirrors the old/new flip.
    new_value_now = metadata.get("new_value")
    new_event = _emit_restore_event(
        original=ev,
        actor=actor,
        request=request,
        flipped_metadata={
            "key": str(key),
            "old_value": new_value_now,
            "new_value": old_value,
            "restored_from_event_id": ev.pk,
        },
    )
    return RestoreResult(
        ok=True,
        message=f"Restored AppSetting '{key}' to its prior value.",
        new_event_id=new_event.pk if new_event else None,
    )


def _restore_weightpreset(
    ev: AuditEvent, *, actor: str = "", request=None
) -> RestoreResult:
    """Roll back a weight preset's payload to its prior version."""
    metadata = ev.metadata or {}
    preset_name = metadata.get("preset_name") or ev.subject_id
    if not preset_name:
        return RestoreResult(
            ok=False,
            message="Original event metadata has no 'preset_name' — can't identify which preset to restore.",
        )
    if "old_weights" not in metadata:
        return RestoreResult(
            ok=False,
            message=(
                "Original event has no 'old_weights' field — restore needs the prior payload."
            ),
        )
    old_weights = metadata.get("old_weights")

    try:
        from apps.suggestions.models import WeightPreset
    except ImportError:
        return RestoreResult(ok=False, message="WeightPreset model not installed.")

    preset = WeightPreset.objects.filter(name=str(preset_name)).first()
    if preset is None:
        return RestoreResult(
            ok=False,
            message=f"No WeightPreset named '{preset_name}' exists to restore into.",
        )
    new_weights_now = preset.weights
    preset.weights = old_weights or {}
    preset.save(update_fields=["weights", "updated_at"])

    new_event = _emit_restore_event(
        original=ev,
        actor=actor,
        request=request,
        flipped_metadata={
            "preset_name": str(preset_name),
            "old_weights": new_weights_now,
            "new_weights": old_weights,
            "restored_from_event_id": ev.pk,
        },
    )
    return RestoreResult(
        ok=True,
        message=f"Restored WeightPreset '{preset_name}' to its prior weights.",
        new_event_id=new_event.pk if new_event else None,
    )


_RESTORE_HANDLERS = {
    "appsetting": _restore_appsetting,
    "weightpreset": _restore_weightpreset,
}


# ── Helpers ───────────────────────────────────────────────────────


def _emit_restore_event(
    *,
    original: AuditEvent,
    actor: str,
    request,
    flipped_metadata: dict[str, Any],
) -> AuditEvent | None:
    """Record a new AuditEvent describing the restore action."""
    try:
        from apps.audit.services.audit_logger import record_audit

        return record_audit(
            action=f"restore_{original.action}",
            subject=(original.subject_type, original.subject_id),
            actor=actor,
            request=request,
            message=f"Operator restored {original.subject_type} '{original.subject_id}' to its prior value.",
            metadata=flipped_metadata,
        )
    except Exception:
        logger.debug("undo_timeline: failed to emit restore audit event", exc_info=True)
        return None


def _to_timeline_entry(ev: AuditEvent) -> TimelineEntry:
    """Convert an AuditEvent ORM row to a UI-shaped TimelineEntry."""
    metadata = ev.metadata or {}
    subject_type = ev.subject_type.lower()

    # AppSetting events use {key, old_value, new_value}.
    # WeightPreset events use {preset_name, old_weights, new_weights}.
    old_value = metadata.get("old_value", metadata.get("old_weights"))
    new_value = metadata.get("new_value", metadata.get("new_weights"))

    is_restorable = subject_type in SUPPORTED_SUBJECT_TYPES and (
        "old_value" in metadata or "old_weights" in metadata
    )
    not_restorable_reason = ""
    if not is_restorable:
        if subject_type not in SUPPORTED_SUBJECT_TYPES:
            not_restorable_reason = (
                f"Subject type '{subject_type}' isn't restorable yet."
            )
        else:
            not_restorable_reason = (
                "Original event didn't capture the prior value — older code path."
            )

    return TimelineEntry(
        id=ev.pk,
        action=ev.action,
        subject_type=ev.subject_type,
        subject_id=ev.subject_id,
        actor=ev.actor,
        message=ev.message,
        created_at=ev.created_at.isoformat(),
        old_value=old_value,
        new_value=new_value,
        is_restorable=is_restorable,
        not_restorable_reason=not_restorable_reason,
        metadata=metadata,
    )
