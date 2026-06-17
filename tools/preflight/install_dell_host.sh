#!/usr/bin/env bash
# SLICE-02 installer: idempotent Dell host prep.
#
# Plain English: installs the small set of Linux packages Dell needs before it
# joins the cluster, then enables SSH and the container runtime as boot services.

HERE="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=host_prep_lib.sh
. "$HERE/host_prep_lib.sh"
cluster_require_gitbash "$0"

host_install_packages "$DELL_SSH" openssh-server rsync containerd iperf3 curl
host_sudo_run "$DELL_SSH" "systemctl enable --now ssh"
host_sudo_run "$DELL_SSH" "systemctl enable --now containerd"
host_assert_linux_filesystem "Dell repo" "$DELL_SSH" "$DELL_REPO_PATH"

printf 'Dell host prep complete. Re-run tools/preflight/test_dell_host.sh to verify.\n'
