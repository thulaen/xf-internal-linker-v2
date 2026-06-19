# ADR 0007 — Python + Rust as the only two backend languages

**Date:** 2026-06-06
**Status:** Accepted
**Deciders:** Project owner.
**Related:** ADR 0006 (Go services tier — superseded for new work), ADR 0007 (root-cause clustering — `clusterd` sidecar superseded).
**Supersedes:** The five-language polyglot model (C, C++, Go, Haskell, Lua) and the Go sidecars tier (streamd, snapshotd, coordd, clusterd, and peers).

## Context

The backend grew into a five-language polyglot: Python for orchestration and machine
learning, C and C++ for numeric kernels, Go for sidecar daemons, Haskell for grouping
logic, and Lua for embedded scripting. Each added language brought its own toolchain,
its own quality gates, and its own slice of the per-commit hook gauntlet. The cost
showed up in three concrete ways:

1. **A brutal per-language commit gauntlet.** Every code-changing commit had to satisfy
   a separate test, lint, coverage, and mutation chain for each language it touched —
   `pytest`/`ruff`/`coverage`/`mutmut` for Python, `clang-tidy`/`mull` for C++,
   `go test`/`go-mutesting` for Go, GHC/MuCheck for Haskell, and more. A one-line change
   that crossed two languages paid both gauntlets. The Haskell mutation gate could not
   even run (no GHC-9.4-compatible mutation tool builds), so that tier was permanently
   blocked.
2. **Disk pressure from load-bearing tool images.** The `backend-quality` and
   `compiled-tools` images each bundle a full per-language toolchain. They are
   load-bearing — the quality gates cannot run without them — so they cannot be pruned,
   and they consume real disk on a single-developer Windows host.
3. **Duplicated home-grown daemons.** The Go sidecars (`streamd`, `snapshotd`, `coordd`,
   `clusterd`, and peers) re-implemented capabilities that already-running
   infrastructure provides. Each was a hand-written "copycat" of a streaming broker, a
   durable evidence store, or a coordinator that Redis, Postgres, Celery, or
   VictoriaMetrics already cover.

The machine-learning and web work is unambiguously Python's. The open question was the
hot-path tier: which single systems language replaces C, C++, Go, and Haskell at once,
under a Python public interface, with no Python fallback to maintain.

## Decision

The backend is **Python + Rust ONLY** for core logic, with **TypeScript/Angular** for the UI. Concretely:

1. **Python owns orchestration and the web layer.** Django, orchestration, module APIs, models, migrations, admin/operator workflows, management commands, schedules, analytics ingestion, report generation, approved offline ML, GUI backend endpoints, and MCP registration. Python may train candidate ranking profiles offline.
2. **Rust owns the performance hot-paths and production correctness.** This includes domain invariants, ranking validity, governance decisions, never-zero weights, movement budgets, score validation, search execution, reranking, normalization, missing-value policy, score breakdown validation, helper workers, optional GPU dispatch, artifact validation, and performance-sensitive compute. Rust must validate, activate, promote, roll back, and live-score ranking profiles. Rust kernels are exposed to Python through PyO3 and built with maturin. The Rust path is **authoritative** with **no Python fallback**.
3. **TypeScript/Angular** owns the browser UI, interaction state, visual workflows, forms, dashboards, and user-facing controls.
4. **PostgreSQL** owns durable relational storage. **ClickHouse, DuckDB, and Polars** own analytics or offline exploration only.
5. **Java** is reserved for later JVM-specific needs such as enterprise integrations, JVM libraries, search/index tooling, streaming connectors, or long-running services. It must not replace Python orchestration, Rust correctness, or Angular UI without a concrete reason.
6. **Capabilities use the lightest proven tool, not a home-grown copycat daemon.** Before writing any new service, reach for infrastructure already running (Redis, Postgres, Celery, VictoriaMetrics) or a proven Python/Rust library.
7. **No other first-party language owns production behavior.** C, C++, Go, Haskell, and Lua are **removed**.
8. **Enforced by tooling.** The guard hook `.githooks/check-removed-languages.py` blocks any commit that re-introduces a removed language. The guard hook `.githooks/check-language-ownership.py` ensures Rust-owned domains are not implemented in Python.

## Alternatives rejected

1. **Java / Spring Boot.** A single mature JVM stack was considered. Rejected: the
   machine-learning ecosystem on the JVM is weak compared with Python's, and the project's
   core is ML. Adopting Java would trade a strong ML story for a strong web story we do not
   need.
2. **Rust-only (drop Python too).** Considered for the simplicity of one language end to
   end. Rejected: Rust's ML and web ecosystems are immature relative to Python's, and the
   learning curve is steep for ML and orchestration code that Python expresses cleanly.
   Python stays the orchestration and ML language.
3. **Status-quo five-language polyglot.** This is the problem itself — the gauntlet cost,
   the disk pressure, and the duplicated daemons described in Context. Keeping it was not a
   real option.

## Consequences

**Positive:**

- **One toolchain for the hot-path and orchestration tiers.** The quality gauntlet
  collapses to `pytest` + `ruff` + `coverage` (plus the Rust crate's own `cargo test` /
  `cargo clippy`), instead of five parallel per-language chains. The permanently-blocked
  Haskell mutation gate disappears.
- **Memory safety at the kernel tier.** Rust replaces the C and C++ kernels at the same
  performance tier while removing the manual-memory-management hazard class (use-after-free,
  buffer overrun) that C and C++ carry.
- **Less disk pressure.** Retiring the Go, C++, and Haskell toolchains shrinks the
  load-bearing `backend-quality` and `compiled-tools` images.
- **Fewer moving parts at runtime.** Capabilities ride on already-running Redis, Postgres,
  Celery, and VictoriaMetrics instead of bespoke daemons that each need their own build,
  deploy, and observability.

**Negative / costs:**

- **Loss of raw C++ speed at the very top end.** Rust does not always match a hand-tuned
  C++ kernel to the last percent. Accepted: Rust replaces C++ at the same performance tier,
  and the memory-safety guarantee plus the single-toolchain saving outweigh the marginal
  difference.
- **A weeks-long migration.** Removing four languages and porting their kernels is not a
  one-commit change. It is done as **deletion plus focused Rust ports**: delete the removed
  language's code and tooling, then port only the hot-paths that need native speed into
  Rust crates under a Python API.

**Precedent.** The pattern "a Rust kernel under a Python API with no Python fallback" is
proven at scale by widely-used projects: PyO3 (the Rust↔Python binding layer), maturin
(the build/packaging tool), Polars (a DataFrame engine whose Rust core is authoritative),
pydantic-core (Pydantic v2's validation core, rewritten in Rust), and HuggingFace
tokenizers (a Rust core under a thin Python API). This ADR follows their model.

## References

- PyO3 — Rust bindings for Python, `https://pyo3.rs`.
- maturin — build and publish Rust-based Python packages, `https://maturin.rs`.
- Polars — Rust-core DataFrame library with a Python API, `https://pola.rs`.
- pydantic-core — Rust validation core under Pydantic v2, `https://github.com/pydantic/pydantic-core`.
- HuggingFace tokenizers — Rust core under a Python API, `https://github.com/huggingface/tokenizers`.
- ADR 0006 — Go services tier (superseded for new work by this ADR).
- ADR 0007 — root-cause clustering via the `clusterd` Go sidecar (the sidecar is retired by this ADR).
- [`.githooks/check-removed-languages.py`](../../.githooks/check-removed-languages.py) — the guard hook that enforces this decision.

[SPEC FRESHNESS: reviewed_at=2026-06-06 next_review=2026-06-30]
