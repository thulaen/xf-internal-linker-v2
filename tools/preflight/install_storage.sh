#!/usr/bin/env bash
# SLICE-09 installer: apply storage classes, storage claims, and quotas.

HERE="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=cluster_lib.sh
. "$HERE/cluster_lib.sh"
cluster_require_gitbash "$0"

STORAGE_MANIFESTS="${STORAGE_MANIFESTS:-k8s/storage/nfs-cold-provisioner.yaml k8s/storage/ssd-hot-provisioner.yaml k8s/scheduling/resource-limits.yaml k8s/obs/02-resource-limits.yaml k8s/scheduling/support-resource-limits.yaml k8s/storage/workload-pvcs.yaml}"

apply_manifest() {
    local manifest="$1" remote="$2" output
    output="$(ssh_host "$MINT_SSH" "kubectl apply -f '$remote' --request-timeout=30s 2>&1")" \
        && return
    if [ "$(basename "$manifest")" = nfs-cold-provisioner.yaml ] \
        && printf '%s' "$output" | grep -Eiq 'reclaimPolicy|field is immutable|forbidden'; then
        ssh_host "$MINT_SSH" "kubectl delete storageclass nfs-cold --ignore-not-found=true --request-timeout=20s" >/dev/null \
            || { fail "Could not recreate nfs-cold StorageClass"; cluster_exit; }
        ssh_host "$MINT_SSH" "kubectl apply -f '$remote' --request-timeout=30s" >/dev/null \
            || { fail "Could not apply recreated nfs-cold StorageClass"; cluster_exit; }
        return
    fi
    fail "Could not apply $manifest: $output"
    cluster_exit
}

for manifest in $STORAGE_MANIFESTS; do
    [ -f "$manifest" ] || { fail "Missing $manifest"; cluster_exit; }
    remote="/tmp/$(basename "$manifest")"
    transfer_with_checksum_retry "$manifest" "$MINT_SSH" "$remote" >/dev/null \
        || { fail "Could not copy $manifest"; cluster_exit; }
    apply_manifest "$manifest" "$remote"
done

patch_cold_pv_reclaim_policy() {
    local patch_cmd
    patch_cmd='for pv in $(kubectl get pv -o jsonpath="{range .items[?(@.spec.storageClassName==\"nfs-cold\")]}{.metadata.name}{\"\n\"}{end}"); do kubectl patch pv "$pv" -p "{\"spec\":{\"persistentVolumeReclaimPolicy\":\"Retain\"}}" --request-timeout=20s >/dev/null || exit 1; done'
    ssh_host "$MINT_SSH" "$patch_cmd" \
        || { fail "Could not set existing nfs-cold volumes to Retain"; cluster_exit; }
}

clear_test_scratch_wrong_node() {
    local clear_cmd
    clear_cmd="phase=\$(kubectl get pvc test-scratch -n xf-test -o jsonpath='{.status.phase}' 2>/dev/null); selected=\$(kubectl get pvc test-scratch -n xf-test -o jsonpath='{.metadata.annotations.volume\\.kubernetes\\.io/selected-node}' 2>/dev/null); if [ \"\$phase\" = Pending ] && [ -n \"\$selected\" ] && [ \"\$selected\" != '$DELL_NODE' ]; then kubectl annotate pvc test-scratch -n xf-test volume.kubernetes.io/selected-node- --request-timeout=20s >/dev/null || exit 1; fi"
    ssh_host "$MINT_SSH" "$clear_cmd" \
        || { fail "Could not clear stale test-scratch selected node"; cluster_exit; }
}

patch_cold_pv_reclaim_policy
clear_test_scratch_wrong_node

printf 'Storage classes, claims, and quotas applied. Re-run tools/preflight/test_storage.sh.\n'
