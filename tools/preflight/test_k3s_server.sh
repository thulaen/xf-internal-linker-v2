#!/usr/bin/env bash
# SLICE-05 verification: Mint k3s server.
#
# Plain English: checks the live control-plane service on Mint. It proves k3s is
# active, uses the small single-server database, disables bundled extras, and
# reserves some memory for the operating system.

HERE="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=host_prep_lib.sh
. "$HERE/host_prep_lib.sh"
cluster_require_gitbash "$0"

assert_mint_k3s_active() {
    local state
    state="$(ssh_host "$MINT_SSH" "sudo systemctl is-active k3s 2>/dev/null")"
    [ "$state" = "active" ] && pass "Mint k3s service is active" || fail "Mint k3s service is ${state:-unknown}"
}

assert_mint_k3s_unit_has_flags() {
    local unit
    unit="$(ssh_host "$MINT_SSH" "sudo systemctl cat k3s 2>/dev/null")"
    grep -q -- "--disable" <<<"$unit" && grep -q "traefik" <<<"$unit" \
        && pass "Mint k3s disables Traefik" \
        || fail "Mint k3s unit does not show Traefik disabled"
    grep -q -- "--disable" <<<"$unit" && grep -q "servicelb" <<<"$unit" \
        && pass "Mint k3s disables ServiceLB" \
        || fail "Mint k3s unit does not show ServiceLB disabled"
    grep -q "10.10.10.91" <<<"$unit" && pass "Mint k3s binds the wired IP" \
        || fail "Mint k3s unit does not include the wired Mint IP"
}

assert_mint_sqlite_datastore() {
    ssh_host "$MINT_SSH" "sudo test -f /var/lib/rancher/k3s/server/db/state.db" \
        && pass "Mint k3s SQLite state database exists" \
        || fail "Mint k3s SQLite state database is missing"
    ssh_host "$MINT_SSH" "sudo test ! -d /var/lib/rancher/k3s/server/db/etcd" \
        && pass "Mint k3s is not using etcd" \
        || fail "Mint k3s has an etcd datastore directory"
}

assert_no_bundled_ingress_or_lb() {
    local bundled
    bundled="$(ssh_host "$MINT_SSH" "kubectl -n kube-system get all -o name --request-timeout=8s 2>/dev/null | grep -E 'traefik|servicelb|svclb' || true")"
    [ -z "$bundled" ] && pass "No bundled Traefik or ServiceLB workload is present" \
        || fail "Bundled k3s workload still exists: $bundled"
}

assert_mint_node_ready() {
    local ready
    ready="$(ssh_host "$MINT_SSH" "kubectl get node '$MINT_NODE' --no-headers --request-timeout=8s 2>/dev/null | awk '{print \$2}'")"
    [ "$ready" = "Ready" ] && pass "Mint node is Ready" || fail "Mint node is ${ready:-missing}"
}

assert_mint_memory_reserved() {
    local values alloc capacity
    values="$(ssh_host "$MINT_SSH" "kubectl get node '$MINT_NODE' -o jsonpath='{.status.allocatable.memory} {.status.capacity.memory}' --request-timeout=8s")"
    alloc="${values%% *}"
    capacity="${values#* }"
    alloc="${alloc%Ki}"
    capacity="${capacity%Ki}"
    if [ -n "$alloc" ] && [ -n "$capacity" ] && [ "$alloc" -lt "$capacity" ] 2>/dev/null; then
        pass "Mint allocatable memory is lower than capacity"
    else
        fail "Mint allocatable memory is not lower than capacity"
    fi
}

assert_mint_k3s_active
assert_mint_k3s_unit_has_flags
assert_mint_sqlite_datastore
assert_no_bundled_ingress_or_lb
assert_mint_node_ready
assert_mint_memory_reserved

cluster_exit
