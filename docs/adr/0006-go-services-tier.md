# ADR 0006 — Go services tier as a peer module type

**Date:** 2026-05-16
**Status:** Accepted
**Deciders:** Project owner.
**Related:** ADR 0001, ADR 0002, ADR 0003.

## Context

The repo already has one Go service (`services/streamd`, the stream-engine broker) and Go 1.25 is installed in the backend Docker image for `go-mutesting`. The modular-monolith plan declared nine Django modules; this leaves the existing Go service unclassified and provides no rule for future Go work.

The user has confirmed (2026-05-16) the intent to use Go anywhere it materially beats Python — primarily concurrent network I/O, long-running daemons, and CLI binaries with cold-start sensitivity.

Three positions were considered:

1. **Pretend Go does not exist in the architecture.** Leave `services/streamd` unclassified. Treats every future Go service as a one-off exception and invites silent cross-language imports.
2. **Add Go as a tenth Django module.** Misleading — Go services do not share a process with Django, do not share the ORM, and cannot be imported as Python modules.
3. **Add a dedicated "services tier" for Go sidecars** that sits next to the nine Django modules. Names the existing reality and gives future Go work a clear shape.

Position 1 is the current default and is what slice 1 found unsatisfactory. Position 2 misrepresents the runtime. Position 3 fits the existing service and explains the future cases.

## Decision

Add a tenth module type — the **services tier** — for Go services that run as sidecars to the Django monolith. Concretely:

1. Each Go service is a peer module with its own folder under `services/<name>/`, its own `api.proto` (gRPC) or `api.http.md` (HTTP+JSON) contract file, and its own `docs/modules/<name>.md` documentation.
2. Go services may not import Python code. Python code may not embed Go libraries directly.
3. The cross-language boundary is a versioned RPC interface registered in the service's contract file. gRPC over Unix socket is preferred; HTTP+JSON is allowed.
4. A new Go service is only allowed after the existing native-rewrite escalation gates pass: profiling proof, source-backed spec, 20× speedup (or `[PERFORMANCE EXEMPTION: ...]`), C++-first check (C++ is preferred for tight numeric kernels), `[NATIVE REWRITE REVIEW: ...]` marker, and an AutoIssue labelled `performance-native-rewrite`.
5. Go services never own Postgres tables. They call Django through `apps.<module>.api` over RPC for any persistent read or write.
6. The nine-module Django dependency direction stays unchanged. Go services are sidecars, not a layer.
7. Each Go service is listed in [`docs/MODULAR-MONOLITH.md`](../MODULAR-MONOLITH.md) under the "Services tier (Go sidecars)" section.

## Consequences

**Positive:**

- The existing `services/streamd` becomes officially part of the architecture rather than an unclassified exception.
- Future Go rewrites have a clear gate (the native-rewrite escalation) and a clear shape (sidecar + RPC contract).
- The Python and Go codebases stay separable; a refactor in either does not cascade into the other.

**Negative:**

- One extra Docker compose entry per Go service. Acceptable; user-approved.
- Two languages to maintain quality tooling for. Mitigated by `scripts/run-go-quality.sh` (added in slice 1.5) mirroring the Python and C++ chains.

**Trade-offs accepted:**

- The cross-language boundary is RPC, not in-process. This adds latency relative to a direct function call but removes ABI risk, build coupling, and shared memory hazards.

## References

- US Patent US10700948B2 — Service-Oriented Modular System Architecture (the sidecar pattern as a documented architectural choice).
- Su 2024 — modular-monolith industry survey, § "Frameworks" coverage of sidecar polyglot services.
- Donovan & Kernighan 2015 — *The Go Programming Language*, Addison-Wesley. Establishes the goroutine + `net/http` concurrency model that justifies Go's fit for network-I/O sidecars.
- ADR 0001 — modular-monolith style.
- ADR 0002 — `api.py` convention (Go services declare an analogous `api.proto` / `api.http.md`).
- ADR 0003 — cross-module FK rule. Go services do not own tables; this rule does not apply to them.
- [`services/streamd/`](../../services/streamd/) — the existing Go service captured by this ADR.
