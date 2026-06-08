# ADR 0009 — Root-cause clustering of AutoIssues via the clusterd sidecar (SUPERSEDED)

> **SUPERSEDED by [ADR 0007 — Python + Rust only](0007-python-rust-two-language.md) — clusterd removed 2026-06-06.**
> This ADR placed the root-cause clustering compute in a Go sidecar (`clusterd`). The backend is
> now Python + Rust only, so the Go sidecar (`clusterd`) was removed on 2026-06-06; the MinHash/LSH
> similarity and grouping compute moves to a Rust extension on the hot path (see
> [`RUST-FIRST.md`](../../RUST-FIRST.md)), with Python orchestration around it and no Python
> fallback. This ADR is kept as historical record only; do not follow its Go-sidecar shape for new
> work.
>
> **Note on the original ADR-number clash:** this file was filed as `0007` while a second `0007`
> (Python + Rust only) was added on 2026-06-06. To resolve the collision this file was renumbered
> to **0009** on 2026-06-07 (the next free number after 0008). The active decision of record for
> language choice is [`0007-python-rust-two-language.md`](0007-python-rust-two-language.md)
> (2026-06-06).

**Date:** 2026-05-29 (renumbered 0007 → 0009 on 2026-06-07)
**Status:** Superseded by ADR 0007 (Python + Rust only) on 2026-06-06; clusterd removed.
**Deciders:** Project owner.
**Related:** ADR 0006 (Go services tier, also superseded), `docs/specs/fr-root-cause-clustering.md`; superseded by ADR 0007 (Python + Rust only).

## Context

The AutoIssue table accumulates many near-duplicate rows — GlitchTip runtime
errors, mutation survivors, FindBugs/rust_defect findings, and log-derived
issues — that describe the same underlying problem with small textual
differences (an id, a line number, a path). The existing dedup only collapses
rows that share an *exact* `canonical_fingerprint`, so near-duplicates survive
as separate rows and inflate the open count.

A root-cause clustering capability is needed to group near-duplicates so one
representative fix closes a whole family. The compute (MinHash/LSH similarity),
the grouping logic (thresholding + connected components), and the orchestration
(batching, transport, persistence) have different performance and correctness
profiles, which maps onto the project's language-ownership model.

Three options were considered:

1. **Pure-Python clustering in the Django process.** Simplest, but the
   MinHash/LSH compute is a hot path that Python serves poorly, and it would add
   a Python-only hot path the CPP-FIRST / sticky-1 rules forbid.
2. **Reuse only the existing C++ `papertrail_dedup` kernel from Python.** Reuses
   proven code, but `papertrail_dedup` is tuned for the paper-trail dedup shape
   and offers no place for the grouping *logic* or conservative tuning.
3. **A dedicated `clusterd` Go sidecar** that splits the work across the three
   languages the model already assigns: Rust for the speed-critical similarity
   compute, Haskell for the grouping logic, Go for the transport/plumbing, with
   Python orchestration through a private gRPC client.

## Decision

Adopt option 3. Concretely:

1. `services/clusterd/` is a Go sidecar in the services tier (ADR 0006), serving
   the `Clusterd` gRPC contract (`services/clusterd/api.proto`) over a
   Unix-domain socket (`clusterd_sock`), with all Rule-K artefacts.
2. The pipeline tiers follow language ownership: **Rust** (`cluster_core` +
   `cluster-sig`) computes MinHash signatures, LSH candidate pairs, and Jaccard
   similarity; **Haskell** (`FindBugs.Clustering`) applies the acceptance
   threshold and groups by single-link connected components; **Go** (`clusterd`)
   batches, shells to the Rust and Haskell helpers, and assembles clusters.
3. **Python** orchestrates through `apps.auto_issues._clusterd_client` and the
   `cluster_autoissues` management command. Clustering **never auto-resolves** a
   row — clusters are proposals; resolution stays a separate reviewed step.
4. Tuning is **conservative**: an Optuna study optimises the parameters under a
   precision floor (default ≥ 0.97 against exact-fingerprint duplicate labels),
   so the tuner cannot trade false merges for more collapsing.
5. The `clusterd` image bundles all three language runtimes in one multi-stage
   image (Rust + GHC + Go build stages → one Debian-slim runtime).

## Consequences

**Positive:**

- Near-duplicate families collapse to one representative, shrinking the open
  AutoIssue count without losing distinct problems (precision-first tuning).
- Each tier lives in the language the model assigns; no Python hot path.
- The compute crate (`cluster_core`) is the benchmark baseline for the
  sticky-1 native-rewrite review against the existing C++ kernel.

**Negative / costs:**

- A new sidecar image bundles three toolchains (larger build, ~239 MB image).
- Cross-language calls go Python → Go → (Rust, Haskell) subprocesses, adding
  process-spawn overhead per batch; acceptable for a batch/offline job, not a
  per-request hot path.

**Follow-ups:**

- Benchmark Rust `cluster_core` vs the C++ `papertrail_dedup` kernel and record
  the winner per the sticky-1 native-rewrite review.
- The Haskell mutation gate is blocked until a GHC-9.4-compatible mutation tool
  is available (MuCheck does not build on GHC 9.4.7).

[SPEC CITED: feature=0007-root-cause-clustering kind=academic_paper id=doi:10.1109/ICWS.2017.13 verified_at=2026-06-02]
[SPEC FRESHNESS: reviewed_at=2026-06-02 next_review=2026-09-02]
