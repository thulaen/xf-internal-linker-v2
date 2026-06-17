#!/usr/bin/env bash
# SLICE-07 installer: apply xf-test RBAC and network policies.

HERE="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=cluster_lib.sh
. "$HERE/cluster_lib.sh"
cluster_require_gitbash "$0"

NETWORK_MANIFESTS=(
    k8s/network/xf-test-rbac.yaml
    k8s/network/xf-test-netpol.yaml
)

for manifest in "${NETWORK_MANIFESTS[@]}"; do
    [ -f "$manifest" ] || { fail "Missing $manifest"; cluster_exit; }
    remote="/tmp/$(basename "$manifest")"
    transfer_with_checksum_retry "$manifest" "$MINT_SSH" "$remote" >/dev/null \
        || { fail "Could not copy $manifest"; cluster_exit; }
    ssh_host "$MINT_SSH" "kubectl apply -f '$remote' --request-timeout=20s" >/dev/null \
        || { fail "Could not apply $manifest"; cluster_exit; }
done

printf 'xf-test RBAC and network policies applied. Re-run tools/preflight/test_net_rbac.sh.\n'
