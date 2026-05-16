"""Generated protobuf + grpc stubs for the streamd contract.

The Python stubs (`api_pb2.py`, `api_pb2_grpc.py`) are generated from
`services/streamd/api.proto` via `python -m grpc_tools.protoc` and committed
alongside this __init__.py. The package is underscore-prefixed because
nothing outside apps/realtime/ should import these stubs — the public
surface is `apps.realtime.api.broadcast` (still on Django Channels in slice
1.5) and the private `apps.realtime._streamd_client.StreamdClient`.

This __init__.py re-exports the message classes (so callers can use
`from apps.realtime._streamd_pb2 import PublishRequest`) and the grpc stub
module (so `apps.realtime._streamd_pb2_grpc` resolves correctly).

Regenerate via:
    docker compose exec -T compiled-tools \
      bash /repo/services/streamd/Makefile-style proto target, OR
    docker compose exec -T backend python -m grpc_tools.protoc \
      --proto_path=/repo/services/streamd \
      --python_out=/repo/backend/apps/realtime/_streamd_pb2 \
      --grpc_python_out=/repo/backend/apps/realtime/_streamd_pb2 \
      /repo/services/streamd/api.proto
"""

# Re-export message classes from the generated api_pb2 module so callers can
# write `from apps.realtime._streamd_pb2 import PublishRequest`. The
# generated module is itself private to this package — direct imports of
# api_pb2 should not happen outside apps/realtime/.
try:
    from .api_pb2 import (  # noqa: F401
        AckOffsetCommand,
        AckOffsetResult,
        Event,
        GetConsumerOffsetCommand,
        GetConsumerOffsetResult,
        HealthRequest,
        HealthResponse,
        ManageError,
        ManageRequest,
        ManageResponse,
        PublishRequest,
        PublishResponse,
        SubscribeRequest,
        TopicStatsCommand,
        TopicStatsResult,
    )
    from . import api_pb2_grpc as _api_pb2_grpc  # noqa: F401
except ImportError:  # pragma: no cover — stubs not generated yet
    # Slice 1.5 places this placeholder so the package imports cleanly even
    # before the regeneration command has run. _streamd_client._load_stubs
    # raises a clear unblock RuntimeError when callers attempt an RPC.
    pass
