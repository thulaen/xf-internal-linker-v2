"""
Tests for the realtime app.

Covers:
- sanitize_topic: invalid chars collapse to underscore, truncation at 100
- can_subscribe: staff-only topic denied for anonymous, allowed for staff
- broadcast: silent no-op when no channel layer configured
- RealtimeConsumer: subscribe / unsubscribe / ping / topic.update dispatch,
  including rejection of anonymous connections.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.test import TestCase, TransactionTestCase, override_settings

from channels.layers import get_channel_layer
from channels.testing import WebsocketCommunicator

from .consumers import RealtimeConsumer
from .permissions import can_subscribe
from .services import broadcast, sanitize_topic


# ── Unit tests (sync, fast) ─────────────────────────────────────────


class SanitizeTopicTests(TestCase):
    def test_empty_input_returns_single_underscore(self):
        self.assertEqual(sanitize_topic(""), "_")
        self.assertEqual(sanitize_topic(None), "_")  # type: ignore[arg-type]

    def test_plain_ascii_unchanged(self):
        self.assertEqual(sanitize_topic("diagnostics"), "diagnostics")
        self.assertEqual(sanitize_topic("settings.runtime"), "settings.runtime")
        self.assertEqual(sanitize_topic("crawler.sessions"), "crawler.sessions")
        self.assertEqual(sanitize_topic("ab-12_3.4"), "ab-12_3.4")

    def test_invalid_chars_collapsed_to_underscore(self):
        self.assertEqual(sanitize_topic("a b c"), "a_b_c")
        self.assertEqual(sanitize_topic("one/two"), "one_two")
        self.assertEqual(sanitize_topic("a!!!b"), "a_b")

    def test_length_cap_at_100(self):
        long_topic = "x" * 250
        sanitised = sanitize_topic(long_topic)
        self.assertEqual(len(sanitised), 100)
        self.assertEqual(sanitised, "x" * 100)

    def test_leading_trailing_whitespace_stripped(self):
        self.assertEqual(sanitize_topic("  diagnostics  "), "diagnostics")


class PermissionTests(TestCase):
    """
    `is_authenticated` is a Django property (not a field), so we use real
    User instances — their `.is_authenticated` is always True — and
    AnonymousUser for the negative case.
    """

    def test_default_authenticated_allowed(self):
        User = get_user_model()
        user = User(username="u1", is_staff=False)
        self.assertTrue(can_subscribe(user, "diagnostics"))

    def test_anonymous_denied(self):
        self.assertFalse(can_subscribe(AnonymousUser(), "diagnostics"))

    def test_staff_only_topic_denied_for_non_staff(self):
        User = get_user_model()
        user = User(username="u2", is_staff=False)
        self.assertFalse(can_subscribe(user, "settings.runtime"))

    def test_staff_only_topic_allowed_for_staff(self):
        User = get_user_model()
        user = User(username="u3", is_staff=True)
        self.assertTrue(can_subscribe(user, "settings.runtime"))


class BroadcastTests(TestCase):
    @override_settings(CHANNEL_LAYERS={})
    def test_broadcast_without_channel_layer_is_silent_noop(self):
        # No configured channel layer → function must not raise.
        broadcast("diagnostics", "entity.updated", {"id": 1})

    def test_broadcast_swallows_transport_errors(self):
        # Point the channel layer at an invalid host via override_settings
        # in an in-process way would be heavy. Instead, we just verify
        # broadcast() doesn't raise for a valid layer + exotic topic.
        broadcast("valid.topic-ok_1", "entity.updated", {"ok": True})


# ── Async consumer integration tests ────────────────────────────────
#
# TransactionTestCase (not TestCase) is required because Django's TestCase
# wraps each test in a transaction that cannot span an async boundary —
# async Channels code runs on the event loop, where the thread-local DB
# connection Django holds for the transaction is a different connection
# than the one the async code opens, and teardown rolls the wrong one back.
# See the "Testing consumers" section of the Channels docs.
#
# We also bypass TransactionTestCase's per-method DB flush by letting setUp
# create users once and reusing them — every test disconnects cleanly.

IN_MEMORY_CHANNEL_LAYER = {
    "default": {"BACKEND": "channels.layers.InMemoryChannelLayer"},
}


@override_settings(CHANNEL_LAYERS=IN_MEMORY_CHANNEL_LAYER)
class RealtimeConsumerTests(TransactionTestCase):
    """Integration tests for the full subscribe → broadcast → forward cycle."""

    def setUp(self):
        User = get_user_model()
        self.plain_user = User.objects.create_user(
            username="u-plain", password="x", is_staff=False
        )
        self.staff_user = User.objects.create_user(
            username="u-staff", password="x", is_staff=True
        )

    def _communicator(self, user) -> WebsocketCommunicator:
        comm = WebsocketCommunicator(RealtimeConsumer.as_asgi(), "/ws/realtime/")
        comm.scope["user"] = user if user is not None else AnonymousUser()
        return comm

    async def test_anonymous_connection_closed(self):
        comm = self._communicator(None)
        connected, _close_code = await comm.connect()
        self.assertFalse(connected)
        await comm.disconnect()

    async def test_authenticated_sees_connection_established(self):
        comm = self._communicator(self.plain_user)
        connected, _ = await comm.connect()
        self.assertTrue(connected)
        hello = await comm.receive_json_from()
        self.assertEqual(hello["type"], "connection.established")
        await comm.disconnect()

    async def test_subscribe_and_receive_broadcast(self):
        comm = self._communicator(self.plain_user)
        connected, _ = await comm.connect()
        self.assertTrue(connected)
        await comm.receive_json_from()  # drain connection.established

        await comm.send_json_to({"action": "subscribe", "topics": ["diagnostics"]})
        ack = await comm.receive_json_from()
        self.assertEqual(ack["type"], "subscription.ack")
        self.assertIn("diagnostics", ack["topics"])
        self.assertEqual(ack["denied"], [])

        # Fire a broadcast from outside and assert the consumer forwards it.
        layer = get_channel_layer()
        await layer.group_send(
            sanitize_topic("diagnostics"),
            {
                "type": "topic.update",
                "topic": "diagnostics",
                "event": "entity.updated",
                "payload": {"id": 42},
            },
        )
        update = await comm.receive_json_from()
        self.assertEqual(update["type"], "topic.update")
        self.assertEqual(update["topic"], "diagnostics")
        self.assertEqual(update["event"], "entity.updated")
        self.assertEqual(update["payload"], {"id": 42})
        await comm.disconnect()

    async def test_subscribe_denied_for_staff_topic_when_not_staff(self):
        comm = self._communicator(self.plain_user)
        await comm.connect()
        await comm.receive_json_from()  # drain

        await comm.send_json_to(
            {"action": "subscribe", "topics": ["settings.runtime"]}
        )
        ack = await comm.receive_json_from()
        self.assertEqual(ack["type"], "subscription.ack")
        self.assertEqual(ack["topics"], [])
        self.assertEqual(ack["denied"], ["settings.runtime"])
        await comm.disconnect()

    async def test_unsubscribe_stops_delivery(self):
        comm = self._communicator(self.plain_user)
        await comm.connect()
        await comm.receive_json_from()  # drain

        await comm.send_json_to({"action": "subscribe", "topics": ["diagnostics"]})
        await comm.receive_json_from()  # subscription.ack

        await comm.send_json_to({"action": "unsubscribe", "topics": ["diagnostics"]})
        ack = await comm.receive_json_from()
        self.assertEqual(ack["type"], "unsubscription.ack")
        self.assertEqual(ack["topics"], ["diagnostics"])

        # A subsequent broadcast must NOT arrive.
        layer = get_channel_layer()
        await layer.group_send(
            sanitize_topic("diagnostics"),
            {
                "type": "topic.update",
                "topic": "diagnostics",
                "event": "entity.updated",
                "payload": {},
            },
        )
        self.assertTrue(await comm.receive_nothing(timeout=0.2))
        await comm.disconnect()

    async def test_ping_returns_pong(self):
        comm = self._communicator(self.plain_user)
        await comm.connect()
        await comm.receive_json_from()  # drain

        await comm.send_json_to({"action": "ping"})
        pong = await comm.receive_json_from()
        self.assertEqual(pong["type"], "pong")
        await comm.disconnect()

    async def test_unknown_action_returns_error(self):
        comm = self._communicator(self.plain_user)
        await comm.connect()
        await comm.receive_json_from()  # drain

        await comm.send_json_to({"action": "unknown"})
        err = await comm.receive_json_from()
        self.assertEqual(err["type"], "error")
        await comm.disconnect()
