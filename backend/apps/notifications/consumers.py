"""
Notifications WebSocket consumer.

Clients connect to ws/notifications/ and receive notification.alert events
whenever emit_operator_alert publishes to the notifications_global group.
"""

from channels.generic.websocket import AsyncJsonWebsocketConsumer

from .services import _NOTIFICATION_GROUP


class NotificationConsumer(AsyncJsonWebsocketConsumer):
    """Global notification stream — one channel for all connected operators."""

    async def connect(self) -> None:
        user = self.scope.get("user")
        if user is None or not user.is_authenticated:
            await self.close(code=4003)
            return
        await self.channel_layer.group_add(_NOTIFICATION_GROUP, self.channel_name)
        await self.accept()
        await self.send_json({
            "type": "connection.established",
            "message": "Connected to notification stream.",
        })

    async def disconnect(self, close_code: int) -> None:
        await self.channel_layer.group_discard(_NOTIFICATION_GROUP, self.channel_name)

    # ── Channel layer event handlers ──────────────────────────────────

    async def notification_alert(self, event: dict) -> None:
        """Forward a notification.alert event from the channel layer to the client."""
        await self.send_json(event)
