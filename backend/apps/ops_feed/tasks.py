"""Slice 1.6 — bullboard → Channels bridge.

A long-lived Celery task subscribes to bullboard's gRPC server-streaming
Subscribe RPC and republishes every bulletin via
    ``apps.realtime.services.broadcast`` so any browser tab listening
on the ``bullboard`` topic sees the bulletin within ~10 ms.

Failure model:

  * If the bullboard binary is down or the sidecars socket is missing,
    the task waits ``_BACKOFF_INITIAL`` seconds, then doubles up to
    ``_BACKOFF_MAX``. The Celery task itself never exits — Celery
    re-enqueues it after each ``time_limit`` hit.
  * Single-leader: ``coordd.Lock(lock_name="bullboard-bridge")`` is taken
    before subscribing so two concurrent celery workers do not both
    fan-out the same bulletin. The lock auto-expires after
    ``_LEADER_LOCK_HOLD_SECONDS`` so a crashed worker recovers within
    one cycle.

Cross-module boundary: this module imports from
``apps.ops_feed._sidecars`` (the bullboard client) and calls
``apps.realtime.services.broadcast``; it does NOT touch Channels
internals or governance modules directly.

References:
  * services/sidecars/api/bullboard.proto §Subscribe
  * docs/specs/fr-sidecars-host.md §bullboard
  * apps.realtime.services.broadcast (slice 1.6 typed wrapper)
"""

from __future__ import annotations

import logging
import time
from typing import Any

logger = logging.getLogger(__name__)

# Defaults — overridable via Celery task kwargs.
_BACKOFF_INITIAL = 2.0
_BACKOFF_MAX = 30.0
_LEADER_LOCK_HOLD_SECONDS = 30
_TASK_SOFT_TIME_LIMIT = 600  # 10 min; Celery re-enqueues after.


try:
    from celery import shared_task
except ImportError:  # pragma: no cover - tests without celery
    shared_task = None  # type: ignore[assignment]


def _run_bridge_once(max_iterations: int | None = None) -> dict[str, int]:
    """Run one bridge cycle. Returns counts so tests can assert on behaviour.

    Acquires the coordd leader lock, opens bullboard.Subscribe, and
    forwards each bulletin via broadcast. Returns when:
      * The subscribe stream ends (sidecars restarted) → counters returned.
      * The leader lock cannot be acquired → counters returned (became follower).
      * ``max_iterations`` is reached (tests pass 1) → counters returned.
    """
    stats = {"received": 0, "broadcast": 0, "errors": 0, "skipped_not_leader": 0}

    # Lazy-import the clients so a worker without sidecars stubs does not
    # break Celery autodiscovery at import time.
    try:
        from apps.diagnostics._sidecars.coordd_client import CoorddClient
        from apps.ops_feed._sidecars.bullboard_client import BullboardClient
        from apps.realtime.services import broadcast
    except Exception as exc:  # noqa: BLE001 - import barrier
        logger.warning("bullboard-bridge: deps missing (%s); skipping cycle", exc)
        stats["errors"] += 1
        return stats

    coordd = CoorddClient(deadline=2.0)
    try:
        lock = coordd.lock(
            lock_name="bullboard-bridge",
            hold_for_seconds=_LEADER_LOCK_HOLD_SECONDS,
        )
    except Exception as exc:  # noqa: BLE001
        stats["skipped_not_leader"] += 1
        logger.debug("bullboard-bridge: not leader (%s); cycle skipped", exc)
        return stats

    logger.info(
        "bullboard-bridge: acquired leader lock token=%s; opening Subscribe stream",
        lock.token[:8],
    )

    bullboard = BullboardClient(deadline=5.0)
    # Subscribe to all bulletins. The Channels layer fan-out happens
    # per-subscriber on the browser side so we do not filter here.
    iteration = 0
    try:
        from apps._sidecars_pb.bullboard import bullboard_pb2_grpc, bullboard_pb2
        from apps._sidecars_shared.channel import sidecars_channel

        with sidecars_channel() as channel:
            stub = bullboard_pb2_grpc.BullboardStub(channel)
            stream = stub.Subscribe(
                bullboard_pb2.SubscribeRequest(event_type="", min_severity=0),
                timeout=_TASK_SOFT_TIME_LIMIT,
            )
            for proto_bulletin in stream:
                stats["received"] += 1
                # Coerce to a plain dict so the wrapper signature does not
                # leak grpc types into apps.realtime.
                payload = {
                    "id": proto_bulletin.id,
                    "event_type": proto_bulletin.event_type,
                    "severity": _severity_name(proto_bulletin.severity),
                    "message": proto_bulletin.message,
                    "posted_at_unix_nanos": proto_bulletin.posted_at_unix_nanos,
                    "linked_autoissue_id": proto_bulletin.linked_autoissue_id,
                }
                try:
                    broadcast("bullboard", "bulletin", payload)
                    stats["broadcast"] += 1
                except Exception as exc:  # noqa: BLE001
                    stats["errors"] += 1
                    logger.warning(
                        "bullboard-bridge: broadcast failed for id=%s: %s",
                        proto_bulletin.id[:8] if proto_bulletin.id else "?",
                        exc,
                    )
                iteration += 1
                if max_iterations is not None and iteration >= max_iterations:
                    break
    except Exception as exc:  # noqa: BLE001 - any stream-level failure
        stats["errors"] += 1
        logger.warning("bullboard-bridge: stream terminated (%s)", exc)
    finally:
        try:
            coordd.unlock(lock.token)
        except Exception as exc:  # noqa: BLE001
            logger.debug("bullboard-bridge: unlock failed (%s)", exc)

    return stats


def _severity_name(severity_value: int) -> str:
    """Map the SEV_* int enum to its symbolic name. Lazy-imports so the
    helper is safe to call from a worker without sidecars stubs."""
    try:
        from apps._sidecars_pb.bullboard import bullboard_pb2

        return bullboard_pb2.Severity.Name(severity_value)
    except Exception:  # noqa: BLE001 - return the int when stubs unavailable
        return f"SEV_{severity_value}"


if shared_task is not None:

    @shared_task(
        name="apps.ops_feed.tasks.run_bullboard_bridge",
        soft_time_limit=_TASK_SOFT_TIME_LIMIT,
        time_limit=_TASK_SOFT_TIME_LIMIT + 30,
    )
    def run_bullboard_bridge(*, max_iterations: int | None = None) -> dict[str, int]:
        """Celery entry point. Wraps ``_run_bridge_once`` so the bridge can
        be replayed under retry logic. Returns the per-cycle stats dict."""
        backoff = _BACKOFF_INITIAL
        while True:
            stats = _run_bridge_once(max_iterations=max_iterations)
            # If we processed any bulletins, reset backoff. Otherwise grow it.
            if stats["received"] > 0:
                backoff = _BACKOFF_INITIAL
            else:
                backoff = min(backoff * 2, _BACKOFF_MAX)
            if max_iterations is not None:
                return stats
            time.sleep(backoff)
