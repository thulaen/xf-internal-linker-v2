"""Redis-backed distributed task locking.

Enforces the golden rule from docs/PERFORMANCE.md §4: never run two Heavy
tasks simultaneously.  Medium tasks follow the same FIFO rule.  Light tasks
never check locks.

Uses Django cache ``cache.add()`` which maps to Redis ``SET NX`` — an atomic
set-if-not-exists operation that is safe across multiple workers.

See [Dean & Barroso 2013, "The Tail at Scale"] for why serial heavy tasks
outperform competing parallel ones on constrained hardware.
"""

from __future__ import annotations

import logging
import time
import uuid

from django.core.cache import cache

logger = logging.getLogger(__name__)

# Cache key prefixes
_LOCK_KEY_PREFIX = "task_lock:"
_LOCK_OWNER_PREFIX = "task_lock_owner:"

# Default lock timeout: 2 hours.  Tasks that run longer should pass a
# higher timeout explicitly.
_DEFAULT_TIMEOUT_SECONDS = 7200

# Unique identifier for this worker process.
_WORKER_ID = str(uuid.uuid4())


def acquire_task_lock(
    weight_class: str,
    task_name: str,
    timeout: int = _DEFAULT_TIMEOUT_SECONDS,
) -> bool:
    """Attempt to acquire the lock for a weight class.

    Returns True if the lock was acquired, False if another task of the
    same weight class is already running.

    Light tasks always return True (no locking).
    """
    if weight_class == "light":
        return True

    lock_key = f"{_LOCK_KEY_PREFIX}{weight_class}"
    owner_key = f"{_LOCK_OWNER_PREFIX}{weight_class}"
    owner_value = f"{task_name}:{_WORKER_ID}:{time.monotonic()}"

    # cache.add() returns True only if the key did not already exist (atomic).
    acquired = cache.add(lock_key, owner_value, timeout)

    if acquired:
        cache.set(owner_key, owner_value, timeout)
        logger.info(
            "task_lock: acquired %s lock for %s (timeout=%ds)",
            weight_class,
            task_name,
            timeout,
        )
    else:
        current_owner = cache.get(lock_key, "unknown")
        logger.info(
            "task_lock: %s lock held by %s — %s must wait",
            weight_class,
            current_owner,
            task_name,
        )

    return acquired


def release_task_lock(weight_class: str, task_name: str) -> None:
    """Release the lock for a weight class.

    Only releases if the current holder matches (prevents releasing
    someone else's lock after a timeout).
    """
    if weight_class == "light":
        return

    lock_key = f"{_LOCK_KEY_PREFIX}{weight_class}"
    owner_key = f"{_LOCK_OWNER_PREFIX}{weight_class}"
    current = cache.get(lock_key, "")

    if current and current.startswith(f"{task_name}:"):
        cache.delete(lock_key)
        cache.delete(owner_key)
        logger.info("task_lock: released %s lock held by %s", weight_class, task_name)
    else:
        logger.warning(
            "task_lock: %s tried to release %s lock but holder is %s",
            task_name,
            weight_class,
            current or "(none)",
        )


def get_active_locks() -> dict[str, str | None]:
    """Return current lock holders for each weight class.

    Used by the Dashboard RunningNow component and Queue View to show
    which tasks are blocking others.
    """
    result: dict[str, str | None] = {}
    for wc in ("heavy", "medium"):
        lock_key = f"{_LOCK_KEY_PREFIX}{wc}"
        holder = cache.get(lock_key)
        result[wc] = holder
    return result


def is_lock_held(weight_class: str) -> bool:
    """Check if a lock is currently held for a weight class."""
    if weight_class == "light":
        return False
    lock_key = f"{_LOCK_KEY_PREFIX}{weight_class}"
    return cache.get(lock_key) is not None
