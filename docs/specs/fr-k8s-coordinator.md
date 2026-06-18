# FR - Coordinator And Merge Rehearsal

[SPEC FRESHNESS: reviewed_at=2026-06-17 next_review=2026-09-17]

## Purpose

Slice 27 coordinates distributed checks and merges reports. This pass adds a
safe dry-run path and records that the full Job and merge implementation remain
partial until the Bazel phases are ready.

## Current Source Of Truth

- Dry-run entry point: `scripts/run-distributed-tests.sh`.
- Route helper: `scripts/lib/route-to-coordinator.sh`.
- Runner image ConfigMap renderer: `tools/runners/image_refs.py`.

## Behavior

Given the coordinator is run with `--dry-run`, when it checks the lockfile, then
it prints the intended namespace, ConfigMap, and image references, and exits
without applying Kubernetes Jobs.

## Citations

- Kubernetes documentation - Jobs: https://kubernetes.io/docs/concepts/workloads/controllers/job/
- Bazel documentation - Build Event Protocol: https://bazel.build/remote/bep
