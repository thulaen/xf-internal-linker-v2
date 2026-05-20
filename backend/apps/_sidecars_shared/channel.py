"""Slice 1.6 — shared gRPC channel + stub-loader helpers for sidecar clients.

The 6 critical sidecar services (snapshotd, bullboard, attrouted, schemard,
coordd, errord) and the 34 skeleton services all share ONE Unix-domain
socket at /var/run/xf-sidecars/sidecars.sock. Each typed client opens a
fresh channel per call so connection lifetime is bounded by the surrounding
context manager — no long-lived channels leaking between Django requests.

Mirrors the streamd pattern at backend/apps/realtime/_streamd_client.py but
generalises the socket-path constant and exposes a service-agnostic stub
loader so individual clients can declare "load these symbols from this
generated module" without duplicating the grpc.insecure_channel boilerplate.

References:
  - services/sidecars/README.md § How to call it from Python
  - docs/specs/fr-sidecars-host.md
"""

from __future__ import annotations

import importlib
import logging
import os
from contextlib import asynccontextmanager, contextmanager
from typing import Any, AsyncIterator, Iterator

logger = logging.getLogger(__name__)

DEFAULT_SOCKET_PATH = os.environ.get(
    "XF_SIDECARS_SOCKET", "/var/run/xf-sidecars/sidecars.sock"
)
DEFAULT_CONNECT_TIMEOUT = float(os.environ.get("XF_SIDECARS_CONNECT_TIMEOUT", "5.0"))
DEFAULT_CALL_DEADLINE = float(os.environ.get("XF_SIDECARS_CALL_DEADLINE", "2.0"))

# Generated stubs go here. Each sidecar service has its own sub-package
# matching the service name (e.g., apps/_sidecars_pb/snapshotd/{api_pb2,
# api_pb2_grpc}.py). The protoc invocation lives in services/sidecars/Makefile.
_STUBS_PACKAGE = "apps._sidecars_pb"


class StubsMissingError(RuntimeError):
    """Raised when a sidecar client's generated protobuf stubs are absent.

    The error message points the caller at the regeneration command so the
    failure is self-healing for a vibe coder: read the error, run the
    command, retry.
    """


def _stubs_unblock_message(service_name: str) -> str:
    return (
        f"sidecars protobuf stubs for {service_name!r} are missing — generate them "
        f"inside the backend container with: docker compose exec -T backend "
        f"python -m grpc_tools.protoc --proto_path=/repo/services/sidecars/api "
        f"--python_out=/repo/backend/apps/_sidecars_pb/{service_name} "
        f"--grpc_python_out=/repo/backend/apps/_sidecars_pb/{service_name} "
        f"/repo/services/sidecars/api/{service_name}.proto "
        f"/repo/services/sidecars/api/shared.proto"
    )


def load_service_stubs(service_name: str) -> tuple[Any, Any]:
    """Lazy-load the generated Python stubs for a sidecar service.

    Returns a (pb, grpc_module) tuple where `pb` is a merged namespace
    exposing BOTH the service-specific message classes (e.g.,
    snapshotd_pb2.SnapshotKind, snapshotd_pb2.CreateSnapshotRequest) AND
    the shared message classes from shared.proto (Empty, Ack, HealthReply,
    HealthStatus). Client wrappers reference symbols off `pb` without
    needing to know which generated file they originated in.

    Raises StubsMissingError when the stubs have not yet been generated so
    the caller does not see a confusing ModuleNotFoundError from grpc.
    """
    try:
        service_pb = importlib.import_module(
            f"{_STUBS_PACKAGE}.{service_name}.{service_name}_pb2"
        )
        shared_pb = importlib.import_module(
            f"{_STUBS_PACKAGE}.{service_name}.shared_pb2"
        )
        grpc_module = importlib.import_module(
            f"{_STUBS_PACKAGE}.{service_name}.{service_name}_pb2_grpc"
        )
    except ImportError as exc:
        raise StubsMissingError(_stubs_unblock_message(service_name)) from exc

    # Build a merged namespace. service_pb wins on conflict so a service
    # may legitimately re-define a shared symbol.
    pb = _merged_namespace(shared_pb, service_pb)
    return pb, grpc_module


def _merged_namespace(*modules: Any) -> Any:
    """Return a namespace object that exposes the union of attributes from
    the given modules. Later modules override earlier modules on conflict.
    """
    from types import SimpleNamespace

    merged: dict[str, Any] = {}
    for module in modules:
        for name in dir(module):
            if name.startswith("_"):
                continue
            merged[name] = getattr(module, name)
    return SimpleNamespace(**merged)


@contextmanager
def sidecars_channel(
    socket_path: str | None = None,
    connect_timeout: float | None = None,
) -> Iterator[Any]:
    """Open a sync gRPC channel to the sidecars Unix-domain socket.

    Yields the channel inside a `with` block; closed on exit. The channel
    target uses the `unix://` scheme which grpc-python turns into an AF_UNIX
    connection without going through TCP loopback.
    """
    try:
        import grpc  # type: ignore[import-not-found]
    except ImportError as exc:  # pragma: no cover
        raise StubsMissingError(
            "grpcio is not installed in this Python environment — add it via "
            "`pip install grpcio` (already pinned in backend/requirements.txt)."
        ) from exc

    target = "unix://" + (socket_path or DEFAULT_SOCKET_PATH)
    timeout = connect_timeout if connect_timeout is not None else DEFAULT_CONNECT_TIMEOUT
    channel = grpc.insecure_channel(target)
    try:
        try:
            grpc.channel_ready_future(channel).result(timeout=timeout)
        except grpc.FutureTimeoutError as exc:  # pragma: no cover - hard to trigger in CI
            channel.close()
            raise StubsMissingError(
                f"sidecars socket at {target!r} did not become ready in {timeout:.1f}s. "
                f"Check `docker compose ps sidecars` and ensure the sidecars_sock "
                f"named volume is mounted into this container."
            ) from exc
        yield channel
    finally:
        channel.close()


@asynccontextmanager
async def async_sidecars_channel(
    socket_path: str | None = None,
) -> AsyncIterator[Any]:
    """Open an async gRPC channel to the sidecars Unix-domain socket.

    For Django Channels consumers + Celery async paths. Mirrors
    `sidecars_channel` for sync callers.
    """
    try:
        import grpc  # type: ignore[import-not-found]
    except ImportError as exc:  # pragma: no cover
        raise StubsMissingError(
            "grpcio is not installed in this Python environment."
        ) from exc

    target = "unix://" + (socket_path or DEFAULT_SOCKET_PATH)
    channel = grpc.aio.insecure_channel(target)
    try:
        yield channel
    finally:
        await channel.close()
