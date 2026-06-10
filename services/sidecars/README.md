# sidecars — 40 Apache-pattern internal services in one Go binary

**Tier:** Services tier (Go sidecars). Peer module to the nine Django modules.
**Slice that introduced sidecars:** 1.6.
**Decision of record:** [`docs/adr/0006-go-services-tier.md`](../../docs/adr/0006-go-services-tier.md).
**Source-backed spec:** [`docs/specs/fr-sidecars-host.md`](../../docs/specs/fr-sidecars-host.md).

## What it does

sidecars hosts **40 small Apache-pattern internal services** under one Go runtime. Streamd (the slice 1.5 reference) is a single-purpose, high-throughput broker that earned its own process. The 40 services here are coordination, evidence, routing, and metadata workers — none of them individually need their own process, and the shared budget forces them to co-host.

Examples:
- **snapshotd** — Parquet-format diagnostic evidence tied to AutoIssues.
- **bullboard** — rolling "what is happening now" feed + threshold-rule promotion.
- **attrouted** — attribute-based work routing (which Celery queue, which handler).
- **schemard** — small Avro-style schema registry that snapshotd consults.
- **coordd** — Zookeeper-style ephemeral nodes, locks, leader election.
- **errord** — Camel-style exception-policy registry for AutoIssue creation.

The full 40 are listed in `services.manifest.yaml`.

## How it runs

```yaml
sidecars:
  image: xf-linker-sidecars:latest
  build:
    context: ./services/sidecars
  restart: always
  volumes:
    - sidecars_sock:/var/run/xf
    - sidecars_data:/var/lib/xf/sidecars
  mem_limit: 640m       # 512 MB cap + 128 MB headroom for runtime
  healthcheck:
    test: ["CMD", "/sidecars-healthcheck"]
    interval: 10s
```

The container binds one Unix-domain socket at `/var/run/xf/sidecars.sock` and holds all storage under `/var/lib/xf/sidecars/`. Different gRPC service names route to different internal handlers — the socket carries 40 services' RPCs over the same listener.

## Hard constraints (TOTAL across the 40)

These are global, not per-service. The `internal/shared/budget` package enforces them at runtime; `.githooks/check-go-service-resource-budget.py` checks `budget.yaml` declares them at every commit.

1. **512 MB RAM total** (`debug.SetMemoryLimit(512 << 20)` + `GOMEMLIMIT=512MiB`).
2. **1 GB storage total** under `/var/lib/xf/sidecars/` (one named Docker volume).
3. **7-day retention** on every file (pruner deletes files older than 168 h).
4. **No Postgres ownership** — persistent state lives in Postgres through the owning Django module's `apps.<x>.api`.
5. **gRPC over ONE Unix-domain socket** at `/var/run/xf/sidecars.sock`.
6. **Single binary, scratch image, ≤ 35 MB.**
7. **Per-service shares in `services.manifest.yaml` are hints, not hard limits.** The idle detector + pruner rebalance when one service is bursty and others are quiet.

## Public surface

The contract is one file per service in `services/sidecars/api/<name>.proto`, plus `api/shared.proto` for common types. Each service declares its own gRPC service so a Python caller picks the right stub. Generated Go stubs live at `services/sidecars/api/gen/`. Generated Python stubs live at `backend/apps/_sidecars_pb/<name>/`. Both are committed so the build does not depend on a fresh `protoc` run.

## How to call it from Python

```python
# Each owning Django module exposes its sidecar surface through its api.py:
from apps.auto_issues.api import create_snapshot          # → snapshotd
from apps.ops_feed.api import post_bulletin               # → bullboard
from apps.sources.api import route_work_unit              # → attrouted
```

The private clients live at `backend/apps/<owning>/_sidecars/<name>_client.py`. No caller outside the owning module imports a gRPC stub directly — `apps.<owning>.api` is the only public surface.

## Local commands

```bash
# Build + run inside docker compose:
docker compose up -d sidecars

# Stop:
docker compose stop sidecars

# Live logs:
docker compose logs -f sidecars

# Check the resident memory + storage usage:
docker stats xf_linker_sidecars --no-stream
docker compose exec -T sidecars du -sh /var/lib/xf/sidecars

# Test suite (inside compiled-tools):
docker compose run --rm compiled-tools make -C /repo/services/sidecars test

# Benchmarks (40 sub-benchmarks):
docker compose run --rm compiled-tools make -C /repo/services/sidecars bench

# Integration (requires the binary running):
docker compose exec -T compiled-tools bash -lc \
  "cd /repo/services/sidecars && go test -tags=integration ./test/..."
```

## Sidecars reference shape

sidecars is the template for any future **multi-service** Go binary. The single-purpose template is `services/streamd/`. The key differences:

- One `cmd/<name>/main.go` per binary — sidecars has ONE `main.go` for all 40 services.
- One contract file per **service** (not per binary). sidecars has 40 contracts plus `shared.proto`.
- Shared infrastructure (budget, pruner, pool, idle, store, socket, otel, manifest) lives under `internal/shared/`.
- Per-service logic lives under `internal/<name>/` and registers against the shared gRPC server in `cmd/sidecars/main.go`.
- Multi-stage scratch Dockerfile, final image ≤ 35 MB.
- Speed benchmarks in `test/bench_all_test.go` cover all 40 services.
