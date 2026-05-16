# FR — Go services-tier tooling chain

**Status:** Draft, slice 1.5.
**Spec ID:** fr-go-services-tooling.
**Predecessor:** [fr-modular-monolith.md](fr-modular-monolith.md) (slice 1).

[SPEC FRESHNESS: reviewed_at=2026-05-16 next_review=2026-06-16]

## Plain-English summary

The repository already has one Go service: `services/streamd`, the stream-engine broker. Slice 1 made the services tier a first-class part of the architecture but did not wire any commit-time enforcement, did not give Go a quality runner that matches the Python and C++ ones, and left streamd as a library-only Go module — no binary, no published contract.

Slice 1.5 closes those gaps in one slice:

1. The two boundary hooks (`check-no-cross-language-import.py`, `check-go-service-contract.py`) hard-block at commit.
2. The Go quality runner (`scripts/run-go-quality.sh` + nine per-stage sub-scripts) mirrors the C++ chain one-for-one.
3. Streamd is promoted to a real sidecar binary with a published gRPC contract over a Unix-domain socket.
4. A private Python client lives at `backend/apps/realtime/_streamd_client.py`. **No public caller switches in this slice** — `apps.realtime.api.broadcast` keeps its Django-Channels path so the slice is a pure infrastructure landing with no behaviour change.

## Why this slice exists

Slice 1's foundation document declared rules. The rules are not enforced without code. The repo also pays a recurring cost for streamd being library-only: any future Python caller that wants stream-broker semantics has to import the library (forbidden by the boundary rule it has not yet enforced), so the natural workaround has been to avoid the library and re-implement broker semantics in Django Channels (which is where `broadcast()` lives today). Promoting streamd to a binary with a public contract closes that gap before the rule-enforcement work makes the cycle visible.

## Citations

| Reference | Kind | Used for |
|---|---|---|
| Donovan & Kernighan 2015 — *The Go Programming Language*, Addison-Wesley, §8 (concurrency) + §11 (testing) | technical_literature | Goroutine + channel scheduling justification for Go on the broker workload; `go test -race` is the canonical Go testing path. |
| Go documentation — `testing` package + `-race` flag (https://pkg.go.dev/testing) | technical_doc | Source of truth for the race detector and the test runner flags `-race`, `-shuffle=on`, `-count=1`, `-coverprofile`. |
| Go documentation — `log/slog` (https://pkg.go.dev/log/slog) | technical_doc | Structured JSON logging from the streamd binary; replaces ad-hoc `fmt.Println`. |
| Go documentation — `signal.NotifyContext` (https://pkg.go.dev/os/signal#NotifyContext) | technical_doc | Graceful shutdown pattern for `cmd/streamd/main.go`. |
| Go documentation — `net/http/pprof` (https://pkg.go.dev/net/http/pprof) and the Go blog post on profiling (https://go.dev/blog/pprof) | technical_doc | Localhost-only pprof endpoint for OpenTelemetry profile scraping. |
| `go-mutesting` README (https://github.com/avito-tech/go-mutesting) | technical_doc | Mutation testing tool, kill-rate gate at ≥ 70%. |
| `staticcheck` documentation (https://staticcheck.dev/docs/) | technical_doc | Strict static analyser. Honours `staticcheck.conf` for narrow silences. |
| `golangci-lint` documentation (https://golangci-lint.run/) | technical_doc | Meta-linter; honours `services/<name>/.golangci.yml`. |
| `gosec` README (https://github.com/securego/gosec) | technical_doc | Static security scanner. |
| `gofmt` documentation (https://pkg.go.dev/cmd/gofmt) | technical_doc | Canonical Go formatter. |
| gRPC Go documentation (https://grpc.io/docs/languages/go/) | technical_doc | gRPC server boilerplate, keepalive defaults, max-message-size knobs. |
| gRPC Python documentation (https://grpc.io/docs/languages/python/) | technical_doc | `grpcio` + `grpcio-tools` for the private Python client. |
| gRPC `unix://` URI scheme — https://github.com/grpc/grpc/blob/master/doc/naming.md | technical_doc | Source for the `unix:///var/run/xf/streamd.sock` dial form. |
| `buf` style guide (https://buf.build/docs/best-practices/style-guide) | technical_doc | Protobuf style rules + breaking-change detection. |
| Linux `man 7 unix` (https://man7.org/linux/man-pages/man7/unix.7.html) | technical_doc | AF_UNIX semantics: socket modes, group ownership, peer credentials. |
| US Patent US10700948B2 — Service-Oriented Modular System Architecture | patent | Sidecar pattern as a documented architectural choice. Cross-referenced from `fr-modular-monolith.md`. |
| Beck 2002 — *Test-Driven Development: By Example*, Addison-Wesley | technical_literature | The Red-Green-Refactor cycle applied across Python, Go, and protobuf. |

[SPEC CITED: feature=fr-go-services-tooling kind=technical_doc id=grpc-go verified_at=2026-05-16]
[SPEC CITED: feature=fr-go-services-tooling kind=technical_doc id=staticcheck verified_at=2026-05-16]
[SPEC CITED: feature=fr-go-services-tooling kind=technical_doc id=go-test-race verified_at=2026-05-16]
[SPEC CITED: feature=fr-go-services-tooling kind=technical_literature id=donovan-kernighan-2015 verified_at=2026-05-16]
[SPEC CITED: feature=fr-go-services-tooling kind=technical_doc id=man7-unix verified_at=2026-05-16]
[SPEC CITED: feature=fr-go-services-tooling kind=patent id=US10700948B2 verified_at=2026-05-16]

## Architecture decisions captured here

These are slice-1.5 commitments, recorded so future slices can reference them without re-deriving:

1. **gRPC over Unix-domain socket** is the default cross-language transport for sidecar services on the same host. Round-trip latency is roughly 30–80 µs versus 100–200 µs for TCP loopback. The named volume `streamd_sock` carries the socket between containers.
2. **Single contract file per service**, at `services/<name>/api.proto` (gRPC) or `services/<name>/api.http.md` (HTTP+JSON). gRPC is preferred; HTTP+JSON is allowed when the contract is read by external systems that don't speak gRPC.
3. **Generated stubs are committed**, not regenerated at build time. Stub paths: `services/<name>/api/gen/*.pb.go`, `backend/apps/<owning-module>/_streamd_pb2/*.py`. Pinned generators: `protoc-gen-go@v1.34`, `protoc-gen-go-grpc@v1.5`.
4. **Binary entry point at `services/<name>/cmd/<name>/main.go`** is mandatory. Library-only Go modules under `services/` are forbidden by `.githooks/check-go-service-contract.py`.
5. **Internal packages stay under `services/<name>/internal/`** so the Go module system enforces module-private access. The binary in `cmd/<name>/main.go` is the only consumer of the internal packages.
6. **The owning Django module's `api.py` is the public Python surface.** The gRPC client lives at `backend/apps/<owning-module>/_streamd_client.py`, underscore-prefixed so it is module-private. No caller outside the owning module imports it.
7. **Speed claim is mandatory.** Every Go service that justifies its existence on performance grounds must ship a benchmark in `services/<name>/test/bench_*_test.go` that proves the speed claim. Missing the claim after 5 tuning iterations files a `performance-native-rewrite` AutoIssue and a `[PERFORMANCE EXEMPTION: ...]` marker — the slice still ships, but honestly.

## Test plan

```
[BDD PROOF: Given streamd is library-only When slice 1.5 lands Then streamd is a binary with 4 RPCs over a Unix socket AND the Go quality chain mirrors C++ one-for-one AND cross-language imports are hard-blocked]
[TDD PROOF: before_or_alongside=yes tests=".githooks/test_check_no_cross_language_import.py;.githooks/test_check_go_service_contract.py;.githooks/test_go_services_layer.py;services/streamd/test/integration/test_unix_socket_roundtrip_test.go;services/streamd/test/bench_publish_subscribe_test.go;backend/apps/realtime/tests/test_streamd_client_contract.py" result=passed]
```

Per-stage verification commands are in `C:\Users\goldm\.claude\plans\slice-1-5-refactored-fountain.md` § 7.

## Performance spec

The streamd binary must hit, on the dev machine over the Unix socket:

- p99 publish→subscribe round-trip latency < 1 ms (1,000 µs)
- throughput > 50,000 messages per second

Up to **5 tuning iterations** are budgeted in the slice's TDD step list. If the target is not met after 5 iterations, the slice ships with:

- `AutoIssue(label='performance-native-rewrite')` filed with the measured numbers and the conclusion that streamd-on-Go is not yet meeting the speed claim;
- `[PERFORMANCE EXEMPTION: function=streamd_publish_subscribe best_p99_ms=<X> best_throughput_msg_s=<Y> iterations=5/5 reason=<...>]` in the handoff entry.

Silent slow numbers are forbidden. Honest failure is preferred.

[PERFORMANCE SPEC: sources=fr-go-services-tooling source_types=technical_doc,technical_literature tdd=yes tests="docker compose run --rm -T compiled-tools bash -lc 'cd /repo/services/streamd && go test -bench=BenchmarkPublishSubscribe -benchmem -count=3 -run=^$ ./test/...'"]

## Stop conditions

- The pre-promotion broker audit (step 12 of the TDD step list) reveals the broker shape is not a fan-out-over-offsets store → pause before writing `api.proto`.
- Benchmark misses target by > 2× (p99 > 2 ms OR throughput < 25,000 msg/s) → file `performance-native-rewrite` AutoIssue + paper-trail entry titled "Reconsider streamd-on-Go" + pause Half B's compose entry before merging.
- `go-mutesting` produces > 200 surviving mutants on streamd → file paper-trail `mutation_survivor`; the kill-rate floor stays at 70%.
- Installing `staticcheck` / `buf` / `protoc-*` requires rebuilding `compiled-tools` and would wipe its layer cache → confirm with user before rebuilding.
- Any change to `apps.realtime.api.broadcast`'s public signature → stop. The slice explicitly chose "no caller switch".

## Relationship to slice 1, slice 2, and slice 10

- Slice 1 (foundation docs) declared the services tier. Slice 1.5 makes it enforceable.
- Slice 2 (Python module import-linter) is independent. The import-linter targets Python-only boundaries; `check-no-cross-language-import.py` targets the Python ↔ Go boundary. The two run side-by-side.
- Slice 10 (shim removal) does not touch the services tier — shims live inside the Django modules. The Go services tier has no shims.
