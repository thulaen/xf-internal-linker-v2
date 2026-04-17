"""
End-to-end tests for the sync ↔ realtime bridge.

Phase R1.3 of the master plan. Proves that SyncJob and WebhookReceipt
lifecycle changes reach a WebSocket subscriber on the expected topic.
"""

from __future__ import annotations


from django.contrib.auth import get_user_model
from django.test import TransactionTestCase, override_settings

from channels.db import database_sync_to_async
from channels.testing import WebsocketCommunicator

from apps.realtime.consumers import RealtimeConsumer
from apps.sync.models import SyncJob, WebhookReceipt


IN_MEMORY_CHANNEL_LAYER = {
    "default": {"BACKEND": "channels.layers.InMemoryChannelLayer"},
}


@override_settings(CHANNEL_LAYERS=IN_MEMORY_CHANNEL_LAYER)
class SyncRealtimeSignalsTests(TransactionTestCase):
    """SyncJob + WebhookReceipt signal wiring."""

    def setUp(self) -> None:
        User = get_user_model()
        self.user = User.objects.create_user(username="sync-r1", password="x")

    async def _subscribe_to(self, *topics: str) -> WebsocketCommunicator:
        comm = WebsocketCommunicator(RealtimeConsumer.as_asgi(), "/ws/realtime/")
        comm.scope["user"] = self.user
        ok, _ = await comm.connect()
        self.assertTrue(ok)
        await comm.receive_json_from()  # connection.established
        await comm.send_json_to({"action": "subscribe", "topics": list(topics)})
        await comm.receive_json_from()  # subscription.ack
        return comm

    @database_sync_to_async
    def _create_sync_job(self, **kw) -> SyncJob:
        return SyncJob.objects.create(**kw)

    @database_sync_to_async
    def _save_sync_job(self, job: SyncJob) -> None:
        job.save()

    @database_sync_to_async
    def _create_webhook(self, **kw) -> WebhookReceipt:
        return WebhookReceipt.objects.create(**kw)

    async def test_sync_job_created_broadcasts(self):
        comm = await self._subscribe_to("jobs.history")
        job = await self._create_sync_job(source="api", mode="full", status="pending")
        update = await comm.receive_json_from()
        self.assertEqual(update["topic"], "jobs.history")
        self.assertEqual(update["event"], "job.created")
        self.assertEqual(update["payload"]["job_id"], str(job.job_id))
        await comm.disconnect()

    async def test_sync_job_updated_broadcasts(self):
        job = await self._create_sync_job(source="api", mode="full", status="pending")
        comm = await self._subscribe_to("jobs.history")
        job.status = "running"
        await self._save_sync_job(job)
        update = await comm.receive_json_from()
        self.assertEqual(update["event"], "job.updated")
        self.assertEqual(update["payload"]["status"], "running")
        await comm.disconnect()

    async def test_webhook_receipt_created_broadcasts(self):
        comm = await self._subscribe_to("webhooks.receipts")
        await self._create_webhook(
            source="api",
            event_type="post.updated",
            payload={"id": 1},
        )
        update = await comm.receive_json_from()
        self.assertEqual(update["topic"], "webhooks.receipts")
        self.assertEqual(update["event"], "receipt.created")
        self.assertEqual(update["payload"]["event_type"], "post.updated")
        await comm.disconnect()
