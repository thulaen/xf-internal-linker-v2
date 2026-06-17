#!/usr/bin/env bash
# Apply the SLICE-23 runner image reference ConfigMap from runner-images.lock.json.
#
# Plain English: the cluster test pipeline should read one ConfigMap whose
# values are rendered from the digest lockfile. This keeps image names out of
# shard and merge Jobs until the later pipeline slices create those Jobs.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
NAMESPACE="${XF_RUNNER_IMAGE_NAMESPACE:-xf-test}"
CONFIGMAP_NAME="${XF_RUNNER_IMAGE_CONFIGMAP:-runner-image-refs}"

python3 "$ROOT/tools/runners/image_refs.py" \
  --format configmap \
  --namespace "$NAMESPACE" \
  --configmap-name "$CONFIGMAP_NAME" \
  | kubectl apply -f -

echo "runner image references applied: namespace=$NAMESPACE configmap=$CONFIGMAP_NAME"
