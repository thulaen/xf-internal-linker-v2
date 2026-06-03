"""Focused tests for diagnostics sidecar clients."""

from __future__ import annotations

from types import SimpleNamespace
from unittest import mock

from django.test import SimpleTestCase

from apps.diagnostics._sidecars import errord_client


class ErrordClientTests(SimpleTestCase):
    def test_handle_uses_empty_top_frames_by_default(self) -> None:
        pb = _ErrordPb()
        grpc_mod = _ErrordGrpc()

        with (
            mock.patch.object(
                errord_client,
                "load_service_stubs",
                return_value=(pb, grpc_mod),
            ),
            mock.patch.object(
                errord_client,
                "sidecars_channel",
                return_value=_FakeChannel(),
            ),
        ):
            result = errord_client.ErrordClient(deadline=1.0).handle(
                class_name="ValueError",
                module="apps.demo",
                message="bad value",
            )

        self.assertEqual(grpc_mod.last_request.top_frames, [])
        self.assertEqual(result.action, "ACT_ALERT")


class _FakeChannel:
    def __enter__(self):
        return object()

    def __exit__(self, exc_type, exc, traceback) -> bool:
        return False


class _Request:
    def __init__(self, **kwargs) -> None:
        self.__dict__.update(kwargs)


class _Action:
    ACT_ALERT = 3

    @staticmethod
    def Name(value: int) -> str:
        return {3: "ACT_ALERT"}.get(value, f"ACT_{value}")


class _ErrordPb:
    HandleAction = _Action
    HandleExceptionRequest = _Request


class _ErrordGrpc:
    last_request = None

    class ErrordStub:
        def __init__(self, channel) -> None:
            self.channel = channel

        def Handle(self, request, timeout):
            _ErrordGrpc.last_request = request
            return SimpleNamespace(
                matched_policy_id="policy-1",
                action=_Action.ACT_ALERT,
                backoff_seconds=0,
                explanation="alert",
                autoissue_severity="high",
            )
