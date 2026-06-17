# FR - Kubernetes Runner Images (SLICE-23 closeout)

[SPEC FRESHNESS: reviewed_at=2026-06-17 next_review=2026-09-17]

## Status

Implemented through the lockfile consumer path. Four runner images are recorded
in `runner-images.lock.json`, the verifier reads that lockfile, and the cluster
can receive a generated ConfigMap with digest-pinned image references. Later
pipeline slices should read that ConfigMap instead of hard-coding image names.

## Source Of Truth

- `runner-images.lock.json` is the only persistent source for runner image
  repository names and digests.
- `tools/runners/image_refs.py` renders `repository@sha256:...` references from
  the lockfile as environment lines, JSON, or a Kubernetes ConfigMap.
- `tools/runners/verify_lockfile.py` reuses the same parser before checking the
  Mint registry.
- `tools/preflight/apply_runner_image_refs.sh` applies the generated ConfigMap
  to `xf-test`.
- `tools/runners/push-runner-images.sh` now defaults to all four runners:
  merge, Python, Rust, and node-browser.

## Rules

- Runner consumers must pull by digest, not by tag.
- The lockfile may keep a tag field as a human pointer, but generated consumer
  output must use `repository@sha256:...`.
- Do not create a second checked-in file that repeats all four image references.
  Generate the cluster ConfigMap from the lockfile.

## Proof

Given the lockfile contains four runner images, When `tools/runners/image_refs.py`
renders references, Then each output value uses a digest pin and no `:latest` or
`:v1` tag is used by the consumer path.
