"""Slice 1.6 — private snapshotd client.

Wraps the gRPC contract at services/sidecars/api/snapshotd.proto. Public
surface is apps.auto_issues.api (slice 1.6: thin app; slice 9: moves to
apps.governance.api per paper-trail #571).

Generated stubs live at backend/apps/_sidecars_pb/snapshotd/ — generate them
with the protoc command spelled out in StubsMissingError when missing.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from apps._sidecars_shared.channel import (
    DEFAULT_CALL_DEADLINE,
    load_service_stubs,
    sidecars_channel,
)

SERVICE_NAME = "snapshotd"

# A health probe is a quick liveness check. When snapshotd is OFF it must fail
# fast rather than block on the 5.0s default channel connect timeout
# (DEFAULT_CONNECT_TIMEOUT in apps._sidecars_shared.channel) — that connect wait
# is the slowest step of the session-start ritual. Data RPCs keep the normal
# connect timeout because by the time they run snapshotd is already reachable.
HEALTH_CONNECT_TIMEOUT_SECONDS = 0.3


@dataclass(frozen=True)
class SnapshotRow:
    """One row stored inside a snapshot. JSON-encoded by the caller."""
    payload_json: bytes


@dataclass(frozen=True)
class SnapshotDTO:
    """Plain-Python copy of services/sidecars/api/snapshotd.proto:Snapshot."""
    id: str
    issue_id: int
    kind: str
    category: str
    schema_version: str
    path: str
    row_count: int
    size_bytes: int
    pinned: bool
    created_at_unix_nanos: int
    last_touched_at_unix_nanos: int


def _snapshot_to_dto(proto_snapshot, kind_enum=None) -> SnapshotDTO:
    """Convert a generated Snapshot protobuf into the public DTO."""
    kind = kind_enum.Name(proto_snapshot.kind) if kind_enum else str(proto_snapshot.kind)
    return SnapshotDTO(
        id=proto_snapshot.id,
        issue_id=proto_snapshot.issue_id,
        kind=kind,
        category=proto_snapshot.category,
        schema_version=proto_snapshot.schema_version,
        path=proto_snapshot.path,
        row_count=proto_snapshot.row_count,
        size_bytes=proto_snapshot.size_bytes,
        pinned=proto_snapshot.pinned,
        created_at_unix_nanos=proto_snapshot.created_at_unix_nanos,
        last_touched_at_unix_nanos=proto_snapshot.last_touched_at_unix_nanos,
    )


class SnapshotdClient:
    """Sync gRPC client. Re-uses the shared sidecars channel per call.

    Long-running Django request paths should construct one client per
    request (the constructor is cheap; channels open per RPC).
    """

    def __init__(self, deadline: float = DEFAULT_CALL_DEADLINE) -> None:
        self._deadline = deadline

    def create_snapshot(
        self,
        *,
        issue_id: int,
        kind: str,
        category: str,
        schema_version: str,
        rows: Iterable[SnapshotRow],
        max_size_mb: int = 0,
    ) -> SnapshotDTO:
        """Write a snapshot to /var/lib/xf/sidecars/snapshotd/issue_<id>/<id>.jsonl."""
        pb, grpc_mod = load_service_stubs(SERVICE_NAME)
        request = pb.CreateSnapshotRequest(
            issue_id=issue_id,
            kind=getattr(pb.SnapshotKind, _normalize_kind(kind)),
            category=category,
            schema_version=schema_version,
            rows=[pb.SnapshotRow(payload_json=r.payload_json) for r in rows],
            max_size_mb=max_size_mb,
        )
        with sidecars_channel() as channel:
            stub = grpc_mod.SnapshotdStub(channel)
            response = stub.CreateSnapshot(request, timeout=self._deadline)
        return _snapshot_to_dto(response, pb.SnapshotKind)

    def get_snapshot(self, snapshot_id: str) -> SnapshotDTO:
        pb, grpc_mod = load_service_stubs(SERVICE_NAME)
        with sidecars_channel() as channel:
            stub = grpc_mod.SnapshotdStub(channel)
            response = stub.GetSnapshot(
                pb.GetSnapshotRequest(id=snapshot_id), timeout=self._deadline
            )
        return _snapshot_to_dto(response, pb.SnapshotKind)

    def list_by_issue(self, issue_id: int) -> list[SnapshotDTO]:
        pb, grpc_mod = load_service_stubs(SERVICE_NAME)
        with sidecars_channel() as channel:
            stub = grpc_mod.SnapshotdStub(channel)
            response = stub.ListByIssue(
                pb.ListByIssueRequest(issue_id=issue_id), timeout=self._deadline
            )
        return [_snapshot_to_dto(s, pb.SnapshotKind) for s in response.items]

    def pin(self, snapshot_id: str, issue_id: int) -> SnapshotDTO:
        pb, grpc_mod = load_service_stubs(SERVICE_NAME)
        with sidecars_channel() as channel:
            stub = grpc_mod.SnapshotdStub(channel)
            response = stub.Pin(
                pb.PinRequest(snapshot_id=snapshot_id, issue_id=issue_id),
                timeout=self._deadline,
            )
        return _snapshot_to_dto(response, pb.SnapshotKind)

    def unpin(self, snapshot_id: str) -> SnapshotDTO:
        pb, grpc_mod = load_service_stubs(SERVICE_NAME)
        with sidecars_channel() as channel:
            stub = grpc_mod.SnapshotdStub(channel)
            response = stub.Unpin(
                pb.UnpinRequest(snapshot_id=snapshot_id), timeout=self._deadline
            )
        return _snapshot_to_dto(response, pb.SnapshotKind)

    def health(self) -> str:
        """Return the SnapshotKind name (SERVING / NOT_SERVING / UNKNOWN)."""
        pb, grpc_mod = load_service_stubs(SERVICE_NAME)
        with sidecars_channel(connect_timeout=HEALTH_CONNECT_TIMEOUT_SECONDS) as channel:
            stub = grpc_mod.SnapshotdStub(channel)
            response = stub.Health(pb.Empty(), timeout=self._deadline)
        return pb.HealthStatus.Name(response.status)


def _normalize_kind(kind: str) -> str:
    """Map a human label ('before', 'after', 'critical', ...) to the SK_* enum."""
    upper = kind.upper().strip()
    if upper.startswith("SK_"):
        return upper
    return f"SK_{upper}"
