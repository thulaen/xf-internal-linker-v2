"""
End-to-end tests for the core ↔ realtime bridge.

Phase R1.3. Proves that AppSetting changes broadcast on the
`settings.runtime` topic AND that the topic is staff-gated — non-staff
subscribers are denied and therefore receive nothing.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TransactionTestCase, override_settings

from channels.db import database_sync_to_async
from channels.testing import WebsocketCommunicator

from apps.core.models import AppSetting
from apps.realtime.consumers import RealtimeConsumer


IN_MEMORY_CHANNEL_LAYER = {
    "default": {"BACKEND": "channels.layers.InMemoryChannelLayer"},
}


@override_settings(CHANNEL_LAYERS=IN_MEMORY_CHANNEL_LAYER)
class AppSettingRealtimeSignalsTests(TransactionTestCase):
    """AppSetting signal → settings.runtime broadcast, staff-gated."""

    def setUp(self) -> None:
        User = get_user_model()
        self.staff = User.objects.create_user(
            username="cfg-staff", password="x", is_staff=True
        )
        self.non_staff = User.objects.create_user(
            username="cfg-plain", password="x", is_staff=False
        )

    async def _subscribe_as(self, user) -> WebsocketCommunicator:
        comm = WebsocketCommunicator(RealtimeConsumer.as_asgi(), "/ws/realtime/")
        comm.scope["user"] = user
        ok, _ = await comm.connect()
        self.assertTrue(ok)
        await comm.receive_json_from()  # connection.established
        await comm.send_json_to({"action": "subscribe", "topics": ["settings.runtime"]})
        return comm

    @database_sync_to_async
    def _create_setting(self, **kw) -> AppSetting:
        return AppSetting.objects.create(**kw)

    @database_sync_to_async
    def _save_setting(self, s: AppSetting) -> None:
        s.save()

    async def test_staff_receives_setting_update(self):
        comm = await self._subscribe_as(self.staff)
        ack = await comm.receive_json_from()
        self.assertEqual(ack["type"], "subscription.ack")
        self.assertIn("settings.runtime", ack["topics"])

        await self._create_setting(
            key="system.test_value", value="42", value_type="int", category="general"
        )
        update = await comm.receive_json_from()
        self.assertEqual(update["topic"], "settings.runtime")
        self.assertEqual(update["event"], "setting.created")
        self.assertEqual(update["payload"]["key"], "system.test_value")
        await comm.disconnect()

    async def test_non_staff_subscription_denied(self):
        comm = await self._subscribe_as(self.non_staff)
        ack = await comm.receive_json_from()
        self.assertEqual(ack["type"], "subscription.ack")
        self.assertEqual(ack["topics"], [])
        self.assertIn("settings.runtime", ack["denied"])

        # Create a setting — non-staff subscriber must NOT receive it.
        await self._create_setting(
            key="system.test_quiet", value="0", value_type="int", category="general"
        )
        self.assertTrue(await comm.receive_nothing(timeout=0.3))
        await comm.disconnect()
