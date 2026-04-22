"""Redis lock for the Scheduled Updates runner.

At most ONE runner process owns the lock at any moment, which is what
enforces the "serial execution" rule from the plan. A Celery beat tick
every 5 minutes tries to acquire the lock; a tick that loses simply
exits — the active holder keeps going.

The lock uses ``SET key value NX EX ttl`` so it's atomic and auto-expires
if the holder crashes (TTL is long enough for the longest job + a
safety buffer). Releasing uses a Lua script that checks the token
first — a crashed holder whose lock already expired can never release
the NEXT holder's lock by accident.
"""

from __future__ import annotations

import logging
import os
import socket
import uuid
from typing import Optional

logger = logging.getLogger(__name__)


RUNNER_LOCK_KEY: str = "scheduled_updates:runner"

# Safe-release Lua: only DEL the key when the value matches the caller's
# token. Without this, a holder whose lock TTL expired mid-job could
# accidentally delete the NEXT holder's freshly-acquired lock.
_RELEASE_LUA: str = """
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('del', KEYS[1])
else
    return 0
end
"""


def make_token() -> str:
    """Build a human-readable lock token: ``<host>:<pid>:<uuid4>``.

    The ``uuid4`` chunk is what guarantees uniqueness across restarts on
    the same PID (Docker can recycle PIDs). Host + PID are kept for
    debugging — `redis-cli get scheduled_updates:runner` tells you which
    worker has the lock.
    """
    return f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:8]}"


def acquire_runner_lock(
    redis_client,
    *,
    ttl_seconds: int,
    token: Optional[str] = None,
) -> Optional[str]:
    """Try to take the runner lock.

    Returns the token string on success, ``None`` on failure (someone
    else owns it). Caller MUST pass the returned token to
    ``release_runner_lock`` on the same redis_client.
    """
    if ttl_seconds <= 0:
        logger.error("acquire_runner_lock called with non-positive ttl=%s", ttl_seconds)
        return None
    token = token or make_token()
    try:
        # `nx=True` → only set when the key does NOT already exist.
        # `ex=ttl_seconds` → auto-expire so a crashed holder can't block forever.
        acquired = redis_client.set(
            RUNNER_LOCK_KEY,
            token,
            nx=True,
            ex=ttl_seconds,
        )
    except Exception:
        logger.exception("acquire_runner_lock: redis set failed")
        return None
    if not acquired:
        return None
    return token


def release_runner_lock(redis_client, token: str) -> bool:
    """Release the runner lock IFF *token* matches the current holder.

    Returns True when the lock was released, False when the caller no
    longer owns it (TTL expired, someone else already took it, etc.).
    Never raises — a lock-release failure should not crash the runner.
    """
    if not token:
        return False
    try:
        result = redis_client.eval(_RELEASE_LUA, 1, RUNNER_LOCK_KEY, token)
    except Exception:
        logger.exception("release_runner_lock: redis eval failed")
        return False
    return bool(result)


def current_holder(redis_client) -> Optional[str]:
    """Return the token currently holding the lock, or None if free."""
    try:
        raw = redis_client.get(RUNNER_LOCK_KEY)
    except Exception:
        logger.exception("current_holder: redis get failed")
        return None
    if raw is None:
        return None
    if isinstance(raw, bytes):
        return raw.decode("utf-8", errors="replace")
    return str(raw)
