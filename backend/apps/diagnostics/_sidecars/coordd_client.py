"""Slice 1.6 — private coordd client.

Wraps the gRPC contract at services/sidecars/api/coordd.proto. Slice 1.6
implements CreateEphemeral / Lock / Unlock / Discover (unary); the
streaming RPCs Watch + Elect inherit Unimplemented (paper-trail #566).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from apps._sidecars_shared.channel import (
    DEFAULT_CALL_DEADLINE,
    load_service_stubs,
    sidecars_channel,
)

logger = logging.getLogger(__name__)

SERVICE_NAME = "coordd"


@dataclass(frozen=True)
class NodeIDDTO:
    id: str
    path: str
    created_at_unix_nanos: int


@dataclass(frozen=True)
class LockTokenDTO:
    token: str
    lock_name: str
    expires_at_unix_nanos: int


class CoorddClient:
    """Sync gRPC client for the coordination sidecar."""

    def __init__(self, deadline: float = DEFAULT_CALL_DEADLINE) -> None:
        self._deadline = deadline

    def create_ephemeral(
        self,
        *,
        path: str,
        data: bytes = b"",
        ttl_seconds: int = 0,
    ) -> NodeIDDTO:
        pb, grpc_mod = load_service_stubs(SERVICE_NAME)
        with sidecars_channel() as channel:
            stub = grpc_mod.CoorddStub(channel)
            response = stub.CreateEphemeral(
                pb.EphemeralRequest(path=path, data=data, ttl_seconds=ttl_seconds),
                timeout=self._deadline,
            )
        return NodeIDDTO(
            id=response.id,
            path=response.path,
            created_at_unix_nanos=response.created_at_unix_nanos,
        )

    def lock(self, *, lock_name: str, hold_for_seconds: int = 0) -> LockTokenDTO:
        pb, grpc_mod = load_service_stubs(SERVICE_NAME)
        with sidecars_channel() as channel:
            stub = grpc_mod.CoorddStub(channel)
            response = stub.Lock(
                pb.LockRequest(lock_name=lock_name, hold_for_seconds=hold_for_seconds),
                timeout=self._deadline,
            )
        return LockTokenDTO(
            token=response.token,
            lock_name=response.lock_name,
            expires_at_unix_nanos=response.expires_at_unix_nanos,
        )

    def unlock(self, token: str) -> bool:
        pb, grpc_mod = load_service_stubs(SERVICE_NAME)
        with sidecars_channel() as channel:
            stub = grpc_mod.CoorddStub(channel)
            response = stub.Unlock(
                pb.UnlockRequest(token=token), timeout=self._deadline
            )
        return response.ok

    def discover(self, group: str) -> list[str]:
        pb, grpc_mod = load_service_stubs(SERVICE_NAME)
        with sidecars_channel() as channel:
            stub = grpc_mod.CoorddStub(channel)
            response = stub.Discover(
                pb.DiscoverRequest(group=group), timeout=self._deadline
            )
        return list(response.members)

    def health(self) -> str:
        pb, grpc_mod = load_service_stubs(SERVICE_NAME)
        with sidecars_channel() as channel:
            stub = grpc_mod.CoorddStub(channel)
            response = stub.Health(pb.Empty(), timeout=self._deadline)
        return pb.HealthStatus.Name(response.status)
