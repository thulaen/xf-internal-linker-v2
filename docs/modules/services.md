# Module: services (Go sidecars)

**Tier:** Services tier — peer to the nine Django modules.
**Status:** Stub — full detail lands alongside each Go service's slice.
**Maps to today:** `services/streamd/` (stream-engine broker).
**Decision of record:** [`docs/adr/0006-go-services-tier.md`](../adr/0006-go-services-tier.md).

## Plain-English summary

The services tier holds long-running Go programs that run alongside the Django app. Each Go service is a sidecar — it shares the deployment and the network, but not the Python process. Go services handle workloads Go materially beats Python at: concurrent network I/O, long-running daemons, CLI binaries with cold-start sensitivity.

A Go service is a peer module to the nine Django modules but lives under `services/<name>/`. It has its own quality tooling, its own tests, its own public interface.

## Current members

- `services/streamd` — stream-engine broker. The existing Go service captured by [ADR 0006](../adr/0006-go-services-tier.md).

Future members arrive only after the native-rewrite escalation proves Python cannot meet the target (see Rules below).

## Public interface

Per service, the public interface is a contract file at the service root:

- `services/<name>/api.proto` — gRPC over Unix socket (preferred).
- `services/<name>/api.http.md` — documented HTTP+JSON contract (allowed when gRPC adds more cost than value).

The contract file is the public surface. Everything else inside the Go module — handlers, internal packages, generated code — is private. Cross-language consumers read the contract file, generate stubs, and call the service.

## Rules

1. **No Postgres ownership.** Go services never own database tables. All persistent reads and writes go through the relevant Django `apps.<module>.api` via RPC.
2. **No direct cross-language import.** Python may not import Go code. Go may not embed Python code. The only legal channel is the RPC contract.
3. **Boundary check (slice 2).** `.githooks/check-no-cross-language-import.py` enforces rule 2 at commit time. The check lands in slice 2 alongside the Python and Angular boundary checks.
4. **Quality tooling (slice 2).** `scripts/run-go-quality.sh` runs `go test -race -coverprofile`, `go-mutesting`, `staticcheck`, and `golangci-lint`. The script lands in slice 2 alongside the Python and C++ quality chains.
5. **Escalation gate.** A new Go service requires the full native-rewrite escalation proof: profiling, source-backed spec, 20× speedup or `[PERFORMANCE EXEMPTION: ...]`, C++-first check, `[NATIVE REWRITE REVIEW: ...]` marker, and an AutoIssue labelled `performance-native-rewrite`.

## Allowed dependencies

Go services may consume any Django module's public `api.py` over RPC. A Go service that calls a lower Django module must not create a cycle through the upper Django modules.

Go services do not depend on each other directly except through their RPC contracts. If two Go services need to exchange data, the boundary is an RPC contract, not a shared Go package.

## Test command

```powershell
docker compose exec -T compiled-tools bash -lc "cd /repo/services/<name> && go test -race ./..."
```

Per-service coverage and mutation targets live in `docs/CODE-COVERAGE-RULES.md`. The Go test command runs through the Docker-managed compiled-tools image so the host does not need a local Go toolchain.

## Open questions

- The `compiled-tools` Docker service is not yet in `docker-compose.yml`. Slice 2 confirms whether the Go test runner uses the existing backend image (which already carries Go 1.25 for `go-mutesting`) or a new dedicated image.
- The `services/streamd` service today has no `api.proto` or `api.http.md` file. Slice 2 backfills the contract file for the existing service before adding new sidecars.

## Citations

- Donovan & Kernighan 2015 — *The Go Programming Language*, Addison-Wesley. Concurrency model behind sidecar suitability.
- US Patent US10700948B2 — sidecar pattern as a documented architectural choice.
