# FR - Bazel Install Rehearsal

[SPEC FRESHNESS: reviewed_at=2026-06-17 next_review=2026-09-17]

## Purpose

Slice 24 starts the Bazel migration. ADR 0010 makes Bazel the authoritative
builder, and Dell is the build and cache machine.

## Current Source Of Truth

- Decision record: `docs/adr/0010-bazel-authoritative-build.md`.
- Migration plan: `docs/BAZEL-MIGRATION-PLAN.md`.
- Bazel pin: `.bazelversion`.
- Bazel settings: `.bazelrc`.

## Behavior

Given Dell has Bazelisk installed, when `bazel version` runs, then it uses the
pinned Bazel version and does not build on MSI.

## Citations

- Bazel documentation: https://bazel.build/
- Bazelisk project: https://github.com/bazelbuild/bazelisk
