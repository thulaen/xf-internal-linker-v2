# FR - Bazel Remote Cache Rehearsal

[SPEC FRESHNESS: reviewed_at=2026-06-17 next_review=2026-09-17]

## Purpose

Slice 25 is the remote build cache. ADR 0010 moves this cache to Dell because
Dell has the fast disk and CPU budget.

## Current Source Of Truth

- Decision record: `docs/adr/0010-bazel-authoritative-build.md`.
- Migration plan: `docs/BAZEL-MIGRATION-PLAN.md`.

## Behavior

Given the cache is configured on Dell, when Bazel runs the same target twice,
then the second run should reuse cached work instead of rebuilding unchanged
inputs.

## Citations

- Bazel documentation - Remote caching: https://bazel.build/remote/caching
- bazel-remote project: https://github.com/buchgr/bazel-remote
- BuildBuddy documentation: https://www.buildbuddy.io/docs/
