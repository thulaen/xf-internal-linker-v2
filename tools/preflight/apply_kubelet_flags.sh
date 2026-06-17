#!/usr/bin/env bash
# SLICE-10 installer: apply node reservations, image cleanup, and priorities.

HERE="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=host_prep_lib.sh
. "$HERE/host_prep_lib.sh"
cluster_require_gitbash "$0"

MINT_CONFIG_SOURCE="${MINT_CONFIG_SOURCE:-k8s/cluster/mint-k3s-config.yaml}"
DELL_CONFIG_SOURCE="${DELL_CONFIG_SOURCE:-k8s/cluster/dell-k3s-agent-config.yaml}"
PRIORITY_SOURCE="${PRIORITY_SOURCE:-k8s/scheduling/priorityclasses.yaml}"
K3S_CONFIG_TARGET="/etc/rancher/k3s/config.yaml"

copy_config() {
    local source="$1" host="$2" remote_name="$3"
    [ -f "$source" ] || { fail "Missing $source"; return 1; }
    transfer_with_checksum_retry "$source" "$host" "/tmp/$remote_name" >/dev/null \
        || { fail "Could not copy $source"; return 1; }
}

copy_config "$MINT_CONFIG_SOURCE" "$MINT_SSH" mint-k3s-config.yaml || cluster_exit
copy_config "$DELL_CONFIG_SOURCE" "$DELL_SSH" dell-k3s-agent-config.yaml || cluster_exit
copy_config "$PRIORITY_SOURCE" "$MINT_SSH" priorityclasses.yaml || cluster_exit

host_sudo_run "$MINT_SSH" "cp /tmp/mint-k3s-config.yaml '$K3S_CONFIG_TARGET' && systemctl restart k3s" \
    || { fail "Could not apply Mint kubelet config"; cluster_exit; }
host_sudo_run "$DELL_SSH" "mkdir -p /etc/rancher/k3s && cp /tmp/dell-k3s-agent-config.yaml '$K3S_CONFIG_TARGET' && systemctl restart k3s-agent" \
    || { fail "Could not apply Dell kubelet config"; cluster_exit; }

ssh_host "$MINT_SSH" "kubectl apply -f /tmp/priorityclasses.yaml --request-timeout=20s" >/dev/null \
    || { fail "Could not apply priority classes"; cluster_exit; }

printf 'Kubelet reservation configs and priority classes applied. Re-run tools/preflight/test_reservations.sh.\n'
