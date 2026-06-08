# Migration Plan — Two-Language Backend: Python + Rust

[SPEC FRESHNESS: reviewed_at=2026-06-06 next_review=2026-06-30]

## 1. The decision (source of truth)

The backend uses **exactly two languages**:

- **Python** — the web app (Django), orchestration, and the machine-learning core
  (embeddings, ranking, vector search via `numpy` / `faiss` / `pgvector`).
- **Rust** — the performance-critical hot-path kernels, exposed to Python as native
  extension modules built with **PyO3 + maturin**.

**Removed entirely: C++, Go, Haskell.**

**Rust hot paths are authoritative — there is NO Python fallback or reference implementation.**
This reverses the old "C++ first, Python is the fallback and reference" policy
(`CPP-FIRST.md`). Each kernel has one implementation: Rust.

### Why this combination (sources)
- PyO3 is the standard Rust↔Python binding; maturin builds and packages the wheels.
  Sources: https://pyo3.rs , https://www.maturin.rs
- Production precedent for "Rust kernel under a Python API, no Python fallback":
  Polars (https://pola.rs), pydantic-core (https://github.com/pydantic/pydantic-core),
  HuggingFace `tokenizers` (https://github.com/huggingface/tokenizers).
- Rust and C++ are the same performance tier (both LLVM-optimised native code); Rust
  adds compile-time memory safety. So replacing C++ with Rust loses no speed and gains safety.

## 2. The "no Python fallback" rule (precise)

- **End state:** every hot-path kernel is Rust only. No `.py` reference copy, no
  "Python fallback path", no runtime language switch.
- **During each port (temporary only):** the existing C++/Python implementation is kept
  as a *parity oracle* — the Rust output is tested against it on real inputs. Once the
  Rust kernel passes parity + its own unit/property tests, **both the C++ and the Python
  copies are deleted in the same change.**
- **Safety net that replaces the fallback:** every Rust kernel ships thorough unit tests
  and property tests, and the Rust build is **mandatory** — CI fails loudly if Rust does
  not build (no silent degradation). A missing/broken Rust build is a hard error, not a
  quiet drop to Python.

## 3. What physically changes

### 3a. C++ kernels → Rust (24 kernels, `backend/extensions/*.cpp`)
Port each to a Rust crate exposed via PyO3, keeping the **same Python-callable API name**
so call sites do not change. Group order (safest first):

| Group | Kernels |
|---|---|
| Text / tokenisation | `texttok`, `linkparse`, `phrasematch`, `generic_anchor_matcher`, `rareterm` |
| Anchor analysis | `anchor_descriptiveness`, `anchor_diversity`, `anchor_self_information` |
| Sketches / probabilistic | `count_min_sketch`, `compressed_bloom`, `counting_bloom`, `l2norm` |
| Ranking / scoring | `scoring`, `pagerank`, `feedrerank`, `fieldrel` |
| Vector search (highest care) | `simsearch`, `ivf_index`, `quantemb`, `passagesim` |
| Infra | `api_rate_limiter`, `papertrail_dedup`, `lesson_index` |

### 3b. Services folded out of Go/Haskell (`services/`)
| Service | Today | Becomes |
|---|---|---|
| `streamd` | Go | Python Celery task / Django command |
| `startupd` | Go | Python (Django startup / management command) |
| `sidecars` | Go | Folded into the Django backend |
| `go` | Go | Folded into the Django backend |
| `findbugs-haskell` | Haskell | Dropped (or a small Python lint step) |
| `speccheck` | Rust | **Kept as Rust** (already the target language) |
| `clusterd` (Rust cluster-sig) | Rust/Go mix | Rust kernel (clustering) + Python glue |

### 3c. Tooling removed
- Mutation: `mull` (C++), `go-mutesting` (Go), `mucheck` (Haskell) — **removed**.
- Kept: `cargo-mutants` (Rust), `mutmut` (Python).
- The `compiled-tools` Docker image (C++/Go/Haskell) — **removed** (this is the 11 GB image).
- proto / Avro contracts and generated stubs — **removed** (no Go services).
- Rust kernels build via **maturin inside Docker** (reproducible, no host toolchain).

### 3d. Commit hooks removed / revised (of 75 total)
Remove: `check-cpp-lifecycle`, `check-go-service-contract`, `check-go-service-resource-budget`,
`check-rust-mandate` (revise → Rust-hot-path mandate), `check-stubs-not-regenerated`,
`check-native-inspection-window`, `check-native-observability-wired`,
`check-mint-first-build` (revise), `check-compiled-build` (revise → Rust build only).

### 3e. Docs to rewrite (the "update everything" list)
- `CPP-FIRST.md` → **`RUST-FIRST.md`** (Rust hot paths, no Python fallback).
- `CLAUDE.md` — replace the C++-first, Go-services-tier, native-runtime, and
  Python-fallback ABSOLUTE/PARAMOUNT rules with the Python+Rust rules.
- `AGENTS.md`, `docs/MODULAR-MONOLITH.md`, `COMPILED-LANGUAGE-RULES.md`,
  `docs/NATIVE_RUNTIME_POLICY.md`, the ADRs under `docs/adr/`, and every spec in
  `docs/specs/` that names C++/Go/Haskell or a Python fallback.
- **New ADR:** "Two-language backend (Python + Rust); C++/Go/Haskell removed; Rust hot
  paths authoritative with no Python fallback."

## 4. Phased execution (each phase leaves the app working and committable)

- **Phase 0 — Decide, document, and GUARD.** This plan + the new ADR + `RUST-FIRST.md`;
  update the `CLAUDE.md`/`AGENTS.md` headers so the policy is law before code moves. **Add
  the guard hook `check-removed-languages.py`** — a fail-closed commit hook that hard-blocks
  any staged `.cpp`/`.hpp`/`.h`, `.go`/`go.mod`/`services/<go>/`, or `.hs`/`.cabal` file, and
  any re-introduction of the `compiled-tools` image or `mull`/`go-mutesting`/`mucheck`. This
  is the real defense: ~230 existing plan/spec docs still mention C++/Go/Haskell, and no
  document can resurrect a language once a commit that adds it is refused. The stale docs are
  then cleanup (Phase 5), not a risk. The hook names the ADR in its failure message so a
  future agent following an old plan is redirected to the Python+Rust policy.
- **Phase 1 — Port C++ → Rust**, one kernel at a time, in the group order above. Each:
  add Rust crate (PyO3, same API) → parity-test against the old code → delete the C++ **and**
  the Python fallback → remove that kernel's C++ hooks. App stays green throughout.
- **Phase 2 — Fold Go services into Python**, one service at a time; delete each
  `services/<go>` folder and its hooks as it lands.
- **Phase 3 — Drop Haskell** (`findbugs-haskell`).
- **Phase 4 — Delete dead tooling**: `compiled-tools` image, `mull`/`go-mutesting`/`mucheck`,
  proto/Avro, the ~8 language hooks; shrink the gauntlet.
- **Phase 5 — Final doc sweep**: every remaining reference to C++/Go/Haskell/Python-fallback
  updated or removed; ADRs reconciled; `docs/CODE-COVERAGE-RULES.md` and the per-file hook
  threshold raised to 95% for both Python and Rust.
- **Phase 6 — Frontend: Apache ECharts for all GUI graphs.** Replace every `chart.js` and
  `d3` graph in the Angular frontend with Apache ECharts. Each chart honours the truthful-state
  rule: it renders real data, or it shows an explicit `empty` / `blocked` / `rebuild-required`
  / `access-denied` state — never a blank surface that implies "all clear." Every new chart
  route is registered in `frontend/src/app/core/routing/deep-link-catalog.ts`; every chart
  element gets a `peHelper` plain-English tooltip. Optuna study-progress charts are wired here
  too (see Phase 7).
- **Phase 7 — Optuna autotuner wiring.** Optuna 4.1.0 is already a dependency powering the
  weekly meta-HPO study (`backend/apps/pipeline/services/meta_hpo_eval.py`). Phase 7 completes
  the wiring so Optuna drives the ranking autotuner (`apps/suggestions/services/weight_tuner.py`)
  over **all** tunables and meta-algorithms registered in `suggestions/tunable_registry.py` and
  `suggestions/meta_registry.py` — new tunables plug in via the registry with no tuner-code
  change. This is **offline-only** (within `ranking_train`); Rust via `ranking_profiles` +
  `ranking_governance` validates and governs every activation — Optuna never promotes a profile.

## 5. Honest scope
This is a **weeks-long, repo-wide migration**, not a single change — but it is mostly
*deletion plus focused Rust ports*, and every phase is independently reviewable and
leaves a working app. Highest-risk items are the numerically-sensitive vector-search
kernels (`simsearch`, `ivf_index`, `quantemb`, `passagesim`): those keep their parity
oracle longest and get the most property tests before the old code is removed.

## Dead-code handling

The rule is simple: **dead code is deleted in the SAME step that replaces it — never
left alongside the replacement.** When a port lands or a language is dropped, the old
path leaves in the same commit as the new path. There is no "delete it later" phase, no
keep-it-just-in-case copy, and no commented-out body. Leaving the old code in place even
for one commit creates two live paths, hides which one runs, and lets the obsolete path
drift, break silently, or get re-imported by mistake.

What "dead code" means here, and exactly how each source is handled:

| Source of dead code | Handling |
|---|---|
| **Python fallback** (the reference implementation kept behind a Rust kernel) | Deleted in the **same commit the Rust kernel lands**. Once the Rust path is the only path, the Python fallback is removed — not gated behind a flag, not left as a "reference" copy. |
| **Removed-language source** (C++ `.cpp`/`.hpp`/`.h`, Go `.go`/`go.mod`/`services/<go>/`, Haskell `.hs`/`.cabal`, Lua) | Deleted **wholesale, not stubbed.** The whole file/folder goes; no empty placeholder, no "kept for history" shell is left behind. |
| **Orphans** — anything that only existed to serve the deleted code: now-unused imports, dead call sites, `except ImportError` fallback guards, dead commit hooks (e.g. `check-cpp-lifecycle`), dead tests, the `compiled-tools` image, and `mull`/`go-mutesting`/`mucheck` wiring | Removed in the **same change** that removes what they pointed at. An orphan left behind is dead code with a delayed failure. |
| **Existing dead code** — the ~112 parked C++ kernel names in `docs/CPP-ROADMAP.md` and the ~35 `Unimplemented` Go sidecar stubs | Deleted **outright.** These never carried a working implementation, so there is nothing to port and nothing to preserve. |

### Verification sweep per step

After each delete-and-replace step, prove no dead code or dangling reference survived by
running all three checks. The step is not done until every one is clean:

1. **`ruff`** — surfaces unused imports left behind by the deletion. Fail-on `F401`
   (imported-but-unused), which catches an `import <deleted module>` that no longer
   resolves to anything live.
2. **`vulture`** — reports unreferenced functions and classes, so any helper that only
   existed to feed the deleted path shows up as dead and gets removed too.
3. **A `grep` for the deleted symbol names returning zero callers** — search the whole
   tree for each removed module/function/class name; the expected result is **no
   matches** (zero remaining callers or imports). Any hit is a dangling reference that
   must be deleted or re-pointed in the same step. The `check-dead-code-on-replace`
   commit hook automates exactly this last check: it reads the modules a commit deletes
   and hard-blocks the commit if any surviving staged file still imports one of them.

## Repo organization (reference-safe only — "sensible, not spaghetti")

This repo is heavily path-coupled (the commit hooks, `ensure_compiled_artifacts.py`, Django
imports/migrations, the CI workflows, and the native-module registration all reference exact
paths), so file moves are done carefully — **a move is only valid if every reference to it is
updated in the same commit**. Three tiers:

- **Safe to remove / gitignore (junk):** `.slice4*.{json,txt,py}`, `.cov.json`, `docker_cleanup.log`,
  `luacov.stats.out` (Lua, removed anyway), `backend/scripts/autoissues_dump.json`, the stray
  root `test_coverage_discovery.py`; ensure generated dirs (`coverage-html/`, `.tmp/`) are gitignored.
- **Safe to move (verify refs first):** the 4 `SCROLL_HIGHLIGHT_*.md` → `docs/frontend/`; archive
  `Inspiration-Temp/`.
- **Move ONLY with atomic reference updates (Phase 5):** the ~20 root rule docs (`CITATION-RULE.md`,
  `NO-DUPLICATES.md`, `DEFAULT-ON-RULE.md`, …) → a `docs/rules/` folder, updating every
  `CLAUDE.md`/`AGENTS.md`/hook reference in the same commit (drops root from ~30 `.md` to a handful).
- **Must stay at root (do NOT move):** `CLAUDE.md`, `AGENTS.md`, `GEMINI.md`, `CODEX.md`,
  `AGENT-HANDOFF.md`, `AI-CONTEXT.md`, `docker-compose*.yml`, `pytest.ini`, `rust-toolchain.toml`,
  `sonar-project.properties`, the compose-mounted observability configs, and the scheduled-task
  `.bat`/`.ps1` scripts.

Much of the decluttering happens for free as the migration deletes `CPP-FIRST.md`,
`COMPILED-LANGUAGE-RULES.md`, `mull.yml`, the Lua configs, and folds `services/` into Python. The
dedicated organization pass runs in **Phase 5** (alongside the repo-wide reference sweep); the
junk cleanup runs once the in-flight kernel-port work lands (never mid-workflow on overlapping paths).

## Full-repo cleanup breakdown (E1 – E8)

These are the sub-tasks that make up Phase 4 and Phase 5. Each is independently committable.

**E1 — Dead-code handling (applies throughout every phase).**  
Delete dead code in the SAME step that replaces it — never leave old code alongside new. Sources and
handling: Python fallback deleted with its Rust port; removed-language source deleted wholesale;
orphans (unused imports, dead call sites, `except ImportError` guards, dead hooks, dead tests, the
`compiled-tools` image, mull/go-mutesting/mucheck wiring) removed in the same change. Existing dead
code (the ~112 parked C++ kernel names in `docs/CPP-ROADMAP.md`, the ~35 `Unimplemented` Go stubs)
deleted outright. Per-step sweep: `ruff` (F401), `vulture`, grep deleted symbol names = 0 callers;
backed by the TDD-tested `.githooks/check-dead-code-on-replace.py`.

**E2 — Disk reclamation (Phase 4).**  
Rebuild `compiled-tools` (≈11 GB today, holds C++/Go/Haskell + Rust toolchains) as a Rust-only image
(cargo, clippy, cargo-mutants, maturin) or fold Rust tooling into `backend-quality`. Drop C++/Go/Haskell
build layers and mull/go-mutesting/mucheck. Repeat on the Dell Docker context. Then compact the WSL VHDX
(needs a Docker restart) to return freed space to Windows. `backend-quality` (Python ruff/pytest) stays.

**E3 — Host-toolchain removal (Phase 4).**  
Remove Go SDK (`C:\Program Files\Go`), CMake, go-mutesting (`~/go/bin`), and any Mint/Dell
ghc/cabal/stack/g++/go installs. Keep Rust (cargo/rustc/clippy); add maturin inside the Docker image.
RISK: confirm Go/CMake are not used by other projects before removing from `Program Files`.

**E4 — AutoIssue + paper-trail retirement (Phase 4).**  
Add a TDD-tested management command that marks every OPEN AutoIssue and paper-trail entry tied to
C++/Go/Haskell/Lua kernels, parked C++ kernels, native observability (perfetto/gwp-asan),
compiled-build, go-service contracts, and mull/go-mutesting/mucheck as resolved/wontfix/stale with
`resolution_lessons` citing ADR 0007. Keep Rust and Python issues. Retire now-dead pickers/verifiers
and remove removed-language sources from the 30-pick + 10-paper-trail quota feeders.

**E5 — Blocking-gates overhaul (Phase 4).**  
Delete from `.githooks/` and un-wire from `scripts/precommit-docker.sh`: `check-compiled-build`,
`check-cpp-lifecycle`, `check-c-abi-conformance`, `check-go-service-contract`,
`check-go-service-resource-budget`, `check-luajit-dialect`, `check-lua-sandbox`,
`check-lua-test-isolation`, `check-native-observability-wired`, `check-native-inspection-window`,
`check-stubs-not-regenerated`. Revise: `check-language-ownership` → Python+Rust only;
`check-no-cross-language-import` → Python↔Rust boundary only; `check-scoped-mutation` /
`check-per-file-coverage` / `check-mutation-score` → Python+Rust only. Update
`config/mutation-routing.json` `languages{}` and `kill_rate_gates{}` to python+rust only.

**E6 — Repo-wide doc/config sweep (Phase 5).**  
Update every reference to C++/Go/Haskell/Lua/Python-fallback across `docs/`, `docs/specs/`,
`docs/adr/`, `CLAUDE.md`, `AGENTS.md`, `config/`, and the rule docs. Delete `CPP-FIRST.md`,
`COMPILED-LANGUAGE-RULES.md`, `docs/NATIVE_RUNTIME_POLICY.md`, `docs/CPP-ROADMAP.md`. Update
`docs/MODULAR-MONOLITH.md` (drop Go-services tier + C++ kernel lifecycle), the ADRs
(Go-services-tier ADR superseded), glossary, and `backend/extensions/CPP-RULES.md`.

**E7 — GitHub Actions update (Phase 5).**  
Collapse the CI multi-language matrix to Python + Rust only in `ci.yml` and
`ci-language-quality.yml`. Drop Go/Haskell/C++ build+test jobs; add Rust (`cargo test`,
`clippy -D warnings`, maturin wheel build). `scoped-mutation.yml` → `mutmut` + `cargo-mutants`
only. `codeql.yml` → keep Python; remove C++/Go/Java CodeQL languages. Wire the 95% coverage
gate (E8) into CI.

**E8 — Code coverage → 95% for Python and Rust (cross-cutting, Phase 5 finalises).**  
Raise the TARGET to 95% across `docs/CODE-COVERAGE-RULES.md`, `AI-CODING-GUIDELINES.md`, the
per-file hook threshold, `config/mutation-routing.json`, and CI. Add Rust coverage via
`cargo-llvm-cov` in the same per-file gate + CI. Raise ACTUAL coverage per module (Python
pytest+coverage, Rust cargo-llvm-cov) until both measure ≥95%. Use a per-module ratchet —
never flip the global threshold to 95% while a module is below it; raise each module's floor to
95% once it gets there so the repo stays committable throughout.
