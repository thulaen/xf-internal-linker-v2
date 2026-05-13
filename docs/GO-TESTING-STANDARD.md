# Go Testing Standard

**Status:** Scaffolding only — no Go code lives in this repo yet. This document is the contract every future Go service must follow the moment its first `*.go` file lands.

This standard exists so that when a Go service (worker, ingestor, gateway, etc.) is added to the project, its test suite enforces the same "tests must mean something" discipline the rest of the stack already enforces. The discipline parallels what `pytest-randomly` does for Python and `--gtest_shuffle` does for C++.

## Mandatory flags for every Go test invocation

Every `go test` invocation — local, pre-commit, pre-push, CI — MUST include:

```bash
go test -shuffle=on -race -count=1 ./...
```

**Why each flag is non-negotiable:**

| Flag | What it does | Why we require it |
|---|---|---|
| `-shuffle=on` | Randomises test execution order across runs | Catches order-dependent tests (tests that pass only because of leftover state from earlier tests). A failing seed is printed so the order can be reproduced via `-shuffle=<seed>`. |
| `-race` | Enables Go's race detector | Catches data races at runtime — Go's concurrency primitives make this trivial to introduce and almost invisible without `-race`. |
| `-count=1` | Disables the test result cache | Forces every CI run to actually execute tests instead of replaying a stale "pass" verdict from a previous build. |

Adding `-v` for verbose output during debugging is fine. Removing `-shuffle=on`, `-race`, or `-count=1` is a policy violation — equivalent to flipping a CI gate from blocking to warning-only without a `# GATE-DOWNGRADE-JUSTIFICATION:` comment.

## Coverage floor

`go test -coverprofile=cover.out -shuffle=on -race -count=1 ./...` followed by `go tool cover -func=cover.out` and a CI step that fails when coverage drops below **95%**. This is the repo-wide Go floor from the first Go service onward. The floor is a ratchet: it may be raised, but it must not be lowered without a documented incident.

## Linter

Strict `golangci-lint` config lives at [`services/go/.golangci.yml`](../services/go/.golangci.yml). It enables `gofmt`, `govet`, `errcheck`, `staticcheck`, `gocyclo=10`, `gocognit=15`, `funlen=50`, `unused`, `gosec`, `misspell`, `dupl`. Pre-commit and CI both run `golangci-lint run ./...` and hard-fail on any finding.

## Mutation testing

Future Go services use `avito-tech/go-mutesting` as a blocking mutation check. The CI job installs the tool and runs `go-mutesting ./...` for every Go module that exists in the repo. If a service later becomes too large for a whole-module run, that service must add a documented package-level scope and keep mutation testing blocking for every package it owns.

## Fuzz testing

Go's standard library has built-in fuzzing (`go test -fuzz=Fuzz*`). When the first Go service lands, every public API takes at least one fuzz target. Crashes are written to `testdata/fuzz/<FuzzFunc>/` and become committed regression tests automatically.

## Where this fits in the pipeline

When the first Go service is added:

1. CI runs the `go-quality` job, invoking the canonical test command above and failing below 95% coverage.
2. Pre-commit gains a `go vet && go test` step on changed packages only.
3. Pre-push runs the full Go test command with the 95% coverage floor and runs `go-mutesting ./...`.
4. The 18-pick AutoIssue ritual gains a 7th source (`go_ci`) if Go-specific picker logic is added.

## Reference

- Go testing docs: https://pkg.go.dev/testing
- `-shuffle` was added in Go 1.17 (August 2021)
- `-race` requires CGO_ENABLED=1 and amd64/arm64; document any architecture skip in the service README
- `golangci-lint` config reference: https://golangci-lint.run/usage/configuration/

## Plain-English summary

If we ever write a Go service, every test command we run will scramble the order of the tests, watch for racing-thread bugs, and refuse to reuse cached results. If a test ever quietly relied on another test running first, the build breaks. If a thread-safety bug creeps in, the race detector says so. Same protection the rest of the codebase already has.
