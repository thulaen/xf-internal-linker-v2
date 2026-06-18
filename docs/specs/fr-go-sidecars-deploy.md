# FR - Prebuilt Sidecar Deployment Rehearsal

[SPEC FRESHNESS: reviewed_at=2026-06-17 next_review=2026-09-17]

## Purpose

Slice 20 deploys prebuilt sidecar images by digest. This repo must not add or
modify removed-language source code. The only allowed path is deploying
already-built images by digest.

## Current Source Of Truth

- Sidecar host background: `docs/specs/fr-sidecars-host.md`.
- Status ledger: `docs/KUBE-PLAN-STATUS.md`.
- Digest lockfile: `sidecar-images.lock.json`.
- Proof command: `bash tools/preflight/test_sidecar_images.sh`.

## Behavior

Given sidecar image digests are recorded, when the sidecar proof runs, then it
accepts only `registry/path@sha256:<fingerprint>` references and rejects empty
values or movable tags.

## Citations

- OCI Image Format Specification: https://github.com/opencontainers/image-spec
- Kubernetes documentation - Images: https://kubernetes.io/docs/concepts/containers/images/
