# FR — compiler/linter warnings (Haskell/C++/Go/Rust) → AutoIssues, one shared "fix 10" quota

[SPEC FRESHNESS: reviewed_at=2026-06-01 next_review=2026-06-30]
[SPEC CITED: feature=compiler-warning-autoissues kind=technical_doc id=gcc-warning-options-14 verified_at=2026-05-31]
[SPEC CITED: feature=compiler-warning-autoissues kind=technical_doc id=clang-diagnostics-reference verified_at=2026-05-31]
[SPEC CITED: feature=compiler-warning-autoissues kind=technical_doc id=go-cmd-vet verified_at=2026-05-31]
[SPEC CITED: feature=compiler-warning-autoissues kind=technical_doc id=rust-rustc-lints verified_at=2026-05-31]
[SPEC CITED: feature=compiler-warning-autoissues kind=technical_doc id=ghc-users-guide-warnings-9 verified_at=2026-05-31]

## Problem

The quality runners compile C++, Go, Rust, and Haskell but only record pass/fail — the
individual compiler/linter warnings are lost. The operator wants every warning/error filed
as a tracked, fixable AutoIssue, with a single hard, commit-blocking quota of 10 shared
across all four languages (confirmed: ONE combined quota, not per-language).

## Sources of truth (warning-line grammar per tool)

- **GCC `-Wall` warning options** — `path:line:col: warning: message [-Wcode]` (`gcc-warning-options-14`).
- **Clang diagnostics reference** — same `path:line[:col]: warning|error: message [-Wcode]` shape;
  cppcheck/clang-tidy follow it, sometimes without a column (`clang-diagnostics-reference`).
- **`go vet` / `go` command** — `path:line:col: message` (golangci-lint appends `[code]`) (`go-cmd-vet`).
- **rustc lints / clippy** — multi-line diagnostics whose machine-parseable location line is
  `  --> path:line:col` (`rust-rustc-lints`).
- **GHC user's guide warnings** — `path:line:col: warning|error: message [-Wcode]` (`ghc-users-guide-warnings-9`).

## Behaviour (Given / When / Then)

- **Given** captured compiler output for a language, **When** `ingest_compiler_warnings` parses it,
  **Then** each warning/error becomes one deduped `SOURCE_COMPILER` AutoIssue keyed by
  `compiler:<language>:<file>:<line>:<code-or-message>`; errors are high severity, warnings low.
- **Given** `>= 10` `compiler` AutoIssues are open (across all four languages combined), **When**
  any commit runs, **Then** the commit is blocked unless `>= 10` were resolved this session;
  **Given** `< 10` are open, the commit is never blocked.

## Design

- Pure parser: `backend/apps/auto_issues/services/compiler_warnings.py` (`parse_warnings`,
  one regex per language, `SimpleTestCase`-testable). Regexes were designed by a parallel
  research fan-out (one agent per language inspecting the repo's quality runners).
- Ingest: `backend/apps/auto_issues/services/compiler_ingest.py` (`ingest_compiler_warnings`)
  → shared `upsert_dedup(source=AutoIssue.SOURCE_COMPILER, ...)`.
- Command: `ingest_compiler_warnings --path <log> --language <cpp|go|rust|haskell> [--dry-run]`.
- Source: `AutoIssue.SOURCE_COMPILER = "compiler"` (one combined source for all four languages).
- Quota: `("compiler", 10)` appended to `ALWAYS_ON_SOURCES` in `.githooks/check-always-on-quota.py`
  — the same drought-aware always-on gate built for pgexporter (see
  docs/specs/fr-pgexporter-autoissues.md). One shared quota of 10, not per-language.
- Runner wiring (follow-up): the language quality runners tee compiler stderr to a log the
  command reads.

## Verification

Unit tests `apps/auto_issues/tests/test_compiler_warnings.py` (one fixture set per language,
plus non-matching summary/progress lines) and `test_compiler_ingest.py` (parse → dedupe →
file under `SOURCE_COMPILER`). The always-on quota reuses `verify_always_on_quota --source
compiler --threshold 10`.
