# FR — Rust Ownership Boundary (Nine Authoritative Responsibilities)

[SPEC FRESHNESS: reviewed_at=2026-06-06 next_review=2026-06-30]
[SPEC CITED: feature=rust-ownership-boundary kind=technical_doc id=ISO/IEC/IEEE-42010:2022 verified_at=2026-06-06]

## Status

PARAMOUNT, BINDING. Defines which production responsibilities Rust owns as the canonical
authority under the Python + Rust two-language model. Companion to
[`../adr/0007-python-rust-two-language.md`](../adr/0007-python-rust-two-language.md),
[`../../RUST-FIRST.md`](../../RUST-FIRST.md), and
[`../PYTHON-RUST-MIGRATION-PLAN.md`](../PYTHON-RUST-MIGRATION-PLAN.md) §F/§G.

## Problem

The backend is migrating to Python + Rust only. "Rust owns the hot paths" is necessary but not
sufficient: correctness-critical decisions (ranking validity, governance verdicts, score and
artifact validation) must also have a single, reproducible, authoritative owner. If those decisions
can be made — or silently re-implemented — in Python, the system loses its single source of truth,
can drift between a Python and a Rust answer, and can activate an unvalidated ranking change. This
spec fixes the boundary so the answer to "who decides?" is unambiguous for nine named
responsibilities.

## Source of truth (citations)

- **Module decomposition / information hiding** — D. L. Parnas, "On the Criteria To Be Used in
  Decomposing Systems into Modules," CACM 15(12):1053–1058, 1972. doi:10.1145/361598.361623. Each
  responsibility is hidden behind one module's public surface; cross-module access is via that
  surface only.
- **Architecture description** — ISO/IEC/IEEE 42010:2022, *Software, systems and enterprise —
  Architecture description.* The ownership table is an architecture decision with explicit
  concerns (correctness, reproducibility, governance) and rationale.
- **Language-boundary mechanism** — PyO3 user guide, <https://pyo3.rs/> (typed Python↔Rust
  objects, `#[pyclass]`/`#[pyfunction]`/`#[pymodule]`), and maturin, <https://www.maturin.rs/>
  (Docker-managed extension build). The boundary carries typed objects, not raw JSON.
- **Deterministic floating-point validation** — IEEE 754-2019, *IEEE Standard for Floating-Point
  Arithmetic.* Where bit-for-bit reproducibility is required, the validation pins operation order
  and a documented absolute/relative tolerance rather than relying on platform-default float
  behaviour.
- **Memory-safe authority layer** — *The Rust Reference*, <https://doc.rust-lang.org/reference/>
  (`unsafe` is forbidden workspace-wide in `rust/Cargo.toml`), so the authority layer cannot carry
  the memory-safety defects the removed C++ could.

## Behaviour (Given / When / Then)

Given the production ranking pipeline runs under the Python + Rust two-language model,
When any of the nine responsibilities below must produce an outcome,
Then the outcome is produced by the single canonical Rust implementation, Python only prepares
inputs and reads results, and the Python↔Rust boundary carries typed/versioned data.

Given Python has trained or exported a candidate ranking profile or model artifact offline,
When that candidate is proposed for activation, promotion, rollback, or live scoring,
Then it does not take effect until Rust returns an `approved` governance verdict AND the GUI
approval workflow records sign-off; Python alone cannot activate it.

Given a Rust-owned capability cannot run (kernel missing, index stale, artifact invalid),
When the corresponding surface renders,
Then it shows a truthful state (`ready` | `empty` | `blocked` | `rebuild-required` |
`access-denied`) and a loud diagnostics/health error — never a blank/fake "all good" surface and
never a silent drop to a Python copy.

## The nine responsibilities

1. **Deterministic validation** — reproducible pass/fail checks (`ranking_evidence`,
   `ranking_governance`). Pin op order + tolerance per IEEE 754; no Python re-implementation.
2. **Hot-path retrieval** — Stage-1 candidate search (`search_index`). No Python/DB fallback after
   cutover; missing index ⇒ `rebuild-required`.
3. **Hot-path reranking** — fusion, top-N rerank, linear + additive-tree scoring, penalties,
   diversity, dedup, final order (`ranking_core`). No Python scoring fallback.
4. **Feature normalization** — normalization, missing-value policy, safe ranges, vector validation
   (`ranking_features`). Missing feature is reported, never silently skipped.
5. **Score validation** — score-breakdown integrity: components sum to total within tolerance, no
   NaN/inf, within bounds (`ranking_core`) before display/store.
6. **Ranking validity checks** — never-zero weights (cannot be disabled), movement budgets,
   monotonicity/compatibility, promotion eligibility (`ranking_profiles`).
7. **Governance decision enforcement** — verdicts ∈ {approved, blocked, needs_work, inconclusive,
   expired, rollback_required} with reason code + plain-English text (`ranking_governance`). Python
   records/displays; it does not decide.
8. **Artifact validation** — shape/schema/version/hash/bounds checks before an artifact enters the
   candidate registry (`ranking_train` → `ranking_profiles`). Unvalidated artifact cannot become a
   candidate.
9. **Performance-sensitive compute** — per-candidate / per-document hot-path math: similarity,
   sketches, sorts, normalization loops, worker batch compute (`ranking_core`, `helper_workers`).

## Boundary contract

Python may train, compare, and report candidate profiles offline (`ranking_train`); Python must not
activate, promote, roll back, govern, or live-score without a Rust verdict. Rust is the canonical
authority for production ranking validity. Communication is via typed DTOs / schemas / artifacts and
PyO3 extensions — no raw unversioned JSON for a canonical ranking decision. No first-party language
other than Python and Rust owns any of the nine responsibilities.

## Enforcement (planned)

- `RUST-FIRST.md` carries the binding ownership table (landed 2026-06-06).
- A future `.githooks/check-language-ownership.py` revision (E5) asserts no Python module under the
  eight `ranking_*` / `helper_workers` modules implements a responsibility the table assigns to Rust
  (heuristic: forbidden function-name patterns + a per-module allowlist), and that the boundary
  modules expose only typed DTOs.
- CI (E7) runs `cargo test` + `clippy -D warnings` on the authority crates so the Rust owner is
  always built and tested.

## Glossary

- **Authority / canonical owner** — the single code path whose answer is the truth; others may read
  it but not recompute it.
- **Governance verdict** — Rust's machine-checked approve/block decision on a ranking change.
- **Never-zero** — the rule that no live ranking weight may be exactly zero (kills a signal
  silently); enforced in Rust and not disableable.
- **Rebuild-required** — a truthful UI/health state meaning a derived store (e.g. the search index)
  is missing or stale and must be rebuilt before the feature works; not an error and not a fake
  "all good".
