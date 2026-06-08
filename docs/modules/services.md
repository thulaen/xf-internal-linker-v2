# Module: services (Go sidecars) — RETIRED

> **RETIRED 2026-06-06.** The backend is now **Python + Rust only** (see
> [ADR 0007](../adr/0007-python-rust-two-language.md) and
> [`RUST-FIRST.md`](../../RUST-FIRST.md)). There is no Go services tier. The Go
> sidecars described below (`services/streamd`, `services/sidecars`, and the
> retired `services/clusterd`) and their RPC contracts are removed. Work those
> sidecars did either moves into Python orchestration or into a Rust extension on
> the hot path. [ADR 0006](../adr/0006-go-services-tier.md) is superseded. The
> migration sequence is in
> [`docs/PYTHON-RUST-MIGRATION-PLAN.md`](../PYTHON-RUST-MIGRATION-PLAN.md). The
> rest of this document is kept only as a historical record of the retired design.

**Tier:** Services tier (RETIRED) — was a peer to the nine Django modules.
**Status:** Retired — the Go services tier no longer exists.
**Maps to today:** `services/streamd/` (stream-engine broker, slice 1.5) + `services/sidecars/` (40 Apache-pattern services in one binary, slice 1.6).
**Decision of record:** [`docs/adr/0006-go-services-tier.md`](../adr/0006-go-services-tier.md).

## Plain-English summary

The services tier holds long-running Go programs that run alongside the Django app. Each Go service is a sidecar — it shares the deployment and the network, but not the Python process. Go services handle workloads Go materially beats Python at: concurrent network I/O, long-running daemons, CLI binaries with cold-start sensitivity.

A Go service is a peer module to the nine Django modules but lives under `services/<name>/`. It has its own quality tooling, its own tests, its own public interface.

## Current members

- `services/streamd` — stream-engine broker. The existing Go service captured by [ADR 0006](../adr/0006-go-services-tier.md). One service per binary; high-throughput streaming workload justifies process isolation.
- `services/sidecars` — 40 Apache-pattern internal services co-hosted in one Go binary. Coordination, evidence, routing, and metadata workers that individually do not justify their own process; the shared 512 MB RAM / 1 GB storage / 7-day retention budget forces them to co-host. Source-backed spec at [`docs/specs/fr-sidecars-host.md`](../specs/fr-sidecars-host.md). Reference shape doc at [`services/sidecars/README.md`](../../services/sidecars/README.md). Slice 1.6 status: 6 services implemented (snapshotd, bullboard, attrouted, schemard, coordd, errord) + 34 skeleton (return `codes.Unimplemented` from RPC methods other than Health).

| Inner service | Apache reference | Owning Django module | Slice 1.6 status |
|---|---|---|---|
| snapshotd | Parquet + Iceberg manifest | governance | implemented |
| bullboard | NiFi bulletin board | operations | implemented |
| attrouted | NiFi route-on-attribute | sources | implemented |
| schemard | Avro | governance | implemented |
| coordd | ZooKeeper + Curator | platform | implemented (Watch + Elect streams in follow-up) |
| errord | Camel exception handler | operations | implemented |
| topicd, provd, pressured, extractd, dagd, ruled, retentd, timetravd, gatewayd, arrowd, catalogd, aclsd, pluginhotd, mesh, smd, tieredd, qsched, gremlind, tsd, hintd, viewd, cepd, xcomd, purged, delayd, flumed, politenessd, fnd, drilld, anomalyd, txd, lookupd, dedupd, compactd | various Apache patterns | various | skeleton (Health only; other RPCs return `codes.Unimplemented`; tracked under `sidecars_followup` in the paper trail) |

Future single-purpose binaries (parallel to streamd) arrive only after the native-rewrite escalation proves Python cannot meet the target (see Rules below). Future inner services added to the sidecars binary only need to fit under the shared budget and follow the manifest convention.

## Public interface

Per service, the public interface is a contract file at the service root:

- `services/<name>/api.proto` — gRPC over Unix socket (preferred).
- `services/<name>/api.http.md` — documented HTTP+JSON contract (allowed when gRPC adds more cost than value).

The contract file is the public surface. Everything else inside the Go module — handlers, internal packages, generated code — is private. Cross-language consumers read the contract file, generate stubs, and call the service.

## Rules

1. **No Postgres ownership.** Go services never own database tables. All persistent reads and writes go through the relevant Django `apps.<module>.api` via RPC.
2. **No direct cross-language import.** Python may not import Go code. Go may not embed Python code. The only legal channel is the RPC contract.
3. **Boundary check (slice 1.5).** `.githooks/check-no-cross-language-import.py` enforces rule 2 at commit time. The check lands in slice 1.5 alongside the Python and Angular boundary checks.
4. **Contract + binary presence check (slice 1.5).** `.githooks/check-go-service-contract.py` enforces that every `services/<name>/` folder publishes BOTH a contract file (`api.proto` or `api.http.md`) AND a binary entry point at `cmd/<name>/main.go`. Library-only Go modules under `services/` are forbidden.
5. **Quality tooling (slice 1.5).** `scripts/run-go-quality.sh` is a stage-by-stage orchestrator that mirrors `scripts/run-cpp-quality.sh`. It calls nine sub-scripts: `run-go-format.sh`, `run-go-vet.sh`, `run-go-staticcheck.sh`, `run-go-lint.sh`, `run-go-gosec.sh`, `run-buf-lint.sh`, `run-go-tests.sh` (race + coverage), `run-go-mutation.sh` (kill-rate ≥ 70%), and `run-go-bench.sh`. The chain lands in slice 1.5 alongside the Python and C++ quality chains.
6. **Escalation gate.** A new Go service requires the full native-rewrite escalation proof: profiling, source-backed spec, 20× speedup or `[PERFORMANCE EXEMPTION: ...]`, C++-first check, `[NATIVE REWRITE REVIEW: ...]` marker, and an AutoIssue labelled `performance-native-rewrite`.

## Allowed dependencies

Go services may consume any Django module's public `api.py` over RPC. A Go service that calls a lower Django module must not create a cycle through the upper Django modules.

Go services do not depend on each other directly except through their RPC contracts. If two Go services need to exchange data, the boundary is an RPC contract, not a shared Go package.

## Test command

```powershell
bash scripts/run-go-quality.sh
```

The orchestrator detects the Go modules in scope from the staged commit, then runs all nine stages inside the `compiled-tools` Docker image so the host never needs a local Go toolchain. Per-service coverage and mutation targets live in `docs/CODE-COVERAGE-RULES.md`.

## Open questions

- _(Closed in slice 1.5)_ The `compiled-tools` Docker service exists in `docker-compose.yml` and carries `go`, `golangci-lint`, `gosec`, `gofmt`, `go-mutesting`, plus the slice-1.5 additions (`staticcheck`, `buf`, `protoc`, `protoc-gen-go`, `protoc-gen-go-grpc`). The Go quality chain runs there.
- _(Closed in slice 1.5)_ `services/streamd/api.proto` publishes the gRPC contract (Publish / Subscribe / Manage / Health). Future Go services backfill their contract alongside their first slice.

## Citations

- Donovan & Kernighan 2015 — *The Go Programming Language*, Addison-Wesley. Concurrency model behind sidecar suitability.
- US Patent US10700948B2 — sidecar pattern as a documented architectural choice.
