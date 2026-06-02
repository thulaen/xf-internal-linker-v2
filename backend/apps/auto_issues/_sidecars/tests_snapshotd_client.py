"""Tests for SnapshotdClient.health() fast-fail connect timeout.

Performance fix: when snapshotd is OFF, health() must fail fast instead of
blocking ~5 seconds on the default gRPC connect timeout
(DEFAULT_CONNECT_TIMEOUT=5.0 in apps._sidecars_shared.channel). A health probe
is a liveness check, so it opens its channel with a short connect timeout
(~0.3s); the data RPCs keep the normal connect timeout.

Named ``tests_snapshotd_client.py`` (matching the ``snapshotd_client.py`` source
stem) so the diff-scoped mutation gate discovers it.
"""
from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase


class HealthFastConnectTimeoutTests(SimpleTestCase):
    """health() must open its channel with a short connect timeout."""

    def _call_health(self):
        from apps.auto_issues._sidecars import snapshotd_client  # noqa: PLC0415

        captured: dict[str, object] = {"connect_timeout": "<unset>"}

        @contextmanager
        def fake_channel(socket_path=None, connect_timeout=None, **kwargs):
            captured["connect_timeout"] = connect_timeout
            yield MagicMock()

        fake_pb = MagicMock()
        fake_pb.HealthStatus.Name.return_value = "HEALTH_SERVING"
        fake_grpc = MagicMock()

        with (
            patch.object(snapshotd_client, "sidecars_channel", fake_channel),
            patch.object(
                snapshotd_client, "load_service_stubs", return_value=(fake_pb, fake_grpc)
            ),
        ):
            result = snapshotd_client.SnapshotdClient().health()
        return result, captured["connect_timeout"]

    def test_health_passes_short_connect_timeout(self):
        """health() opens its channel with an explicit sub-second connect timeout."""
        result, connect_timeout = self._call_health()
        self.assertEqual(result, "HEALTH_SERVING")
        self.assertIsInstance(
            connect_timeout, float, "health() must pass an explicit connect_timeout"
        )
        # Fast probe: strictly between 0 and 1 second (kills the 5.0s default and
        # the 0/1 number mutants).
        self.assertGreater(connect_timeout, 0.0)
        self.assertLess(connect_timeout, 1.0)

    def test_data_rpcs_do_not_pass_short_connect_timeout(self):
        """Only the health probe shortens the connect timeout; data RPCs do not."""
        from apps.auto_issues._sidecars import snapshotd_client  # noqa: PLC0415

        captured: dict[str, object] = {"connect_timeout": "<unset>"}

        @contextmanager
        def fake_channel(socket_path=None, connect_timeout=None, **kwargs):
            captured["connect_timeout"] = connect_timeout
            yield MagicMock()

        fake_pb, fake_grpc = _fake_stubs()
        with (
            patch.object(snapshotd_client, "sidecars_channel", fake_channel),
            patch.object(
                snapshotd_client, "load_service_stubs", return_value=(fake_pb, fake_grpc)
            ),
        ):
            snapshotd_client.SnapshotdClient().get_snapshot("snap-1")
        # The data RPC must NOT pass the fast health timeout; it leaves it at the
        # default (None) so the shared channel uses DEFAULT_CONNECT_TIMEOUT.
        self.assertIsNone(captured["connect_timeout"])


class ServiceNameTests(SimpleTestCase):
    """The client loads stubs for the literal 'snapshotd' service."""

    def test_service_name_is_snapshotd(self):
        from apps.auto_issues._sidecars import snapshotd_client  # noqa: PLC0415

        self.assertEqual(snapshotd_client.SERVICE_NAME, "snapshotd")

    def test_health_loads_stubs_for_snapshotd(self):
        """load_service_stubs is called with the exact 'snapshotd' name (kills the string mutant)."""
        from apps.auto_issues._sidecars import snapshotd_client  # noqa: PLC0415

        fake_pb, fake_grpc = _fake_stubs()
        loader = MagicMock(return_value=(fake_pb, fake_grpc))

        @contextmanager
        def fake_channel(socket_path=None, connect_timeout=None, **kw):
            yield MagicMock()

        with (
            patch.object(snapshotd_client, "sidecars_channel", fake_channel),
            patch.object(snapshotd_client, "load_service_stubs", loader),
        ):
            snapshotd_client.SnapshotdClient().health()
        loader.assert_called_with("snapshotd")


class NormalizeKindTests(SimpleTestCase):
    """_normalize_kind maps human labels to SK_* without double-prefixing."""

    def test_bare_label_gets_sk_prefix(self):
        from apps.auto_issues._sidecars import snapshotd_client  # noqa: PLC0415

        # Kills the f"SK_{upper}" string mutant.
        self.assertEqual(snapshotd_client._normalize_kind("before"), "SK_BEFORE")
        self.assertEqual(snapshotd_client._normalize_kind("after"), "SK_AFTER")

    def test_already_prefixed_label_is_unchanged(self):
        from apps.auto_issues._sidecars import snapshotd_client  # noqa: PLC0415

        # Kills the startswith("SK_") mutant: a value already prefixed must NOT
        # be prefixed again (the mutant would return "SK_SK_AFTER").
        self.assertEqual(snapshotd_client._normalize_kind("SK_AFTER"), "SK_AFTER")
        self.assertEqual(snapshotd_client._normalize_kind("sk_before"), "SK_BEFORE")


class FrozenDataclassTests(SimpleTestCase):
    """SnapshotRow and SnapshotDTO are immutable (frozen=True)."""

    def test_snapshot_row_is_frozen(self):
        from dataclasses import FrozenInstanceError  # noqa: PLC0415

        from apps.auto_issues._sidecars import snapshotd_client  # noqa: PLC0415

        row = snapshotd_client.SnapshotRow(payload_json=b"{}")
        with self.assertRaises(FrozenInstanceError):
            row.payload_json = b"changed"  # type: ignore[misc]

    def test_snapshot_dto_is_frozen(self):
        from dataclasses import FrozenInstanceError  # noqa: PLC0415

        from apps.auto_issues._sidecars import snapshotd_client  # noqa: PLC0415

        dto = snapshotd_client._snapshot_to_dto(_fake_proto_snapshot(), None)
        with self.assertRaises(FrozenInstanceError):
            dto.id = "other"  # type: ignore[misc]


class SnapshotDtoConversionTests(SimpleTestCase):
    """_snapshot_to_dto maps a generated proto snapshot onto the public DTO."""

    def test_snapshot_to_dto_copies_every_field(self):
        from apps.auto_issues._sidecars import snapshotd_client  # noqa: PLC0415

        proto = _fake_proto_snapshot()
        kind_enum = MagicMock()
        kind_enum.Name.return_value = "SK_BEFORE"

        dto = snapshotd_client._snapshot_to_dto(proto, kind_enum)

        self.assertEqual(dto.id, "snap-1")
        self.assertEqual(dto.issue_id, 42)
        self.assertEqual(dto.kind, "SK_BEFORE")
        self.assertEqual(dto.category, "perf")
        self.assertEqual(dto.schema_version, "v1")
        self.assertEqual(dto.path, "/var/lib/xf/sidecars/snapshotd/issue_42/snap-1.jsonl")
        self.assertEqual(dto.row_count, 3)
        self.assertEqual(dto.size_bytes, 128)
        self.assertTrue(dto.pinned)
        self.assertEqual(dto.created_at_unix_nanos, 111)
        self.assertEqual(dto.last_touched_at_unix_nanos, 222)

    def test_snapshot_to_dto_without_kind_enum_uses_str(self):
        from apps.auto_issues._sidecars import snapshotd_client  # noqa: PLC0415

        proto = _fake_proto_snapshot()
        dto = snapshotd_client._snapshot_to_dto(proto, None)
        # No enum supplied -> the raw kind value is stringified.
        self.assertEqual(dto.kind, str(proto.kind))


class SnapshotDataRpcTests(SimpleTestCase):
    """The data RPCs build a request, pass the call deadline, and return a DTO."""

    def _run(self, method_name, *args, **kwargs):
        from apps.auto_issues._sidecars import snapshotd_client  # noqa: PLC0415

        fake_pb, fake_grpc = _fake_stubs()
        self.pb = fake_pb
        self.stub = fake_grpc.SnapshotdStub.return_value

        @contextmanager
        def fake_channel(socket_path=None, connect_timeout=None, **kw):
            yield MagicMock()

        with (
            patch.object(snapshotd_client, "sidecars_channel", fake_channel),
            patch.object(
                snapshotd_client, "load_service_stubs", return_value=(fake_pb, fake_grpc)
            ),
        ):
            client = snapshotd_client.SnapshotdClient(deadline=2.5)
            self.deadline = client._deadline
            return getattr(client, method_name)(*args, **kwargs)

    def test_constructor_keeps_the_deadline(self):
        # Kills the `self._deadline = None` mutant on the constructor.
        self._run("get_snapshot", "snap-1")
        self.assertEqual(self.deadline, 2.5)

    def test_create_snapshot_builds_request_and_passes_deadline(self):
        from apps.auto_issues._sidecars import snapshotd_client  # noqa: PLC0415

        rows = [snapshotd_client.SnapshotRow(payload_json=b"{}")]
        dto = self._run(
            "create_snapshot",
            issue_id=42,
            kind="before",
            category="perf",
            schema_version="v1",
            rows=rows,
        )
        self.assertEqual(dto.id, "snap-1")
        # The request was built (kills the `request = None` mutant) with the
        # caller's fields and the default max_size_mb=0 (kills the =1 mutant).
        _, kwargs = self.pb.CreateSnapshotRequest.call_args
        self.assertEqual(kwargs["issue_id"], 42)
        self.assertEqual(kwargs["category"], "perf")
        self.assertEqual(kwargs["schema_version"], "v1")
        self.assertEqual(kwargs["max_size_mb"], 0)
        # The call deadline reached the stub (kills the deadline mutant).
        _, call_kwargs = self.stub.CreateSnapshot.call_args
        self.assertEqual(call_kwargs["timeout"], 2.5)

    def test_create_snapshot_forwards_explicit_max_size_mb(self):
        from apps.auto_issues._sidecars import snapshotd_client  # noqa: PLC0415

        rows = [snapshotd_client.SnapshotRow(payload_json=b"{}")]
        self._run(
            "create_snapshot",
            issue_id=7,
            kind="after",
            category="perf",
            schema_version="v1",
            rows=rows,
            max_size_mb=9,
        )
        _, kwargs = self.pb.CreateSnapshotRequest.call_args
        self.assertEqual(kwargs["max_size_mb"], 9)

    def test_get_snapshot_returns_dto(self):
        self.assertEqual(self._run("get_snapshot", "snap-1").id, "snap-1")

    def test_list_by_issue_returns_dtos(self):
        result = self._run("list_by_issue", 42)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].id, "snap-1")

    def test_pin_returns_dto(self):
        self.assertTrue(self._run("pin", "snap-1", 42).pinned)

    def test_unpin_returns_dto(self):
        self.assertEqual(self._run("unpin", "snap-1").id, "snap-1")


def _fake_proto_snapshot():
    """A stand-in for the generated Snapshot protobuf with every field set."""
    proto = MagicMock()
    proto.id = "snap-1"
    proto.issue_id = 42
    proto.kind = 1
    proto.category = "perf"
    proto.schema_version = "v1"
    proto.path = "/var/lib/xf/sidecars/snapshotd/issue_42/snap-1.jsonl"
    proto.row_count = 3
    proto.size_bytes = 128
    proto.pinned = True
    proto.created_at_unix_nanos = 111
    proto.last_touched_at_unix_nanos = 222
    return proto


def _fake_stubs():
    """Build (pb, grpc_mod) doubles whose RPC methods return a fake snapshot."""
    snap = _fake_proto_snapshot()
    fake_pb = MagicMock()
    fake_pb.SnapshotKind.SK_BEFORE = 1
    fake_pb.SnapshotKind.Name.return_value = "SK_BEFORE"

    stub = MagicMock()
    stub.CreateSnapshot.return_value = snap
    stub.GetSnapshot.return_value = snap
    stub.Pin.return_value = snap
    stub.Unpin.return_value = snap
    list_response = MagicMock()
    list_response.items = [snap]
    stub.ListByIssue.return_value = list_response

    fake_grpc = MagicMock()
    fake_grpc.SnapshotdStub.return_value = stub
    return fake_pb, fake_grpc
