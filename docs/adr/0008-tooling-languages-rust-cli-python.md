# ADR 0008 — Tooling languages: Rust CLI + Python; no third language

[SPEC FRESHNESS: reviewed_at=2026-06-07 next_review=2026-06-30]

- **Status:** Accepted, 2026-06-07.
- **Supersedes/extends:** [ADR 0007 — Python + Rust two-language](0007-python-rust-two-language.md).
- **Companion spec:** [`../specs/fr-rust-cli-tooling.md`](../specs/fr-rust-cli-tooling.md).

## Context

Repo tooling (log forensics, old-data cleanup, CI checks, validators, auditors) has leaned on
**PowerShell**, which is Windows-only and error-prone, plus ad-hoc Bash (and on this host `bash`
resolves to a broken WSL shell). A proposal was raised to add **Perl** as a dedicated, cross-platform
"tooling-only, not app-architecture" language.

ADR 0007 made the backend **Python + Rust only** precisely to end language sprawl: every extra
language is another toolchain to install on every machine + CI runner, another quality gate, more
disk, and a maintenance island. This session removed Go, Haskell, Lua, and C++ for exactly those
reasons.

## Decision

1. **No third first-party language. No Perl.** Adding Perl (or any new language) for "tooling" still
   means a new interpreter, package manager (CPAN), CI lane, and a knowledge island — the same pain
   ADR 0007 removed. Rust + Python already cover every cross-platform tooling need.
2. **Durable CLI tooling is Rust** — a single self-contained, cross-platform binary (cross-platform
   *by compilation*), no runtime to install, fast, type-safe. Built with `clap`, shipped as **one
   multi-command binary (`xftool`)** whose subcommands are **thin front-ends over the existing app
   crates** (`ranking_core`, `ranking_profiles`, artifact-validation, `search_index`, …). The
   validation/diff/audit logic lives **once**; the app reaches it via PyO3, the CLI via `clap`.
3. **App/operator workflows that need Django/Postgres state are Python/Django management commands** —
   anything that needs the ORM, the migration graph, or live DB state (e.g. `schema_migration_checker`).
4. **Utilities and libraries are used freely** — they are invoked tools / libraries, not first-party
   languages that own code, so they do **not** violate "Python + Rust only":
   - **ripgrep (`rg`)** — fast text/log search.
   - **jq** — JSON slicing in the shell.
   - **DuckDB** — in-process SQL over CSV/Parquet (CLI or Python).
   - **Polars** — fast dataframe batch processing in Python (already an approved tool).
5. **PowerShell is retired from cross-platform logic.** It stays only for genuinely Windows-host
   operations (Docker Desktop / WSL control, the Dell/Mint `.ps1` helpers). No new cross-platform
   logic is written in PowerShell.
6. **Tooling is NOT app architecture.** The `xftool` crate lives under a tooling path
   (`rust/tools/`), the app **never imports it**, and it never owns production behaviour. It is for
   CI checks, log forensics, data cleanup, and auditing only.

## Consequences

- One new Rust crate (`rust/tools/`, binary `xftool`) — no new language, no new runtime, no new CI
  toolchain. It compiles with the same cargo path already used for the kernels.
- Tools reuse existing crates (DRY) — a tool is a few lines, not a reimplementation.
- The toolkit grows via a **catalog** (the companion spec) in waves; it is not 1000 stubs written up
  front (that would violate KISS/DRY/THINK-BEFORE-YOU-CODE). Each tool earns its place.
- PowerShell-only scripts that contain cross-platform logic are migrated to `xftool` subcommands or
  Python over time.

## Alternatives rejected

- **Perl for tooling** — rejected: a third language reintroduces the polyglot tax ADR 0007 removed.
- **Keep PowerShell for everything** — rejected: Windows-only, error-prone, not portable to the Dell
  helper or CI.
- **1000 separate tool binaries/crates** — rejected: bloat; one multi-command binary with a catalog
  of subcommands is the maintainable shape.
