#!/usr/bin/env bash
# Shared helpers for the cluster-era preflight checks (SLICE-01+).
#
# Plain English: the small reusable pieces every cluster network check needs —
# refuse to run under WSL, log in to a node over SSH, count pass/fail, find the
# wired network card, and copy a file with a checksum + retry. (The older lib.sh
# in this folder is the SUPERSEDED WSL2-on-Dell preflight library; the cluster
# scripts source THIS file instead.)
#
# Reached from MSI via the Windows SSH aliases: "dell" (Dell over WiFi) and
# "mint-wifi" (Mint over WiFi). Heavy cluster traffic runs on the wired
# 10.10.10.0/24 cable between the two nodes.

set -u

DELL_SSH="${DELL_SSH:-dell}"
MINT_SSH="${MINT_SSH:-mint-wifi}"
DELL_NODE="${DELL_NODE:-dell-ubuntu-01-optiplex-micro-7010}"
MINT_NODE="${MINT_NODE:-minthelper01-lenovo-c50-30}"
MINT_WIRED_IP="${MINT_WIRED_IP:-10.10.10.91}"
DELL_WIRED_IP="${DELL_WIRED_IP:-10.10.10.92}"
MINT_WIFI_IP="${MINT_WIFI_IP:-192.168.0.91}"
SSH_TIMEOUT="${SSH_TIMEOUT:-8}"
POSTGRES_SERVICE_NAME="${POSTGRES_SERVICE_NAME:-postgres}"
POSTGRES_ENDPOINTSLICE_NAME="${POSTGRES_ENDPOINTSLICE_NAME:-postgres-external}"
POSTGRES_SERVICE_NAMESPACE_LIST="${POSTGRES_SERVICE_NAMESPACE_LIST:-xf-app xf-obs xf-test}"
POSTGRES_SERVICE_PORT="${POSTGRES_SERVICE_PORT:-5432}"

_failures=0
pass() { printf 'PASS: %s\n' "$1"; }
fail() { printf 'FAIL: %s\n' "$1" >&2; _failures=$((_failures + 1)); }

# Refuse to run under WSL: its ssh can't see the Windows ~/.ssh/config aliases
# (dell, mint-wifi), so every remote check would silently return empty.
cluster_require_gitbash() {
    if grep -qiE 'microsoft|wsl' /proc/version 2>/dev/null; then
        printf 'FAIL: run under git-bash, not WSL.\n' >&2
        printf '  WHY: WSL ssh lacks the Windows host aliases (dell, mint-wifi);\n' >&2
        printf '       every remote check would silently return empty.\n' >&2
        printf '  FIX: /bin/bash %s\n' "${1:-this script}" >&2
        exit 2
    fi
}

ssh_host() { ssh -n -o BatchMode=yes -o ConnectTimeout="$SSH_TIMEOUT" "$1" "$2" 2>/dev/null; }

# The network interface on a node that holds the wired 10.10.10.x address.
wired_iface() { ssh_host "$1" "ip -o -4 addr show 2>/dev/null | awk '/10\\.10\\.10\\./{print \$2; exit}'"; }

# Copy a local file to host:dest, verifying the SHA-256 checksum and retrying up
# to N times (default 3). Echoes the verified checksum on success; non-zero if
# every try produced a corrupt/missing copy. This is the "never a false pass"
# transfer: it only succeeds when the remote bytes match the source exactly.
transfer_with_checksum_retry() {
    local src="$1" host="$2" dest="$3" tries="${4:-3}" want got i
    want="$(sha256sum "$src" 2>/dev/null | awk '{print $1}')"
    [ -n "$want" ] || return 2
    for i in $(seq 1 "$tries"); do
        scp -q -o BatchMode=yes -o ConnectTimeout="$SSH_TIMEOUT" "$src" "$host:$dest" 2>/dev/null
        got="$(ssh_host "$host" "sha256sum '$dest' 2>/dev/null | awk '{print \$1}'")"
        [ "$got" = "$want" ] && { printf '%s' "$want"; return 0; }
    done
    return 1
}

cluster_exit() {
    if [ "$_failures" -eq 0 ]; then printf '\nALL CHECKS PASSED.\n'; exit 0; fi
    printf '\n%d CHECK(S) FAILED.\n' "$_failures" >&2
    exit 1
}
