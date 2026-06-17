#!/usr/bin/env bash
# SLICE-08 verification: Mint NFS cold-storage server.
#
# Plain English: proves the existing Mint NFS server is enabled, exports the one
# live cold-storage root, and exposes it only to the wired cluster network.

HERE="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=host_prep_lib.sh
. "$HERE/host_prep_lib.sh"
cluster_require_gitbash "$0"

EXPORTS_TEMPLATE="$HERE/etc-exports.template"
if ! nfs_load_export_template "$EXPORTS_TEMPLATE"; then
    fail "exports template has no active NFS export line"
    cluster_exit
fi

host_assert_ssh "Mint" "$MINT_SSH"
host_assert_package "Mint" "$MINT_SSH" nfs-kernel-server
host_assert_service_active "Mint" "$MINT_SSH" nfs-server
host_assert_any_service_enabled "Mint" "$MINT_SSH" nfs-server nfs-kernel-server
host_assert_path_exists "Mint" "$MINT_SSH" "$NFS_EXPORT_ROOT"
host_assert_nfs_export \
    "Mint" "$MINT_SSH" "$NFS_EXPORT_ROOT" "$NFS_EXPORT_CIDR" "$NFS_EXPORT_OPTIONS"
host_assert_ufw_rules "Mint" "$MINT_SSH" "$NFS_EXPORT_CIDR" 2049/tcp

cluster_exit
