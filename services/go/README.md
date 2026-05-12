# Go services (scaffold)

This directory is the home for any Go service the project adds in the future. As of 2026-05-12, no Go code lives here — but the testing + linting standards are already set:

- [`docs/GO-TESTING-STANDARD.md`](../../docs/GO-TESTING-STANDARD.md) — mandates `go test -shuffle=on -race -count=1` and the coverage-ratchet pattern
- [`.golangci.yml`](.golangci.yml) — strict golangci-lint config (gocyclo=10, gocognit=15, funlen=50, gosec, staticcheck, etc.)

## When the first Go service lands

Adding the first `.go` file triggers these follow-ups:

1. CI gets a new `go-test` job mirroring `backend-test`, running the canonical command:
   ```
   go test -shuffle=on -race -count=1 -coverprofile=cover.out ./...
   ```
2. CI gets a `go-lint` job running `golangci-lint run ./...` against this config
3. `.githooks/pre-commit` gains a Go fast band (changed-package only) using the same hardware-aware `MAX_JOBS_FAST` cap as the existing Python / Angular / C++ fast band
4. `.githooks/pre-push` gains a Go heavy band — full `go test ./...` + lint + `go-mutesting` mutation testing on changed packages
5. The 18-pick AutoIssue ritual may grow a 7th source (`go_ci`) if Go-specific picker logic is added

## Subdirectories

- `contracts/` — placeholder for any future Pact provider-verification logic if a Go service exposes HTTP endpoints the Angular frontend consumes

## Why scaffold ahead of code

Defining the standard up front means the first Go contributor doesn't have to negotiate test-runner conventions, linter strictness, or CI integration as a side project. They write the service; the scaffolding picks up the gates.
