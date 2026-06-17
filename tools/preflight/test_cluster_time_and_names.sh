#!/usr/bin/env bash
# SLICE-04 verification: cluster clock-sync + cross-node name resolution.
#
# Plain English: this proves two things about the two cluster machines (Mint and
# Dell). First, their clocks agree with real internet time (so logs, certs, and
# tokens line up). Second, each machine can find the other by its name, not just
# its number, over the private wired cable. Run it from MSI; it logs into both
# machines over SSH (aliases "dell" and "mint-wifi") and checks read-only state.
#
# Run with git-bash (NOT WSL):
#   /bin/bash tools/preflight/test_cluster_time_and_names.sh
# Exit 0 = every check passed; non-zero = at least one failed (message on stderr).

HERE="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=cluster_lib.sh
. "$HERE/cluster_lib.sh"
cluster_require_gitbash "$0"

MAX_CLOCK_OFFSET_SECONDS="${MAX_CLOCK_OFFSET_SECONDS:-2}"

# A host's clock is healthy when systemd reports it synchronized AND chrony's
# own offset from true time is under the tolerance.
assert_clock_synced() {
    local label="$1" target="$2" synced offset
    synced="$(ssh_host "$target" 'timedatectl show -p NTPSynchronized --value')"
    [ "$synced" = "yes" ] || { fail "$label clock not NTP-synchronized (got '${synced:-no answer}')"; return; }
    offset="$(ssh_host "$target" "chronyc tracking 2>/dev/null | awk -F: '/System time/{gsub(/^ +/,\"\",\$2); split(\$2,p,\" \"); v=p[1]+0; if(v<0)v=-v; print v}'")"
    awk -v o="$offset" -v m="$MAX_CLOCK_OFFSET_SECONDS" 'BEGIN{exit !(o!=""&&o<m)}' \
        && pass "$label clock synchronized (offset ${offset}s < ${MAX_CLOCK_OFFSET_SECONDS}s)" \
        || fail "$label clock offset ${offset:-unknown}s exceeds ${MAX_CLOCK_OFFSET_SECONDS}s"
}

# A host resolves the peer by name when getent maps the peer's node name to its
# wired cluster IP.
assert_resolves_peer() {
    local label="$1" target="$2" peer_name="$3" peer_ip="$4" result
    result="$(ssh_host "$target" "getent hosts $peer_name")"
    grep -Eq "(^|[[:space:]])${peer_ip}([[:space:]]|$)" <<<"$result" \
        && pass "$label resolves $peer_name -> $peer_ip" \
        || fail "$label does not resolve $peer_name to $peer_ip (got: ${result:-no answer})"
}

# Name-based reachability: prove the resolved name reaches a real cluster port.
assert_reaches_peer() {
    local label="$1" target="$2" peer_name="$3" port="$4"
    if ssh_host "$target" "timeout 3 bash -c 'echo > /dev/tcp/${peer_name}/${port}'"; then
        pass "$label reaches ${peer_name}:${port} by name"
    else
        fail "$label cannot reach ${peer_name}:${port} by name"
    fi
}

assert_clock_synced "Mint" "$MINT_SSH"
assert_clock_synced "Dell" "$DELL_SSH"
assert_resolves_peer "Dell" "$DELL_SSH" "$MINT_NODE" "$MINT_WIRED_IP"
assert_resolves_peer "Mint" "$MINT_SSH" "$DELL_NODE" "$DELL_WIRED_IP"
assert_reaches_peer "Dell" "$DELL_SSH" "$MINT_NODE" 6443
assert_reaches_peer "Mint" "$MINT_SSH" "$DELL_NODE" 5432

cluster_exit
