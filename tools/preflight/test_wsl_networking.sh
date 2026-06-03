#!/usr/bin/env bash
# Runs the K8S.01 WSL2 networking checks.
set -u

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$DIR/lib.sh"

fails=0

echo "K8S.01 preflight: checking WSL2 mirrored networking, Mint reachability, time sync, and NFS tooling."

echo "Scenario 1: mirrored networking is active"
assert_ip_mirrored || fails=$((fails + 1))

echo "Scenario 2: WSL2 sees Mint over the cable"
assert_ping "$MINT_CABLE_IP" || fails=$((fails + 1))

echo "Scenario 3: WSL2 resolves mint.local through Multicast DNS"
assert_mdns_resolution "$MINT_HOSTNAME" || fails=$((fails + 1))

echo "Scenario 4: clock skew is under two seconds across nodes"
assert_clock_skew || fails=$((fails + 1))

echo "Scenario 5: NFS client tooling present in WSL2"
assert_nfs_client || fails=$((fails + 1))

[[ "$fails" -eq 0 ]] && echo "ALL 5 SCENARIOS PASSED" && exit 0
echo "$fails SCENARIOS FAILED"
exit 1
