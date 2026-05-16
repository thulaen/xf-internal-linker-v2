# streamd — Go stream-engine broker sidecar

**Tier:** Services tier (Go sidecars). Peer module to the nine Django modules.
**Slice that promoted streamd from library to binary:** 1.5.
**Decision of record:** [`docs/adr/0006-go-services-tier.md`](../../docs/adr/0006-go-services-tier.md).

## What it does

streamd is the in-process broker for live events flowing through the Django app: a Python caller publishes an event, every subscribed Python or Go caller receives it in order, and the broker remembers a short history per topic so a slow subscriber can replay from where it left off after a reconnect.

streamd has been a Go library since the project started. Slice 1.5 promoted it to a real sidecar binary so callers no longer have to import Go code into Python — the boundary is a gRPC contract spoken over a Unix-domain socket.

## How it runs

```yaml
streamd:
  image: xf-linker-streamd:latest
  build:
    context: ./services/streamd
  volumes:
    - streamd_sock:/var/run/xf
```

The streamd container mounts the `streamd_sock` named volume at `/var/run/xf`. Inside that volume it binds the Unix-domain socket `/var/run/xf/streamd.sock`. The backend container mounts the same volume so the private Python client at `backend/apps/realtime/_streamd_client.py` can dial the socket without going through TCP.

## Public surface

The contract is `services/streamd/api.proto`. Four RPCs:

| RPC | Kind | Notes |
|---|---|---|
| `Publish` | unary | Append one event to a topic. Returns the assigned offset. |
| `Subscribe` | server-streaming | Optional replay from a past offset, then live fan-out. |
| `Manage` | bidi-streaming | Admin commands: ack consumer offset, read consumer offset, topic stats. |
| `Health` | unary | Liveness probe used by Docker's healthcheck. |

The generated Go stubs live at `services/streamd/api/gen/*.pb.go`. The generated Python stubs for the private client live at `backend/apps/realtime/_streamd_pb2/`. Both are committed so the build does not depend on a fresh `protoc` run.

## How to call it from Python

```python
from apps.realtime.api import broadcast

broadcast("diagnostics", "entity.updated", {"id": 42})
```

`apps.realtime.api.broadcast` still uses Django Channels in slice 1.5 — the streamd binary and the private Python client land but no public caller switches over yet. A future slice migrates `broadcast` once the speed benchmark is settled.

## Streamd reference shape

Streamd is the template every future Go service follows:

- Binary entry point at `cmd/<name>/main.go`. **Library-only Go modules under `services/` are forbidden.**
- gRPC over a Unix-domain socket. Faster than TCP loopback and avoids JSON serialisation overhead.
- One contract file per service (`api.proto` preferred, `api.http.md` allowed).
- Internal packages under `internal/`. Generated stubs under `api/gen/`.
- Multi-stage scratch Dockerfile, final image < 25 MB.
- A speed benchmark in `test/bench_*_test.go` that proves the speed claim.

## Local commands

```bash
# Compile both binaries.
make build

# Unit + race tests.
make test

# Speed benchmark (integration build tag, needs the gRPC stubs generated).
make bench

# Regenerate gRPC stubs after editing api.proto.
make proto
```

All targets work inside the `compiled-tools` Docker image so the host never needs Go installed.

## Performance targets

- p99 publish → subscribe round-trip latency over the Unix socket: **< 1 ms**
- Throughput (one subscriber, 256-byte payload): **> 50,000 messages per second**
- Image size: **< 25 MB**

If a benchmark misses the targets after 5 tuning iterations, slice 1.5 ships an honest `[PERFORMANCE EXEMPTION: ...]` marker plus a `performance-native-rewrite` AutoIssue. Honest failure is preferred to silent slow numbers.

## Citations

See [`docs/specs/fr-go-services-tooling.md`](../../docs/specs/fr-go-services-tooling.md) for the full citation list (Donovan-Kernighan 2015, gRPC docs, `man 7 unix`, etc.) and the source-backed argument for every decision in this README.
