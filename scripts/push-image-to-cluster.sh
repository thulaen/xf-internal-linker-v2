#!/usr/bin/env bash
# Resilient PUSH of an already-built backend image into the cluster registry.
#
# Why this exists: pushing images to the Mint-hosted registry by hand is fragile
# over the flaky MSI<->Mint WiFi. This makes the PUSH robust:
#   - `docker push` is LAYER-AWARE (only changed layers transfer; no full
#     re-export like skopeo does on the docker-daemon source).
#   - it runs DETACHED on Mint via setsid, so a dropped SSH/WiFi connection can
#     NOT abort the push.
#   - it polls the registry until the new tag's manifest is live.
#
# This script does the PUSH only. Produce the image first with the project's
# normal image-creation flow (it lands as ${SRC_IMAGE} in Mint's local Docker),
# then run this to ship it into the cluster registry.
#
# Prereqs (already set up): Mint's Docker trusts 10.10.10.91:5000 as an
# insecure (private, wired) registry; both k3s nodes trust it via registries.yaml.
#
# Usage:
#   scripts/push-image-to-cluster.sh [TAG]
# TAG defaults to a UTC timestamp. Use an immutable tag (not :latest) so the
# cluster's imagePullPolicy:IfNotPresent always pulls the new image.
set -euo pipefail
export MSYS_NO_PATHCONV=1   # stop git-bash mangling remote /paths in ssh args

REGISTRY="10.10.10.91:5000"
IMAGE="xf-linker-backend"
SRC_IMAGE="xf-linker-backend-runtime:latest"   # the local image tag in Mint's Docker
MINT="mint-wifi"
TAG="${1:-$(date -u +%Y%m%d-%H%M%S)}"
REF="${REGISTRY}/${IMAGE}:${TAG}"

echo "==> [1/3] ship detached push-runner to Mint..."
ssh -o ConnectTimeout=15 "$MINT" "cat > /tmp/xf-push.sh" <<RUNNER
#!/bin/bash
set +e
docker tag ${SRC_IMAGE} ${REF}
docker push ${REF}
echo "XF_PUSH_DONE rc=\$?"
RUNNER

echo "==> [2/3] run push detached on Mint (immune to WiFi drops)..."
ssh -o ConnectTimeout=15 "$MINT" "rm -f /tmp/xf-push.log; setsid bash /tmp/xf-push.sh > /tmp/xf-push.log 2>&1 </dev/null & echo launched"

echo "==> [3/3] poll registry until ${IMAGE}:${TAG} is live..."
for i in $(seq 1 40); do
  code=$(ssh -o ConnectTimeout=8 -o ServerAliveInterval=4 -o ServerAliveCountMax=2 "$MINT" \
    "curl -s -o /dev/null -w %{http_code} http://${REGISTRY}/v2/${IMAGE}/manifests/${TAG}" 2>/dev/null || echo "conn-retry")
  printf '  [%02d] manifest=%s\n' "$i" "$code"
  if [ "$code" = "200" ]; then
    echo "DONE: ${REF} is live. Set the image to ${REF} in k8s/app/*.yaml and 'kubectl apply' + rollout."
    exit 0
  fi
  sleep 12
done
echo "TIMEOUT: push not confirmed. Inspect on Mint: ssh ${MINT} 'tail /tmp/xf-push.log'" >&2
exit 1
