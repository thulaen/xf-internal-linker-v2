# FR - Registry And Image Pre-Pull Rehearsal

[SPEC FRESHNESS: reviewed_at=2026-06-17 next_review=2026-09-17]

## Purpose

Slice 22 provides the cluster image registry on Mint and pre-pulls key images
onto Dell so pods can start without waiting on large network pulls.

## Current Source Of Truth

- Registry manifest: `k8s/registry/registry.yaml`.
- Image pre-pull manifest: `k8s/registry/image-prepull.yaml`.
- Install helper: `tools/preflight/install_registry_mirror.sh`.
- Proof helper: `tools/preflight/test_registry_mirror.sh`.

## Behavior

Given the registry manifest is applied, when the proof helper runs, then the
registry answers `/v2/`, the pre-pull manifest targets worker nodes, and runner
image references come from `runner-images.lock.json`.

## Citations

- Docker Distribution registry documentation: https://distribution.github.io/distribution/
- Kubernetes documentation - Images: https://kubernetes.io/docs/concepts/containers/images/
