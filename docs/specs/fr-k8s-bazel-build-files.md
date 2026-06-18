# FR - Bazel Build File Rehearsal

[SPEC FRESHNESS: reviewed_at=2026-06-17 next_review=2026-09-17]

## Purpose

Slice 24 also covers BUILD file generation. This remains partial until Rust
extension, backend image, and frontend build outputs are fully switched to
Bazel.

## Current Source Of Truth

- Bazel migration plan: `docs/BAZEL-MIGRATION-PLAN.md`.
- Existing runner targets: `tools/runners/BUILD.bazel` and child BUILD files.

## Behavior

Given the runner targets already build, when the next Bazel phase lands, then it
adds one proven target at a time and deletes the superseded build path in the
same phase.

## Citations

- Bazel documentation - BUILD files: https://bazel.build/concepts/build-files
- rules_oci documentation: https://github.com/bazel-contrib/rules_oci
