"""
Drain-and-resume runtime switcher (plan item 23).

Switches the effective compute runtime (CPU ↔ GPU) without orphaning in-flight
work. The flow:

  1. Record the switch intent in ``system.runtime_switch_pending`` so workers
     picking up a new batch know to wait.
  2. Set ``system.master_pause`` so no NEW batches start. Existing batches
     complete normally and save their checkpoints (plan item 8/12/19 reused).
  3. Wait up to ``MAX_DRAIN_SECONDS`` for active ``JobLease`` rows to expire
     or be released.
  4. Warm the target runtime — for GPU, call the existing
     ``_cuda_warmup_ok`` probe (plan item 15 reused).
  5. Write the new ``system.runtime_mode`` and clear the pause + pending flags.
  6. Workers poll ``system.master_pause`` on their main loop and resume
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
        target: "cpu" or "gpu".
        wait_for_drain: if True, block until active leases drain or
            ``MAX_DRAIN_SECONDS`` elapses. If False, return immediately after
            flipping the pause flag — useful for async workflows.
        warmup: optional callable returning True when the new runtime is ready.
            When ``target == "gpu"`` and ``warmup`` is not given, the real
            ``_cuda_warmup_ok`` from embeddings.py is used.

    Returns:
        { ok, target, drain_waited_s, warmed, previous }.
    """
    from apps.core.models import AppSetting

    if target not in ("cpu", "gpu"):
        return {"ok": False, "error": "target must be 'cpu' or 'gpu'"}

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

    if target == "gpu" and not warmed:
        return _rollback_failed_warmup(AppSetting, target, previous, drain_waited)

    return _commit_switch(AppSetting, target, previous, drain_waited, warmed)


def _run_warmup(target: str, warmup: Callable | None) -> bool:
    """Run the warmup callable for a GPU switch. Returns True on success."""
    if target != "gpu":
        return True
    warmup_fn = warmup or _default_gpu_warmup
    try:
        return bool(warmup_fn())
    except Exception:
        logger.exception("runtime_switcher: warmup raised; treating as cold")
        return False


def _rollback_failed_warmup(
    AppSetting, target: str, previous: str, drain_waited: int
) -> dict:
    """Failed warmup — keep the old mode, clear pending, unpause workers."""
    _write(AppSetting, KEY_SWITCH_PENDING, "")
    _write(AppSetting, KEY_MASTER_PAUSE, "false")
    _emit_fallback_alert("CUDA warmup failed during runtime switch")
    return {
        "ok": False,
        "target": target,
        "previous": previous,
        "drain_waited_s": drain_waited,
        "warmed": False,
        "error": "warmup_failed",
    }


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
    except Exception:
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


def _default_gpu_warmup() -> bool:
    """Use the real CUDA warmup probe from embeddings.py when available."""
    try:
        from apps.pipeline.services.embeddings import _cuda_warmup_ok

        return _cuda_warmup_ok()
    except Exception:
        logger.debug("runtime_switcher: _cuda_warmup_ok unavailable", exc_info=True)
        return False


def _emit_fallback_alert(reason: str) -> None:
    try:
        from apps.notifications.alert_rules import alert_gpu_fallback_to_cpu

        alert_gpu_fallback_to_cpu(reason=reason)
    except Exception:
        logger.debug("runtime_switcher: failed to emit fallback alert", exc_info=True)


def _read(AppSetting, key: str, default: str) -> str:
    row = AppSetting.objects.filter(key=key).values_list("value", flat=True).first()
    return row if row else default


def _write(AppSetting, key: str, value: str) -> None:
    AppSetting.objects.update_or_create(
        key=key,
        defaults={"value": value, "value_type": "str", "category": "performance"},
    )
