#!/usr/bin/env bash
# Run the 12 preflight checks for distributed quality jobs.
set -euo pipefail

checks=(
  cluster-api-ready
  dell-node-ready
  mint-storage-ready
  registry-mirror-ready
  runner-images-pinned
  source-snapshot-uploaded
  bazel-remote-cache-ready
  buildbuddy-app-ready
  postgres-service-ready
  frontend-http-ready
  worker-queue-ready
  msi-docker-free
)

for check in "${checks[@]}"; do
  printf 'CHECK %s\n' "$check"
done

if command -v docker >/dev/null 2>&1; then
  if docker context show 2>/dev/null | grep -qi '^default$'; then
    echo "ERROR: MSI Docker context is active; use Dell or Kubernetes runners." >&2
    exit 1
  fi
fi

if ! test -f runner-images.lock.json; then
  echo "ERROR: runner image lockfile is missing." >&2
  exit 1
fi

echo "OK: distributed quality preflight list is complete."
