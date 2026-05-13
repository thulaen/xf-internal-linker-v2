# Go services (scaffold)

This directory is the home for any Go service the project adds in the future. As of 2026-05-12, no Go code lives here — but the testing + linting standards are already set:

- [`docs/GO-TESTING-STANDARD.md`](../../docs/GO-TESTING-STANDARD.md) — mandates `go test -shuffle=on -race -count=1`, 95% coverage, and blocking mutation testing
- [`.golangci.yml`](.golangci.yml) — strict golangci-lint config (gocyclo=10, gocognit=15, funlen=50, gosec, staticcheck, etc.)

## When the first Go service lands

Adding the first `.go` file triggers these follow-ups:

1. CI runs the `go-quality` job, running the canonical command:
   ```
   go test -shuffle=on -race -count=1 -coverprofile=cover.out ./...
   ```
2. CI fails if `go tool cover -func=cover.out` reports less than 95% total coverage
3. `.githooks/pre-commit` gains a Go fast band (changed-package only) using the same hardware-aware `MAX_JOBS_FAST` cap as the existing Python / Angular / C++ fast band
4. `.githooks/pre-push` runs the full Go test command with the 95% coverage floor and runs `go-mutesting ./...`
5. The 18-pick AutoIssue ritual may grow a 7th source (`go_ci`) if Go-specific picker logic is added

## Subdirectories

- `contracts/` — placeholder for any future Pact provider-verification logic if a Go service exposes HTTP endpoints the Angular frontend consumes

## Why scaffold ahead of code

Defining the standard up front means the first Go contributor doesn't have to negotiate test-runner conventions, linter strictness, or CI integration as a side project. They write the service; the scaffolding picks up the gates.
