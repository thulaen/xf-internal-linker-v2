# Modular Monolith

**Status:** Foundation document — slice 1 of 10. Every later slice references it.
**Last updated:** 2026-06-06.
**Source-backed spec:** [`docs/specs/fr-modular-monolith.md`](specs/fr-modular-monolith.md).
**Decisions of record:** [`docs/adr/0001-modular-monolith.md`](adr/0001-modular-monolith.md), [`0002`](adr/0002-public-interface-api-py.md), [`0003`](adr/0003-cross-module-fk-allowed.md), [`0004`](adr/0004-no-event-bus-yet.md), [`0005`](adr/0005-shims-removed-in-slice-10.md), [`0007`](adr/0007-python-rust-two-language.md).

> **Language note (2026-06-06):** the backend is **Python + Rust only**. Rust owns the
> hot paths (the per-candidate scoring loop, candidate retrieval, embedding/sketch math)
> and holds the single canonical implementation for the nine ranking responsibilities listed
> in [`RUST-FIRST.md`](../RUST-FIRST.md). There is **no Python fallback** for a Rust kernel.
> C, C++, Go, Haskell, and Lua are removed. The earlier "C++ for hot paths" and "Go services
> tier" sections of this document are superseded — see [ADR 0007](adr/0007-python-rust-two-language.md)
> and [`docs/PYTHON-RUST-MIGRATION-PLAN.md`](PYTHON-RUST-MIGRATION-PLAN.md). The nine Django
> modules, the `api.py` boundary, and the one-way dependency direction below are unchanged.

## Plain-English summary

This project is **one deployable backend** (one Django container, one set of running Celery workers, one database). The codebase inside that backend is split into **modules** — named folders that own a slice of the work. Each module hides its insides. Other modules only reach it through one file: `api.py`. That one file is the **public interface**. Anything not exported by `api.py` is private.

This document spells out the modules, the import rules, and the order in which the rest of the codebase is brought into shape. It exists because Parnas (1972) and Lehman (1980) both showed that code without a clear module description drifts. Su (2024) found the most common modular-monolith failure mode is "no shared definition of what a module is." This file is that shared definition.

If you only read one document about how this code is organised, read this one. If a deeper question pops up, the source-backed spec and the five Architecture Decision Records cover the rest.

## What this is and what this is not

**This is** the internal layout of the Django backend. The modules in this document describe how Python code under `backend/` is grouped.

**This is not** the runtime architecture. The runtime — Django, Celery, Redis, Postgres, Angular — is still one deployable unit. The system diagram in [`docs/v2-master-plan.md`](v2-master-plan.md) § 3 is unchanged. We did not move to microservices. We did not add a message bus. We did not split the database.

The shift is editorial: the code becomes easier to read and to change because each module's public surface is named and small.

## Module map

The backend is split into nine modules. Every module owns one job. The module names are deliberately small — under three syllables when possible — so a sentence about the code stays short.

| Module | Owns |
|--------|------|
| **platform** | Cross-cutting helpers everything else uses: settings, hardware profile, disk-pressure circuit breaker, audit logging, error tracking, feature flags, plain-English helpers. |
| **content** | Posts, pages, threads, anchor phrases, distilled text. The content model the linker reads and writes against. |
| **sources** | The read-only connectors to XenForo and WordPress. Owns API clients, webhook receivers, SSH-export fallbacks, rate limiting. Never writes to the live forum. |
| **pipeline** | The 3-stage ranking pipeline: candidate selection, scoring, re-ranking. Owns the Rust extensions for the hot paths and the Python orchestration around them. |
| **suggestions** | Proposed links: status transitions (proposed → reviewed → applied → rejected), the review queue, anchor policy enforcement, near-duplicate clustering. |
| **analytics** | The read-only data taps to Google Search Console, Google Analytics 4, Matomo. Owns the ingest cadence, the rate limiter, the impact-tracking tables. |
| **graph** | Link-graph storage, PageRank, node affinity, graph fitness checks, visualization data. |
| **operations** | Background jobs, Celery beat schedules, websockets, jobs dashboard, paper-trail, AutoIssue picker, performance baselines. The "ops console" surface. |
| **governance** | Specs, ADRs, glossary, citations, hook enforcement, paper-trail policy, business-logic checklist runner. The rule-enforcement surface. |

The names exist as folders today only conceptually. Slice 2 maps each existing `backend/apps/<name>/` to one of the nine modules. Slice 3 starts moving code into `api.py` files.

## Services tier (Go sidecars) — RETIRED

> **Retired 2026-06-06.** The backend is now **Python + Rust only**, so there is no Go
> services tier. The Go sidecars (`services/streamd`, `services/sidecars`, `services/clusterd`)
> and their RPC contracts are removed. Work that those sidecars did either moves into Python
> orchestration or into a Rust extension on the hot path. [ADR 0006](adr/0006-go-services-tier.md)
> (Go services tier) and [ADR 0009 — root-cause clustering via the clusterd sidecar](adr/0009-root-cause-clustering.md)
> are superseded by [ADR 0007 — Python + Rust only](adr/0007-python-rust-two-language.md). The
> migration sequence is in [`docs/PYTHON-RUST-MIGRATION-PLAN.md`](PYTHON-RUST-MIGRATION-PLAN.md).
>
> The nine-module Django dependency direction below is unchanged. The hot-path compute that used
> to be argued between "C++ first" and "Go sidecar" is now always a Rust extension built through
> the Docker-managed maturin path, with the single canonical implementation and no Python fallback
> (see [`RUST-FIRST.md`](../RUST-FIRST.md)).

## Public interface convention

Every module declares its public surface in **one file**: `api.py`, at the module root.

```text
backend/apps/<module>/
├── api.py            # public — exported names live here
├── models.py         # private
├── services/         # private
├── tests/            # private
├── migrations/       # private
└── ...
```

Three rules govern `api.py`:

1. **Only re-exports.** `api.py` does no real work. It imports names from private modules and re-exports them via `__all__`.
2. **Small.** A module with more than ~30 public names usually wants to be split. The `api.py` file is a quick way to see if the module has grown too many jobs.
3. **Typed.** Every public function has a type signature. Every public class has typed fields. The public surface is the place the type checker pays the most attention.

A module that consumes another module **only** imports from that module's `api.py`. Reaching into private files is forbidden — even when it would work.

```python
# allowed
from apps.content.api import Post, distill_post

# forbidden
from apps.content.services._internal import _normalise_anchor
```

The boundary check (slice 2) enforces this with `import-linter`. Until then, the rule is a code-review one.

## Boundary rule

The boundary rule is the single rule that keeps modules independent:

> **No cross-module import except through `api.py`.**

This rule is enforced in three layers:

1. **Today (slices 1-2)** — code review.
2. **Slice 3 onward** — `import-linter` contract published in this repo. Pre-commit hook blocks any new violation. Existing violations are listed and ratcheted down.
3. **Slice 10 onward** — every violation is an error. Shims and exceptions removed.

Inside a module, files import each other freely. Across modules, only `api.py`.

## Dependency direction

The nine modules sit in three layers. Imports flow **only** downward.

```text
Layer 3 — orchestration:    operations · governance
Layer 2 — business:         pipeline · suggestions · analytics · graph
Layer 1 — foundation:       platform · content · sources
```

Rules:

- Layer 3 modules may import from Layer 2 or Layer 1.
- Layer 2 modules may import from Layer 1.
- Layer 2 modules may **not** import from each other directly. If `suggestions` needs something the `pipeline` produces, the answer is a typed record on `pipeline.api` plus a clearly-named call.
- Layer 1 modules may not import from each other. `platform` may import from neither `content` nor `sources`. `content` and `sources` are siblings; if they need to share a record, it lives in `platform.api`.

This shape stops circular dependencies before they start. It also means a change to `content` cannot ripple sideways into `analytics` — only downward, into things `content` already owns.

## Test plan

Every slice ends with a check the next agent can run. The check is small and Docker-managed where applicable.

- **Slice 1 (this slice)** — `python -m pytest -p randomly -q .githooks/test_check_modular_monolith_docs.py` passes. Spec-citation regression `python -m pytest -p randomly -q .githooks/test_check_spec_citation.py` still passes.
- **Slice 2** — `import-linter` runs from the pre-commit hook against the contract published in `pyproject.toml`. The contract names the 9 modules and the dependency direction above. First run reports the baseline. Ratchet from there.
- **Slice 3-9** — each slice moves one module into its `api.py` shape. The slice's test is "before the move, code-review found N cross-module reaches into private files; after the move, the count is 0 for that module." `import-linter` proves it on each commit.
- **Slice 10** — every shim file is deleted. `import-linter` runs with zero exceptions. The pre-commit hook is the only enforcement that remains.

## Stop conditions

A slice halts and asks the user when:

- A module turns out to need more than three publicly-exported records to do its job (this usually signals that the module is doing two jobs and should be split).
- A cross-module Python import is found that cannot be solved through `api.py` (this is rare; the usual cause is a missing typed record in the lower module).
- A foreign-key crosses a module boundary in a new way and the slice's author is not sure whether the FK is on the right side. (See ADR 0003 for the existing answer.)
- A change in one slice would force a change in three or more other slices in the same session. (That signals the module map is wrong; revise the map, then proceed.)

Stopping is the right answer. The cost of a wrong module boundary is years; the cost of a one-day pause to talk it through is one day.

## Slice ledger

The full plan covers ten slices. Each slice has a single goal and a single check.

| Slice | Goal | Single check |
|-------|------|--------------|
| 1 | Foundation document + spec + ADRs + glossary + per-agent rule. | The 7 tests in `test_check_modular_monolith_docs.py` pass. |
| 2 | Map every `backend/apps/<name>/` to one of the 9 modules. Add `import-linter` baseline contract. | `import-linter` reports its first ratchet number. |
| 3 | Move `platform.api` first (smallest, most-used). | `import-linter` ratchet drops; no module reaches into `platform` private files. |
| 4 | Move `content.api`. | Same shape as slice 3. |
| 5 | Move `sources.api`. | Same shape. |
| 6 | Move `pipeline.api`. | Same shape. Rust extension boundary unchanged — Python wrapper goes through `api.py`. |
| 7 | Move `suggestions.api`. | Same shape. |
| 8 | Move `analytics.api` and `graph.api` (smaller; can land together). | Same shape. |
| 9 | Move `operations.api` and `governance.api`. | Same shape. |
| 10 | Delete the shims. Final pre-commit hook flips from "ratchet" to "zero". | `import-linter` runs with zero violations and zero exceptions. |

Each slice carries its own source-backed spec, BDD scenarios, TDD test, coverage target, and stop conditions. The handoff template at the bottom of [`docs/specs/fr-modular-monolith.md`](specs/fr-modular-monolith.md) is reused across slices.

## How this is enforced

Three layers, increasing strictness:

1. **Documents** — this file, the spec, the ADRs, the glossary. Every agent reads them. Every reader can answer "what's a module here?"
2. **Hook tests** — `.githooks/test_check_modular_monolith_docs.py` confirms the documents stay present and correct. The pre-commit hook in slice 2 promotes the test to a check that blocks commits.
3. **Compile-time** — once `import-linter` is wired in slice 2, every commit that violates the dependency direction is blocked. The build itself becomes the enforcer.

Documents tell humans the rules. Hooks tell agents the rules. The compile-time check tells the code the rules. All three are needed.

## What a module owns

Every module document under `docs/modules/<name>.md` answers the same six questions. Slice 2 fills them out:

1. **Job** — what is the module's single responsibility (the "and"-test from `AI-CODING-GUIDELINES.md`)?
2. **Public records** — which types and functions does `api.py` export?
3. **Owned tables** — which Postgres tables does this module write to?
4. **Dependencies** — which modules does this module import from? (Always downward.)
5. **Open questions** — known unresolved questions for the slice that moves this module.
6. **Citations** — at least one patent, RFC, DOI, or stable URL behind the module's central algorithm or design choice.

Slice 1 lands the stubs. The detail arrives in the slice that moves the module.

## FAQ for the vibe coder

**Is this a rewrite?** No. Nothing about the runtime changes. The app starts, stops, and behaves exactly the same way. Only the names and the import paths shift, slice by slice.

**Do I (the user) need to do anything?** Approve each slice and accept the small change in test commands. Nothing operational changes.

**What about plugins?** The plugin system in `docs/v2-master-plan.md` § 13 continues. A plugin is a module too; it follows the same `api.py` rule. Slice 2 covers plugin registration.

**What about Rust extensions?** They are private to the module that owns them. The module's `api.py` re-exports the Python wrappers around the Rust extension. The boundary rule does not change for Rust. (The backend has no C++/Go code any more — see the language note at the top.)

**Why not microservices?** A microservice split costs roughly 10× what a module split costs and would solve a problem we don't have (multi-team scale, polyglot runtime, independent deploy). See ADR 0001 for the full reasoning.

**Why not an event bus now?** An event bus solves a problem we haven't measured yet. We may add one when there is evidence that direct calls have become a real coupling problem. See ADR 0004.

## Citations

The detailed citations live in [`docs/specs/fr-modular-monolith.md`](specs/fr-modular-monolith.md). Short list:

- Parnas 1972 — *On the Criteria To Be Used in Decomposing Systems into Modules.*
- Lehman 1980 — *Programs, Life Cycles, and Laws of Software Evolution.*
- Conway 1968 — *How Do Committees Invent?*
- Su 2024 — modular-monolith industry survey (cited in spec).
- US10700948B2; US8645233B2 — architectural fitness functions and module-dependency enforcement.
- ISO/IEC/IEEE 42010:2022 — architecture description.
- ISO/IEC/IEEE 29148:2018 — requirements engineering.
- Beck 2002 — *Test-Driven Development: By Example.*
- Percival & Gregory 2020 — *Architecture Patterns with Python.*
- Nygard — *Documenting Architecture Decisions* (ADR template).
- import-linter, Nx enforce-module-boundaries, grimp — tool documentation.
