# FR - Guarded Kubernetes Cutover

[SPEC FRESHNESS: reviewed_at=2026-06-17 next_review=2026-09-17]

## Purpose

Slice 28 guards the final switch. It proves cluster readiness and keeps Docker
removal on MSI blocked until the database, media, observability, GlitchTip,
remote checks, rollback data, and manual review are all marked true.

## Current Source Of Truth

- Cluster readiness check: `.githooks/check-k8s-cluster-ready.py`.
- MSI Docker proof helper: `scripts/msi_docker_cutover.py`.
- Guarded removal script: `scripts/remove-msi-docker.ps1`.

## Behavior

Given the cluster is not proven ready, when the readiness check runs, then it
prints a plain-English failure and returns non-zero. Given the proof file is
incomplete, when the removal script runs, then it refuses to remove Docker.

## Citations

- Kubernetes documentation - Nodes: https://kubernetes.io/docs/concepts/architecture/nodes/
- Kubernetes documentation - Resource management for Pods and containers: https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/
