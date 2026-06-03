#!/usr/bin/env bash
# Shared probes for the K8S.01 WSL2 preflight.

set -u

MINT_CABLE_IP="${MINT_CABLE_IP:-10.10.10.91}"
MINT_WIFI_IP="${MINT_WIFI_IP:-192.168.0.91}"
MINT_HOSTNAME="${MINT_HOSTNAME:-mint.local}"
MINT_SSH_TARGET="${MINT_SSH_TARGET:-mint}"
MAX_CABLE_RTT_MS="${MAX_CABLE_RTT_MS:-2}"
MAX_CLOCK_OFFSET_SECONDS="${MAX_CLOCK_OFFSET_SECONDS:-2}"

pass() {
    printf 'PASS: %s\n' "$1"
}

fail() {
    printf 'FAIL: %s\n' "$1" >&2
    return 1
}

require_command() {
    command -v "$1" >/dev/null 2>&1 || fail "$1 is not available"
}

windows_powershell() {
    local script="$1"
    local direct="${WINDOWS_POWERSHELL_DIRECT:-powershell.exe}"
    local init_path="${WSL_INIT_EXE:-/init}"
    local ps_path="${WINDOWS_POWERSHELL_EXE:-/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe}"

    if command -v "$direct" >/dev/null 2>&1; then
        timeout 8s "$direct" -NoProfile -Command "$script" 2>/dev/null && return 0
    fi
    if [[ -x "$init_path" && -f "$ps_path" ]]; then
        timeout 8s "$init_path" "$ps_path" -NoProfile -Command "$script"
        return $?
    fi
    return 127
}

assert_ip_mirrored() {
    require_command ip || return 1

    local wsl_ips host_ips
    wsl_ips="$(ip -4 -o addr show scope global | awk '{print $4}' | cut -d/ -f1)"
    host_ips="$(windows_powershell \
        "Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue | Where-Object { \$_.InterfaceAlias -notlike 'Loopback*' -and \$_.IPAddress -notlike '169.254.*' -and \$_.IPAddress -ne '127.0.0.1' } | Select-Object -ExpandProperty IPAddress" \
        | tr -d '\r')"

    [[ -n "$wsl_ips" ]] || fail "WSL has no global IPv4 address" || return 1
    [[ -n "$host_ips" ]] || fail "Windows active non-loopback IPv4 address was not found" || return 1

    local candidate
    while IFS= read -r candidate; do
        if grep -Fxq "$candidate" <<<"$host_ips"; then
            pass "WSL IPv4 $candidate matches an active Windows mirrored address"
            return 0
        fi
    done <<<"$wsl_ips"

    fail "WSL IPv4 address does not match Windows addresses: WSL=[$wsl_ips] Windows=[$host_ips]"
}

assert_ping() {
    local target="${1:-$MINT_CABLE_IP}"
    require_command ping || return 1

    local output avg
    output="$(ping -c 4 -W 2 "$target" 2>&1)" || fail "$target did not answer ping: $output" || return 1
    grep -q "0% packet loss" <<<"$output" || fail "$target ping had packet loss: $output" || return 1
    avg="$(awk -F'/' '/rtt|round-trip/ {print $5}' <<<"$output")"
    awk -v avg="$avg" -v max="$MAX_CABLE_RTT_MS" 'BEGIN { exit !(avg != "" && avg < max) }' \
        || fail "$target average round-trip time was ${avg:-unknown} ms, expected under ${MAX_CABLE_RTT_MS} ms" \
        || return 1
    pass "$target answered ping with ${avg} ms average round-trip time"
}

assert_mdns_resolution() {
    local target="${1:-$MINT_HOSTNAME}"
    require_command getent || return 1

    local result
    result="$(getent hosts "$target" 2>/dev/null || true)"
    grep -Eq "(^|[[:space:]])(${MINT_CABLE_IP}|${MINT_WIFI_IP})([[:space:]]|$)" <<<"$result" \
        || fail "$target did not resolve to $MINT_CABLE_IP or $MINT_WIFI_IP; got: ${result:-no answer}" \
        || return 1
    pass "$target resolved through Multicast DNS: $result"
}

chrony_offset_seconds() {
    chronyc tracking 2>/dev/null | awk -F':' '
        /System time/ {
            gsub(/^[[:space:]]+/, "", $2)
            split($2, parts, " ")
            value = parts[1] + 0
            if (value < 0) value = -value
            print value
        }'
}

tracking_offset_seconds() {
    awk -F':' '
        /System time/ {
            gsub(/^[[:space:]]+/, "", $2)
            split($2, parts, " ")
            value = parts[1] + 0
            if (value < 0) value = -value
            print value
        }'
}

assert_local_chrony() {
    require_command chronyc || return 1

    local offset
    offset="$(chrony_offset_seconds)"
    awk -v offset="$offset" -v max="$MAX_CLOCK_OFFSET_SECONDS" 'BEGIN { exit !(offset != "" && offset < max) }' \
        || fail "local chrony offset was ${offset:-unknown}s, expected under ${MAX_CLOCK_OFFSET_SECONDS}s" \
        || return 1
    pass "local chrony offset is ${offset}s"
}

assert_mint_chrony() {
    require_command ssh || return 1

    local offset tracking
    tracking="$(ssh -o BatchMode=yes -o ConnectTimeout=4 "$MINT_SSH_TARGET" "chronyc tracking" 2>/dev/null || true)"
    if [[ -z "$tracking" ]]; then
        tracking="$(windows_powershell "ssh mint 'chronyc tracking'" 2>/dev/null | tr -d '\r' || true)"
    fi
    offset="$(tracking_offset_seconds <<<"$tracking")"
    awk -v offset="$offset" -v max="$MAX_CLOCK_OFFSET_SECONDS" 'BEGIN { exit !(offset != "" && offset < max) }' \
        || fail "Mint chrony offset through $MINT_SSH_TARGET was ${offset:-unknown}s" \
        || return 1
    pass "Mint chrony offset is ${offset}s through $MINT_SSH_TARGET"
}

assert_windows_time() {
    local status
    status="$(windows_powershell "w32tm /query /status" 2>&1 | tr -d '\r')"
    grep -Eq "Source:|Leap Indicator:" <<<"$status" \
        || fail "Windows Time did not report a usable status: $status" \
        || return 1
    pass "Windows Time reports a usable status"
}

assert_clock_skew() {
    assert_local_chrony || return 1
    assert_mint_chrony || return 1
    assert_windows_time || return 1
}

assert_nfs_client() {
    dpkg -s nfs-common >/dev/null 2>&1 || fail "nfs-common is not installed" || return 1
    command -v mount.nfs4 >/dev/null 2>&1 || fail "mount.nfs4 is not available" || return 1
    pass "nfs-common is installed and mount.nfs4 is available"
}
