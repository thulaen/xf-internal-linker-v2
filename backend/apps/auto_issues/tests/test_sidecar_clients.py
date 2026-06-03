"""Focused tests for the auto-issues sidecar clients."""

from __future__ import annotations

from types import SimpleNamespace
from unittest import mock

from django.test import SimpleTestCase

from apps.auto_issues._sidecars import schemard_client, snapshotd_client

# Selector coverage: apps.auto_issues._sidecars.schemard_client
# Selector coverage: apps.auto_issues._sidecars.snapshotd_client


class SnapshotdClientTests(SimpleTestCase):
    def test_create_snapshot_maps_kind_name_from_response(self) -> None:
        pb = _SnapshotPb()
        grpc_mod = _SnapshotGrpc()

        with (
            mock.patch.object(
                snapshotd_client,
                "load_service_stubs",
                return_value=(pb, grpc_mod),
            ),
            mock.patch.object(
                snapshotd_client,
                "sidecars_channel",
                return_value=_FakeChannel(),
            ),
        ):
            result = snapshotd_client.SnapshotdClient(deadline=1.0).create_snapshot(
                issue_id=42,
                kind="before",
                category="quota",
                schema_version="v1",
                rows=[snapshotd_client.SnapshotRow(payload_json=b"{}")],
            )

        self.assertEqual(result.kind, "SK_BEFORE")
        self.assertEqual(grpc_mod.last_request.kind, pb.SnapshotKind.SK_BEFORE)
        self.assertEqual(grpc_mod.last_request.rows[0].payload_json, b"{}")


class SchemardClientTests(SimpleTestCase):
    def test_register_maps_response_to_dto(self) -> None:
        pb = _SchemardPb()
        grpc_mod = _SchemardGrpc()

        with (
            mock.patch.object(
                schemard_client,
                "load_service_stubs",
                return_value=(pb, grpc_mod),
            ),
            mock.patch.object(
                schemard_client,
                "sidecars_channel",
                return_value=_FakeChannel(),
            ),
        ):
            result = schemard_client.SchemardClient(deadline=1.0).register(
                subject="autoissue",
                schema_json='{"type":"object"}',
                require_backward_compat=True,
            )

        self.assertEqual(result.subject, "autoissue")
        self.assertEqual(result.version, 7)
        self.assertTrue(grpc_mod.last_register_request.require_backward_compat)

    def test_check_compat_maps_level_and_response(self) -> None:
        pb = _SchemardPb()
        grpc_mod = _SchemardGrpc()

        with (
            mock.patch.object(
                schemard_client,
                "load_service_stubs",
                return_value=(pb, grpc_mod),
            ),
            mock.patch.object(
                schemard_client,
                "sidecars_channel",
                return_value=_FakeChannel(),
            ),
        ):
            result = schemard_client.SchemardClient(deadline=1.0).check_compat(
                subject="autoissue",
                candidate_schema_json="{}",
                level="BACKWARD",
            )

        self.assertTrue(result.compatible)
        self.assertEqual(result.checked_level, "COMP_BACKWARD")
        self.assertEqual(grpc_mod.last_check_request.level, pb.CompatLevel.COMP_BACKWARD)


class _FakeChannel:
    def __enter__(self):
        return object()

    def __exit__(self, exc_type, exc, traceback) -> bool:
        return False


class _Request:
    def __init__(self, **kwargs) -> None:
        self.__dict__.update(kwargs)


class _SnapshotKind:
    SK_BEFORE = 1

    @staticmethod
    def Name(value: int) -> str:
        return {1: "SK_BEFORE"}.get(value, f"SK_{value}")


class _SnapshotPb:
    SnapshotKind = _SnapshotKind
    CreateSnapshotRequest = _Request
    SnapshotRow = _Request


class _SnapshotGrpc:
    last_request = None

    class SnapshotdStub:
        def __init__(self, channel) -> None:
            self.channel = channel

        def CreateSnapshot(self, request, timeout):
            _SnapshotGrpc.last_request = request
            return SimpleNamespace(
                id="snap-1",
                issue_id=request.issue_id,
                kind=request.kind,
                category=request.category,
                schema_version=request.schema_version,
                path="/tmp/snap-1.jsonl",
                row_count=len(request.rows),
                size_bytes=2,
                pinned=False,
                created_at_unix_nanos=1,
                last_touched_at_unix_nanos=1,
            )


class _CompatLevel:
    COMP_BACKWARD = 1

    @staticmethod
    def Name(value: int) -> str:
        return {1: "COMP_BACKWARD"}.get(value, f"COMP_{value}")


class _SchemardPb:
    CompatLevel = _CompatLevel
    RegisterSchemaRequest = _Request
    GetSchemaRequest = _Request
    LatestRequest = _Request
    CheckCompatRequest = _Request
    Empty = _Request


class _SchemardGrpc:
    last_register_request = None
    last_check_request = None

    class SchemardStub:
        def __init__(self, channel) -> None:
            self.channel = channel

        def Register(self, request, timeout):
            _SchemardGrpc.last_register_request = request
            return SimpleNamespace(
                subject=request.subject,
                version=7,
                schema_json=request.schema_json,
                created_at_unix_nanos=99,
            )

        def CheckCompat(self, request, timeout):
            _SchemardGrpc.last_check_request = request
            return SimpleNamespace(
                compatible=True,
                detail="ok",
                checked_level=request.level,
            )
