"""
WebSocket consumer for real-time job progress updates.

The Angular frontend connects to ws://.../ws/jobs/<job_id>/
and receives push events as the Celery pipeline task progresses.

Message format sent to the client:
{
    "type": "job.progress",
    "job_id": "...",
    "state": "running|completed|failed|cancelled",
    "progress": 0.75,           // 0.0 to 1.0
    "message": "Processing...",
    "suggestions_created": 42,
    "destinations_processed": 100,
    "destinations_total": 150,
    "error": null
}
"""

import logging

from channels.generic.websocket import AsyncJsonWebsocketConsumer

logger = logging.getLogger(__name__)


class JobProgressConsumer(AsyncJsonWebsocketConsumer):
    """
    WebSocket consumer that streams Celery pipeline job progress to the frontend.

    Each connected client subscribes to a single job_id channel group.
    Celery tasks publish progress events via the channel layer, and this
    consumer forwards them to the connected WebSocket client.

    URL pattern: ws://host/ws/jobs/<job_id>/
    """

    async def connect(self) -> None:
        """Accept the WebSocket connection and join the job's channel group."""
        self.job_id = self.scope["url_route"]["kwargs"]["job_id"]
        self.group_name = f"job_{self.job_id}"

        # Join the job-specific channel group
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

        logger.info("WebSocket client connected for job %s", self.job_id)

        # Send initial connection acknowledgement
        await self.send_json({
            "type": "connection.established",
            "job_id": self.job_id,
            "message": "Connected. Waiting for job progress events.",
        })

    async def disconnect(self, close_code: int) -> None:
        """Leave the job's channel group on disconnect."""
        await self.channel_layer.group_discard(self.group_name, self.channel_name)
        logger.debug("WebSocket client disconnected from job %s (code=%s)", self.job_id, close_code)

    async def receive_json(self, content: dict, **kwargs) -> None:
        """
        Handle messages from the client.
        Currently only 'ping' is supported (for keep-alive).
        """
        if content.get("type") == "ping":
            await self.send_json({"type": "pong"})

    # ── Channel layer event handlers ──────────────────────────────
    # These are called when Celery publishes to the group via channel layer.

    async def job_progress(self, event: dict) -> None:
        """Forward a job.progress event from Celery to the WebSocket client."""
        await self.send_json(event)

    async def job_complete(self, event: dict) -> None:
        """Forward a job.complete event and optionally close the connection."""
        await self.send_json(event)
        # Keep connection open so the client can acknowledge before disconnecting

    async def job_failed(self, event: dict) -> None:
        """Forward a job.failed event from Celery."""
        await self.send_json(event)
