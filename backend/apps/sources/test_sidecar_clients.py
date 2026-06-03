"""Focused tests for sources sidecar clients."""

from __future__ import annotations

from types import SimpleNamespace
from unittest import mock

from django.test import SimpleTestCase

from apps.sources._sidecars import attrouted_client


class AttroutedClientTests(SimpleTestCase):
    def test_route_sends_attributes_and_unit_id(self) -> None:
        pb = _AttroutedPb()
        grpc_mod = _AttroutedGrpc()

        with (
            mock.patch.object(
                attrouted_client,
                "load_service_stubs",
                return_value=(pb, grpc_mod),
            ),
            mock.patch.object(
                attrouted_client,
                "sidecars_channel",
                return_value=_FakeChannel(),
            ),
        ):
            result = attrouted_client.AttroutedClient(deadline=1.0).route(
                source="xenforo",
                attributes={"priority": "high"},
                unit_id="unit-1",
            )

        self.assertEqual(grpc_mod.last_request.attributes, {"priority": "high"})
        self.assertEqual(grpc_mod.last_request.unit_id, "unit-1")
        self.assertEqual(result.target, "celery:high")


class _FakeChannel:
    def __enter__(self):
        return object()

    def __exit__(self, exc_type, exc, traceback) -> bool:
        return False


class _Request:
    def __init__(self, **kwargs) -> None:
        self.__dict__.update(kwargs)


class _AttroutedPb:
    RouteRequest = _Request


class _AttroutedGrpc:
    last_request = None

    class AttroutedStub:
        def __init__(self, channel) -> None:
            self.channel = channel

        def Route(self, request, timeout):
            _AttroutedGrpc.last_request = request
            return SimpleNamespace(
                matched_rule_id="rule-1",
                target="celery:high",
                explanation="priority route",
            )
