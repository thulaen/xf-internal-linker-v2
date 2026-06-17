#!/usr/bin/env bash
# SLICE-03 installer: idempotent Mint host prep.
#
# Plain English: keeps Mint awake, creates the cluster data folders, creates the
# service account, installs base packages, and applies the firewall baseline.

HERE="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=host_prep_lib.sh
. "$HERE/host_prep_lib.sh"
cluster_require_gitbash "$0"

host_install_packages "$MINT_SSH" curl nfs-kernel-server ufw rsync chrony iperf3
host_ensure_system_user "$MINT_SSH" "$MINT_SERVICE_USER" "$MINT_SERVICE_UID"
host_ensure_owned_paths "$MINT_SSH" "$MINT_SERVICE_USER" "${MINT_LAYOUT_PATHS[@]}"
host_mask_targets "$MINT_SSH" sleep.target suspend.target hibernate.target hybrid-sleep.target
host_apply_ufw_rules "$MINT_SSH" "$HOME_LAN_CIDR" "${MINT_HOME_FIREWALL_RULES[@]}"
host_apply_ufw_rules "$MINT_SSH" "$MSI_CONTROL_CIDR" "${MINT_MSI_FIREWALL_RULES[@]}"
host_apply_ufw_rules "$MINT_SSH" "$CLUSTER_LAN_CIDR" "${MINT_CLUSTER_FIREWALL_RULES[@]}"
host_sudo_run "$MINT_SSH" "ufw default deny incoming && ufw default allow outgoing && ufw --force enable"

printf 'Mint host prep complete. Re-run tools/preflight/test_mint_host.sh to verify.\n'
