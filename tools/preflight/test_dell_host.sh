#!/usr/bin/env bash
# SLICE-02 verification: Dell host prep.
#
# Plain English: checks that Dell is a real Linux worker host. It must answer
# SSH, keep the repo on a Linux filesystem, run a container service at boot,
# and have the transfer and network tools later slices rely on.

HERE="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=host_prep_lib.sh
. "$HERE/host_prep_lib.sh"
cluster_require_gitbash "$0"

host_assert_ssh "Dell" "$DELL_SSH"
host_assert_linux_filesystem "Dell repo" "$DELL_SSH" "$DELL_REPO_PATH"
host_assert_any_service_enabled "Dell runtime" "$DELL_SSH" containerd docker
host_assert_any_service_enabled "Dell remote access" "$DELL_SSH" ssh sshd
host_assert_command "Dell" "$DELL_SSH" rsync
host_assert_command "Dell" "$DELL_SSH" iperf3

cluster_exit
