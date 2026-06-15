# ADR 0010 — Bazel is the authoritative build system

**Date:** 2026-06-15
**Status:** Accepted
**Deciders:** Project owner (explicit decision, 2026-06-15).
**Related:** ADR 0007 (Python + Rust two-language — unchanged: Bazel builds Python + Rust + Angular only); KUBE PLAN SLICE-23/24/25/26/27 (the test-pipeline slices this ADR commits to).
**Supersedes (for BUILDING + build-time test distribution/caching):**
- The **Docker-managed maturin path** as the *direct* Rust build entry point (CLAUDE.md "PARAMOUNT — Docker-managed Rust builds"). Rust crates are still PyO3 extension modules; Bazel becomes the build *orchestrator* that produces the `.so` artifacts. maturin remains usable for local dev/wheel packaging but is no longer the authoritative CI/cluster build path.
- The **smart Docker build router** (CLAUDE.md "Pattern B Build Routing"; `scripts/build-smart.ps1`, `scripts/smart_build.py`, `config/docker-build-routing.json`) for producing images.
- The **container-ownership** model for *building* the quality/runner images (CLAUDE.md "Quality-Tool Container Ownership") — Bazel `rules_oci` builds those images. Where tests *execute* (Dell, fail-closed) is unchanged.
- The bespoke build-time distribution + caching scripts, phased out as Bazel takes each job: `machine_routing.py`, `quality_cache.py`, `run_pytest_on_context.py`, `run_lint_on_context.py`, `turbo_tests.py`, `merge_shard_outputs.py`, `ensure_compiled_artifacts.py`, `_stage_prebuilt_rust_so.py`.

## Context

Since the two-language decision (ADR 0007), the repo grew a complete but bespoke build + test
system: a hash-based smart Docker build router (Dell 92 % / Mint 8 %), maturin Rust builds via
`dell-rust.sh`, a boot-time content-addressed artifact stager (`ensure_compiled_artifacts.py`), five
hand-written quality/runner Docker images, and a custom test-distribution layer
(`machine_routing.py` Hamilton split + `quality_cache.py` content cache + per-language
`run_*_on_context.py` shard runners + `turbo_tests.py` + `merge_shard_outputs.py`). It works, but it
is **a large amount of home-grown build/distribution/caching code that re-implements what Bazel
provides natively** (content-addressed cache, hermetic reproducible builds, affected-target
selection, remote execution, digest-pinned outputs). Maintaining it is the cost ADR 0007 warned
about, moved up one layer from languages to build tooling.

The KUBE PLAN's test-pipeline slices (23–27) already specify Bazel + `rules_oci` + a remote cache
(BuildBuddy/bazel-remote) + Bazel-native test sharding. The open question was whether to keep
extending the bespoke system or adopt Bazel as the single source of build truth.

## Decision

**Bazel is the authoritative build system.** Concretely:

1. **One build graph.** Bazel builds the runner/quality images (`rules_oci`, reproducible digests),
   the Rust PyO3 `.so` kernels (`rules_rust`), and the Angular bundle. Outputs are content-addressed
   and digest-pinned; every consumer (shards, merge job, pre-pull) reads the same bytes.
2. **One cache, on Dell's NVMe.** A Bazel remote cache (bazel-remote / BuildBuddy) runs on **Dell's
   NVMe** (a build cache is read/written constantly and must be on fast disk) and replaces
   `quality_cache.py` + `sccache` + the per-tool caches. "Never re-run what already passed" is Bazel's
   CAS, not a custom JSONL.
3. **One test-distribution model.** Bazel computes affected targets (replacing `commit_scope.py` for
   build/test selection) and runs tests; Dell remains the **fail-closed** execution target (this
   property is preserved as a Bazel remote-executor / platform constraint, not dropped).
4. **Phased replace-and-delete.** Each capability moves to Bazel and the superseded script is
   **deleted in the same change** — never two live systems for one job. The migration order and the
   per-phase deletions are in [`docs/BAZEL-MIGRATION-PLAN.md`](../BAZEL-MIGRATION-PLAN.md).
5. **Build node + remote cache are on Dell.** Bazel (via Bazelisk, pinned in `.bazelversion`) and the
   remote cache run on **Dell** — the only machine with the CPU (20 threads), RAM, and **SSD/NVMe**
   for a disk- and cache-heavy build. MSI builds nothing; Mint reverts to k3s control plane + durable
   NFS storage + image registry + observability (which suits its weak hardware). **This deviates from
   the KUBE PLAN's Mint-builder design** — Mint is a 2014 Pentium on a spinning HDD with ~4 GB free, a
   poor build/cache host. Because Dell also runs the database + tests, Bazel is **resource-capped**
   (JVM heap + `--local_ram_resources` / `--local_cpu_resources`) so build + test + DB coexist within
   Dell's 15 GB. Tests still execute on Dell, fail-closed (unchanged).

## Alternatives rejected

1. **Keep the bespoke system; do not adopt Bazel.** The existing scripts already deliver
   reproducible, diff-scoped, cached, distributed, digest-pinned builds. Rejected by the project owner
   (2026-06-15): the owner wants a single authoritative builder to avoid the maintenance and
   correctness risk of home-grown build/distribution/caching code, even though the existing system
   works. The cost of this choice (a multi-week migration replacing a working system) is accepted.
2. **Bazel for building only; keep the custom test-distribution.** A smaller middle ground. Rejected
   for the same reason: it leaves two systems (Bazel build cache + `quality_cache.py`) and does not
   reach a single source of truth.

## Consequences

**Positive:**
- One reproducible, content-addressed build graph; digest-pinned images and kernels by construction.
- The home-grown distribution/caching/staging code (`machine_routing.py`, `quality_cache.py`,
  `run_*_on_context.py`, `turbo_tests.py`, `merge_shard_outputs.py`, `ensure_compiled_artifacts.py`)
  is retired, shrinking the maintenance surface.
- Affected-target selection and remote caching come from a battle-tested tool, not bespoke logic.

**Negative / costs (accepted):**
- **A multi-week migration that replaces a working system**, with unavoidable transitional overlap
  inside each phase until that phase's delete step lands.
- **PyO3 + maturin under Bazel is the hard part.** Building PyO3 extension modules with `rules_rust`
  (or invoking maturin from a Bazel rule) and wiring them into the Python runtime is the highest-risk
  piece; it is de-risked with a spike before the bulk port.
- **`rules_oci` is not `docker build`.** Images are assembled from pulled bases + tar layers, not
  `RUN` steps; tools like kubectl/jq/sqlite3 are added as layers, not `apt install`.
- **Three ABSOLUTE/PARAMOUNT CLAUDE.md rules change.** The maturin-direct, smart-build, and
  container-ownership-for-building rules are superseded by this ADR; CLAUDE.md + AGENTS.md are updated
  at the cutover phase, and a guard prevents resurrecting the smart-build router.

## References

- Bazel — `https://bazel.build`. Bazelisk (version manager) — `https://github.com/bazelbuild/bazelisk`.
- `rules_oci` — reproducible OCI images in Bazel, `https://github.com/bazel-contrib/rules_oci`.
- `rules_rust` — Rust (incl. PyO3 cdylib) under Bazel, `https://github.com/bazelbuild/rules_rust`.
- `rules_python` — `https://github.com/bazelbuild/rules_python`.
- bazel-remote — remote cache, `https://github.com/buchgr/bazel-remote`; BuildBuddy — `https://www.buildbuddy.io`.
- OCI Image Format Spec — `https://github.com/opencontainers/image-spec`.
- ADR 0007 — Python + Rust two-language (the language scope Bazel builds within).
- [`docs/BAZEL-MIGRATION-PLAN.md`](../BAZEL-MIGRATION-PLAN.md) — the phased replace-and-delete roadmap.

[SPEC FRESHNESS: reviewed_at=2026-06-15 next_review=2026-07-15]
