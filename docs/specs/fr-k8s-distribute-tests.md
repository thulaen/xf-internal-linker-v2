# FR - Distributed Test Rehearsal

[SPEC FRESHNESS: reviewed_at=2026-06-17 next_review=2026-09-17]

## Purpose

Slice 26 keeps tests and mutation on Dell, with affected-target selection and
digest-pinned runner images. It stays partial until the Bazel test graph fully
replaces the existing quality runners.

## Current Source Of Truth

- Runner image lockfile: `runner-images.lock.json`.
- Dry-run entry point: `scripts/run-distributed-tests.sh`.
- Route helper: `scripts/lib/route-to-coordinator.sh`.

## Behavior

Given a dry run, when the distributed test wrapper runs, then it prints the
coordinator command and the runner image references without creating Jobs.

## Citations

- Bazel documentation - Test encyclopedia: https://bazel.build/reference/test-encyclopedia
- Kubernetes documentation - Jobs: https://kubernetes.io/docs/concepts/workloads/controllers/job/
