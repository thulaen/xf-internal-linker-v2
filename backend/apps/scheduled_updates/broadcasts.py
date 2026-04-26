"""WebSocket broadcasts for the Scheduled Updates orchestrator.

Piggybacks on the existing :mod:`apps.realtime` topic-bus — no new
consumer, no new URL. Frontend subscribes to the ``scheduled_updates``
topic via the shared ``/ws/realtime/`` socket and receives every event
defined here.

Events
------
- ``job.state_change``  — any lifecycle flip (pending → running →
  completed / failed / paused / missed). Payload is the job's full
  summary so the UI doesn't need a follow-up fetch.
- ``job.progress``      — emitted from inside the checkpoint callable
  during an active run. Light-weight (pct + message only).
- ``alert.raised``      — deduped alert appeared or reopened.
- ``alert.resolved``    — count of alerts auto-resolved when a job
  succeeded after a rough patch.
- ``alert.acknowledged`` — operator clicked the ✕.

All broadcasts are best-effort — the underlying helper silently
no-ops when the channel layer isn't configured (e.g. inside unit
tests without Redis). Producer side never raises.
"""

from __future__ import annotations

from typing import Any

from apps.realtime.services import broadcast

from .models import JobAlert, ScheduledJob

#: The single topic every scheduled-updates event fires on. Keep the
#: bare name short — the realtime helper sanitises it to a Channels
#: group name deterministically.
TOPIC_SCHEDULED_UPDATES: str = "scheduled_updates"


# ─────────────────────────────────────────────────────────────────────
# Payload builders
# ─────────────────────────────────────────────────────────────────────


def _job_summary(job: ScheduledJob) -> dict[str, Any]:
    """Return the dict every state-change / progress payload carries."""
    return {
        "key": job.key,
        "display_name": job.display_name,
        "state": job.state,
        "priority": job.priority,
        "progress_pct": job.progress_pct,
        "current_message": job.current_message,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
        "last_run_at": job.last_run_at.isoformat() if job.last_run_at else None,
        "last_success_at": (
            job.last_success_at.isoformat() if job.last_success_at else None
        ),
        "cadence_seconds": job.cadence_seconds,
        "duration_estimate_sec": job.duration_estimate_sec,
        "pause_token": job.pause_token,
    }


def _alert_summary(alert: JobAlert) -> dict[str, Any]:
    return {
        "id": alert.pk,
        "job_key": alert.job_key,
        "alert_type": alert.alert_type,
        "calendar_date": alert.calendar_date.isoformat(),
        "message": alert.message,
        "first_raised_at": (
            alert.first_raised_at.isoformat() if alert.first_raised_at else None
        ),
        "last_seen_at": (
            alert.last_seen_at.isoformat() if alert.last_seen_at else None
        ),
        "acknowledged_at": (
            alert.acknowledged_at.isoformat() if alert.acknowledged_at else None
        ),
        "resolved_at": (alert.resolved_at.isoformat() if alert.resolved_at else None),
        "is_active": alert.is_active,
    }


# ─────────────────────────────────────────────────────────────────────
# Public broadcast entry points
# ─────────────────────────────────────────────────────────────────────


def broadcast_state_change(job: ScheduledJob) -> None:
    """Emit ``job.state_change`` with the full job summary."""
    broadcast(
        topic=TOPIC_SCHEDULED_UPDATES,
        event="job.state_change",
        payload=_job_summary(job),
    )


def broadcast_progress(job_key: str, progress_pct: float, message: str) -> None:
    """Emit ``job.progress`` — light-weight update from inside a run."""
    broadcast(
        topic=TOPIC_SCHEDULED_UPDATES,
        event="job.progress",
        payload={
            "key": job_key,
            "progress_pct": float(progress_pct),
            "current_message": (message or "")[:240],
        },
    )


def broadcast_alert_raised(alert: JobAlert, *, reopened: bool = False) -> None:
    """Emit ``alert.raised`` when raise_alert creates or reopens an alert."""
    payload = _alert_summary(alert)
    payload["reopened"] = bool(reopened)
    broadcast(
        topic=TOPIC_SCHEDULED_UPDATES,
        event="alert.raised",
        payload=payload,
    )


def broadcast_alerts_resolved(job_key: str, count: int) -> None:
    """Emit ``alert.resolved`` with the count of rows the sweep closed."""
    broadcast(
        topic=TOPIC_SCHEDULED_UPDATES,
        event="alert.resolved",
        payload={
            "job_key": job_key,
            "count": int(count),
        },
    )


def broadcast_alert_acknowledged(alert: JobAlert) -> None:
    """Emit ``alert.acknowledged`` — operator clicked the ✕ on the dashboard."""
    broadcast(
        topic=TOPIC_SCHEDULED_UPDATES,
        event="alert.acknowledged",
        payload=_alert_summary(alert),
    )
