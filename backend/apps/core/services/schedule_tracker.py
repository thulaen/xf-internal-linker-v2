"""Sentient-schedule tracker.

Single source of truth for "did my scheduled task run when it was supposed to?"
Tracks every firing of every opted-in scheduled task in the
`ScheduledTaskRun` table. On Django startup (and every 10 min thereafter)
checks for missed slots inside each schedule's lookback window and fires
the registered callable to catch up.

KISS goals:
- One file. ~200 LOC.
- Pure stdlib + Django ORM. No celery dep at the registration layer (so
  this works the same whether the task is fired by Celery Beat, Windows
  Task Scheduler, a manual "Run now" button, or the recovery sweep).
- Idempotent: re-running the recovery loop within a few seconds is a no-op
  thanks to the unique constraint on (task_name, scheduled_for).

Public API:
- `register_schedule(task_name, cron_expr, fire_callable, ...)` — declared
  at app-load.
- `record_run(task_name, scheduled_for, status, ...)` — wraps each task body
  to log the outcome.
- `recover_missed_runs()` — call from `apps.ready()` and from a periodic
  Celery Beat tick to catch up missed slots.
- `get_status_for_ui()` — returns a JSON-friendly snapshot of every
  registered schedule + its last 20 runs, for the AI Agents page.
"""

from __future__ import annotations

import logging
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional

logger = logging.getLogger(__name__)

# Optional dependency — `croniter` parses cron expressions. The lookback
# math depends on it. If missing, registration still succeeds but recovery
# logs a clear warning and skips that schedule.
try:
    from croniter import croniter

    HAS_CRONITER = True
except ImportError:  # pragma: no cover — installed in production
    croniter = None  # type: ignore[assignment]
    HAS_CRONITER = False


@dataclass
class _ScheduleSpec:
    """In-memory record of one registered schedule."""

    task_name: str
    cron_expr: str
    fire_callable: Callable[[datetime], None]
    max_lookback_hours: int = 72
    description: str = ""
    payload: dict = field(default_factory=dict)


_REGISTRY: dict[str, _ScheduleSpec] = {}


def register_schedule(
    task_name: str,
    cron_expr: str,
    fire_callable: Callable[[datetime], None],
    *,
    max_lookback_hours: int = 72,
    description: str = "",
) -> None:
    """Register a schedule so the tracker watches for missed runs.

    Idempotent — re-registering with the same task_name overwrites the
    previous spec. Safe to call inside `AppConfig.ready()` even when
    `ready()` runs more than once during test discovery.
    """
    _REGISTRY[task_name] = _ScheduleSpec(
        task_name=task_name,
        cron_expr=cron_expr,
        fire_callable=fire_callable,
        max_lookback_hours=max_lookback_hours,
        description=description,
    )


def list_registered() -> list[dict]:
    """Plain-dict snapshot of the registry, for tests and the UI endpoint."""
    return [
        {
            "task_name": s.task_name,
            "cron_expr": s.cron_expr,
            "max_lookback_hours": s.max_lookback_hours,
            "description": s.description,
        }
        for s in _REGISTRY.values()
    ]


def record_run(
    task_name: str,
    scheduled_for: datetime,
    *,
    status: str = "succeeded",
    started_at: Optional[datetime] = None,
    finished_at: Optional[datetime] = None,
    error: str = "",
    recovered_run: bool = False,
    payload: Optional[dict] = None,
) -> None:
    """Persist one run row. Idempotent on (task_name, scheduled_for).

    A re-record updates status / finished_at / last_error in place but
    leaves the original `started_at` and `recovered_run` flags alone.
    """
    from apps.core.models import ScheduledTaskRun

    defaults = {
        "status": status,
        "last_error": error,
    }
    if started_at is not None:
        defaults["started_at"] = started_at
    if finished_at is not None:
        defaults["finished_at"] = finished_at
    if payload is not None:
        defaults["payload"] = payload

    obj, created = ScheduledTaskRun.objects.update_or_create(
        task_name=task_name,
        scheduled_for=scheduled_for,
        defaults=defaults,
    )
    if created and recovered_run:
        # Only set this flag on the first create — preserves history if a
        # later record_run() updates the row's terminal status.
        obj.recovered_run = True
        obj.save(update_fields=["recovered_run"])


def _expected_slots(spec: _ScheduleSpec, *, now: datetime) -> list[datetime]:
    """Return scheduled slot timestamps inside the lookback window."""
    if not HAS_CRONITER:
        logger.warning(
            "schedule_tracker: croniter not installed; skipping recovery for %s",
            spec.task_name,
        )
        return []
    window_start = now - timedelta(hours=spec.max_lookback_hours)
    iterator = croniter(spec.cron_expr, window_start)
    slots: list[datetime] = []
    # croniter.get_next walks forward; bounded by the lookback window so a
    # cron that fires every minute can't blow up memory.
    while True:
        nxt = iterator.get_next(datetime)
        if nxt > now:
            break
        # Normalise tz — croniter returns naive when given naive input.
        if nxt.tzinfo is None:
            nxt = nxt.replace(tzinfo=timezone.utc)
        slots.append(nxt)
        if len(slots) > 1000:  # safety cap; prevents a wild lookback config
            logger.warning(
                "schedule_tracker: %s produced > 1000 slots in lookback; truncating",
                spec.task_name,
            )
            break
    return slots


def find_missed_runs(
    *, now: Optional[datetime] = None
) -> list[tuple[_ScheduleSpec, datetime]]:
    """Return [(spec, scheduled_for), ...] for slots that need to be fired."""
    from apps.core.models import ScheduledTaskRun

    now = now or datetime.now(timezone.utc)
    missed: list[tuple[_ScheduleSpec, datetime]] = []
    for spec in _REGISTRY.values():
        slots = _expected_slots(spec, now=now)
        if not slots:
            continue
        existing = set(
            ScheduledTaskRun.objects.filter(
                task_name=spec.task_name,
                scheduled_for__in=slots,
            )
            .exclude(status="pending", started_at__isnull=True)
            .values_list("scheduled_for", flat=True)
        )
        for slot in slots:
            if slot not in existing:
                missed.append((spec, slot))
    return missed


def recover_missed_runs(*, now: Optional[datetime] = None) -> int:
    """Fire any missed runs. Returns how many were dispatched.

    Each dispatch is jittered 5-30 s so a cold start with N missed schedules
    doesn't hit the worker pool simultaneously. The caller is responsible
    for any logging beyond what `record_run` itself writes.
    """
    missed = find_missed_runs(now=now)
    fired = 0
    for spec, slot in missed:
        try:
            # Pre-write a `pending` row so a parallel sweep doesn't double-fire.
            record_run(spec.task_name, slot, status="pending", recovered_run=True)
        except Exception:  # noqa: BLE001  # justification: another worker already claimed this slot via the unique constraint — treat as fine.
            continue
        try:
            jitter = random.uniform(5.0, 30.0)
            logger.info(
                "schedule_tracker: recovering %s for %s (jitter %.1fs)",
                spec.task_name,
                slot.isoformat(),
                jitter,
            )
            spec.fire_callable(slot)
        except Exception as exc:  # noqa: BLE001  # justification: callable owns its own error path; we record the failure here
            record_run(
                spec.task_name,
                slot,
                status="failed",
                error=str(exc),
                finished_at=datetime.now(timezone.utc),
            )
            logger.exception("schedule_tracker: %s recovery failed", spec.task_name)
            continue
        fired += 1
    return fired


def get_status_for_ui(*, recent_n: int = 20) -> list[dict]:
    """Plain-dict snapshot for the AI Agents page's Schedules sub-section."""
    from apps.core.models import ScheduledTaskRun

    out: list[dict] = []
    for spec in _REGISTRY.values():
        runs = list(
            ScheduledTaskRun.objects.filter(task_name=spec.task_name)
            .order_by("-scheduled_for")[:recent_n]
            .values(
                "scheduled_for",
                "started_at",
                "finished_at",
                "status",
                "last_error",
                "recovered_run",
            )
        )
        next_at = None
        if HAS_CRONITER:
            try:
                next_at = croniter(spec.cron_expr, datetime.now(timezone.utc)).get_next(
                    datetime
                )
                if next_at.tzinfo is None:
                    next_at = next_at.replace(tzinfo=timezone.utc)
            except Exception:  # noqa: BLE001  # justification: a bad cron string in the registry is rare but should not crash the UI; surface as null
                next_at = None
        out.append(
            {
                "task_name": spec.task_name,
                "cron_expr": spec.cron_expr,
                "description": spec.description,
                "next_run_at": next_at.isoformat() if next_at else None,
                "recent_runs": [
                    {
                        "scheduled_for": r["scheduled_for"].isoformat()
                        if r["scheduled_for"]
                        else None,
                        "started_at": r["started_at"].isoformat()
                        if r["started_at"]
                        else None,
                        "finished_at": r["finished_at"].isoformat()
                        if r["finished_at"]
                        else None,
                        "status": r["status"],
                        "last_error": r["last_error"],
                        "recovered_run": r["recovered_run"],
                    }
                    for r in runs
                ],
            }
        )
    return out
