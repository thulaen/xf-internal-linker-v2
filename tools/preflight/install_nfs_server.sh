#!/usr/bin/env bash
# SLICE-08 installer: idempotent Mint NFS export setup.
#
# Plain English: installs the NFS server, keeps the single live export root, and
# replaces /etc/exports with the reviewed template in this folder.

HERE="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=host_prep_lib.sh
. "$HERE/host_prep_lib.sh"
cluster_require_gitbash "$0"

EXPORTS_TEMPLATE="$HERE/etc-exports.template"
if ! nfs_load_export_template "$EXPORTS_TEMPLATE"; then
    printf 'FAIL: exports template has no active NFS export line.\n' >&2
    exit 1
fi

host_install_packages "$MINT_SSH" nfs-kernel-server nfs-common
host_sudo_run "$MINT_SSH" "mkdir -p '$NFS_EXPORT_ROOT' && chmod 0777 '$NFS_EXPORT_ROOT'"
transfer_with_checksum_retry "$EXPORTS_TEMPLATE" "$MINT_SSH" /tmp/xf-exports >/dev/null
host_sudo_run "$MINT_SSH" "install -m 0644 /tmp/xf-exports /etc/exports"
host_sudo_run "$MINT_SSH" "exportfs -ra && systemctl enable --now nfs-server"
host_apply_ufw_rules "$MINT_SSH" "$NFS_EXPORT_CIDR" 2049/tcp

printf 'Mint NFS export is configured. Re-run tools/preflight/test_nfs_server.sh to verify.\n'
