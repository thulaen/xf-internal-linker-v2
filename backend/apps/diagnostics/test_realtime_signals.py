"""
End-to-end tests for the diagnostics ↔ realtime bridge.

Phase R1.1 of the master plan.

These tests prove that when the backend mutates a diagnostics row, a
WebSocket subscriber on the `diagnostics` topic actually receives a
broadcast without the test explicitly calling `broadcast()`. That's the
whole point of the signal wiring — nothing else in the app needs to know
real-time exists.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TransactionTestCase, override_settings

from channels.db import database_sync_to_async
from channels.testing import WebsocketCommunicator

from apps.diagnostics.models import ServiceStatusSnapshot, SystemConflict
from apps.realtime.consumers import RealtimeConsumer


IN_MEMORY_CHANNEL_LAYER = {
    "default": {"BACKEND": "channels.layers.InMemoryChannelLayer"},
}


@override_settings(CHANNEL_LAYERS=IN_MEMORY_CHANNEL_LAYER)
class DiagnosticsRealtimeSignalsTests(TransactionTestCase):
    """Signal wiring: model save/delete → realtime broadcast → WS client."""

    def setUp(self) -> None:
        User = get_user_model()
        self.user = User.objects.create_user(username="r1-user", password="x")

    async def _connect(self) -> WebsocketCommunicator:
        comm = WebsocketCommunicator(RealtimeConsumer.as_asgi(), "/ws/realtime/")
        comm.scope["user"] = self.user
        connected, _ = await comm.connect()
        self.assertTrue(connected)
        await comm.receive_json_from()  # connection.established
        await comm.send_json_to({"action": "subscribe", "topics": ["diagnostics"]})
        await comm.receive_json_from()  # subscription.ack
        return comm

    # ── DB helpers (wrap sync ORM for async test methods) ────────────
    _create_service = staticmethod(
        database_sync_to_async(ServiceStatusSnapshot.objects.create)
    )
    _create_conflict = staticmethod(
        database_sync_to_async(SystemConflict.objects.create)
    )

    @staticmethod
    @database_sync_to_async
    def _save_service(snap: ServiceStatusSnapshot) -> None:
        snap.save()

    @staticmethod
    @database_sync_to_async
    def _delete_service(snap: ServiceStatusSnapshot) -> None:
        snap.delete()

    @staticmethod
    @database_sync_to_async
    def _save_conflict(conflict: SystemConflict) -> None:
        conflict.save()

    # ── Tests ────────────────────────────────────────────────────────

    async def test_service_status_saved_broadcasts(self):
        comm = await self._connect()
        await self._create_service(
            service_name="postgresql", state="healthy", explanation="OK"
        )
        update = await comm.receive_json_from()
        self.assertEqual(update["type"], "topic.update")
        self.assertEqual(update["topic"], "diagnostics")
        self.assertEqual(update["event"], "service.status.created")
        self.assertEqual(update["payload"]["service_name"], "postgresql")
        self.assertEqual(update["payload"]["state"], "healthy")
        await comm.disconnect()

    async def test_service_status_updated_broadcasts(self):
        snap = await self._create_service(service_name="redis", state="healthy")
        comm = await self._connect()

        snap.state = "failed"
        await self._save_service(snap)

        update = await comm.receive_json_from()
        self.assertEqual(update["event"], "service.status.updated")
        self.assertEqual(update["payload"]["state"], "failed")
        await comm.disconnect()

    async def test_http_worker_service_status_is_suppressed(self):
        """
        http_worker is the decommissioned C# row. REST view filters it out
        (see apps/diagnostics/views.py). The signal must also suppress it so
        the same stale row doesn't slip through the WebSocket.
        """
        comm = await self._connect()
        await self._create_service(service_name="http_worker", state="failed")
        # Nothing should arrive.
        self.assertTrue(await comm.receive_nothing(timeout=0.2))
        await comm.disconnect()

    async def test_service_status_deleted_broadcasts(self):
        snap = await self._create_service(service_name="celery_worker", state="healthy")
        comm = await self._connect()

        snap_id = snap.pk
        await self._delete_service(snap)

        update = await comm.receive_json_from()
        self.assertEqual(update["event"], "service.status.deleted")
        self.assertEqual(update["payload"]["id"], snap_id)
        self.assertEqual(update["payload"]["service_name"], "celery_worker")
        await comm.disconnect()

    async def test_system_conflict_saved_broadcasts(self):
        comm = await self._connect()
        await self._create_conflict(
            conflict_type="mismatch",
            title="Spec drift",
            description="Spec and code disagree.",
            severity="high",
            location="apps/pipeline/services.py",
        )
        update = await comm.receive_json_from()
        self.assertEqual(update["event"], "conflict.created")
        self.assertEqual(update["payload"]["severity"], "high")
        self.assertEqual(update["payload"]["title"], "Spec drift")
        await comm.disconnect()

    async def test_system_conflict_resolved_still_broadcasts_as_update(self):
        conflict = await self._create_conflict(
            conflict_type="drift",
            title="A drift",
            description="...",
            severity="medium",
            location="x.py",
        )
        comm = await self._connect()

        conflict.resolved = True
        await self._save_conflict(conflict)
        update = await comm.receive_json_from()
        self.assertEqual(update["event"], "conflict.updated")
        self.assertTrue(update["payload"]["resolved"])
        await comm.disconnect()
