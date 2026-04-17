"""
Realtime WebSocket consumer.

One endpoint (/ws/realtime/) handles every topic the frontend cares about.
Clients subscribe / unsubscribe with JSON frames over the same connection,
so a single tab holds one socket regardless of how many widgets it shows.

Message protocol
----------------
Client → server:
    {"action": "subscribe",   "topics": ["diagnostics", "crawler.sessions"]}
    {"action": "unsubscribe", "topics": ["crawler.sessions"]}
    {"action": "publish",     "topic": "presence.dashboard",
                              "event": "heartbeat", "payload": {...}}
    {"action": "ping"}

Server → client:
    {"type": "connection.established", "message": "..."}
    {"type": "subscription.ack",       "topics": ["diagnostics"], "denied": ["settings.runtime"]}
    {"type": "unsubscription.ack",     "topics": ["crawler.sessions"]}
    {"type": "pong"}
    {"type": "topic.update",           "topic": "diagnostics",
                                       "event": "entity.updated",
                                       "payload": {...}}
    {"type": "error",                  "message": "..."}

Design rules
------------
- Anonymous connections are rejected with close code 4003.
- Per-connection topic set tracked in self._topics; cleaned up on disconnect.
- Per-topic permission check runs at subscribe time via apps.realtime.permissions.
- The `topic_update` handler is the Channels dispatch target for
  group_send messages with type="topic.update". Names must use underscores.
"""

from __future__ import annotations

import logging
from typing import Any, Iterable

from channels.generic.websocket import AsyncJsonWebsocketConsumer

from .permissions import can_publish, can_subscribe
from .services import abroadcast, sanitize_topic

logger = logging.getLogger(__name__)


class RealtimeConsumer(AsyncJsonWebsocketConsumer):
    """Generic topic-based WebSocket endpoint. See module docstring."""

    # Max topics a single connection may hold simultaneously. Guards against
    # a client that tries to flood subscribe requests.
    MAX_TOPICS_PER_CONNECTION = 64

    async def connect(self) -> None:
        user = self.scope.get("user")
        if user is None or not getattr(user, "is_authenticated", False):
            await self.close(code=4003)
            return

        # Initialise the per-connection subscription set. Channels reuses the
        # consumer instance across messages, so this dict stays alive for the
        # lifetime of the socket.
        self._topics: set[str] = set()

        await self.accept()
        await self.send_json(
            {
                "type": "connection.established",
                "message": "Realtime channel ready. Send an action=subscribe frame to start.",
            }
        )

    async def disconnect(self, close_code: int) -> None:
        # Defensive — the instance may be torn down before connect() finished.
        topics = getattr(self, "_topics", set())
        for topic in list(topics):
            await self._leave(topic)
        topics.clear()

    # ── Incoming frames ───────────────────────────────────────────────

    async def receive_json(self, content: Any, **kwargs: Any) -> None:
        if not isinstance(content, dict):
            await self._send_error("Frame must be a JSON object.")
            return

        action = content.get("action")
        if action == "subscribe":
            await self._handle_subscribe(content.get("topics"))
        elif action == "unsubscribe":
            await self._handle_unsubscribe(content.get("topics"))
        elif action == "publish":
            # Phase RC / Gaps 139-142 — client-originated broadcast.
            await self._handle_publish(
                content.get("topic"),
                content.get("event"),
                content.get("payload"),
            )
        elif action == "ping":
            await self.send_json({"type": "pong"})
        else:
            await self._send_error(f"Unknown action: {action!r}")

    async def _handle_subscribe(self, topics_raw: Any) -> None:
        topics = self._normalise_topics(topics_raw)
        if topics is None:
            await self._send_error("`topics` must be a list of strings.")
            return

        user = self.scope.get("user")
        added: list[str] = []
        denied: list[str] = []

        for topic in topics:
            if topic in self._topics:
                continue
            if len(self._topics) >= self.MAX_TOPICS_PER_CONNECTION:
                denied.append(topic)
                continue
            if not can_subscribe(user, topic):
                denied.append(topic)
                continue
            await self._join(topic)
            added.append(topic)

        await self.send_json(
            {"type": "subscription.ack", "topics": added, "denied": denied}
        )

    async def _handle_unsubscribe(self, topics_raw: Any) -> None:
        topics = self._normalise_topics(topics_raw)
        if topics is None:
            await self._send_error("`topics` must be a list of strings.")
            return

        removed: list[str] = []
        for topic in topics:
            if topic in self._topics:
                await self._leave(topic)
                removed.append(topic)

        await self.send_json({"type": "unsubscription.ack", "topics": removed})

    async def _handle_publish(self, topic: Any, event: Any, payload: Any) -> None:
        """Phase RC / Gaps 139-142 — client publishes a payload that
        the server immediately fans out to every subscriber of the
        topic (including the publisher's other tabs).

        Hard-limited to collaboration namespaces by ``can_publish``;
        any other topic returns an error frame so a misuse fails loud
        instead of silently broadcasting.
        """
        if not isinstance(topic, str) or not topic.strip():
            await self._send_error("`topic` must be a non-empty string.")
            return
        if not isinstance(event, str) or not event.strip():
            await self._send_error("`event` must be a non-empty string.")
            return
        if payload is None:
            payload = {}
        if not isinstance(payload, dict):
            await self._send_error("`payload` must be a JSON object.")
            return

        topic = topic.strip()
        if not can_publish(self.scope.get("user"), topic):
            await self._send_error(f"Publishing to {topic!r} is not allowed.")
            return

        # Stamp the publisher so subscribers can ignore their own
        # echo if they want to. Username + a stable connection id.
        user = self.scope.get("user")
        publisher = {
            "username": getattr(user, "username", "") or "",
            "user_id": getattr(user, "pk", None),
            "connection_id": self.channel_name,
        }
        full_payload = {**payload, "_publisher": publisher}

        # Reuses the producer helper so the channel-layer group_send
        # + sanitize_topic logic stays in one place. The async twin
        # (`abroadcast`) avoids the async_to_sync warning here.
        await abroadcast(topic, event.strip(), full_payload)

    # ── Group membership ──────────────────────────────────────────────

    async def _join(self, topic: str) -> None:
        group = sanitize_topic(topic)
        await self.channel_layer.group_add(group, self.channel_name)
        self._topics.add(topic)

    async def _leave(self, topic: str) -> None:
        group = sanitize_topic(topic)
        await self.channel_layer.group_discard(group, self.channel_name)
        self._topics.discard(topic)

    # ── Channels group dispatch ───────────────────────────────────────

    async def topic_update(self, event: dict) -> None:
        """
        Forward a topic.update event from the channel layer to the client.

        Channels translates the type field "topic.update" into the method
        name `topic_update` (dots → underscores). Producers call
        apps.realtime.services.broadcast() which shapes the event for us.
        """
        await self.send_json(
            {
                "type": "topic.update",
                "topic": event.get("topic"),
                "event": event.get("event"),
                "payload": event.get("payload") or {},
            }
        )

    # ── Helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _normalise_topics(raw: Any) -> list[str] | None:
        if not isinstance(raw, Iterable) or isinstance(raw, (str, bytes)):
            return None
        topics: list[str] = []
        for item in raw:
            if not isinstance(item, str):
                return None
            trimmed = item.strip()
            if trimmed:
                topics.append(trimmed)
        return topics

    async def _send_error(self, message: str) -> None:
        await self.send_json({"type": "error", "message": message})
