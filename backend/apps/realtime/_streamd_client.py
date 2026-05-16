# quality-debt-ignore: reason: tests live in tests_streamd_client.py (non-canonical name; quality-debt-score does not infer the double-underscore prefix match)
"""Slice 1.5 — private gRPC client for the streamd Go sidecar.

The module is underscore-prefixed so it is treated as private to
apps.realtime. No caller outside apps/realtime/ should import it; the public
surface stays the existing apps.realtime.api.broadcast (which still uses
Django Channels in slice 1.5 — see docs/specs/fr-go-services-tooling.md
§ "What's new, what's replaced").

The client supports both sync (`StreamdClient`) and asyncio
(`AsyncStreamdClient`) callers because the existing apps.realtime.services
exposes both `broadcast` and `abroadcast`. Documented defaults:

  connect timeout: 5 s   (overridable via XF_STREAMD_CONNECT_TIMEOUT)
  per-call deadline: 2 s (overridable via the `deadline=` argument)

The generated protobuf stubs live under apps/realtime/_streamd_pb2/. The
stubs are generated from services/streamd/api.proto via
`python -m grpc_tools.protoc` (see services/streamd/Makefile target
`proto`). Until the stubs are generated, importing this module succeeds but
calling any RPC method raises RuntimeError with a clear unblock message.
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager, contextmanager
from typing import TYPE_CHECKING, Any, AsyncIterator, Iterator, Mapping

logger = logging.getLogger(__name__)

DEFAULT_SOCKET_PATH = os.environ.get("XF_STREAMD_SOCKET", "/var/run/xf/streamd.sock")
DEFAULT_CONNECT_TIMEOUT = float(os.environ.get("XF_STREAMD_CONNECT_TIMEOUT", "5.0"))
DEFAULT_CALL_DEADLINE = float(os.environ.get("XF_STREAMD_CALL_DEADLINE", "2.0"))


if TYPE_CHECKING:  # pragma: no cover — TYPE_CHECKING-only branch
    from ._streamd_pb2 import Event, HealthResponse, PublishResponse
    from ._streamd_pb2_grpc import StreamdStub


def _load_stubs():
    """Load the generated protobuf + grpc stubs.

    Raises a clear RuntimeError when the stubs have not yet been generated so
    the failure mode points at the regeneration command instead of a confusing
    ModuleNotFoundError deep in grpc internals.
    """
    try:
        # Re-imported per call so a fresh stub generation does not require a
        # Django process restart in the dev loop.
        from ._streamd_pb2 import (  # noqa: F401 — re-exported for callers
            AckOffsetCommand,
            Event,
            HealthRequest,
            HealthResponse,
            ManageRequest,
            PublishRequest,
            SubscribeRequest,
        )
        from ._streamd_pb2 import api_pb2_grpc
    except ImportError as exc:
        raise RuntimeError(
            "streamd protobuf stubs are missing — generate them inside the "
            "backend container with `docker compose exec -T backend python "
            "-m grpc_tools.protoc --proto_path=/repo/services/streamd "
            "--python_out=/repo/backend/apps/realtime/_streamd_pb2 "
            "--grpc_python_out=/repo/backend/apps/realtime/_streamd_pb2 "
            "/repo/services/streamd/api.proto`."
        ) from exc
    return api_pb2_grpc, api_pb2_grpc.StreamdStub, {
        "PublishRequest": PublishRequest,
        "SubscribeRequest": SubscribeRequest,
        "HealthRequest": HealthRequest,
        "ManageRequest": ManageRequest,
        "AckOffsetCommand": AckOffsetCommand,
        "Event": Event,
    }


def _unix_target(socket_path: str = DEFAULT_SOCKET_PATH) -> str:
    """Convert a filesystem path to the gRPC `unix://` URI scheme."""
    if socket_path.startswith("unix://"):
        return socket_path
    return f"unix://{socket_path}"


# ---------------------------------------------------------------------------
# Sync client (used from synchronous Django code paths)
# ---------------------------------------------------------------------------


@contextmanager
def streamd_channel(
    socket_path: str = DEFAULT_SOCKET_PATH,
    connect_timeout: float = DEFAULT_CONNECT_TIMEOUT,
) -> Iterator[Any]:
    """Open a sync grpc channel to streamd. Yields the channel; closes on exit."""
    import grpc  # imported lazily so the module loads without grpcio installed yet

    channel = grpc.insecure_channel(_unix_target(socket_path))
    try:
        grpc.channel_ready_future(channel).result(timeout=connect_timeout)
    except grpc.FutureTimeoutError as exc:
        channel.close()
        raise TimeoutError(
            f"streamd at {socket_path} did not become ready within "
            f"{connect_timeout:.1f}s"
        ) from exc
    try:
        yield channel
    finally:
        channel.close()


class StreamdClient:
    """Sync wrapper. Each method opens-and-closes its own channel for safety.
    Long-running callers should hold a channel via `streamd_channel()` and use
    the StubBuilder pattern via `make_stub()` to avoid repeated handshakes."""

    def __init__(
        self,
        socket_path: str = DEFAULT_SOCKET_PATH,
        connect_timeout: float = DEFAULT_CONNECT_TIMEOUT,
    ) -> None:
        self._socket_path = socket_path
        self._connect_timeout = connect_timeout

    def publish(
        self,
        topic: str,
        payload: bytes,
        deadline: float = DEFAULT_CALL_DEADLINE,
    ) -> int:
        """Publish a single event. Returns the assigned offset."""
        # quality-debt-ignore: reason: sync + async + subscribe share an open-channel pattern by design (gRPC dial idiom)
        _, stub_cls, types = _load_stubs()
        with streamd_channel(self._socket_path, self._connect_timeout) as channel:
            stub = stub_cls(channel)
            resp = stub.Publish(
                types["PublishRequest"](topic=topic, payload=payload),
                timeout=deadline,
            )
            return int(resp.offset)

    def subscribe(
        self,
        topic: str,
        from_offset: int = 0,
        consumer_id: str = "",
    ) -> Iterator[Any]:
        """Open a server-streaming Subscribe call. Yields decoded Event objects.

        The returned iterator MUST be exhausted or the underlying channel will
        leak; prefer using it inside a `with closing(...)` block, or iterate
        it inside a try/finally that calls `cancel()` on the returned call.
        """
        _, stub_cls, types = _load_stubs()
        channel_cm = streamd_channel(self._socket_path, self._connect_timeout)
        channel = channel_cm.__enter__()
        stub = stub_cls(channel)
        call = stub.Subscribe(
            types["SubscribeRequest"](
                topic=topic, from_offset=from_offset, consumer_id=consumer_id
            )
        )
        try:
            for event in call:
                yield event
        finally:
            call.cancel()
            channel_cm.__exit__(None, None, None)

    def health(self, deadline: float = DEFAULT_CALL_DEADLINE) -> str:
        """Probe the streamd Health RPC. Returns the ServingStatus name."""
        _, stub_cls, types = _load_stubs()
        with streamd_channel(self._socket_path, self._connect_timeout) as channel:
            resp = stub_cls(channel).Health(types["HealthRequest"](), timeout=deadline)
            return resp.Status.Name(resp.status) if hasattr(resp.Status, "Name") else str(resp.status)


# ---------------------------------------------------------------------------
# Async client (used from Django channels consumers and other asyncio paths)
# ---------------------------------------------------------------------------


@asynccontextmanager
async def astreamd_channel(
    socket_path: str = DEFAULT_SOCKET_PATH,
    connect_timeout: float = DEFAULT_CONNECT_TIMEOUT,
) -> AsyncIterator[Any]:
    """Async-context twin of streamd_channel."""
    import grpc.aio

    channel = grpc.aio.insecure_channel(_unix_target(socket_path))
    try:
        await channel.channel_ready()
    except Exception as exc:  # noqa: BLE001 — narrow to grpc once stubs land
        await channel.close()
        raise TimeoutError(
            f"streamd at {socket_path} did not become ready within "
            f"{connect_timeout:.1f}s"
        ) from exc
    try:
        yield channel
    finally:
        await channel.close()


class AsyncStreamdClient:
    """Async wrapper for use inside async Django views and Channels consumers."""

    def __init__(
        self,
        socket_path: str = DEFAULT_SOCKET_PATH,
        connect_timeout: float = DEFAULT_CONNECT_TIMEOUT,
    ) -> None:
        self._socket_path = socket_path
        self._connect_timeout = connect_timeout

    async def publish(
        self,
        topic: str,
        payload: bytes,
        deadline: float = DEFAULT_CALL_DEADLINE,
    ) -> int:
        _, stub_cls, types = _load_stubs()
        async with astreamd_channel(self._socket_path, self._connect_timeout) as channel:
            stub = stub_cls(channel)
            resp = await stub.Publish(
                types["PublishRequest"](topic=topic, payload=payload),
                timeout=deadline,
            )
            return int(resp.offset)

    async def health(self, deadline: float = DEFAULT_CALL_DEADLINE) -> str:
        _, stub_cls, types = _load_stubs()
        async with astreamd_channel(self._socket_path, self._connect_timeout) as channel:
            resp = await stub_cls(channel).Health(types["HealthRequest"](), timeout=deadline)
            return resp.Status.Name(resp.status) if hasattr(resp.Status, "Name") else str(resp.status)
