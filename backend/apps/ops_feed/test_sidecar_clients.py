"""Focused tests for ops-feed sidecar clients."""

from __future__ import annotations

from types import SimpleNamespace
from unittest import mock

from django.test import SimpleTestCase

from apps.ops_feed._sidecars import bullboard_client


class BullboardClientTests(SimpleTestCase):
    def test_post_normalizes_plain_severity_label(self) -> None:
        pb = _BullboardPb()
        grpc_mod = _BullboardGrpc()

        with (
            mock.patch.object(
                bullboard_client,
                "load_service_stubs",
                return_value=(pb, grpc_mod),
            ),
            mock.patch.object(
                bullboard_client,
                "sidecars_channel",
                return_value=_FakeChannel(),
            ),
        ):
            result = bullboard_client.BullboardClient(deadline=1.0).post(
                event_type="deploy",
                severity="error",
                message="Deploy failed",
                context_json=b'{"service":"backend"}',
            )

        self.assertEqual(grpc_mod.last_request.severity, pb.Severity.SEV_ERROR)
        self.assertEqual(result.severity, "SEV_ERROR")


class _FakeChannel:
    def __enter__(self):
        return object()

    def __exit__(self, exc_type, exc, traceback) -> bool:
        return False


class _Request:
    def __init__(self, **kwargs) -> None:
        self.__dict__.update(kwargs)


class _Severity:
    SEV_ERROR = 3

    @staticmethod
    def Name(value: int) -> str:
        return {3: "SEV_ERROR"}.get(value, f"SEV_{value}")


class _BullboardPb:
    Severity = _Severity
    PostBulletinRequest = _Request


class _BullboardGrpc:
    last_request = None

    class BullboardStub:
        def __init__(self, channel) -> None:
            self.channel = channel

        def Post(self, request, timeout):
            _BullboardGrpc.last_request = request
            return SimpleNamespace(
                id="bulletin-1",
                event_type=request.event_type,
                severity=request.severity,
                message=request.message,
                context_json=request.context_json,
                posted_at_unix_nanos=1,
                linked_autoissue_id=0,
            )
