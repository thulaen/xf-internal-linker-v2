"""
Realtime broadcast helper.

Public API:
    broadcast(topic: str, event: str, payload: dict) -> None

Wraps channel_layer.group_send so every topic uses the same event envelope
and the same group-name sanitization. Call sites live in each data-owning
app's signals.py (see docs/REALTIME.md).

Channels group-name rules (Redis backend): ASCII letters, digits, hyphens,
periods, underscores. Max 100 characters. Anything else gets stripped.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Mapping

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

logger = logging.getLogger(__name__)

# Public group message `type` — matches `topic_update` handler on the consumer.
_MESSAGE_TYPE = "topic.update"

# Redis-safe character set for channel group names.
_SAFE_GROUP_CHARS = re.compile(r"[^A-Za-z0-9._-]+")
_MAX_GROUP_NAME_LEN = 100


def sanitize_topic(topic: str) -> str:
    """
    Reduce a topic string to a valid Channels group name.

    - Non-letter / non-digit / non-`._-` characters become underscores.
    - Truncated to 100 chars.
    - Empty / None input returns "_".

    Sanitization is deterministic so producers and subscribers agree on the
    group name without coordination.
    """
    if not topic:
        return "_"
    safe = _SAFE_GROUP_CHARS.sub("_", topic.strip())
    safe = safe[:_MAX_GROUP_NAME_LEN] or "_"
    return safe


def broadcast(topic: str, event: str, payload: Mapping[str, Any] | None = None) -> None:
    """
    Fan a structured update out to every WebSocket client subscribed to `topic`.

    Arguments
    ---------
    topic
        Free-form topic name (e.g. "diagnostics", "settings.runtime",
        "crawler.sessions"). Sanitised before use as a Channels group name.
    event
        Short dotted event name within the topic (e.g. "entity.updated",
        "entity.deleted", "prereq.changed"). Consumed by the frontend as a
        routing key.
    payload
        Arbitrary JSON-serialisable dictionary forwarded to the client.

    Safety
    ------
    - Silent no-op if no channel layer is configured (tests without Redis).
    - Logs — does not raise — on transport errors so a broken Redis does not
      take down the task that was only trying to notify listeners.
    """
    group = sanitize_topic(topic)
    layer = get_channel_layer()
    if layer is None:
        logger.debug("realtime.broadcast skipped (no channel layer configured)")
        return

    message = {
        "type": _MESSAGE_TYPE,
        "topic": topic,
        "event": event,
        "payload": dict(payload or {}),
    }
    try:
        async_to_sync(layer.group_send)(group, message)
    except Exception:  # noqa: BLE001 — transport failures must not crash producers
        logger.exception("realtime.broadcast failed for topic=%s event=%s", topic, event)


async def abroadcast(
    topic: str, event: str, payload: Mapping[str, Any] | None = None
) -> None:
    """Async-context twin of :func:`broadcast`.

    Phase RC / Gaps 139-142 — the realtime consumer's ``publish``
    handler is itself async, so we skip ``async_to_sync`` (which would
    emit a deprecation warning under Channels 4) and call the channel
    layer directly.
    """
    group = sanitize_topic(topic)
    layer = get_channel_layer()
    if layer is None:
        logger.debug("realtime.abroadcast skipped (no channel layer configured)")
        return
    message = {
        "type": _MESSAGE_TYPE,
        "topic": topic,
        "event": event,
        "payload": dict(payload or {}),
    }
    try:
        await layer.group_send(group, message)
    except Exception:  # noqa: BLE001
        logger.exception(
            "realtime.abroadcast failed for topic=%s event=%s", topic, event
        )


__all__ = ["broadcast", "abroadcast", "sanitize_topic"]
