"""
Notification service — emit_operator_alert and related helpers.

All alert creation must go through emit_operator_alert so that deduplication,
cooldown, and WebSocket fan-out are applied consistently.
"""

import logging
from datetime import timedelta

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.utils import timezone

from .models import AlertDeliveryAttempt, OperatorAlert

logger = logging.getLogger(__name__)

# Default cooldown windows by severity (seconds)
_COOLDOWN_BY_SEVERITY: dict[str, int] = {
    OperatorAlert.SEVERITY_INFO: 900,       # 15 min
    OperatorAlert.SEVERITY_SUCCESS: 900,
    OperatorAlert.SEVERITY_WARNING: 900,
    OperatorAlert.SEVERITY_ERROR: 900,
    OperatorAlert.SEVERITY_URGENT: 300,     # 5 min — urgent events repeat faster
}

_NOTIFICATION_GROUP = "notifications_global"


def emit_operator_alert(
    event_type: str,
    severity: str,
    title: str,
    message: str,
    *,
    source_area: str = OperatorAlert.AREA_SYSTEM,
    dedupe_key: str,
    related_object_type: str = "",
    related_object_id: str = "",
    related_route: str = "",
    payload: dict | None = None,
    error_log_id: int | None = None,
    cooldown_seconds: int | None = None,
) -> OperatorAlert:
    """
    Create or increment an OperatorAlert and push it to connected clients.

    If an alert with the same dedupe_key exists and its last_seen_at is within
    the cooldown window, the existing row is updated (occurrence_count++) rather
    than creating a new row.  The WebSocket event is still published so the
    frontend can update its badge count.

    The underlying job or task must still fail/complete honestly if this call
    raises — the try/except in callers should never swallow the original error.
    """
    now = timezone.now()
    cooldown = cooldown_seconds if cooldown_seconds is not None else _COOLDOWN_BY_SEVERITY.get(severity, 900)
    cutoff = now - timedelta(seconds=cooldown)

    # Try to find an existing alert within the cooldown window
    existing = (
        OperatorAlert.objects.filter(
            dedupe_key=dedupe_key,
            last_seen_at__gte=cutoff,
        )
        .exclude(status=OperatorAlert.STATUS_RESOLVED)
        .order_by("-last_seen_at")
        .first()
    )

    if existing:
        existing.occurrence_count += 1
        existing.last_seen_at = now
        # Re-open a read/acknowledged alert if the same event fires again
        if existing.status in (OperatorAlert.STATUS_READ, OperatorAlert.STATUS_ACKNOWLEDGED):
            existing.status = OperatorAlert.STATUS_UNREAD
            existing.read_at = None
            existing.acknowledged_at = None
        existing.save(update_fields=["occurrence_count", "last_seen_at", "status", "read_at", "acknowledged_at"])
        alert = existing
    else:
        error_log = None
        if error_log_id is not None:
            try:
                from apps.audit.models import ErrorLog
                error_log = ErrorLog.objects.get(pk=error_log_id)
            except ErrorLog.DoesNotExist:
                pass
            except Exception:
                logger.debug("Failed to fetch ErrorLog %s", error_log_id, exc_info=True)

        alert = OperatorAlert.objects.create(
            event_type=event_type,
            severity=severity,
            title=title,
            message=message,
            source_area=source_area,
            dedupe_key=dedupe_key,
            related_object_type=related_object_type,
            related_object_id=related_object_id,
            related_route=related_route,
            payload=payload or {},
            error_log=error_log,
            first_seen_at=now,
            last_seen_at=now,
        )

        # Log in_app delivery as "sent" for every new alert
        AlertDeliveryAttempt.objects.create(
            alert=alert,
            channel=AlertDeliveryAttempt.CHANNEL_IN_APP,
            result=AlertDeliveryAttempt.RESULT_SENT,
        )

    # Push to WebSocket group — non-fatal if channel layer is unavailable
    _push_to_websocket(alert)

    return alert


def resolve_operator_alert(dedupe_key: str) -> None:
    """
    Find any open (unresolved) alert with the matching dedupe_key and mark it as resolved.
    """
    now = timezone.now()
    updated = OperatorAlert.objects.filter(
        dedupe_key=dedupe_key
    ).exclude(
        status=OperatorAlert.STATUS_RESOLVED
    ).update(
        status=OperatorAlert.STATUS_RESOLVED,
        resolved_at=now,
        updated_at=now
    )

    if updated > 0:
        # Push a refresh signal to WebSocket so the UI knows the alert is gone
        try:
            channel_layer = get_channel_layer()
            if channel_layer:
                event = {
                    "type": "notification.resolve",
                    "dedupe_key": dedupe_key,
                    "resolved_at": now.isoformat(),
                }
                async_to_sync(channel_layer.group_send)(_NOTIFICATION_GROUP, event)
        except Exception:
            logger.warning("resolve_operator_alert: failed to push WebSocket event", exc_info=True)


def _push_to_websocket(alert: OperatorAlert) -> None:
    """Send a notification.alert event to all connected clients."""
    try:
        channel_layer = get_channel_layer()
        if channel_layer is None:
            return
        event = {
            "type": "notification.alert",
            "alert_id": str(alert.alert_id),
            "event_type": alert.event_type,
            "severity": alert.severity,
            "status": alert.status,
            "title": alert.title,
            "message": alert.message,
            "source_area": alert.source_area,
            "related_route": alert.related_route,
            "occurrence_count": alert.occurrence_count,
            "created_at": alert.first_seen_at.isoformat(),
            "payload": alert.payload,
        }
        async_to_sync(channel_layer.group_send)(_NOTIFICATION_GROUP, event)
    except Exception:
        logger.warning("emit_operator_alert: failed to push WebSocket event", exc_info=True)


def get_unread_summary() -> dict:
    """Return unread counts by severity and the latest alert timestamp."""
    unread = OperatorAlert.objects.filter(status=OperatorAlert.STATUS_UNREAD)
    summary: dict[str, int] = {
        OperatorAlert.SEVERITY_INFO: 0,
        OperatorAlert.SEVERITY_SUCCESS: 0,
        OperatorAlert.SEVERITY_WARNING: 0,
        OperatorAlert.SEVERITY_ERROR: 0,
        OperatorAlert.SEVERITY_URGENT: 0,
    }
    total = 0
    latest_at = None
    for row in unread.values("severity", "first_seen_at"):
        summary[row["severity"]] = summary.get(row["severity"], 0) + 1
        total += 1
        if latest_at is None or row["first_seen_at"] > latest_at:
            latest_at = row["first_seen_at"]

    return {
        "total_unread": total,
        "by_severity": summary,
        "latest_at": latest_at.isoformat() if latest_at else None,
    }
