#!/usr/bin/env bash
# SLICE-03 verification: Mint host prep.
#
# Plain English: checks that Mint is ready to be the control and storage host:
# no sleep targets, a service account, a data folder, NFS tools, and a firewall
# that allows the cluster ports only from the cluster network.

HERE="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=host_prep_lib.sh
. "$HERE/host_prep_lib.sh"
cluster_require_gitbash "$0"

host_assert_ssh "Mint" "$MINT_SSH"
host_assert_targets_masked "Mint" "$MINT_SSH" sleep.target suspend.target
host_assert_user "Mint" "$MINT_SSH" "$MINT_SERVICE_USER" "$MINT_SERVICE_UID"
host_assert_paths_owned_by "Mint" "$MINT_SSH" "$MINT_SERVICE_USER" "${MINT_OWNED_CHECK_PATHS[@]}"
host_assert_package "Mint" "$MINT_SSH" nfs-kernel-server
host_assert_command "Mint" "$MINT_SSH" ufw
host_assert_ufw_rules "Mint" "$MINT_SSH" "$HOME_LAN_CIDR" 22/tcp
host_assert_ufw_rules "Mint" "$MINT_SSH" "$MSI_CONTROL_CIDR" "${MINT_MSI_FIREWALL_RULES[@]}"
host_assert_ufw_rules "Mint" "$MINT_SSH" "$CLUSTER_LAN_CIDR" "${MINT_VERIFIED_FIREWALL_RULES[@]}"

cluster_exit
