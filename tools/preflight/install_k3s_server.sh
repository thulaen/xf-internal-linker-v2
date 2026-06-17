#!/usr/bin/env bash
# SLICE-05 installer note for Mint k3s server.
#
# Plain English: the live server is already installed. This script reapplies the
# repo-owned Mint config without uninstalling k3s or deleting any cluster data.

HERE="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=host_prep_lib.sh
. "$HERE/host_prep_lib.sh"
cluster_require_gitbash "$0"

CONFIG_SOURCE="${CONFIG_SOURCE:-k8s/cluster/mint-k3s-config.yaml}"
REMOTE_CONFIG="/etc/rancher/k3s/config.yaml"

[ -f "$CONFIG_SOURCE" ] || { fail "Missing $CONFIG_SOURCE"; cluster_exit; }
scp -q -o BatchMode=yes -o ConnectTimeout="$SSH_TIMEOUT" "$CONFIG_SOURCE" "$MINT_SSH:/tmp/mint-k3s-config.yaml" \
    || { fail "Could not copy Mint k3s config"; cluster_exit; }
host_sudo_run "$MINT_SSH" "cp /tmp/mint-k3s-config.yaml '$REMOTE_CONFIG' && systemctl restart k3s"

printf 'Mint k3s config reapplied. Re-run tools/preflight/test_k3s_server.sh to verify.\n'
