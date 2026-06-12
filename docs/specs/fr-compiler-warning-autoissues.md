# Rust Compiler Warnings And Errors To AutoIssues

[SPEC FRESHNESS: reviewed_at=2026-06-12 next_review=2026-07-12]
[SPEC CITED: feature=rust-compiler-warning-autoissues kind=technical_doc id=rust-rustc-lints verified_at=2026-06-12]
[SPEC CITED: feature=rust-compiler-warning-autoissues kind=technical_doc id=rust-clippy-lints verified_at=2026-06-12]
[SPEC CITED: feature=rust-compiler-warning-autoissues kind=technical_doc id=docs-adr-0007-python-rust-two-language verified_at=2026-06-12]

## Problem

The active backend language set is Python plus Rust. Rust owns compiled hot
paths. The quality runners must not file new C++, Go, Haskell, or Lua compiler
work. Rust compiler and Clippy warnings/errors must become tracked, fixable
AutoIssues with one hard, commit-blocking quota of 10.

## Sources Of Truth

- rustc lints and diagnostics: Rust compiler diagnostics use a header line such
  as `warning:` or `error[E0308]:` and a machine-readable location line shaped
  as `  --> path:line:col`.
- Clippy lint docs: Clippy lint names may appear in notes shaped like
  `#[warn(clippy::name)]`.
- ADR 0007: this repo is Python plus Rust only for backend work. Removed
  compiled languages do not get new active warning pickers.

## Behaviour

Given captured Rust compiler output, when `ingest_compiler_warnings` parses it
with `--language rust`, then each warning/error becomes one deduped
`SOURCE_RUST_COMPILER` AutoIssue keyed by
`rust_compiler:rust:<file>:<line>:<code-or-message>`.

Given a Rust compiler error is filed, when the AutoIssue is created or updated,
then severity is high and priority is higher than a warning.

Given a Rust compiler warning is filed, when the AutoIssue is created or
updated, then severity is low and the affected Rust source file is recorded.

Given a removed backend language such as C++, Go, Haskell, or Lua, when the
command is called, then the command rejects it and files nothing.

Given 10 or more `rust_compiler` AutoIssues are open, when any commit runs,
then the commit is blocked unless at least 10 were resolved this session.
Given fewer than 10 are open, the commit is not blocked by this quota.

## Design

- Pure parser: `backend/apps/auto_issues/services/compiler_warnings.py`
  parses Rust diagnostics only.
- Ingest: `backend/apps/auto_issues/services/compiler_ingest.py` files through
  `upsert_dedup(source=AutoIssue.SOURCE_RUST_COMPILER, ...)`.
- Command: `ingest_compiler_warnings --path <log> --language rust [--dry-run]`.
- Source: `AutoIssue.SOURCE_RUST_COMPILER = "rust_compiler"`.
- Quota: `("rust_compiler", 10)` in `.githooks/check-always-on-quota.py`.
- Migration: existing `source="compiler"` rows are remapped to
  `source="rust_compiler"`.
- Runner wiring: Rust quality runners tee rustc/clippy stderr to a log the
  command reads.

## Verification

- `backend/apps/auto_issues/tests/test_compiler_warnings.py`
- `backend/apps/auto_issues/tests/test_compiler_ingest.py`
- `backend/apps/auto_issues/tests/test_ingest_compiler_warnings_command.py`
- `.githooks/test_check_always_on_quota.py`
- `backend/apps/auto_issues/tests/test_verify_always_on_quota.py`
