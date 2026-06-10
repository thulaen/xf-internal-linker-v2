# RUST-FIRST.md — Rust Is The Default Compute Path

**Status:** PARAMOUNT. Every AI agent reads this before adding a new hot-path function or modifying an existing one.

[SPEC FRESHNESS: reviewed_at=2026-06-06 next_review=2026-06-30]

## The Rule

Rust extensions are the first-choice compute path for any function that runs more than once per ranker call, per-candidate scoring loop, or per-document import. Rust kernels are built as native Python extension modules via **PyO3 + maturin** through the Docker-managed build path — there is no host toolchain to install.

**Rust is AUTHORITATIVE. There is NO Python fallback and NO Python reference implementation.** This REVERSES the old `CPP-FIRST.md` policy that named Python the fallback and reference. Each kernel has exactly one implementation: Rust. The safety net that used to be "drop back to Python" is replaced by thorough Rust unit tests plus property tests, and by a build that fails loudly when Rust does not compile.

If a hot path is currently Python-only or C++-only, the next session that touches it must either:
1. Port it to a Rust extension following the pattern below (a Rust crate exposed via PyO3, keeping the same Python-callable API name so call sites do not change), OR
2. File a Report Registry entry explaining why the Rust port is impossible (for example, the algorithm needs a Python-only library at the boundary) AND prove via benchmark that the existing path runs under 5 ms per call.

The Python+Rust two-language decision is recorded in [`docs/adr/0007-python-rust-two-language.md`](docs/adr/0007-python-rust-two-language.md). The full migration sequence (port C++ → Rust kernel by kernel, then delete the old code) lives in [`docs/PYTHON-RUST-MIGRATION-PLAN.md`](docs/PYTHON-RUST-MIGRATION-PLAN.md).

## Rust Ownership Boundary — Nine Authoritative Responsibilities (BINDING)

[SPEC FRESHNESS: reviewed_at=2026-06-06 next_review=2026-06-30]

Rust is not only the hot-path compute path; it is the **authority** for a fixed set of nine
responsibilities. For each of these, Rust holds the single canonical implementation, Python may
prepare inputs and read results but **must not decide the outcome**, and the Python↔Rust boundary
carries typed, versioned data (PyO3 objects or schema'd DTOs) — never raw unversioned JSON for a
canonical ranking decision. Each responsibility maps to a §G ranking module
(see [`docs/PYTHON-RUST-MIGRATION-PLAN.md`](docs/PYTHON-RUST-MIGRATION-PLAN.md) §F/§G).

A change that puts any of these behaviours in Python (or that lets Python activate, promote,
roll back, or live-score without a Rust verdict) violates this rule. The source-backed spec is
[`docs/specs/fr-rust-ownership-boundary.md`](docs/specs/fr-rust-ownership-boundary.md).

| # | Responsibility | Plain-English meaning | Binding rule | §G module |
|---|---|---|---|---|
| 1 | **Deterministic validation** | The same inputs always produce the same pass/fail answer, on every machine. | Rust owns every validity check that must be reproducible. No floats-as-truth where bit-for-bit reproducibility is required; document the tolerance. Python must not re-implement the check "to be fast". | `ranking_evidence`, `ranking_governance` |
| 2 | **Hot-path retrieval** | Picking the candidate set to consider (Stage-1 search) for each request. | Rust executes the search-index query and candidate retrieval. After cutover there is **no Python/DB substring fallback** — a missing/stale index is a `rebuild-required` state, not a silent Python scan. | `search_index` |
| 3 | **Hot-path reranking** | Re-ordering the top candidates with the full scoring model. | Rust owns candidate fusion, top-N rerank, linear + additive-tree scoring, penalties, diversity, dedup suppression, and the final deterministic order. **No Python scoring fallback.** | `ranking_core` |
| 4 | **Feature normalization** | Turning raw signal values into the clean, bounded numbers the scorer expects. | Rust owns normalization, the missing-value policy, safe ranges, and vector validation. A missing feature follows the documented policy and is **reported**, never silently skipped or defaulted in Python. | `ranking_features` |
| 5 | **Score validation** | Checking that a computed score and its breakdown are well-formed and add up. | Rust validates the score breakdown (components sum to the total within tolerance, no NaN/inf, within declared bounds) before any score is shown or stored. | `ranking_core` |
| 6 | **Ranking validity checks** | Enforcing the rules a ranking profile must obey to be allowed. | Rust enforces never-zero weights, movement budgets, monotonicity/compatibility, and promotion eligibility. **Never-zero cannot be disabled.** No profile is valid without a Rust pass. | `ranking_profiles` |
| 7 | **Governance decision enforcement** | The final approve/block decision on a ranking change, with a reason. | Rust is the decision engine. Verdicts ∈ {approved, blocked, needs_work, inconclusive, expired, rollback_required} each with a reason code + plain-English text. Python records and displays the verdict; it does **not** make it. No activation/promotion/rollback without a Rust verdict + GUI approval. | `ranking_governance` |
| 8 | **Artifact validation** | Checking that an exported model/artifact is safe before it can be used. | Rust validates every artifact (shape, schema, version, hash, bounds) before it enters the candidate registry. Python may train/export offline; an unvalidated artifact **cannot** become a candidate. | `ranking_train` → validated by `ranking_profiles` |
| 9 | **Performance-sensitive compute** | The per-candidate / per-document math that runs in tight loops. | Rust owns all hot-path compute per the "Hot Path" definitions above (similarity, sketches, sorts, normalization loops, worker batch compute). Adding a hot path without a Rust kernel is forbidden. | `ranking_core`, `helper_workers` |

**The boundary, stated once:** Python may **train, compare, and report** candidate ranking
profiles offline (`ranking_train`, e.g. Optuna), but Python must **not activate, promote, roll
back, govern, or live-score** without Rust validation. Rust is the canonical authority for
production ranking validity. Python and Rust communicate only via typed DTOs / schemas / artifacts
and PyO3 extensions — **no raw unversioned JSON** for a canonical ranking decision. No first-party
language other than Python and Rust owns any of these nine responsibilities.

**Truthful states (no fake "all good"):** when a Rust-owned capability cannot run, the surface
shows the real state — `ready`, `empty`, `blocked`, `rebuild-required`, or `access-denied` — never
a blank/fake surface implying success. A missing Rust kernel is a loud diagnostics/health error
(see "Diagnostic Visibility" below), not a quiet Python copy.

## What Counts As A "Hot Path"

- Any function called inside `score_destination_matches` per candidate
- Any function called inside the candidate-retrieval Stage 1 per host
- Any function in the Celery embedding loop
- Any function in `text_cleaner.py` regex chain (called per imported post)
- Any cosine / Euclidean / Jaccard / KL / JSD / similarity computation
- Any sort / partial-sort / heap operation over more than 100 items
- Any sketch (MinHash / Bloom / HyperLogLog / Count-Min) build or query

## What Does NOT Count

- Settings reads (Postgres latency dominates)
- Dashboard aggregates (called once per page render)
- Celery task orchestration (one call per beat tick)
- Migration data backfills (one-shot, not on hot path)
- Model loading (cached after first import)

## Porting Discipline — Zero-Fallback

When you port a kernel from the old C++/Python world to Rust, you are not allowed to leave two implementations behind. The discipline is:

1. **Keep the old C++/Python only as a TEMPORARY parity oracle.** While the port is in progress, the existing implementation stays in the tree so the Rust output can be checked against it on real inputs.
2. **Test the Rust kernel against that oracle** plus its own Rust unit tests and property tests until it passes.
3. **Delete BOTH the C++ source AND the Python fallback in the SAME commit** that lands the proven Rust kernel. There is no "remove the old code next session" step — the port commit is the deletion commit. This is the zero-fallback rule: when the port lands, exactly one implementation (Rust) survives.

The numerically-sensitive vector-search kernels (`simsearch`, `ivf_index`, `quantemb`, `passagesim`) keep their parity oracle the longest and get the most property tests before the old code is removed.

## Dead-Code-On-Replace

When a kernel is replaced, the same change that adds the Rust kernel also deletes everything the old kernel left behind:

- the old C++ / Python source for that kernel,
- the Python fallback path,
- every import of the old kernel,
- every call site that referenced the old name (call sites keep the same API name, so this is a no-op when done right — but any leftover compatibility shim is removed),
- the now-dead tests that only existed to exercise the removed code.

A missing or broken Rust build is a **LOUD hard error** surfaced to diagnostics and the System Health page — never a silent drop to Python. CI fails loudly when the Rust build does not compile. There is no runtime language switch and no quiet degradation path: if Rust is not there, the system reports it as broken rather than pretending to work on a slower Python copy.

## Pattern To Follow

A Rust kernel is a crate built into a Python extension module by maturin, called from Python under the **same API name** the old kernel used. The shape is:

1. **Rust crate** under the extensions tree with a `Cargo.toml` and a `lib.rs` (or a module per kernel). The core compute function is plain Rust that takes slices / raw buffers (`&[f32]`, `&[u8]`, `usize`) so it can be benchmarked directly with Criterion without going through Python.
2. **PyO3 wrapper** (`#[pyfunction]` / `#[pymodule]`) that exposes the core function to Python under the same callable name the old C++/Python kernel used, so import sites and call sites do not change.
3. **Rust unit tests** (`#[cfg(test)]`) — three or more parity tests against a hand-computed expected value. These replace the old Google Test cases.
4. **Property tests** (`proptest` / `quickcheck`) — generate random inputs and assert invariants. These are the safety net that replaces the Python fallback.
5. **Criterion benchmark** under the crate's `benches/` — three input sizes per the Mandatory Benchmark Rule. These replace the old Google Benchmark cases.
6. **maturin build registration** so the Docker-managed build compiles and installs the wheel. No host `cargo` / `rustc` is required or allowed — the toolchain lives in the Docker build image.
7. **Diagnostic surfacing.** The consumer reports the kernel's load state to the System Health page. An import or load failure is a hard error, logged via `ingest_error()`, not a quiet fallback.

## Performance Floors

| Kernel class | Required speedup vs the previous implementation |
|---|---|
| Mission-critical hot path (passagesim, scoring) | ≥10× |
| Standard hot path (quantemb, ivf_index, pagerank) | ≥3× |
| Build-time / offline (codebook training) | ≥2× |

Rust and C++ are the same performance tier — both compile to LLVM-optimised native code — so a Rust port loses no speed versus the C++ it replaces and gains compile-time memory safety. If your benchmark misses the floor, file a Report Registry entry and ask before merging.

## Diagnostic Visibility

Every hot path that has a Rust kernel surfaces its activation status on `/diagnostics` via the `native_scoring` ServiceStatusSnapshot:

- `runtime_path`: `rust` (live) | `error` (kernel failed to load)
- `kernel_loaded`: bool
- `load_error`: short string when the kernel did not load
- `benchmark_status`: `green` (within floor) | `yellow` (off floor) | `red` (regressed >2×)

There is no `python` value for `runtime_path` — the system never silently runs a Python copy. If the operator sees `runtime_path: error` for a kernel, the Rust extension either failed to build or the compiled module is missing, and the Docker-managed maturin rebuild fixes it. A broken build is a visible, loud failure, not a degraded mode.

## Tooling languages — Rust CLI + Python (ADR 0008)

Repo tooling (CI checks, log forensics, old-data cleanup, validators, auditors) is **Rust + Python
only — no third language, no Perl.** Durable cross-platform CLI tooling is a single Rust multi-tool
binary (`xftool`) whose subcommands are **thin front-ends over the existing app crates** (reuse, not
reimplement); anything needing Django/Postgres state is a Python management command. `ripgrep`, `jq`,
`DuckDB`, and `Polars` are invoked utilities/libraries (not first-party languages) and may be used
freely. PowerShell is retired from cross-platform logic (kept only for Windows-host ops like Docker
Desktop / WSL / the Dell-Mint `.ps1` helpers). Tooling is **not** app architecture: `xftool` lives in
`rust/tools/`, the app never imports it. See [`docs/adr/0008-tooling-languages-rust-cli-python.md`](docs/adr/0008-tooling-languages-rust-cli-python.md)
and the framework + catalog in [`docs/specs/fr-rust-cli-tooling.md`](docs/specs/fr-rust-cli-tooling.md).

## Forbidden Patterns

- ❌ Adding a hot-path function without a Rust kernel ("we'll port it later" never happens)
- ❌ Adding a third tooling language (Perl, etc.) — tooling is Rust CLI + Python only (ADR 0008)
- ❌ Keeping a Python fallback or Python reference copy of a kernel after its Rust port has landed
- ❌ Leaving the old C++ source in the tree after the Rust kernel that replaces it is proven
- ❌ Replacing a working Rust kernel with a numpy/scipy call to "simplify"
- ❌ Silently dropping to Python when the Rust build is missing or broken — that must be a loud diagnostics/health error
- ❌ Adding a Rust crate with no parity unit tests, no property tests, or no Criterion benchmark
- ❌ Installing or relying on a host `cargo`/`rustc` toolchain — builds go through the Docker-managed maturin path

## Forward-Thinking Note

The user has an i5-12450H today and may upgrade to a workstation-class CPU later. Rust compiles through LLVM with `target-cpu=native`, so the extensions automatically pick up AVX-512 / VNNI / AMX instructions on the new chip without code changes — the same upgrade payoff the C++ kernels gave, now with compile-time memory safety on top. Because there is no Python fallback, every hot path is Rust on every machine: the slow-path perf cliff the old fallback created is gone for good.
