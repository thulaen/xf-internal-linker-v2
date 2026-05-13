# Mutation Testing

Mutation testing checks whether tests notice when code is deliberately broken. A mutation tool
changes one small thing, such as flipping `>` to `<`, then runs the tests. If the tests still
pass, that mutant survived and the test suite needs a stronger assertion.

## Tool Standard

Use a mutation tool only when all of these are true:

- It has public releases or project activity from 2021-01-01 through 2026-05-12.
- It is mature enough for repeatable CI use, or the repo keeps it in pilot mode only.
- It can run on a small package, file, or test target instead of mutating the whole repo.
- It has a time limit, worker limit, shard support, or another clear large-project control.
- It writes a machine-readable report that can feed `.githooks/check-mutation-score.py`.

Activity inside the last five years is required, but it is not enough by itself. Large-project
behaviour matters more than adding a tool for every language.

## Current Gates

| Language area | Tool | Status | Reason |
|---|---|---|---|
| Python | mutmut | Active CI gate | Current release line is active in 2026, it works with pytest, and CI runs it on focused backend files. |
| Angular | StrykerJS | Active CI gate | Current release line is active in 2026, it supports Angular through the JavaScript and TypeScript runner, and CI runs it on a focused service. |
| JavaScript / TypeScript | StrykerJS | Active path through the Angular gate | Same tool as Angular. Add non-Angular JavaScript files by expanding `frontend/stryker.config.json` with focused targets. |
| C++ | Mull | Scoped CI pilot | Active project with scoped native-test execution. CI installs it only for `test_fieldrel`, not the whole C++ tree. |
| Go | avito-tech/go-mutesting | Active CI gate when Go modules exist | Active in 2025 and supports file, directory, and package targets. CI runs it for every Go module once a `go.mod` exists. |

## Docker Availability

The `compiled-tools` Docker service installs the backend-side compiled-language and mutation
tools so a new PC can rebuild the stack and get the same tools quickly:

- `mutmut` for Python.
- `mull-runner-19` for scoped C++ mutation pilots.
- `go` and `go-mutesting` for future scoped Go package mutation pilots.
- `cmake`, `ninja`, and `clang++-19` for C++ tests, fuzzing, and benchmarks.

The frontend Stryker toolchain lives in the frontend build image. Check it with:

```bash
docker compose --profile tools run --rm compiled-tools
docker compose --profile tools run --rm frontend-mutation-tools
```

Run frontend mutation from that image with:

```bash
docker compose --profile tools run --rm frontend-mutation-tools npx stryker run
```

## Python

```bash
cd backend
mutmut run \
  --paths-to-mutate=apps/pipeline/services/field_aware_relevance.py \
  --runner="python -m pytest apps/pipeline/tests.py::FieldAwareRelevanceServiceTests -p randomly -x -q --no-cov" \
  --processes=2
mutmut results
```

`mutmut results` exits with failure if any mutant survived. Mutmut must run on a system with
`fork`, so use Linux or WSL for local runs.

## Angular And JavaScript

```bash
cd frontend
npm run test:mutation
```

Reports land in `frontend/reports/stryker.html` and `frontend/reports/stryker.json`. The
Stryker break threshold is 95%, so CI fails below 95%.

## C++ Rule

Mull is installed in CI from the official Mull package repository and runs only against
`test_fieldrel`. Do not expand it to the whole extension tree. Any new C++ target must have:

- A focused target, not a whole-extension mutation run.
- A fixed worker count and timeout.
- A JSON report or another stable machine-readable report.
- A documented runtime at three sizes: small, medium, and large.
- A documented maintenance check showing the tool has been updated since 2021-01-01.

The current C++ install path is the `cpp-mull-fieldrel` CI job. It installs Mull 19, builds the
focused native test with Clang 19, writes `backend/extensions/reports/mull/mutants.json`, and
checks the mutation score ratchet.

## Go Rule

Go mutation testing must run before Go code lands and stay blocking after Go code exists.

Gremlins is not enabled because its own project documentation says it is aimed at smallish Go
modules and can take hours on very large modules. Gooze is also not enabled yet because it is
new and still below version 1.0. Either tool can be reconsidered only as a focused package-level
pilot with a time limit, pinned version, and machine-readable report.

The installed Go tool is `github.com/avito-tech/go-mutesting/cmd/go-mutesting@latest`. CI
installs it now so the tool is ready before Go code lands. The default target is `./...` inside
each Go module. If a future Go module becomes too large for that whole-module target, the module
must add a documented package-level target and keep mutation testing blocking for every package it
owns.

## Ratchet

`.mutation-score-baseline.json` records per-target floors. The score can go up, but it must
not go down. New scoring, parsing, and state-transition code should add a focused Python,
Angular, or JavaScript mutation target before merge when the target is small enough to run
predictably.

## Sources Checked

- PyPI `mutmut` release history: current release `3.5.0` on 2026-02-22.
- StrykerJS GitHub release history: current release `v9.6.1` on 2026-04-10.
- Mull project site: active project docs describe C and C++ mutation testing with CI-native scoped runs.
- Gremlins documentation and Go package page: active in 2025, but version `v0.6.0` is not stable and its docs warn about very large modules.
- avito-tech `go-mutesting` Go package page: active in 2025, supports file, directory, and package targets, and has JSON output configuration.
- Gooze Go package page: active in 2026, but version `v0.2.0` is too new for a default large-module gate.
