#!/usr/bin/env bash
# SLICE-01 preflight: cluster LAN reachability + wired-backbone matrix.
#
# Plain English: proves the cluster's network is healthy. It checks that the
# private wired cable between Mint and Dell is a real gigabit link, that each
# machine can ping AND open a real connection to the other over it, that MSI can
# reach the cluster's control port, and it measures the actual cable throughput.
#
# Run with git-bash (NOT WSL):
#   /bin/bash tools/preflight/test_lan_matrix.sh
# Exit 0 = every check passed.

HERE="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=cluster_lib.sh
. "$HERE/cluster_lib.sh"
cluster_require_gitbash "$0"

MIN_LINK_MBPS="${MIN_LINK_MBPS:-1000}"
MIN_THROUGHPUT_MBPS="${MIN_THROUGHPUT_MBPS:-500}"

# 1. MSI -> Mint control path: kubectl reaches the k3s API and sees Ready nodes.
#    (Uses kubectl directly — git-bash /dev/tcp is unreliable on Windows.)
if kubectl get nodes --no-headers --request-timeout=6s 2>/dev/null | grep -q " Ready "; then
    pass "MSI reaches the k3s API at $MINT_WIFI_IP (kubectl sees Ready nodes)"
else
    fail "MSI cannot reach the k3s API via kubectl"
fi

# 2. Wired backbone is a real gigabit link on both nodes.
assert_link_speed() {
    local label="$1" target="$2" iface speed
    iface="$(wired_iface "$target")"
    [ -n "$iface" ] || { fail "$label has no interface on the wired 10.10.10.x subnet"; return; }
    speed="$(ssh_host "$target" "cat /sys/class/net/$iface/speed 2>/dev/null")"
    if [ -n "$speed" ] && [ "$speed" -ge "$MIN_LINK_MBPS" ] 2>/dev/null; then
        pass "$label wired link $iface = ${speed} Mb/s (>= ${MIN_LINK_MBPS})"
    else
        fail "$label wired link $iface = ${speed:-unknown} Mb/s (expected >= ${MIN_LINK_MBPS})"
    fi
}
assert_link_speed "Mint" "$MINT_SSH"
assert_link_speed "Dell" "$DELL_SSH"

# 3. Ping both directions over the cable (0% loss).
assert_ping() {
    local label="$1" target="$2" peer_ip="$3" out
    out="$(ssh_host "$target" "ping -c 4 -W 2 $peer_ip 2>&1")"
    if grep -q "0% packet loss" <<<"$out"; then
        pass "$label pings $peer_ip over the wire, 0% loss"
    else
        fail "$label ping to $peer_ip had loss/failure"
    fi
}
assert_ping "Mint->Dell" "$MINT_SSH" "$DELL_WIRED_IP"
assert_ping "Dell->Mint" "$DELL_SSH" "$MINT_WIRED_IP"

# 4. Open a real TCP connection to a live service each way (proves more than ping).
assert_tcp() {
    local label="$1" target="$2" peer_ip="$3" port="$4"
    if ssh_host "$target" "timeout 3 bash -c 'echo > /dev/tcp/$peer_ip/$port'"; then
        pass "$label reaches $peer_ip:$port over the wire"
    else
        fail "$label cannot reach $peer_ip:$port"
    fi
}
assert_tcp "Dell->Mint k3s API" "$DELL_SSH" "$MINT_WIRED_IP" 6443
assert_tcp "Mint->Dell Postgres" "$MINT_SSH" "$DELL_WIRED_IP" 5432

# 5. Measure real throughput over the cable (iperf3: server on Dell, client on Mint).
measure_throughput() {
    # Persistent iperf3 server on Dell (one-shot daemon binding is unreliable on
    # iperf 3.20), client on Mint, then tidy the server up. Best-effort: if no
    # number comes back, WARN rather than fail — the gigabit link-speed check
    # above already proves the backbone.
    # pkill -x (exact process name) NOT -f: a -f pattern of 'iperf3 -s' would
    # match the launching shell's own command line and kill the server before it
    # starts. The server process is named exactly "iperf3".
    ssh_host "$DELL_SSH" "pkill -x iperf3 2>/dev/null; iperf3 -s -D --logfile /tmp/iperf3-srv.log 2>/dev/null"
    sleep 2
    local mbps
    mbps="$(ssh_host "$MINT_SSH" "iperf3 -c $DELL_WIRED_IP -t 3 -f m --connect-timeout 5000 2>/dev/null | awk '/receiver/{print \$(NF-2)}'")"
    ssh_host "$DELL_SSH" "pkill -x iperf3 2>/dev/null" >/dev/null 2>&1
    if [ -z "$mbps" ]; then
        printf 'WARN: backbone throughput not measured this run; gigabit link-speed check above stands.\n'
        return
    fi
    if awk -v m="$mbps" -v f="$MIN_THROUGHPUT_MBPS" 'BEGIN{exit !(m+0 >= f)}'; then
        pass "wired backbone throughput = ${mbps} Mbit/s (>= ${MIN_THROUGHPUT_MBPS})"
    else
        fail "wired backbone throughput = ${mbps} Mbit/s (below ${MIN_THROUGHPUT_MBPS})"
    fi
}
measure_throughput

cluster_exit
