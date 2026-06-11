"""Slice 1.6 — Sidecars black-box characterization test.

Verifies the sidecars Go binary (co-hosting 40 services) behaves
according to contract over its Unix-domain socket.
"""

from __future__ import annotations

import grpc
import pytest

from apps._sidecars_shared.channel import sidecars_channel, load_service_stubs


@pytest.fixture(scope="module")
def channel():
    with sidecars_channel(connect_timeout=2.0) as ch:
        yield ch


@pytest.mark.integration
class TestSidecarsCharacterization:
    def test_critical_service_health(self, channel) -> None:
        """Verify real services (e.g. snapshotd) answer Health checks."""
        pb, grpc_module = load_service_stubs("snapshotd")
        stub = grpc_module.SnapshotdStub(channel)
        
        reply = stub.Health(pb.Empty(), timeout=1.0)
        assert reply.status == pb.HEALTH_SERVING

    def test_skeleton_service_health(self, channel) -> None:
        """Verify skeleton services (e.g. topicd) answer Health checks."""
        pb, grpc_module = load_service_stubs("topicd")
        stub = grpc_module.TopicdStub(channel)
        
        reply = stub.Health(pb.Empty(), timeout=1.0)
        assert reply.status == pb.HEALTH_SERVING

    def test_skeleton_service_rpc_unimplemented(self, channel) -> None:
        """Verify skeleton services return UNIMPLEMENTED for real RPCs."""
        pb, grpc_module = load_service_stubs("topicd")
        stub = grpc_module.TopicdStub(channel)
        
        with pytest.raises(grpc.RpcError) as exc_info:
            # Topicd's ListTopics RPC should be UNIMPLEMENTED
            stub.ListTopics(pb.Empty(), timeout=1.0)
        
        assert exc_info.value.code() == grpc.StatusCode.UNIMPLEMENTED
