# quality-debt-ignore: reason: tests live in tests_clusterd_client.py (double-underscore private module)
"""Private gRPC client for the clusterd Go sidecar (root-cause clustering).

Underscore-prefixed = private to apps.auto_issues. Callers go through the
`cluster_autoissues` management command or apps.auto_issues.services, never this
module directly. Mirrors apps.realtime._streamd_client.

The generated protobuf stubs live under apps/auto_issues/_clusterd_pb2/,
produced from services/clusterd/api.proto via `grpc_tools.protoc`. Importing
this module always succeeds; calling an RPC before the stubs exist raises a
RuntimeError that names the regeneration command.

Defaults (overridable via env):
  socket          XF_CLUSTERD_SOCKET        /var/run/xf-clusterd/clusterd.sock
  connect timeout XF_CLUSTERD_CONNECT_TIMEOUT  5 s
  per-call deadline XF_CLUSTERD_CALL_DEADLINE  30 s  (clustering can be heavy)
"""
from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Iterable, Iterator, List, Sequence, Tuple

DEFAULT_SOCKET_PATH = os.environ.get(
    "XF_CLUSTERD_SOCKET", "/var/run/xf-clusterd/clusterd.sock"
)
DEFAULT_CONNECT_TIMEOUT = float(os.environ.get("XF_CLUSTERD_CONNECT_TIMEOUT", "5.0"))
DEFAULT_CALL_DEADLINE = float(os.environ.get("XF_CLUSTERD_CALL_DEADLINE", "120.0"))

# (issue_id, feature_hashes)
Item = Tuple[int, Sequence[int]]


class ClusterResult:
    """One root-cause cluster: a representative issue id and all member ids."""

    __slots__ = ("representative_id", "member_ids")

    def __init__(self, representative_id: int, member_ids: Sequence[int]):
        self.representative_id = int(representative_id)
        self.member_ids = [int(m) for m in member_ids]

    def __eq__(self, other: object) -> bool:
        return (
            isinstance(other, ClusterResult)
            and other.representative_id == self.representative_id
            and other.member_ids == self.member_ids
        )

    def __repr__(self) -> str:
        return f"ClusterResult(rep={self.representative_id}, members={self.member_ids})"


def _load_stubs():
    try:
        from ._clusterd_pb2 import api_pb2, api_pb2_grpc
    except ImportError as exc:  # pragma: no cover — exercised only pre-generation
        raise RuntimeError(
            "clusterd protobuf stubs are missing — regenerate with "
            "`python -m grpc_tools.protoc -I services/clusterd "
            "--python_out=backend/apps/auto_issues/_clusterd_pb2 "
            "--grpc_python_out=backend/apps/auto_issues/_clusterd_pb2 "
            "services/clusterd/api.proto`."
        ) from exc
    return api_pb2, api_pb2_grpc


def _unix_target(socket_path: str = DEFAULT_SOCKET_PATH) -> str:
    """Convert a filesystem path to the gRPC `unix://` URI scheme."""
    if socket_path.startswith("unix://"):
        return socket_path
    return f"unix://{socket_path}"


def _build_request(items: Iterable[Item], threshold: float):
    """Build a ClusterRequest from (id, features) pairs."""
    api_pb2, _ = _load_stubs()
    return api_pb2.ClusterRequest(
        items=[
            api_pb2.Item(id=int(issue_id), features=[int(f) for f in features])
            for issue_id, features in items
        ],
        threshold=float(threshold),
    )


def _map_clusters(response) -> List[ClusterResult]:
    """Map a ClusterResponse into ClusterResult objects."""
    return [
        ClusterResult(c.representative_id, c.member_ids) for c in response.clusters
    ]


@contextmanager
def _channel(
    socket_path: str = DEFAULT_SOCKET_PATH,
    connect_timeout: float = DEFAULT_CONNECT_TIMEOUT,
) -> Iterator[object]:
    import grpc

    # 64 MiB so large clustering batches (~12k items) fit; default is 4 MiB.
    max_msg = 64 * 1024 * 1024
    channel = grpc.insecure_channel(
        _unix_target(socket_path),
        options=[
            ("grpc.max_send_message_length", max_msg),
            ("grpc.max_receive_message_length", max_msg),
        ],
    )
    try:
        grpc.channel_ready_future(channel).result(timeout=connect_timeout)
        yield channel
    finally:
        channel.close()


class ClusterdClient:
    """Synchronous clusterd client used by the cluster_autoissues command."""

    def __init__(
        self,
        socket_path: str = DEFAULT_SOCKET_PATH,
        call_deadline: float = DEFAULT_CALL_DEADLINE,
    ):
        self._socket_path = socket_path
        self._call_deadline = call_deadline

    def cluster(
        self, items: Iterable[Item], threshold: float
    ) -> List[ClusterResult]:
        _, api_pb2_grpc = _load_stubs()
        request = _build_request(items, threshold)
        with _channel(self._socket_path) as channel:
            stub = api_pb2_grpc.ClusterdStub(channel)
            response = stub.Cluster(request, timeout=self._call_deadline)
        return _map_clusters(response)

    def health(self) -> bool:
        api_pb2, api_pb2_grpc = _load_stubs()
        with _channel(self._socket_path) as channel:
            stub = api_pb2_grpc.ClusterdStub(channel)
            response = stub.Health(api_pb2.HealthRequest(), timeout=self._call_deadline)
        return response.status == api_pb2.HealthResponse.SERVING
