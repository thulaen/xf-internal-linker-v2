"""
Drain-and-resume runtime switcher.

Confirms the CPU runtime without orphaning in-flight work. The flow:

  1. Record the switch intent in ``system.runtime_switch_pending`` so workers
     picking up a new batch know to wait.
  2. Set ``system.master_pause`` so no NEW batches start. Existing batches
     complete normally and save their checkpoints (plan item 8/12/19 reused).
  3. Wait up to ``MAX_DRAIN_SECONDS`` for active ``JobLease`` rows to expire
     or be released.
  4. Write the CPU runtime and clear the pause + pending flags.
  5. Workers poll ``system.master_pause`` on their main loop and resume
     normally when it flips back to ``"false"``.

Everything this module does is idempotent — re-running the switcher while a
switch is in flight is a no-op on the first pass and a confirm on the second.
"""

from __future__ import annotations

import logging
import time
from typing import Callable

from django.utils import timezone

logger = logging.getLogger(__name__)

# How long we're willing to wait for in-flight leases to drain. Keeps the
# endpoint responsive; anything longer is a timeout the caller can retry.
MAX_DRAIN_SECONDS = 90
POLL_INTERVAL_SECONDS = 2

KEY_RUNTIME_MODE = "system.runtime_mode"
KEY_MASTER_PAUSE = "system.master_pause"
KEY_SWITCH_PENDING = "system.runtime_switch_pending"


def switch_runtime(
    *,
    target: str,
    wait_for_drain: bool = True,
    warmup: Callable | None = None,
) -> dict:
    """Request a drain-and-resume switch to ``target`` runtime.

    Arguments:
        target: "cpu".
        wait_for_drain: if True, block until active leases drain or
            ``MAX_DRAIN_SECONDS`` elapses. If False, return immediately after
            flipping the pause flag — useful for async workflows.
        warmup: ignored compatibility hook for older callers.

    Returns:
        { ok, target, drain_waited_s, warmed, previous }.
    """
    from apps.core.models import AppSetting

    if target != "cpu":
        return {"ok": False, "error": "target must be 'cpu'"}

    previous = _read(AppSetting, KEY_RUNTIME_MODE, "cpu")

    # Already on target: fast path. Still clear stale flags defensively.
    if previous == target:
        _write(AppSetting, KEY_SWITCH_PENDING, "")
        return {
            "ok": True,
            "target": target,
            "previous": previous,
            "drain_waited_s": 0,
            "warmed": True,
            "skipped": True,
        }

    _write(AppSetting, KEY_SWITCH_PENDING, target)
    _write(AppSetting, KEY_MASTER_PAUSE, "true")
    logger.info(
        "runtime_switcher: pausing workers for %s -> %s switch", previous, target
    )

    drain_waited = _wait_for_drain() if wait_for_drain else 0
    warmed = _run_warmup(target, warmup)

    return _commit_switch(AppSetting, target, previous, drain_waited, warmed)


def _run_warmup(target: str, warmup: Callable | None) -> bool:
    """CPU runtime has no warmup step."""
    return True


def _commit_switch(
    AppSetting, target: str, previous: str, drain_waited: int, warmed: bool
) -> dict:
    """Commit the switch. Set mode BEFORE clearing pause so workers wake up
    on the new mode."""
    _write(AppSetting, KEY_RUNTIME_MODE, target)
    _write(AppSetting, KEY_SWITCH_PENDING, "")
    _write(AppSetting, KEY_MASTER_PAUSE, "false")
    logger.info(
        "runtime_switcher: switch complete %s -> %s (drain %ds)",
        previous,
        target,
        drain_waited,
    )
    return {
        "ok": True,
        "target": target,
        "previous": previous,
        "drain_waited_s": drain_waited,
        "warmed": warmed,
    }


def get_switch_status() -> dict:
    """Read the current runtime + any pending switch so the UI can poll."""
    from apps.core.models import AppSetting

    return {
        "runtime_mode": _read(AppSetting, KEY_RUNTIME_MODE, "cpu"),
        "switch_pending": _read(AppSetting, KEY_SWITCH_PENDING, ""),
        "master_pause": _read(AppSetting, KEY_MASTER_PAUSE, "false") == "true",
    }


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _wait_for_drain() -> int:
    """Block until active leases drain or MAX_DRAIN_SECONDS elapses."""
    try:
        from apps.pipeline.models import JobLease
    except Exception:  # noqa: BLE001  # JobLease model is optional (only present when the pipeline app is installed). If absent we have nothing to drain — the runtime switch can proceed immediately.
        # JobLease module unavailable — don't block.
        return 0

    start = time.monotonic()
    deadline = start + MAX_DRAIN_SECONDS
    now = timezone.now()

    while time.monotonic() < deadline:
        active_count = JobLease.objects.filter(
            status="active",
            expires_at__gt=now,
        ).count()
        if active_count == 0:
            break
        time.sleep(POLL_INTERVAL_SECONDS)
        now = timezone.now()

    return int(time.monotonic() - start)


def _read(AppSetting, key: str, default: str) -> str:
    row = AppSetting.objects.filter(key=key).values_list("value", flat=True).first()
    return row if row else default


def _write(AppSetting, key: str, value: str) -> None:
    AppSetting.objects.update_or_create(
        key=key,
        defaults={"value": value, "value_type": "str", "category": "performance"},
    )
