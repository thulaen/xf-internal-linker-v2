#!/usr/bin/env bash
# Shared dry-run routing for the future Kubernetes test coordinator.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
NAMESPACE="${XF_COORDINATOR_NAMESPACE:-xf-test}"
CONFIGMAP_NAME="${XF_RUNNER_IMAGE_CONFIGMAP:-runner-image-refs}"

echo "[DISTRIBUTED TEST ROUTE]"
echo "Namespace: $NAMESPACE"
echo "Runner image ConfigMap: $CONFIGMAP_NAME"
python3 "$ROOT/tools/runners/image_refs.py" --format env
