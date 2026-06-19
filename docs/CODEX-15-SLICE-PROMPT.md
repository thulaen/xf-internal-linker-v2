# Codex Execution Prompt — Finish the Python + Rust Migration in 15 Slices

Historical note: this document describes the retired MSI Docker-era workflow. Current MSI commands must use Kubernetes, `python scripts/backend_manage.py`, or SSH to Dell/Mint helpers.

> **Paste this whole file to Codex as its task.** It is the single source of truth for the
> remaining migration work. Work **one slice at a time, in order, each as its own commit.** Stop
> and report after every slice. Do not start the next slice until the current one is committed.

---

## 0. Mission & current state

**Mission:** finish migrating the backend from a 5-language polyglot (Python + C++ + Go + Haskell +
Lua) to **Python + Rust ONLY**. Rust owns the performance hot paths *and* the correctness authority,
exposed to Python via **PyO3 + maturin/cargo**, with **no Python fallback**.

**Already done (do not redo):**
- Phase 0 guard rails authored: ADR 0007, `RUST-FIRST.md` (incl. the **Nine Authoritative
  Responsibilities** table), `docs/PYTHON-RUST-MIGRATION-PLAN.md`, `docs/specs/fr-rust-ownership-boundary.md`,
  the guard hooks `check-removed-languages.py` + `check-dead-code-on-replace.py`, the MSI build guard
  `.claude/hooks/block-msi-build-test.py`, the Dell build helper `scripts/dell-rust.sh`, and the
  `CLAUDE.md`/`AGENTS.md`/`CODEX.md`/`GEMINI.md` rule headers. (These may still be uncommitted — that
  is **Slice 1**.)
- **5 kernels are fully DONE** — Rust crate landed in `rust/extensions/<k>/`, C++ source + header +
  fuzz harness deleted, the shared C++ bench files (`bench_streaming_sketches.cpp`,
  `bench_anchor_garbage.cpp`) deleted, and the name moved into `RUST_EXTENSION_NAMES` (out of the C++
  `EXTENSION_NAMES`) in `scripts/ensure_compiled_artifacts.py`: **`l2norm`**, **`count_min_sketch`**,
  **`counting_bloom`**, **`compressed_bloom`**, **`anchor_self_information`**. Do NOT re-port these — Slice 2
  is verify-only for the sketch/bloom ones and Slice 3 skips `anchor_self_information`.
- **18 kernels REMAIN** (C++ still present under `backend/extensions/`): `anchor_descriptiveness`,
  `anchor_diversity`, `api_rate_limiter`, `feedrerank`, `fieldrel`, `generic_anchor_matcher`,
  `ivf_index`, `lesson_index`, `linkparse`, `pagerank`, `papertrail_dedup`, `passagesim`,
  `phrasematch`, `quantemb`, `rareterm`, `scoring`, `simsearch`, `texttok`. These are the §6 caveat
  table and Slices 3–9.
- A separate (non-slice) feature already landed by another agent: a GlitchTip *slowest-performance*
  → AutoIssue picker (`backend/apps/auto_issues/services/glitchtip_perf_picker.py` + test). Leave it.

**Read before writing anything:** `docs/PYTHON-RUST-MIGRATION-PLAN.md`,
`docs/adr/0007-python-rust-two-language.md`, `RUST-FIRST.md`, `docs/specs/fr-rust-ownership-boundary.md`,
`CLAUDE.md`, `AGENTS.md`, and the latest entry in `AGENT-HANDOFF.md`.

---

## 1. Absolute rules — violating any one is a protocol failure

1. **Python + Rust ONLY.** Never add or modify a `.cpp/.cc/.cxx/.c/.cu/.h/.hpp/.hh/.go/.proto/.hs/.lhs/.cabal/.lua/.java` file — you may only **delete** them. `.githooks/check-removed-languages.py` hard-blocks additions/edits (deletions are allowed via `--diff-filter=ACM`).
2. **Zero-fallback, single commit (RUST-FIRST.md).** When you port a kernel you must, in the **same commit**: (a) land the proven Rust crate, (b) delete the C++ source + header + fuzz + dedicated bench, (c) delete the Python fallback, (d) refactor every call site to call the Rust module directly. A missing Rust kernel is a **LOUD diagnostics/health error**, never a silent drop to Python. No "remove the old code next session."
3. **Contract parity, not byte parity.** Most kernels used `std::hash`/platform floats and have few or zero callers, so exact C++ output is neither reproducible nor required. Honour the **`behavioural_contract`** in `backend/tmp/port-specs/<kernel>.json`. Reproduce **exact** values only when that spec's `parity_basis == "exact"` (then assert exact equality, e.g. against the documented algorithm or the pure-Python oracle while it still exists).
4. **Builds / tests / compiles run on DELL, never on MSI.** MSI (this Windows host) is weight `0.0`, **fail-closed**; its `compiled-tools` image was removed, and `.claude/hooks/block-msi-build-test.py` hard-errors any local `cargo` / `pytest` / `python -m pytest` / `manage.py test` / `docker compose run|exec backend-quality|compiled-tools` / `npm build|test` / `cmake` / `make` / `maturin` / `go build|test`. Use the Dell commands in §2.
5. **`bash` is broken here — it resolves to WSL bash** (`/c/Windows/system32/bash`, no distro). **Always** invoke scripts with Git Bash explicitly: `/usr/bin/bash scripts/<x>.sh ...`. Never `bash scripts/<x>.sh`.
6. **Never** run `docker compose down -v`, `docker volume rm`, `docker volume prune`, `docker system prune` (a hook blocks the last one), or `--no-verify`. **Never** `manage.py changepassword` / `set_password` on any user except `playwright-local`. **Never** remove or gate the `glitchtip` / `glitchtip-worker` / `glitchtip-init` services.
7. **Do NOT restart Docker or WSL.** New 10 GB-RAM / all-logical-processor limits are written to `.wslconfig` on both machines and the user has **explicitly paused** the restart. Leave Docker/WSL alone.
8. **TDD always — Red → Green → Refactor.** Test first (observe FAIL), minimum code (observe PASS), refactor while green. Test code is held to the same standard as production code.
9. **Plain English** in every chat reply, commit message, and `AGENT-HANDOFF.md` entry (`PLAIN-ENGLISH-RULE.md`): no jargon/acronyms without definition, no analogies, no metaphors. Three parts: what you did, what now works, what broke.
10. **One slice = one commit**, landed clean through the full pre-commit gauntlet (no `--no-verify`). The repo stays green and committable after every slice.
11. **Observability stack stays up** (`sonarqube`, `glitchtip*`, `pyroscope`, `otel-collector`, `vmsingle/vmagent/vmalert`, `loki`, `alloy`, `tempo`, `grafana`, `postgres-exporter`). Sonar + Pyroscope run on Dell; the rest on MSI. Don't stop any to dodge a hook.

---

## 2. The commands you MUST use (Dell, not MSI)

| Need | Command (from repo root, in Git Bash) |
|---|---|
| Session-start payload | `python scripts/session_start_payload.py` |
| Build a Rust kernel | `/usr/bin/bash scripts/dell-rust.sh build -p <kernel>` |
| Test a Rust kernel | `/usr/bin/bash scripts/dell-rust.sh test -p <kernel>` |
| Clippy (gate is `-D warnings`, pedantic) | `/usr/bin/bash scripts/dell-rust.sh clippy -p <kernel> --all-targets -- -D warnings` |
| Format check | `/usr/bin/bash scripts/dell-rust.sh fmt --check` |
| Whole-workspace test | `/usr/bin/bash scripts/dell-rust.sh test --workspace` |
| **Rust mutation gate** (>=75% kill) | `python scripts/bazel_default.py run //tools/quality:mutation` |
| Rust coverage (ratchet → 95%) | `/usr/bin/bash scripts/run-rust-coverage.sh` is wrapped by the Dell shard; for ad-hoc use `/usr/bin/bash scripts/dell-rust.sh llvm-cov -p <kernel>` |
| **Python tests on Dell** | `XF_PYTEST_SPLIT=1 python scripts/run_pytest_on_context.py <pytest-args>` (Dell's own `xf_dell_test` Postgres/Redis) |
| Guard gate: removed languages | `python .githooks/check-removed-languages.py` |
| Guard gate: dead-code-on-replace | `python .githooks/check-dead-code-on-replace.py` |
| Runtime mgmt command (allowed on MSI) | `docker compose exec -T backend python manage.py <non-test command>` |
| Docker image build (rare) | `& scripts/build-smart.ps1 --target <service>` or `python scripts/smart_build.py --target <service>` |

Notes:
- `scripts/dell-rust.sh` syncs `rust/` to the Dell `xf_dell_compiled_repo` volume each call (build
  output excluded) and runs cargo in Dell's `xf-linker-compiled-tools` image, reusing the shared
  `compiled_artifacts` store and the persistent cargo/llvm cache. It **fails closed** if Dell is
  unreachable — start Docker Desktop on Dell, then retry. Set `XF_DELL_RUST_NO_SYNC=1` to reuse the
  last sync (only when you have not edited `rust/` since).
- Pre-computed **kernel port specs:** `backend/tmp/port-specs/<kernel>.json`. **Read the spec FIRST.**
  Fields: `public_api`, `kind` (`class` | `functions` | `mixed`), `needs_numpy` (bool),
  `behavioural_contract`, `parity_basis` (`exact` | `contract`), `python_callers` (list),
  `python_fallback_path` (path | `"none"`), `cpp_files_to_delete` (list), `bench_file` (shared file +
  lines to edit | `"none"`), `registry_refs` (exact edits).
- Reference ports to copy: `rust/extensions/l2norm/` (free functions + numpy) and
  `rust/extensions/count_min_sketch/` (a `#[pyclass]`).

---

## 3. The per-slice loop (run this EXACTLY for every slice)

**(a) Session start.** `python scripts/session_start_payload.py`, read the latest `AGENT-HANDOFF.md`
entry, and emit these markers in order at the top of your handoff entry:
`[HANDOFF READ: ...]` → `[TDD PREFLIGHT: ...]` → `[STICKY 1 READ: ...]` → `[REGISTRY READ: ...]` →
`[GUIDELINES READ: ...]` → `[PAPER TRAIL READ: ...]` → `[SNAPSHOTS READ: ...]` →
`[LESSONS BEFORE START: ...]` → `[QUALITY GATE READ: ...]` → `[GH ACTIONS READ: ...]`.
Use `--session-type reconciliation` to drop the AutoIssue quota from 30 to 10 when the slice is not a
fresh feature.

**(b) Resolve the quota BEFORE the slice work.** Fix the picked AutoIssues (30, or 10 in
reconciliation) and the 10 picked paper-trail entries, each with a two-part
`Trap: ... Fix shape: ...` lesson via the management commands. The commit is hard-blocked until the
live database proves they are resolved after the previous handoff timestamp.

**(c) BDD plan.** Write the slice behaviour as `Given / When / Then` before any code. Search resolved
history for the touched area: `docker compose exec -T backend python manage.py search_resolved_issues --area <path>` and `... read_scoped_lessons --area <path>`.

**(d) Do the slice work, TDD.** Author Rust on MSI (file writes only); build/test/clippy on **Dell**.
For kernels, the **Rust `#[cfg(test)]` contract tests are the gate** (they run on Dell via cargo test).
For Python changes, the TDD test runs on **Dell** via `run_pytest_on_context.py`.

**(e) Per-touched-production-file markers** (one set per file) — emit these EXACT forms:

```
[TDD CYCLE STRICT: file=<src> red=<test>:<line> red_run_at=<ISO8601> red_result=FAIL green=<src>:<line> green_run_at=<ISO8601> green_result=PASS refactor="<summary or none>" lesson_autoissue=#<N>]
[TDD COVERAGE: file=<src> edge_cases=<N>|N/A:"<≥20-char reason>" resource_release=<N>|N/A:"..." latency=<N>|N/A:"..." smoke=<N>|N/A:"..." e2e=<N>|N/A:"..."]
[TDD CYCLE: file=<src> red=<test>:<line> green=<src>:<line> refactor="ruff_clean=true; cyclomatic_delta=<+/-N>; dup_lines_delta=<+/-M>"]
[TEST CASE MAPPING: file=<src> test_cases=#<idA>,#<idB>]
```

Plus once per commit:

```
[CODE REVIEW LESSONS: <N> logged from <M> files; deduped <K> against prior]
[CODE REVIEW AGENTS: codex=done logged=#<...>]
[SPEC PROOF: specs=<paths> source_types=<patent|academic_paper|technical_doc|standard> checked_at=<YYYY-MM-DD> status=<current|updated>]
[BDD PROOF: Given ... When ... Then ...]
[TDD PROOF: before_or_alongside=yes tests="<commands>" result=passed]
[SPEC CODE REVIEW: specs=<paths> result=<matched|updated>]
```

Per touched **function** (Rule A) — a real perf proof, or a substantive exemption:

```
[PERFORMANCE PROOF: function=<fn> baseline_ns=X post_ns=Y speedup=Z.ZZx iterations=N/10]
[PERFORMANCE EXEMPTION: function=<fn> best_achieved=X.YYx iterations=N/10 reason="<I/O-bound|algorithmically-optimal|hardware-bound|already-vectorised|...>"]
[PROFILING PROOF: service=<name> scope=<paths> source=pyroscope+otel_profiles hotspots=<0-5> baseline=<link-or-command> decision=<optimized|not-relevant|not-achievable|autoissue-filed>]
```

**(f) Zero-fallback wiring (kernel slices).** Delete the C++ + Python fallback, refactor callers, then
prove the guards pass: `python .githooks/check-removed-languages.py` and
`python .githooks/check-dead-code-on-replace.py` (both must exit 0).

**(g) Commit through the full gauntlet.** Never `--no-verify`. Each hook prints a three-part FAIL
(what / why / unblock); fix the root cause and re-run. Auto-iterate until the chain passes. Run the
**Bazel mutation gate on Dell** (`python scripts/bazel_default.py run //tools/quality:mutation`) and record
`turbo=used`.

**(h) Close the handoff entry** with:

```
[QUALITY GATE RESULT: guidelines=passed tests=passed coverage=met mutation=passed check_setup=passed]
[COVERAGE SUMMARY: target=<X>% actual=<Y>% — met / not met]
turbo=used    (or turbo=blocked:<plain reason>)
Tech-debt delta: <items resolved this slice>
```

**(i) Stop and report** in plain English. Wait for "next slice" unless told to continue.

---

## 4. The commit gauntlet — order & what each gate wants

`scripts/precommit-docker.sh` runs ~50 hard-block hooks. The early, most common ones:
`check-tdd-preflight` (the `[TDD PREFLIGHT]` marker) → `check-tdd-cycle` (`[TDD CYCLE]` per file) →
`check-tdd-strict` (`[TDD CYCLE STRICT]` + `[TDD COVERAGE]`, with `red_result=FAIL` before
`green_result=PASS` and `red_run_at < green_run_at`, plus a real `tdd_lesson` AutoIssue) →
`check-test-case-mandate` (`[TEST CASE MAPPING]` + a `test_case` AutoIssue with Given/When/Then) →
`check-lessons-read-at-session-start` → `check-snapshotd-ritual` → `check-code-review-lessons`
(`[CODE REVIEW LESSONS]`, `N + K ≥ M` files) → `check-registry-read` (30/10 AutoIssues resolved in DB)
→ `check-paper-trail-read` (10 paper-trail resolved) → `check-paper-trail-evidence` →
`check-perf-proof` (`[PERFORMANCE PROOF/EXEMPTION]`) → `check-profiling-proof` → `check-spec-citation`
→ `check-removed-languages` → `check-dead-code-on-replace` → `check-observability-stack` →
`check-glossary` → quality gates (`check-rust-mandate`, `check-per-file-coverage`,
`check-scoped-mutation`, `turbo-tests`). Generated stubs and pure-docs commits are exempt from the
TDD chain. If Docker or the backend DB cannot be reached, the commit MUST fail — do not skip.

---

## 5. Anatomy of a kernel port (worked procedure — follow for Slices 2–9)

For kernel `<k>` (read `backend/tmp/port-specs/<k>.json` first):

**1. Create the crate `rust/extensions/<k>/`** mirroring `count_min_sketch` (class) or `l2norm`
(functions). `Cargo.toml`:

```toml
[package]
name = "<k>"
version.workspace = true            # plus edition/rust-version/license/repository/readme/keywords/categories/description via .workspace = true
description = "<one line>"

[lib]
name = "<k>"                         # MUST equal the #[pymodule] fn name and the Python import name
crate-type = ["cdylib", "rlib"]     # cdylib = the importable .so; rlib = cargo test/bench reach the pure core

[dependencies]
pyo3 = { version = "0.26", features = ["abi3-py310", "extension-module"] }
# numpy = { version = "0.26" }      # ONLY if spec.needs_numpy == true

[dev-dependencies]
criterion = "0.5"

[[bench]]
name = "bench_<k>"
harness = false

[lints]
workspace = true                    # unsafe_code = forbid; clippy all/pedantic/nursery/cargo = warn
```

Also add `pyproject.toml` (maturin backend, module name `<k>`), `README.md` (one paragraph: purpose,
ships as `<k>.so` imported as `extensions.<k>`, pointers to the plan + RUST-FIRST), and
`benches/bench_<k>.rs` (criterion, 3 input sizes — the Mandatory Benchmark Rule).

**2. `src/lib.rs` shape:**
- a **pure-Rust core** (no PyO3) holding ALL logic over native types, unit-testable without Python;
- thin `#[pyfunction]` / `#[pyclass]`+`#[pymethods]` wrappers exposing the **exact** `public_api`
  (same names, arg names, defaults, return types, exceptions → `ValueError`/`RuntimeError`);
- a `#[pymodule] fn <k>(...)` registering the surface (name == `[lib] name`);
- a `#[cfg(test)] mod tests` that asserts the `behavioural_contract` with **standalone expectations**
  (invariants + hand-computed exact values) **and boundary mutants** (strict-vs-nonstrict comparisons,
  min-vs-max, off-by-one) so cargo-mutants kills them. `unsafe` is forbidden.

**3. Register for the Dell build (file edits on MSI):**
- add `"extensions/<k>"` to `members` in `rust/Cargo.toml`;
- in `scripts/ensure_compiled_artifacts.py`: **add** `"<k>"` to `RUST_EXTENSION_NAMES`, **remove**
  it from the C++ `EXTENSION_NAMES`, **and add** a `"<k>": "<one public attr>"` entry to
  `RUST_EXTENSION_EXPECTED_ATTRS` (the build/import check loads the `.so` and asserts this attribute is
  present — e.g. `l2norm: normalize_l2_batch`, `count_min_sketch: CountMinSketch`);
- in `backend/extensions/setup.py`: delete the `Pybind11Extension("<k>", ["<k>.cpp"], ...)` entry
  (leave a one-line NOTE);
- leave `backend/apps/diagnostics/health.py` `_NATIVE_RUNTIME_MODULES` `<k>` entry **unchanged**
  (the Rust module still exposes the same attribute; the bare `<k>.so` vs `.cpython-*.so` is how
  health.py labels the runtime path "rust" vs "cpp").

**4. Build + test + clippy on Dell, iterate to green:**
```
/usr/bin/bash scripts/dell-rust.sh fmt --check
/usr/bin/bash scripts/dell-rust.sh clippy -p <k> --all-targets -- -D warnings
/usr/bin/bash scripts/dell-rust.sh test -p <k>
```

**5. Self-verify (adversarial):** re-read `src/lib.rs` vs the C++ and the spec — can any input violate
the contract (under-count, false negative, wrong reduction, off-by-one)? Are all public names +
signatures + exceptions present? Is `<k>` in `RUST_EXTENSION_NAMES` and out of `EXTENSION_NAMES`?

**6. Zero-fallback wiring (same commit):**
- `git rm` the paths in `spec.cpp_files_to_delete` (`.cpp`, header, fuzz). **Confirm each path still
  exists before `git rm`** — the fuzz harnesses under `backend/extensions/fuzz/fuzz_<k>.cpp` are still
  present for the 18 remaining kernels, but some bench/test files the specs name are already gone.
- For a **shared** bench/test file named in `spec.bench_file`, EDIT it (remove only the `<k>` include +
  its block(s)); same for `backend/extensions/fuzz/CMakeLists.txt`. **Stale-spec caveat:** the two
  shared benches the specs reference — `backend/extensions/benchmarks/bench_anchor_garbage.cpp` and
  `bench_streaming_sketches.cpp` — were **already deleted in Slice 1** (NOTE comments remain in
  `benchmarks/CMakeLists.txt`), so for the anchor kernels (`anchor_descriptiveness`,
  `generic_anchor_matcher`) there is no shared C++ bench to edit; just add the Rust Criterion bench.
  Every other remaining kernel has its own **per-kernel** bench at
  `backend/extensions/benchmarks/bench_<k>.cpp` (delete, do not edit) registered in that CMakeLists —
  delete that bench, remove its `add_bench(<k> ...)` line, and recreate the bench in Rust.
- if `spec.python_fallback_path != "none"`: delete the `<k>` fallback function(s) and refactor EVERY
  caller in `spec.python_callers` to import + call the Rust module **directly** — no
  `try/except → python` branch (a kept import guard must raise/log LOUD, not compute in Python).
  Preserve the caller's existing public behaviour and any `int()/float()/bool()` coercions.
- grep proof: `grep -rn "<k>.cpp\|from.*<k> import\|import <k>" backend --include=*.py --include=*.cpp`
  — every survivor resolves to the Rust module or is gone.
- stage **only** this kernel's files (NEVER `git add -A backend/extensions` — it sweeps unrelated
  pre-existing modified `.cpp/.h`). Run the two guard gates (must exit 0).

**7. Mutation gate:** `python scripts/bazel_default.py run //tools/quality:mutation` -> kill rate >= 0.75 for the new
package; kill survivors by strengthening tests.

**8. Commit** through the gauntlet. Repeat for the next kernel in the slice.

---

## 6. Kernel caveat table (read with each spec)

> This table lists the **18 kernels that REMAIN** to port. The 5 already-finished kernels (`l2norm`,
> `count_min_sketch`, `counting_bloom`, `compressed_bloom`, `anchor_self_information`) are DONE — Rust
> landed and C++ deleted in Slice 1 — so they are not in this table.

| Kernel | kind | numpy | parity_basis | risk | callers — special handling |
|---|---|---|---|---|---|
| generic_anchor_matcher | mixed | no | exact | low | 1 caller; assert exact |
| phrasematch | functions | no | exact | low | 1 caller; assert exact |
| texttok | functions | no | exact | medium | 3 callers; exact tokens |
| rareterm | functions | no | exact | medium | 1 caller |
| linkparse | functions | no | exact | medium | 3 callers |
| fieldrel | functions | no | exact | medium | 1 caller |
| anchor_descriptiveness | functions | no | exact | medium | 1 caller; byte-level Damerau-Levenshtein + trigram Jaccard, assert exact |
| anchor_diversity | functions | **yes** | exact | medium | 1 caller; numpy int32 arrays in, dict-of-arrays out; abs tol 1e-6 |
| api_rate_limiter | class | no | contract | medium | **6 callers** — refactor all carefully |
| lesson_index | class | no | contract | medium | **9 callers** — refactor all carefully |
| feedrerank | functions | **yes** | exact | high | 3 callers |
| pagerank | functions | **yes** | exact | high | 4 callers; converge to same stationary dist within tol |
| papertrail_dedup | class | no | contract | high | 3 callers; MinHash+LSH — verify paper-trail dedup still collapses near-dupes |
| scoring | functions | **yes** | contract | high | 4 callers; ranking hot path, ≥10× floor, score-breakdown validation in Rust |
| passagesim | functions | **yes** | contract | high | 1 caller; keep parity oracle longest, add proptest |
| simsearch | functions | **yes** | contract | high | 2 callers; keep parity oracle longest, add proptest |
| ivf_index | functions | **yes** | contract | high | 1 caller; keep parity oracle longest, add proptest |
| quantemb | functions | **yes** | exact | high | 2 callers; quantisation must round-trip identically |

---

## 7. The 15 slices

> Each slice = one commit. **Goal / Scope / Deliverables / Acceptance / Depends-on.** Stop & report after each.

### Slice 1 — Land the Phase 0 foundation
- **Goal:** commit the already-authored guard rails so the safety net is in `master`.
- **Scope:** `docs/adr/0007-python-rust-two-language.md`, `RUST-FIRST.md`, `docs/PYTHON-RUST-MIGRATION-PLAN.md`, `docs/specs/fr-rust-ownership-boundary.md`, `.githooks/check-removed-languages.py`(+test at `.githooks/test_check_removed_languages.py`), `.githooks/check-dead-code-on-replace.py`(+test), `.claude/hooks/block-msi-build-test.py`(+test at `.claude/hooks/test_block_msi_build_test.py`), `scripts/dell-rust.sh`, `config/mutation-routing.json`, `config/rust-coverage-floor.json`, the rule headers in `CLAUDE.md`/`AGENTS.md`/`CODEX.md`/`GEMINI.md`, `.gitignore`, and the `rust/` workspace + the **5 already-finished crates** (`l2norm`, `count_min_sketch`, `counting_bloom`, `compressed_bloom`, `anchor_self_information`) with their C++/fuzz/shared-bench deletions and `RUST_EXTENSION_NAMES` registry edits. Because these 5 deletions land here in the foundation, Slices 2 and 3 must NOT re-port them.
- **Deliverables:** one commit; guard-hook + `block-msi-build-test` tests green; full marker set.
- **Acceptance:** `check-removed-languages`, `check-dead-code-on-replace`, `block-msi-build-test` tests pass; gauntlet passes; `git status` clean for these paths.
- **Depends on:** none.

### Slice 2 — Sketch/bloom family (verify-only)
- **Goal:** `count_min_sketch`, `counting_bloom`, `compressed_bloom` are **already ported, wired, and
  their C++ deleted in Slice 1** — this slice only **verifies and confirms** them. Re-run the Dell
  build/test/clippy + mutation gate on the three crates, confirm `RUST_EXTENSION_NAMES` holds them and
  the C++ `EXTENSION_NAMES` does not, and confirm no Python caller still imports a removed fallback.
  **Do NOT re-port, re-delete, or re-author** these kernels. If Slice 1 already committed all three
  cleanly, this slice may be a no-op commit (or fold its verification into Slice 1's report).
- **Scope:** `rust/extensions/{count_min_sketch,counting_bloom,compressed_bloom}/` (verify), plus a read
  of `scripts/ensure_compiled_artifacts.py` and `backend/extensions/setup.py` to confirm the registries.
  **Note:** the shared C++ bench `backend/extensions/benchmarks/bench_streaming_sketches.cpp` and the
  per-kernel C++ bloom sources were **already deleted in Slice 1** — there is nothing left to edit there.
- **Acceptance:** `dell-rust.sh test -p <k>` green for each of the three; guards exit 0; mutation ≥75%; no dangling refs.
- **Depends on:** Slice 1.

### Slice 3 — Anchor family
- **Goal:** port `anchor_descriptiveness` (`exact` — assert exact Damerau-Levenshtein + trigram Jaccard
  on **bytes**), `anchor_diversity` (numpy, `exact`, abs tol 1e-6), `generic_anchor_matcher` (`exact`).
  (`anchor_self_information` is **already done** — ported and deleted in Slice 1; do NOT re-port it.)
- **Scope:** their crates + the anchor callers/fallbacks named in each `backend/tmp/port-specs/<k>.json`
  (`python_callers`) + the fuzz harnesses listed in each spec's `cpp_files_to_delete`
  (`backend/extensions/fuzz/fuzz_anchor_descriptiveness.cpp`, `fuzz_generic_anchor_matcher.cpp`, etc).
  **Caveat — stale bench reference:** the port-specs for these kernels still say to EDIT the shared
  C++ bench `backend/extensions/benchmarks/bench_anchor_garbage.cpp`, but that file was **already
  deleted in Slice 1** (see the NOTE in `backend/extensions/benchmarks/CMakeLists.txt`). There is no
  C++ bench to edit — instead just add the Rust Criterion bench at
  `rust/extensions/<k>/benches/bench_<k>.rs` (3 input sizes) per the Mandatory Benchmark Rule.
- **Acceptance:** Dell tests green; callers Rust-direct; guards exit 0; mutation ≥75%.
- **Depends on:** Slice 1.

### Slice 4 — Text/term family
- **Goal:** port `texttok`, `phrasematch`, `rareterm`, `linkparse` (all `exact`; assert exact tokens/parse output).
- **Acceptance:** Dell tests green; callers Rust-direct; guards exit 0; mutation ≥75%.
- **Depends on:** Slice 1.

### Slice 5 — Relevance/feed family
- **Goal:** port `fieldrel`, `feedrerank` (numpy), `api_rate_limiter` (class, **6 callers**), `lesson_index` (class, **9 callers**).
- **Acceptance:** Dell tests green; **all** callers refactored to Rust-direct with behaviour preserved; guards exit 0; mutation ≥75%.
- **Depends on:** Slice 1.

### Slice 6 — Graph + dedup
- **Goal:** port `pagerank` (numpy; same stationary distribution within tolerance) and `papertrail_dedup` (MinHash+LSH). After wiring, prove the paper-trail flow still collapses near-duplicates at ≥0.85 Jaccard.
- **Acceptance:** Dell tests green; paper-trail dedup verified; guards exit 0; mutation ≥75%.
- **Depends on:** Slice 1.

### Slice 7 — Vector search A (high risk)
- **Goal:** port `simsearch`, `passagesim`. **Keep the C++ as a parity oracle the longest**; add `proptest` property tests; delete C++ only after contract + property tests pass on Dell.
- **Acceptance:** Dell tests + property tests green; retrieval within documented tolerance; guards exit 0; mutation ≥75%.
- **Depends on:** Slice 1.

### Slice 8 — Vector search B (high risk)
- **Goal:** port `ivf_index`, `quantemb` (quantisation must round-trip identically). Same care as Slice 7.
- **Acceptance:** Dell tests + property tests green; guards exit 0; mutation ≥75%.
- **Depends on:** Slice 1.

### Slice 9 — Scoring + C++ build-system teardown
- **Goal:** port `scoring` (ranking hot path; ≥10× floor; move the score-breakdown validation into Rust — see the `scoring` row in §6). `scoring` is the **last** kernel, so once it lands ALL kernels are Rust; then delete the C++ build system: remaining `backend/extensions/*.cpp/*.h`, `setup.py` C++ entries, `backend/extensions/benchmarks/CMakeLists.txt` (+ the leftover per-kernel `bench_<k>.cpp` and edge-test files), `backend/extensions/tests/*.cpp`, `backend/extensions/fuzz/`, and the C++ branch of `scripts/ensure_compiled_artifacts.py`.
- **Acceptance:** zero `.cpp/.h` under `backend/extensions/`; Dell tests green; mutation ≥75%; `check-cpp-lifecycle` passes empty (or is queued for removal in Slice 12).
- **Depends on:** Slices 2–8.

### Slice 10 — Phase 2: fold Go services into Python
- **Goal:** replace `services/{streamd,startupd,sidecars,go,speccheck}` with Python on existing infra (Celery / Redis Streams / Postgres advisory locks / Django commands / VictoriaMetrics, per the capability-adoption map). Delete each folder + its Go pre-commit hooks + its `docker-compose.yml` block. Read `backend/tmp/recon/phase2_go_services.md`.
- **Acceptance:** each service's behaviour has a Python equivalent with Dell tests; `check-go-service-*` hooks + folders + compose blocks removed; app boots and all routes/health truthful.
- **Depends on:** Slice 1.

### Slice 11 — Phase 3: drop Haskell + Lua
- **Goal:** remove `services/findbugs-haskell` (replace its capability with a small Python step if still needed) and all `.lua` + Lua hooks/wiring/CI. Read `backend/tmp/recon/phase3_haskell_lua.md`.
- **Acceptance:** no `.hs/.cabal/.lua` remain; Haskell/Lua hooks + compose blocks + CI jobs removed; app boots.
- **Depends on:** Slice 1.

### Slice 12 — Phase 4 (E5+E2+E3+E4): strip tooling, slim images, retire issues
- **Goal:**
  - **E5 — delete** (hook + test + un-wire from `scripts/precommit-docker.sh`): `check-compiled-build`, `check-cpp-lifecycle`, `check-c-abi-conformance`, `check-go-service-contract`, `check-go-service-resource-budget`, `check-luajit-dialect`, `check-lua-sandbox`, `check-lua-test-isolation`, `check-lua-test-sandbox`, `check-native-observability-wired`, `check-native-inspection-window`, `check-stubs-not-regenerated`.
  - **E5 — revise:** `check-language-ownership` → Python+Rust; `check-no-cross-language-import` → Python↔Rust only; `check-mint-first-build` → routing minus removed langs; **`check-rust-mandate` → the Dell path** (`scripts/dell-rust.sh` / turbo), since MSI has no `compiled-tools`; `check-scoped-mutation`/`check-per-file-coverage`/`check-mutation-score` → Python+Rust; `check-glossary` → drop removed-language terms.
  - **E2:** rebuild `compiled-tools` as a Rust-only tools image (cargo, clippy, cargo-mutants, cargo-llvm-cov, maturin); drop mull/go-mutesting/mucheck.
  - **E3:** remove host Go SDK + CMake + go-mutesting (confirm not used by other projects first; needs the user for uninstall/admin — flag it).
  - **E4:** add `backend/apps/auto_issues/.../retire_removed_language_work.py` (+test) to mark removed-language AutoIssues + paper-trail entries resolved/wontfix/stale citing ADR 0007; retire dead pickers/verifiers (`verify_perfetto_autoissues`, `verify_gwp_asan_autoissues`); remove removed-language sources from the 30-pick/10-paper-trail feeders. **Keep `rust_defect` + Python issues.** Read `backend/tmp/recon/e5_hooks.md` + `e4_governance.md`.
- **Acceptance:** precommit chain runs Python+Rust only and passes; removed-language AutoIssues retired in the DB; app boots.
- **Depends on:** Slices 9, 10, 11.

### Slice 13 — Phase 5 (E6+E7): doc/config sweep + GitHub Actions
- **Goal:**
  - **E6 — delete:** `CPP-FIRST.md`, `COMPILED-LANGUAGE-RULES.md`, `docs/NATIVE_RUNTIME_POLICY.md`, `docs/CPP-ROADMAP.md`, `backend/extensions/CPP-RULES.md`. **Update:** `docs/MODULAR-MONOLITH.md` (drop Go-services tier + C++ kernel lifecycle), the ADRs (mark the Go-services-tier ADR superseded), the glossary in `PLAIN-ENGLISH-RULE.md`, and `config/*.json`. Read `backend/tmp/recon/e6_docs_config.md`.
  - **E7 — GitHub Actions:** collapse `ci-language-quality.yml` to Python+Rust; in `ci.yml` drop Go/Haskell/C++/Lua build+test, keep Python (pytest+coverage), add Rust (cargo test + `clippy -D warnings` + cargo build); `scoped-mutation.yml` → mutmut + cargo-mutants only; `codeql.yml` → Python only. Wire the 95% coverage gate (Slice 14) into CI. Read `backend/tmp/recon/e7_github_actions.md`.
- **Acceptance:** no C++/Go/Haskell/Lua references remain in docs/config/CI; CI green; app boots.
- **Depends on:** Slice 12.

### Slice 14 — E8: coverage → 95% (Python + Rust)
- **Goal:** raise the TARGET to 95% in `docs/CODE-COVERAGE-RULES.md`, `AI-CODING-GUIDELINES.md`, `.githooks/check-per-file-coverage.py`, `config/mutation-routing.json`, and the CI gate. Add **Rust coverage via `cargo-llvm-cov`** wired into the per-file gate + CI. Raise ACTUAL coverage per-module to ≥95% (write/extend tests; run on Dell). **Ratchet, not a cliff** — lift each module's floor to 95% only once it reaches it, so the repo stays committable throughout.
- **Acceptance:** every touched module ≥95%; the global gate is 95% via the per-module ratchet; CI green; `[COVERAGE SUMMARY: target=95% actual=<Y>% — met]`.
- **Depends on:** Slice 13 (cross-cutting — also lift floors as modules are touched in earlier slices).

### Slice 15 — Phase 6 (ECharts) + Phase 7 (Optuna)
- **Goal:**
  - **Phase 6:** replace `chart.js@4.x` + `d3@7.x` with **Apache ECharts** across every GUI graph. Each chart honours the truthful-state rule (real data | empty | blocked | rebuild-required | access-denied — never a blank chart implying "all good"). Register every chart/route in `frontend/src/app/core/routing/deep-link-catalog.ts` with plain-English `peHelper` tooltips. Read `backend/tmp/recon/phase6_echarts.md`.
  - **Phase 7:** complete Optuna ↔ autotuner ↔ tunable/meta registries (`backend/apps/pipeline/services/meta_hpo_eval.py`, `backend/apps/suggestions/services/weight_tuner.py`, `suggestions/tunable_registry.py`, `suggestions/meta_registry.py`) so Optuna drives the autotuner over **all current + future** weights/meta-algos with no tuner-code change per new tunable. Offline-only (`ranking_train`); Rust (`ranking_profiles` + `ranking_governance`) governs activation. Read `backend/tmp/recon/phase7_optuna.md`.
  - **If too large for one commit, split into 15a (ECharts) and 15b (Optuna)** — each independently green.
- **Acceptance:** no `chart.js`/`d3` left; charts render with truthful states + deep-link entries + peHelpers; Optuna drives the autotuner over the registries with Dell tests green; activation still gated by Rust.
- **Depends on:** Slices 12–14.

---

## 8. Gotchas & troubleshooting

- **`bash: /bin/bash: No such file or directory` / WSL relay error** → you used `bash`; switch to `/usr/bin/bash`.
- **`dell-rust.sh` says Dell unreachable** → Docker Desktop on the Dell machine is stopped. Ask the user to start it (you cannot launch it remotely). Do not fall back to a local build.
- **`run_pytest_on_context.py` fail-open re-ran locally** → a transient local-Docker flake; just re-run — the next run routes to Dell (`[PYTEST SPLIT: dell -> N target(s)]`). Never accept a local MSI test run as the proof.
- **A hook blocks your command quoting** (e.g. it pattern-matched a literal `docker compose build` inside your test data) → move the literal into a file (Write is not scanned) instead of a Bash command line.
- **`check-rust-mandate` fails locally before Slice 12** → it still expects local `compiled-tools`; run the Rust gate via Dell and, if it blocks the commit, that's expected until Slice 12 revises it — coordinate the order (do Slice 12's `check-rust-mandate` revision if a kernel commit is blocked by it).
- **`cargo --locked` fails after adding a crate** → the new member changed resolution; regenerate `rust/Cargo.lock` (`/usr/bin/bash scripts/dell-rust.sh build` without `--locked`), then commit the updated lockfile.
- **Workspace won't parse** → a `members` entry points at a dir with no `Cargo.toml`; finish that crate or remove the member line.
- **Never** restart Docker/WSL to "fix" anything — the restart is paused by the user.

---

## 9. Definition of done (whole migration)

- All C++ kernels are Rust; **zero** `.cpp/.h/.go/.proto/.hs/.cabal/.lua/.java` remain in the repo.
- Go services folded into Python; Haskell + Lua gone; removed-language hooks/CI/docs gone; `compiled-tools` is Rust-only; host Go/CMake removed; removed-language AutoIssues retired.
- Coverage ≥95% (Python + Rust) via the per-module ratchet, enforced locally and in CI.
- ECharts everywhere with truthful states; Optuna autotuner wired (offline; Rust-governed activation).
- Every slice landed as its own clean commit through the full gauntlet (no `--no-verify`), each with `turbo=used`, complete per-file markers, resolved quotas, and a plain-English handoff entry.
- The app boots; every Rust-owned capability reports a truthful state on `/diagnostics`.

## 10. How to report after each slice (plain English, three parts)

1. **What I did** — the slice + the files touched.
2. **What now works** that didn't before.
3. **What broke or is unfinished** — honestly; never bury a failure, never claim partial as done.

Quote the commit hash and the `[QUALITY GATE RESULT]`, `[COVERAGE SUMMARY]`, and `turbo=` lines. Then
stop and wait for "next slice" unless told to continue.
Historical note: this document describes the retired MSI Docker-era workflow. Current MSI commands must use Kubernetes, `python scripts/backend_manage.py`, or SSH to Dell/Mint helpers.
