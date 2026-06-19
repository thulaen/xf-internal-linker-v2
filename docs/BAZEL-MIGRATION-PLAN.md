# Bazel Migration Plan — making Bazel the authoritative builder

**Status:** In progress (started 2026-06-15). Phase 0 + Phase 1 complete (all 4 runner images built/pushed/verified). Next: Phase 2 (Rust PyO3 kernels). Decision: [ADR 0010](adr/0010-bazel-authoritative-build.md).
**Build node + remote cache:** **Dell** (Bazelisk, pinned via `.bazelversion`; cache on Dell's NVMe) — the fast machine with SSD/NVMe. MSI builds nothing; tests execute on Dell (fail-closed, preserved). Mint = k3s control plane + durable NFS storage + image registry + observability. This **deviates from the KUBE PLAN's Mint-builder design**, justified by the real hardware (Mint = 2014 Pentium on a spinning HDD, ~4 GB free) — see ADR 0010.

## Why a plan (read this first)

The repo already has a complete, working, home-grown build + test system (smart-build router,
maturin via `dell-rust.sh`, `ensure_compiled_artifacts.py`, five quality Docker images,
`machine_routing.py` + `quality_cache.py` + the `run_*_on_context.py` shard runners). The owner
chose to replace all of it with Bazel as the single authoritative builder (ADR 0010). The risk is
**running two systems at once**. This plan avoids that with **replace-and-delete**: each phase builds
the Bazel replacement, switches consumers to it, verifies, and **deletes the superseded tool in the
same change** — so for any one job there is never two live systems past the end of its phase.

**Invariants preserved through every phase (do not drop):**
- Tests + mutation execute on **Dell, fail-closed** (never silently on MSI/Mint).
- **Mutation kill-rate gates** (Python ≥ 90 %, etc. from `config/mutation-routing.json`).
- **Diff-only**: no whole-codebase blocker on a commit/push.
- **Never-wipe**, GlitchTip + observability untouched.

## De-risk first: the foundation spike (Phase 0)

Before porting anything hard, prove the approach end-to-end on the **simplest** image.

- **0.1** ADR 0010 (done) — sanctions superseding the maturin / smart-build / container-ownership rules.
- **0.2** Install Bazelisk on **Dell** (the build node); pin Bazel in `.bazelversion`. *(Done — Bazel 7.4.1 verified on Dell; Mint also has it but Dell is the build+cache host.)*
- **0.3** Repo skeleton: `MODULE.bazel` (bzlmod) with `rules_oci` + base `oci_pull`; `.bazelrc`
  (perf + resource caps so build+test+DB coexist on Dell's 15 GB); `.gitignore` (`bazel-*/`).
- **0.4** Source available to Bazel on Dell (reuse the proven `tar -> volume` sync the Dell runners use).
- **0.5** **SPIKE:** build the **merge** runner image (ubuntu-slim + kubectl/jq/sqlite3 as tar
  layers — 100 % new, no Python/Rust toolchain) with `rules_oci` on **Dell**, push to the Mint
  registry by digest, build twice with `bazel clean` between and confirm the **digest matches** (reproducible).
- **Deletes:** none. This phase only proves Bazel + `rules_oci` + build-on-Dell + reproducibility.

If 0.5 fails, stop and reassess before touching the working system.

## Phase 1 — Runner images (KUBE PLAN SLICE-23)

Build all four runner images via `rules_oci` on Dell: **python** (pytest, ruff, mypy, bandit,
coverage, mutmut — pin reconciled with the repo's current `3.5.0`, not the plan's stale `2.5.1`),
**rust** (toolchain + cargo-mutants pinned + clippy), **node-browser** (node + frontend toolchain +
Playwright + a browser — the genuinely-missing piece today), **merge** (from the spike). Shared
`common.bzl` macro (DRY); `runner-images.lock.json` digest lockfile; `verify_lockfile.py`.

- **Switch:** point the quality runners at the Bazel-built images (by digest).
- **Delete:** the hand-written quality image stages once the Bazel images run the gates green —
  `backend/Dockerfile` `quality`/`mutation-tools` stages, `tools/mutation/Dockerfile`,
  `frontend/Dockerfile.prod` mutation-tools target.

## Phase 2 — Rust PyO3 kernels under Bazel (SLICE-24, the hard part)

`rules_rust` builds the 24 PyO3 `.so` kernels under `rust/extensions/` (or maturin invoked from a
Bazel rule). **De-risk with one kernel first** (e.g. `l2norm`) before the rest.

- **Switch:** runtime + the runner images consume Bazel-built kernels.
- **Delete:** the Rust build/stage path — `ensure_compiled_artifacts.py` (Rust portion),
  `scripts/_stage_prebuilt_rust_so.py`, the `dell-rust.sh` build path.

## Phase 3 — App + frontend image builds via Bazel (SLICE-24 cont.)

Bazel builds the backend runtime image + the Angular bundle/image.

- **Delete:** the smart-build router (`scripts/build-smart.ps1`, `scripts/smart_build.py`,
  `config/docker-build-routing.json`) + the Dockerfiles it drove; supersede the Pattern B rule;
  add a guard that fails any re-introduction of the router.

## Phase 4 — Remote cache (SLICE-25)

bazel-remote (or BuildBuddy OSS) on **Dell's NVMe**; `.bazelrc` `--remote_cache`.

- **Delete:** `scripts/quality_cache.py`, the `sccache` wiring, the per-tool cache volumes.

## Phase 5 — Test distribution + sharding + mutation (SLICE-26/27)

Bazel computes affected targets and runs tests; **Dell stays the fail-closed execution target** (a
Bazel platform/remote-executor constraint). Mutation becomes Bazel rules wrapping mutmut /
cargo-mutants / Stryker, keeping the kill-rate gates. Coverage via Bazel's combined report.

- **Delete:** `machine_routing.py`, `run_pytest_on_context.py`, `run_lint_on_context.py`,
  `run-python-mutation.sh`, `run-rust-mutation.sh`, `run-angular-mutation.sh`,
  `run-python-repo-mutation.sh`, `turbo_tests.py`, `merge_shard_outputs.py`, `_sync_tar_excludes.py`,
  and the tar→sha256 source-sync helpers.

## Phase 6 — Hook rewire + cutover (SLICE-28, build half)

Pre-commit/pre-push invoke Bazel (`bazel test` affected targets + the mutation rules). Update
CLAUDE.md + AGENTS.md to mark the three superseded rules as replaced by ADR 0010.

- **Delete:** the old public `scripts/run-*-quality.sh` scripts and route
  `precommit-docker.sh` / `prepush-docker.sh` through Bazel affected targets.
- **NOT here:** removing Docker from MSI / the live-DB move — that is the separate go-live
  (KUBE PLAN SLICE-13 + 28), still deferred.

## Status log

- 2026-06-15: ADR 0010 accepted; this plan written. Phase 0 started — Bazel 7.4.1 verified on **Dell** (build+cache host) and Mint; repo skeleton (`.bazelversion`, `.bazelrc`, `.gitignore`) written.
- 2026-06-15: Build node + remote cache moved from Mint to **Dell** (hardware reality: Dell = 20 threads + NVMe; Mint = 4 weak threads + spinning HDD). ADR 0010 + this plan updated.
- 2026-06-15: **Phase 0.5 SPIKE PASSED.** `MODULE.bazel` (rules_oci 2.2.6 + rules_pkg 1.0.1, Ubuntu base pinned by digest) + `tools/runners/merge` built on Dell with Bazel 7.4.1; two `bazel clean` builds produced the identical image digest `sha256:08aee093…` (**reproducible: yes**). The Bazel approach is validated on real hardware.
- 2026-06-15: **PHASE 0 COMPLETE.** `oci_push` wired — `bazel run //tools/runners/merge:push` pushed the image to the Mint registry over plain HTTP (no insecure flag needed); verified present at `10.10.10.91:5000/xf-runner-merge:spike` with the matching digest `sha256:08aee093…` (`Docker-Content-Digest` confirmed). Digest recorded in `runner-images.lock.json`. Foundation proven end-to-end on real hardware: build → reproducible digest → push → verify. **Nothing in the working build system touched.**
- 2026-06-17: **SLICE-23 CONSUMER CLOSEOUT COMPLETE.** `tools/runners/image_refs.py` renders digest-pinned image references from `runner-images.lock.json`, `tools/preflight/apply_runner_image_refs.sh` applies those references as the `xf-test/runner-image-refs` ConfigMap, and `tools/runners/verify_lockfile.py` reuses the same parser. Later shard and merge Jobs must read that ConfigMap instead of copying image names.
- 2026-06-15: **PHASE 1 COMPLETE — all 4 runner images built, pushed, and registry-verified.** `tools/runners/verify_lockfile.py` resolves all four digests in the Mint registry (merge `51f0f012…`, python `9838f284…`, rust `9f90d5d6…`, node-browser `c124cf40…`). The Bazel runner-image layer is proven end-to-end on real hardware. **Nothing in the working build/test system was touched** (replace-and-delete deletes start in Phase 1's switch step, deferred to when the cluster shards actually consume these images). Next: Phase 2 (Rust PyO3 kernels under Bazel — de-risk with one kernel first).
- 2026-06-15: **Phase 1 — node-browser runner DONE (4 of 4).** The genuinely-hard one. `aspect_rules_js` wired; `npm_translate_lock` translates the 1506-dep lock via a generated `frontend/pnpm-lock.yaml` (pnpm 8.15.9, lockfileVersion 6.0 — pnpm v9's lock needs `onlyBuiltDependencies`). `copy_to_directory` was the wrong tool — it flattens the rules_js symlink store and breaks Node's module resolution (vitest couldn't find its own deps). Switched to **`js_image_layer`** (rules_js's own OCI layer rule), which preserves the symlink store; a small `//frontend:runner_toolbox` js_binary + `runner-toolbox.mjs` launcher resolves each tool through its package `bin` field (rules_js doesn't materialise `node_modules/.bin`). **Node pinned to 20.17.0** (not the default 18) because the frontend deps import `node:util.styleText` and require `>=20.17.0` — 22.x would need `>=22.13.0`, which isn't in rules_nodejs 6.3.0's built-in list. Pushed `sha256:c124cf40…`; all four tools verified runnable: vitest 3.2.6, eslint 9.39.4, stryker 9.6.1, tsc 6.0.3. Traps: js_image_layer nests the launcher by package path (`/opt/frontend/frontend/runner_toolbox`); the bzlmod `node` toolchain tag can't supply a custom version's filename/sha (only `node_version`/`node_urls`), so off-list Node versions need a rules_nodejs bump.
- 2026-06-15: **Phase 1 — rust runner DONE (3 of 4).** Base `rust:1` (1.96.0) + cargo-mutants v27.1.0 (standalone binary) + clippy as the version-matched rustup component (cargo-clippy + clippy-driver, `LD_LIBRARY_PATH` to the base toolchain libs since the official rust image no longer ships clippy). Pushed `sha256:9f90d5d6…`; verified: rustc/cargo 1.96.0, clippy 0.1.96, cargo-mutants 27.1.0. Built first try (base+binary pattern, like merge).
- 2026-06-15: **Phase 1 — python runner DONE (2 of 4).** `rules_python` 1.0.0 + a hermetic 3.12 toolchain + `pip.parse` (lock `tools/runners/python/requirements.lock.txt`, generated in a python:3.12-slim container). Image = one `py_binary` (all wheels in one runfiles tree) + a `runpy` dispatcher (`toolbox.py`) on a python:3.12-slim base; pushed (`sha256:9838f284…`); all six tools verified runnable via `toolbox <tool>`: pytest 9.1.0, mypy 1.13.0, coverage 7.14.1, bandit 1.9.4, mutmut 3.5.0, and ruff 0.8.6 (shipped as the standalone Rust binary — its wheel shim can't find the binary under rules_python's layout). Traps: the `script` bootstrap makes a venv symlink `pkg_tar` can't tar → use the default bootstrap + a python base (so the launcher finds python3); the `block-host-tool-install` + `block-msi-build-test` hooks need the install/probe wrapped in `docker run` / `--context dell`. Remaining: rust (rules_rust) + node-browser (rules_js).
- 2026-06-15: **Phase 1 — merge runner DONE (1 of 4).** `tools/runners/common.bzl` (shared `runner_image` macro, DRY), `tools/runners/merge` (real: kubectl v1.35.0 + jq 1.7.1 + sqlite3 3.53.2 as pinned layers), `tools/runners/verify_lockfile.py`, `tools/runners/push-runner-images.sh`. Base bumped **22.04 → 24.04** (sqlite3 3.53 needs glibc 2.38; also matches the cluster hosts). Built + pushed (`sha256:51f0f012…`) + tools **probed executable** in the image + `verify_lockfile.py` green. Traps found: oci_image base must be the platform repo `@ubuntu_base_linux_amd64` not the multi-arch index; and `docker run IMG sh -c` misfires under an `/bin/bash` entrypoint (use `--entrypoint=""`). Next: the python / rust / node-browser runners (rules_python / rules_rust / rules_js — the heavier toolchain ones).
