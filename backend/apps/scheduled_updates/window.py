"""Window-guard helpers — pure functions, no side effects.

The runner will only start a job when both of these are True:

1. The current local time is between 11:00 and 23:00.
2. The job's ``duration_estimate_sec`` would NOT push completion past 23:00.

Rule (2) is the "no new jobs past 22:55 for a 10-minute job" safety net
the user explicitly asked for — the laptop goes to sleep at 23:00 and
an overrun job will never finish.

A job that's already running past the cutoff is not interrupted — the
plan's acceptable trade in PR-A is *state preservation > strict window*.
Only NEW starts are refused.

History
-------
2026-04-25: Window opening time widened from 13:00 → 11:00 to give the
operator two extra hours of capacity per day. The laptop typically
wakes around 10:00 and sleeps after 23:00; opening at 11:00 leaves a
1-hour buffer for boot/login/morning admin before scheduled work fires.
"""

from __future__ import annotations

from datetime import datetime, timedelta, time
from zoneinfo import ZoneInfo

from django.conf import settings

#: Local hour the window opens at (inclusive). Jobs may start at or after
#: this hour if everything else checks out. Widened from 13 → 11 on
#: 2026-04-25 per operator request.
WINDOW_START_HOUR: int = 11

#: Local hour the window closes at (exclusive). Jobs must COMPLETE by
#: this hour — a 10-minute job at 22:55 would finish at 23:05 and is
#: refused by ``would_overflow()``.
WINDOW_END_HOUR: int = 23

#: Grace seconds added to duration estimates when checking overflow.
#: Helps cover startup latency / small delays without being over-strict.
OVERFLOW_GRACE_SECONDS: int = 30


def _local_tz() -> ZoneInfo:
    """The timezone the window is measured in.

    Defaults to ``settings.TIME_ZONE`` (Django's configured tz), falling
    back to UTC if that's unset or invalid. Keeping this a function
    instead of a module-level constant lets tests monkey-patch
    ``settings.TIME_ZONE`` cleanly.
    """
    tz_name = getattr(settings, "TIME_ZONE", None) or "UTC"
    try:
        return ZoneInfo(tz_name)
    except Exception:
        return ZoneInfo("UTC")


def _to_local(now: datetime | None) -> datetime:
    """Return *now* in local tz. If None, use the current moment."""
    if now is None:
        now = datetime.now(tz=_local_tz())
    elif now.tzinfo is None:
        # Naive datetime — assume it's already local.
        now = now.replace(tzinfo=_local_tz())
    else:
        now = now.astimezone(_local_tz())
    return now


def is_within_window(now: datetime | None = None) -> bool:
    """Return True when *now* (default: current local time) is in [11:00, 23:00)."""
    local = _to_local(now)
    return WINDOW_START_HOUR <= local.hour < WINDOW_END_HOUR


def would_overflow(duration_sec: int, now: datetime | None = None) -> bool:
    """Return True when starting a *duration_sec* job at *now* would finish after 23:00.

    Uses ``OVERFLOW_GRACE_SECONDS`` of slack so a 30-second-off estimate
    doesn't shove an otherwise-safe job into the overflow branch.

    If *now* is already outside the window, returns True — there is no
    valid start that wouldn't overflow (the window is already closed or
    hasn't opened yet).
    """
    local = _to_local(now)
    if not is_within_window(local):
        return True
    cutoff = local.replace(
        hour=WINDOW_END_HOUR,
        minute=0,
        second=0,
        microsecond=0,
    )
    projected_finish = local + timedelta(seconds=duration_sec + OVERFLOW_GRACE_SECONDS)
    return projected_finish > cutoff


def time_until_window_opens(now: datetime | None = None) -> timedelta:
    """How long until 11:00 local from *now*.

    Returns ``timedelta(0)`` when the window is already open. Used by the
    dashboard's "next window opens in HH:MM" label.
    """
    local = _to_local(now)
    if is_within_window(local):
        return timedelta(0)
    window_open = datetime.combine(
        local.date(),
        time(hour=WINDOW_START_HOUR),
        tzinfo=local.tzinfo,
    )
    if local.hour >= WINDOW_END_HOUR:
        # Past the close — next open is tomorrow.
        window_open = window_open + timedelta(days=1)
    return window_open - local


def seconds_remaining_in_window(now: datetime | None = None) -> int:
    """Seconds until 23:00 local from *now*.

    Returns 0 when the window is closed. Used by the runner to pick the
    right lock TTL without overshooting the cutoff.
    """
    local = _to_local(now)
    if not is_within_window(local):
        return 0
    cutoff = local.replace(
        hour=WINDOW_END_HOUR,
        minute=0,
        second=0,
        microsecond=0,
    )
    return max(0, int((cutoff - local).total_seconds()))
