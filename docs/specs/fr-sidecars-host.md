# FR — Sidecars host: 40 internal services in one Go binary

[SPEC FRESHNESS: reviewed_at=2026-05-17 next_review=2026-06-17]
[SPEC CITED: feature=sidecars-host kind=architecture id=services-tier-multi-service-binary verified_at=2026-05-17]
[SPEC CITED: feature=sidecars-host kind=technical_doc id=apache-tomcat-servlet-container-pattern verified_at=2026-05-17]
[SPEC CITED: feature=sidecars-host kind=technical_literature id=donovan-kernighan-2015-go-programming-language-ch-8-concurrency verified_at=2026-05-17]
[SPEC CITED: feature=sidecars-host kind=academic_paper id=parnas-1972-doi-10.1145-361598.361623 verified_at=2026-05-17]
[SPEC CITED: feature=sidecars-host kind=technical_doc id=parquet-format-spec-parquet.apache.org-docs-file-format verified_at=2026-05-17]
[SPEC CITED: feature=sidecars-host kind=technical_doc id=iceberg-spec-iceberg.apache.org-spec verified_at=2026-05-17]
[SPEC CITED: feature=sidecars-host kind=academic_paper id=iso-iec-ieee-42010-2022-architecture-description verified_at=2026-05-17]
[SPEC CITED: feature=sidecars-host kind=technical_doc id=grpc-naming-conventions-grpc.io-docs-guides-naming verified_at=2026-05-17]

## Summary

`services/sidecars/` is the second member of the services tier (per [ADR 0006](../adr/0006-go-services-tier.md)) and the first **multi-service** Go binary in the project. Where [`services/streamd/`](../../services/streamd/) is one service in one process, `sidecars` hosts **40 Apache-pattern internal services** under one runtime: snapshotd (Parquet-style evidence), bullboard (rolling event feed), attrouted (attribute-based routing), schemard (schema registry), coordd (Zookeeper-style coordination), errord (exception policies), and 34 others (full list in `services/sidecars/services.manifest.yaml`).

The 40 services individually do not justify 40 processes. The shared 512 MB RAM / 1 GB storage / 7-day retention budget forces them to co-host. Different gRPC service names route to different internal handlers off one Unix-domain socket.

## Why a multi-service binary now, not 40 separate binaries

| Concern | One binary | 40 binaries |
|---|---|---|
| Operator complexity | One container, one socket, one healthcheck | 40 containers, 40 sockets, 40 healthchecks |
| Memory overhead | One Go runtime (~30 MB baseline) | ~30 MB × 40 = ~1.2 GB just for runtimes |
| Build/deploy | One Dockerfile, one image | 40 Dockerfiles, 40 image builds |
| Test surface | One `go test ./...` | 40 separate test runs |
| Cross-service helpers (budget, pruner, pool, idle) | Shared package | Copy-pasted or library-published 40× |

The pattern is the Apache Tomcat servlet-container pattern: one binary, many independent applications, shared runtime. Streamd is kept separate because its workload (high-throughput streaming) genuinely benefits from process isolation.

## Hard constraints (TOTAL across the 40)

All values declared in `services/sidecars/budget.yaml` and read by both `cmd/sidecars/main.go` at boot and `.githooks/check-go-service-resource-budget.py` at every commit.

1. **512 MB RAM total** — enforced via `runtime/debug.SetMemoryLimit(512 << 20)` in main.go plus `GOMEMLIMIT=512MiB` env var. `internal/shared/budget.OnPressure` fires when RSS exceeds 80% of cap; `internal/shared/idle.ForceReleaseLowest` is the callback.
2. **1 GB storage total** under `/var/lib/xf/sidecars/` — enforced by `internal/shared/pruner` every 60 seconds.
3. **7-day retention** on every file — `pruner.sweepAged` deletes anything older than 168 h. Pinned snapshotd files are exempt from age but still count toward the cap.
4. **No Postgres ownership** — every persistent record lives in Postgres through the owning Django module's `apps.<x>.api`. The sidecars binary's local state under `/var/lib/xf/sidecars/` is ephemeral evidence + caches, not the system of record.
5. **gRPC over ONE Unix-domain socket** at `/var/run/xf-sidecars/sidecars.sock`. Path differs from streamd's socket (`/var/run/xf/streamd.sock`) so the two volumes do not collide in the backend container's mount tree.
6. **Single binary, scratch image, ≤ 35 MB.** Multi-stage Dockerfile builds with `-trimpath -ldflags="-s -w"`.
7. **Per-service shares in `services.manifest.yaml` are hints**, not hard caps. The idle detector + pruner rebalance under pressure: a bursty service may exceed its nominal share if neighbours are quiet.

## Architecture

```
services/sidecars/
├── api/                          # 40 .proto files + shared.proto
│   ├── shared.proto              # Empty, Ack, HealthReply, HealthStatus
│   ├── snapshotd.proto           # 9 RPCs (CreateSnapshot, Compare, Pin, …)
│   ├── bullboard.proto           # rolling feed + threshold rules
│   ├── attrouted.proto           # attribute-based routing
│   ├── schemard.proto            # Avro-style schema registry
│   ├── coordd.proto              # Zookeeper-style coordination
│   ├── errord.proto              # exception policies
│   ├── topicd.proto              # 34 skeleton .proto files generated from
│   ├── provd.proto               # services.manifest.yaml. Each declares the
│   ├── …                         # service interface + empty messages.
│   └── gen/                      # *.pb.go + *_grpc.pb.go (committed)
├── cmd/
│   ├── sidecars/main.go          # ~250 lines; registers all 40 services
│   ├── sidecars-healthcheck/     # Docker healthcheck binary
│   ├── gen-proto-skeletons/      # one-shot dev tool
│   └── gen-server-skeletons/     # one-shot dev tool
├── internal/
│   ├── shared/                   # 8 packages: budget, pruner, pool, idle,
│   │   ├── budget/               # store, socket, otel, manifest. All built
│   │   ├── pruner/               # with TDD; 100% of headline behaviour
│   │   ├── pool/                 # covered by tests.
│   │   ├── idle/
│   │   ├── store/
│   │   ├── socket/
│   │   ├── otel/
│   │   └── manifest/
│   ├── snapshotd/server.go       # 6 critical services with real RPC logic.
│   ├── bullboard/server.go
│   ├── attrouted/server.go
│   ├── schemard/server.go
│   ├── coordd/server.go
│   ├── errord/server.go
│   └── <34 others>/server.go     # Skeleton: Health real, other RPCs
│                                 # return codes.Unimplemented.
├── services.manifest.yaml        # 40 entries; source of truth.
├── budget.yaml                   # Global cap declarations.
├── Dockerfile                    # Multi-stage scratch.
├── go.mod / go.sum / Makefile / buf.yaml / staticcheck.conf
└── README.md
```

## Source-backed references

The architecture and the resource-budget approach are grounded in:

- **Apache Tomcat servlet-container pattern** — one binary, many independent applications, shared runtime. tomcat.apache.org/tomcat-10.1-doc/architecture/overview.html.
- **Apache Parquet** file format spec — columnar storage with row-group bounds and per-row caps. parquet.apache.org/docs/file-format/.
- **Apache Iceberg** manifest spec — pinned-snapshot semantics, schema-version evolution rules. iceberg.apache.org/spec/.
- **Apache NiFi bulletin board + route-on-attribute** docs — pattern reference for bullboard and attrouted. nifi.apache.org.
- **Apache Avro** schema-evolution rules — backward/forward/full compat semantics for schemard. avro.apache.org/docs/specification/.
- **Apache ZooKeeper Programmer's Guide** — ephemeral nodes, lock recipes, leader election (coordd). zookeeper.apache.org/doc/r3.9.2/zookeeperProgrammers.html.
- **Apache Camel error-handling DSL** — exception-policy registry pattern (errord). camel.apache.org/manual/error-handler.html.
- **gRPC over Unix-socket** — `unix://` scheme, naming + dialer semantics. grpc.io/docs/guides/naming/.
- **Go runtime soft memory limit** — `runtime/debug.SetMemoryLimit` semantics. pkg.go.dev/runtime/debug#SetMemoryLimit.
- **bbolt README** — single-file embedded key/value store; ACID semantics; no external process. github.com/etcd-io/bbolt.
- **Donovan & Kernighan 2015** — *The Go Programming Language*. Chapter 8 (concurrency) + Chapter 11 (testing). ISBN 978-0134190440.
- **Parnas 1972** — *On the Criteria To Be Used in Decomposing Systems into Modules*. CACM 15(12).
- **Beck 2002** — *Test-Driven Development by Example*. ISBN 978-0321146533. Drives the Red-Green-Refactor cycle used for every shared-infra package + schemard.
- **ISO/IEC/IEEE 42010:2022** — Systems and software engineering — Architecture description. www.iso.org/standard/74393.html.
- **Su 2024** — *Modular Monoliths: A Pragmatic Guide*. Cited for the "stay in one process, separate the modules" decision.

## Hard-rule additions to CLAUDE.md / AGENTS.md / CODEX.md / GEMINI.md

This slice introduces the **Snapshot Evidence Read** absolute rule (lands AFTER `.githooks/check-snapshotd-ritual.py` has a passing test suite, per the user-approved plan):

> **ABSOLUTE — Snapshot Evidence Read.** Immediately after `[PAPER TRAIL READ: ...]`, every agent MUST run
> `docker compose exec -T backend python manage.py print_open_snapshots --by-severity --top 3`
> and emit
> `[SNAPSHOTS READ: <N> snapshots attached to <M> open issues — picked: #<id1>(<kind1>), #<id2>(<kind2>), #<id3>(<kind3>)]`.
> The three picks are the highest-severity snapshots whose AutoIssues are in the agent's 30-pick set or 10-paper-trail set.

`.githooks/check-snapshotd-ritual.py` scans the staged AGENT-HANDOFF entry for the marker after `[PAPER TRAIL READ: ...]` and hard-blocks the commit with the Rule-F three-part message if missing. The rule cannot be overridden by an in-session prompt.

## BDD acceptance

```gherkin
Feature: Sidecars host boots and serves 40 services under one budget

  Scenario: Container reaches healthy state under the cap
    Given services/sidecars is built via the multi-stage Dockerfile
    When  docker compose up sidecars runs
    Then  the container reaches healthy state in under 15 seconds
    And   exactly one process is running inside the container
    And   resident memory is under 256 MB at idle
    And   resident memory under 50 % mixed load stays under 512 MB
    And   /var/lib/xf/sidecars/ exists and is under 1 GB
    And   /var/run/xf-sidecars/sidecars.sock is mode 0660

  Scenario: All 40 gRPC service names route correctly
    Given the sidecars binary is running
    When  a Python caller dials xf.sidecars.v1.Schemard.Health
    Then  the call routes to internal/schemard.Server.Health
    And   the reply is HEALTH_SERVING with service="schemard"
    When  a caller dials xf.sidecars.v1.Topicd.Produce (a skeleton service)
    Then  the call returns codes.Unimplemented with a descriptive message

  Scenario: Memory pressure triggers idle release on the lowest-priority service
    Given the budget detector sees RSS > 80 % of cap
    When  the OnPressure callback fires
    Then  the idle tracker selects the lowest-priority service that has not
          been released in the last MinBetweenReleases
    And   that service's Idle() releases its in-memory caches
    And   higher-priority services are not asked to release

  Scenario: Pinned snapshotd snapshots survive the 7-day age sweep
    Given a snapshotd file dated 200 hours ago is pinned
    And   a snapshotd file dated 200 hours ago is unpinned
    When  the pruner runs RunOnce
    Then  the unpinned file is deleted by the age sweep
    And   the pinned file survives
```

## TDD evidence (Slice 1.6)

| Package | Tests | Coverage focus |
|---|---|---|
| `internal/shared/budget` | 8 tests | Pressure threshold, backoff, multi-callback, context cancellation |
| `internal/shared/pruner` | 9 tests | Age sweep, cap eviction, pinned LRU, missing dir |
| `internal/shared/pool` | 7 tests | Size routing, oversize bypass, concurrent safety, zeroing |
| `internal/shared/idle` | 6 tests | Touch reset, force-release priority, backoff |
| `internal/shared/store` | 7 tests | Scoped DB per service, handle reuse, isolation |
| `internal/shared/socket` | 5 tests | Listen at mode 0660, stale-socket cleanup, parent-dir creation |
| `internal/shared/otel` | 5 tests | /healthz 200 vs 503, /debug/pprof mount, graceful shutdown |
| `internal/shared/manifest` | 9 tests | YAML round-trip, duplicate-name rejection, max-services cap, live-manifest parse |
| `internal/schemard` | 6 tests | Register increments versions, backward-compat rejection, Latest, Health |

Total: 62 unit tests across 9 packages. All pass with `go test -race -count=1 ./...`.

## Implemented vs skeleton (honest)

The user-approved plan allocated this session to **foundation + 6 critical implementations + 34 skeletons**. Per the slice's acceptance criteria, the handoff entry uses `[SIDECARS STATUS:]` to declare each of the 40 as one of `{implemented, skeleton, missing}`. There are no `missing` entries: every service has a real `internal/<name>/server.go` registered against the gRPC server.

The 6 critical services implement their **headline RPCs** with real logic. They do NOT all implement every RPC declared in their `.proto`; streaming RPCs (snapshotd.Search, snapshotd.ReadRows, bullboard.Subscribe, coordd.Watch, coordd.Elect) inherit `codes.Unimplemented` from their `Unimplemented*Server` embed this slice. Each gap is filed under `sidecars_followup` in the paper trail.

## Verification commands

```bash
# Build + boot the binary
docker compose up -d sidecars
docker stats xf_linker_sidecars --no-stream        # RSS < 640 MB
docker images xf-linker-sidecars:latest --format "{{.Size}}"   # < 35 MB
docker compose exec -T sidecars du -sh /var/lib/xf/sidecars   # < 1 GB

# Test suite (62 tests across 9 packages)
docker compose run --rm compiled-tools bash -lc "cd /repo/services/sidecars && go test -race -count=1 ./..."

# Run-time soak (deferred to follow-up — needs the Python clients first)
# docker compose exec -T compiled-tools bash -lc "cd /repo/services/sidecars && go test -tags=integration ./test/..."

# Hooks (after K.1 + K.2 land)
# python -m unittest .githooks/test_check_snapshotd_ritual.py
# python -m unittest .githooks/test_check_go_service_resource_budget.py
```

## Risks + open questions

- **Parquet → JSON-Lines fallback**: snapshotd ships with JSON-Lines instead of Parquet this slice. `parquet-go` adds ~3 MB to the binary; if the binary already approaches the 35 MB cap with the simpler format, the Parquet swap may force a Dockerfile refactor (eg., move snapshotd to its own binary). Tracked under `sidecars_followup`.
- **Python clients**: not generated this slice. The 6 critical services need their `backend/apps/<owning>/_sidecars/<name>_client.py` files + the shared `client_base.py` before any Python caller can talk to the sidecars binary. Tracked under `sidecars_followup`.
- **`apps.governance` / `apps.operations` modules**: per the user-approved plan, the spec calls these "future slice 9 work". Today snapshotd's Python client will live under `apps/auto_issues/_sidecars/` and bullboard's under `apps/ops_feed/_sidecars/`, with a comment `# slice 1.6: will move to apps.governance.api / apps.operations.api in slice 9`.
- **UI addendum (Errors page tabs)**: not shipped this slice; the backend implementations need the Python clients first. Tracked under `sidecars_followup`.

## Followup tasks (paper-trail)

One paper-trail entry per skeleton service tagged `sidecars_followup`:
`topicd, provd, pressured, extractd, dagd, ruled, retentd, timetravd, gatewayd, arrowd, catalogd, aclsd, pluginhotd, mesh, smd, tieredd, qsched, gremlind, tsd, hintd, viewd, cepd, xcomd, purged, delayd, flumed, politenessd, fnd, drilld, anomalyd, txd, lookupd, dedupd, compactd`.

Plus one entry each for:
- Parquet swap on snapshotd (currently JSON-Lines).
- Python clients for all 40 (6 critical first, then 34 thin stubs).
- `apps.governance` / `apps.operations` consolidation (slice 9 dependency).
- Errors page UI addendum.
- `peHelper` directive + glossary integration (frontend gap).
- `eslint-plugin-boundaries` wiring (frontend gap).
