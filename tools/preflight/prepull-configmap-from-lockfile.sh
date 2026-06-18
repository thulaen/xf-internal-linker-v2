#!/usr/bin/env bash
# Render runner image references for Slice 22/23 pre-pull consumers.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
NAMESPACE="${XF_RUNNER_IMAGE_NAMESPACE:-xf-test}"
CONFIGMAP_NAME="${XF_RUNNER_IMAGE_CONFIGMAP:-runner-image-refs}"

python3 "$ROOT/tools/runners/image_refs.py" \
  --format configmap \
  --namespace "$NAMESPACE" \
  --configmap-name "$CONFIGMAP_NAME"
