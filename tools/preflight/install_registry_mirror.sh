#!/usr/bin/env bash
# Apply Slice 22 registry and image pre-pull manifests. Dry-run by default.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=cluster_lib.sh
. "$HERE/cluster_lib.sh"

EXECUTE=0
for arg in "$@"; do
  case "$arg" in
    --execute) EXECUTE=1 ;;
    --help) echo "Usage: $0 [--execute]"; exit 0 ;;
    *) echo "Unknown argument: $arg" >&2; exit 2 ;;
  esac
done

for manifest in k8s/registry/registry.yaml k8s/registry/image-prepull.yaml; do
  [ -f "$manifest" ] || { fail "Missing $manifest"; cluster_exit; }
done

if [ "$EXECUTE" -ne 1 ]; then
  echo "[REGISTRY MIRROR INSTALL: dry-run]"
  echo "Would apply k8s/registry/registry.yaml and k8s/registry/image-prepull.yaml on Mint."
  exit 0
fi

cluster_require_gitbash "$0"

for manifest in k8s/registry/registry.yaml k8s/registry/image-prepull.yaml; do
  remote="/tmp/$(basename "$manifest")"
  transfer_with_checksum_retry "$manifest" "$MINT_SSH" "$remote" >/dev/null \
    || { fail "Could not copy $manifest"; cluster_exit; }
  ssh_host "$MINT_SSH" "kubectl apply -f '$remote' --request-timeout=20s" >/dev/null \
    || { fail "Could not apply $manifest"; cluster_exit; }
done

echo "Registry and image pre-pull manifests applied."
